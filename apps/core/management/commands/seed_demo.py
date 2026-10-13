from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketing.models import Coupon, CouponIssue
from apps.marketing.services import CouponError, issue_coupon
from apps.members.models import Member
from apps.members.services import apply_points, create_store_recharge, ensure_member_profile, pay_store_recharge, recharge
from apps.orders.models import CartItem, Order
from apps.orders.services import (
    add_to_cart,
    cancel_order,
    complete_order,
    create_order_from_cart,
    pay_order,
    receive_order,
    refund_order,
    request_cancel,
    restore_stock,
    ship_order,
)
from apps.products.models import Category, Product

PRODUCT_IMAGES = {
    "SKU-R12": "products/sku-r12.jpg",
    "SKU-S08": "products/sku-s08.jpg",
    "SKU-C11": "products/sku-c11.jpg",
    "SKU-M16": "products/sku-m16.jpg",
    "SKU-B10": "products/sku-b10.jpg",
    "SKU-W12": "products/sku-w12.jpg",
    "SKU-T10": "products/sku-t10.jpg",
    "SKU-L08": "products/sku-l08.jpg",
    "SKU-H06": "products/sku-h06.jpg",
    "SKU-P01": "products/sku-p01.jpg",
    "SKU-S03": "products/sku-s03.jpg",
    "SKU-A04": "products/sku-a04.jpg",
    "SKU-G07": "products/sku-g07.jpg",
}

User = get_user_model()
DEMO_PASSWORD = "member123456"
DEMO_REMARK = "演示数据"

MEMBERS = [
    ("demo_member", "演示会员", "13800000001", 1200, "200.00"),
    ("member_lin", "林小花", "13800000002", 5200, "400.00"),
    ("member_chen", "陈晨", "13800000003", 80, "150.00"),
    ("member_zhou", "周舟", "13800000004", 1800, "260.00"),
    ("member_wu", "吴岚", "13800000005", 10200, "800.00"),
]

UNITS = {"bouquet": "束", "green": "盆", "gift": "盒"}

PRODUCTS = [
    ("bouquet", "红玫瑰花束", "SKU-R12", Decimal("128.00"), "12 枝红玫瑰，适合纪念日。", "热恋与郑重的爱"),
    ("bouquet", "向日葵花束", "SKU-S08", Decimal("88.00"), "8 枝向日葵，明亮治愈。", "沉默的爱，向着光"),
    ("bouquet", "康乃馨花束", "SKU-C11", Decimal("98.00"), "感恩与日常问候。", "感恩与长久的惦记"),
    ("bouquet", "混搭花束", "SKU-M16", Decimal("168.00"), "设计师混搭，适合送礼。", "把不同的心意收成一束"),
    ("bouquet", "满天星花束", "SKU-B10", Decimal("68.00"), "轻盈浪漫，适合日常。", "思念如星，细碎而长久"),
    ("bouquet", "白玫瑰花束", "SKU-W12", Decimal("138.00"), "12 枝白玫瑰，纯净典雅。", "纯净、敬重与新的开始"),
    ("bouquet", "郁金香花束", "SKU-T10", Decimal("118.00"), "粉杏郁金香，温柔而明亮。", "高雅的告白"),
    ("bouquet", "百合花束", "SKU-L08", Decimal("158.00"), "白百合，适合探望与祝福。", "百年好合，祝福安然"),
    ("bouquet", "绣球花束", "SKU-H06", Decimal("148.00"), "蓝白绣球，团圆与感谢。", "希望与团圆"),
    ("green", "小型观叶盆栽", "SKU-P01", Decimal("56.00"), "桌面绿植，易养护。", "把一小片绿意留给日常"),
    ("green", "多肉组合", "SKU-S03", Decimal("42.00"), "三盆多肉组合。", "坚韧而温柔的陪伴"),
    ("green", "龟背竹盆栽", "SKU-A04", Decimal("128.00"), "大型叶片，适合客厅一角。", "坚毅生长，岁月悠长"),
    ("gift", "鲜花礼盒", "SKU-G07", Decimal("198.00"), "开盖即送的礼盒花，适合当面赠礼。", "打开即是心意"),
]


class Command(BaseCommand):
    help = "导入答辩演示数据（会员、商品、订单、券）。可重复执行，--force 会重建带「演示数据」标记的订单。"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="删除演示订单后重新生成")

    def handle(self, *args, **options):
        self._seed_users()
        self._seed_catalog()
        members = self._seed_members()
        if options["force"]:
            self._wipe_demo_orders()
        self._seed_coupons(members)
        if options["force"] or not Order.objects.filter(remark=DEMO_REMARK).exists():
            self._seed_orders(members)
        else:
            self.stdout.write("已有演示订单，跳过下单（需要重建请加 --force）")
        self._seed_cart(members[0])
        self.stdout.write(self.style.SUCCESS("演示数据就绪。会员密码均为 member123456"))

    def _seed_users(self):
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={"role": User.Role.ADMIN, "email": "admin@example.com", "is_staff": True, "is_superuser": True},
        )
        if not admin.password:
            admin.set_password("admin123456")
            admin.role = User.Role.ADMIN
            admin.save()
        staff, created = User.objects.get_or_create(
            username="staff",
            defaults={"role": User.Role.STAFF, "email": "staff@example.com", "is_staff": True},
        )
        if created:
            staff.set_password("staff123456")
            staff.role = User.Role.STAFF
            staff.save()

    def _seed_catalog(self):
        cats = {}
        for slug, name, order in (("bouquet", "花束", 0), ("green", "绿植", 1), ("gift", "礼盒", 2)):
            cats[slug], _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": name, "sort_order": order, "is_active": True}
            )
        for cat, name, sku, price, desc, language in PRODUCTS:
            Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "category": cats[cat],
                    "name": name,
                    "price": price,
                    "stock": {"SKU-P01": 4, "SKU-S03": 6}.get(sku, 200),
                    "description": desc,
                    "flower_language": language,
                    "is_on_sale": True,
                    "unit": UNITS.get(cat, "件"),
                    "image": PRODUCT_IMAGES.get(sku, ""),
                },
            )

    def _seed_members(self):
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        result = []
        for index, (username, real_name, phone, points, store) in enumerate(MEMBERS):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"role": User.Role.MEMBER, "phone": phone},
            )
            if created or not user.has_usable_password():
                user.set_password(DEMO_PASSWORD)
            user.role = User.Role.MEMBER
            user.phone = phone
            user.save()
            member = ensure_member_profile(user)
            member.real_name = real_name
            member.default_address = "演示路 88 号花间集"
            member.save(update_fields=["real_name", "default_address", "updated_at"])
            if member.total_points < points:
                apply_points(member, points - member.total_points, "manual", remark="演示积分")
            member.refresh_from_db()
            if member.store_balance < Decimal(store):
                recharge(member, Decimal(store) - member.store_balance, remark="演示充值")
            created_day = today - timedelta(days=12 - min(index * 2, 12))
            Member.objects.filter(pk=member.pk).update(
                created_at=timezone.make_aware(datetime.combine(created_day, time(9, 30)), tz)
            )
            result.append(member)
        return result

    def _seed_coupons(self, members):
        for coupon in Coupon.objects.filter(is_active=True):
            for member in members:
                try:
                    issue_coupon(member, coupon)
                except CouponError:
                    pass

    def _wipe_demo_orders(self):
        qs = Order.objects.filter(remark=DEMO_REMARK)
        for order in qs:
            try:
                if order.status == Order.Status.PENDING:
                    cancel_order(order)
                elif order.status in {Order.Status.PAID, Order.Status.SHIPPED, Order.Status.COMPLETED}:
                    refund_order(order)
                elif order.stock_reserved:
                    restore_stock(order)
            except Exception:
                if order.stock_reserved:
                    restore_stock(order)
        qs.delete()
        CouponIssue.objects.filter(member__user__username__in=[m[0] for m in MEMBERS], source="issue").delete()
        self.stdout.write("已清理旧演示订单")

    def _seed_orders(self, members):
        products = list(Product.objects.filter(sku__in=[p[2] for p in PRODUCTS], is_on_sale=True))
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        admin = User.objects.filter(is_superuser=True).first()
        count = 0
        for i in range(14):
            day = today - timedelta(days=13 - i)
            dt = timezone.make_aware(datetime.combine(day, time(11 + (i % 6), 20)), tz)
            member = members[i % len(members)]
            product = products[i % len(products)]
            CartItem.objects.filter(member=member).delete()
            add_to_cart(member, product, 1 + (i % 2))
            extra = products[(i + 3) % len(products)]
            if extra.pk != product.pk and i % 3 == 0:
                add_to_cart(member, extra, 1)
            delivery = i in {0, 3, 6, 9}
            order = create_order_from_cart(
                member,
                use_store=i % 2 == 0,
                operator=admin,
                auto_coupon=(i % 5 == 0),
                fulfillment=Order.Fulfillment.DELIVERY if delivery else Order.Fulfillment.PICKUP,
                receiver_name=str(member) if delivery else "",
                receiver_phone=(member.user.phone or "13800000000") if delivery else "",
                address="演示路 88 号花间集" if delivery else "",
            )
            order.remark = DEMO_REMARK
            order.save(update_fields=["remark"])
            if i == 1:
                cancel_order(order, operator=admin, remark="演示取消")
            elif i == 12:
                pass
            else:
                order = pay_order(order, success=True, operator=admin)
                if i == 9:
                    order = request_cancel(order, operator=member.user, remark="演示申请取消")
                elif delivery:
                    if i != 9:
                        order = ship_order(order, operator=admin)
                    if i in {0, 3}:
                        order = receive_order(order, operator=admin)
                elif i % 2 == 1:
                    order = complete_order(order, operator=admin)
                if i == 4:
                    order = refund_order(order, operator=admin)
            updates = {"created_at": dt, "updated_at": dt}
            if order.status not in {Order.Status.PENDING, Order.Status.CANCELLED}:
                updates["paid_at"] = dt
            Order.objects.filter(pk=order.pk).update(**updates)
            count += 1
        self.stdout.write(f"已生成演示订单 {count} 笔")
        demo = members[0]
        if not demo.store_recharges.filter(status="success").exists():
            item = create_store_recharge(demo, Decimal("100.00"), operator=demo.user)
            pay_store_recharge(item, success=True, operator=demo.user)
            self.stdout.write("已生成演示自助充值 1 笔")

    def _seed_cart(self, member):
        product = Product.objects.filter(is_on_sale=True).first()
        if product:
            CartItem.objects.filter(member=member).delete()
            add_to_cart(member, product, 1)
