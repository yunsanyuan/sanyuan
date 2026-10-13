from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from apps.marketing.models import Coupon, CouponIssue
from apps.marketing.services import CouponError, expire_due_issues, issue_coupon, receive_coupon
from apps.members.models import MemberLevel, PointsRecord
from apps.members.services import apply_points, ensure_member_profile, recharge
from apps.orders.models import CartItem, Order
from apps.orders.services import (
    OrderError,
    add_to_cart,
    approve_cancel,
    cancel_order,
    cancel_unfulfilled_order,
    complete_order,
    create_order_from_cart,
    expire_pending_orders,
    pay_order,
    pickup_order,
    receive_order,
    refund_order,
    reject_cancel,
    set_cart_quantity,
    ship_order,
    withdraw_cancel,
)
from apps.products.models import Category, Product

User = get_user_model()


@pytest.fixture
def member(db):
    user = User.objects.create_user(username="loop_member", password="pass123456", role=User.Role.MEMBER)
    profile = ensure_member_profile(user)
    assert profile is not None
    return profile


@pytest.fixture
def product(db):
    cat, _ = Category.objects.get_or_create(slug="test-cat", defaults={"name": "测试分类"})
    return Product.objects.create(
        category=cat,
        name="测试玫瑰",
        sku="SKU-TEST-R",
        price=Decimal("100.00"),
        stock=10,
        is_on_sale=True,
    )


def test_points_upgrade_to_silver(member):
    apply_points(member, 1000, PointsRecord.Source.MANUAL, remark="测试升级")
    member.refresh_from_db()
    assert member.current_points == 1000
    assert member.level.code == "silver"


def test_store_recharge_and_not_negative(member):
    rec = recharge(member, Decimal("50.00"))
    assert rec.balance_after == Decimal("50.00")
    member.refresh_from_db()
    assert member.store_balance == Decimal("50.00")


def test_order_pay_complete_refund_loop(member, product):
    recharge(member, Decimal("40.00"), remark="测试储值")
    add_to_cart(member, product, 1)
    order = create_order_from_cart(member, use_store=True, auto_coupon=False)
    product.refresh_from_db()
    assert product.stock == 9
    assert order.status == Order.Status.PENDING
    pay_order(order, success=True)
    order.refresh_from_db()
    member.refresh_from_db()
    assert order.status == Order.Status.PAID
    assert order.store_paid_amount == Decimal("40.00")
    assert order.gateway_paid_amount == Decimal("60.00")
    assert order.points_awarded > 0
    complete_order(order)
    refund_order(order)
    order.refresh_from_db()
    product.refresh_from_db()
    member.refresh_from_db()
    assert order.status == Order.Status.REFUNDED
    assert product.stock == 10
    assert member.store_balance == Decimal("40.00")


def test_expire_pending_orders_restores_stock(member, product):
    add_to_cart(member, product, 2)
    order = create_order_from_cart(member, use_store=False, auto_coupon=False)
    product.refresh_from_db()
    assert product.stock == 8
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    assert expire_pending_orders() == 1
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert product.stock == 10
    assert expire_pending_orders() == 0


def test_pay_rejects_expired_order(member, product):
    add_to_cart(member, product, 1)
    order = create_order_from_cart(member, use_store=False, auto_coupon=False)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    with pytest.raises(OrderError, match="超时"):
        pay_order(order, success=True)
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_cancel_restores_stock(member, product):
    add_to_cart(member, product, 2)
    order = create_order_from_cart(member, use_store=False, auto_coupon=False)
    product.refresh_from_db()
    assert product.stock == 8
    cancel_order(order)
    product.refresh_from_db()
    assert product.stock == 10
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_coupon_redeem_and_cancel_restore(member, product):
    now = timezone.now()
    coupon = Coupon.objects.create(
        name="测试满50减10",
        code="TEST50-10",
        kind=Coupon.Kind.AMOUNT,
        min_amount=Decimal("50.00"),
        face_value=Decimal("10.00"),
        total_count=10,
        per_user_limit=1,
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=7),
        is_active=True,
    )
    issue = receive_coupon(member, coupon)
    add_to_cart(member, product, 1)
    order = create_order_from_cart(member, use_store=False, coupon_issue=issue, auto_coupon=False)
    order.refresh_from_db()
    assert order.coupon_amount == Decimal("10.00")
    assert order.payable_amount == Decimal("90.00")
    issue.refresh_from_db()
    assert issue.status == CouponIssue.Status.USED
    cancel_order(order)
    issue.refresh_from_db()
    assert issue.status == CouponIssue.Status.CLAIMED


def test_expire_due_coupons(member):
    now = timezone.now()
    coupon = Coupon.objects.create(
        name="过期券",
        code="TEST-EXP",
        kind=Coupon.Kind.AMOUNT,
        face_value=Decimal("5.00"),
        total_count=10,
        per_user_limit=2,
        valid_from=now - timedelta(days=10),
        valid_to=now + timedelta(days=1),
        is_active=True,
    )
    issue = issue_coupon(member, coupon)
    assert coupon.remaining == 9
    issue.expire_at = now - timedelta(seconds=5)
    issue.save(update_fields=["expire_at"])
    n = expire_due_issues(now)
    issue.refresh_from_db()
    assert n >= 1
    assert issue.status == CouponIssue.Status.EXPIRED
    assert coupon.remaining == 10
    again = receive_coupon(member, coupon)
    assert again.status == CouponIssue.Status.CLAIMED
    assert again.hold_key == f"{coupon.pk}:{member.pk}"


def test_receive_coupon_rejects_second_active_hold(member):
    now = timezone.now()
    coupon = Coupon.objects.create(
        name="限领一张",
        code="ONCE-HOLD",
        kind=Coupon.Kind.AMOUNT,
        face_value=Decimal("5.00"),
        total_count=10,
        per_user_limit=1,
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=7),
        is_active=True,
    )
    receive_coupon(member, coupon)
    with pytest.raises(CouponError, match="上限"):
        receive_coupon(member, coupon)
    with pytest.raises(IntegrityError):
        CouponIssue.objects.create(
            coupon=coupon,
            member=member,
            status=CouponIssue.Status.CLAIMED,
            source=CouponIssue.Source.CLAIM,
            expire_at=now + timedelta(days=7),
        )


def test_add_to_cart_rejects_insufficient_stock(member, product):
    with pytest.raises(OrderError, match="库存不足"):
        add_to_cart(member, product, 11)
    assert not CartItem.objects.filter(member=member, product=product).exists()
    add_to_cart(member, product, 8)
    with pytest.raises(OrderError, match="库存不足"):
        add_to_cart(member, product, 3)
    assert CartItem.objects.get(member=member, product=product).quantity == 8
    with pytest.raises(OrderError, match="库存不足"):
        set_cart_quantity(member, product, 11)


def test_create_order_rejects_insufficient_stock(member, product):
    add_to_cart(member, product, 10)
    product.stock = 3
    product.save(update_fields=["stock", "updated_at"])
    with pytest.raises(OrderError, match="库存不足"):
        create_order_from_cart(member, use_store=False, auto_coupon=False)
    product.refresh_from_db()
    assert product.stock == 3


def test_dashboard_payload_shape(db):
    from apps.dashboard.services import PAID_STATUSES, dashboard_payload

    data = dashboard_payload()
    assert len(data["days"]) == 14
    assert set(data["kpi"]) >= {"today_sales", "today_orders", "members", "pending", "store_balance"}
    assert "sales" in data and "bestsellers" in data and "brand" in data
    assert Order.Status.SHIPPED in PAID_STATUSES
    assert Order.Status.PAID in PAID_STATUSES
    assert Order.Status.CANCEL_REQUESTED in PAID_STATUSES
    assert Order.Status.COMPLETED in PAID_STATUSES


def test_delivery_ship_receive_and_pickup(member, product):
    add_to_cart(member, product, 1)
    with pytest.raises(OrderError, match="收花人"):
        create_order_from_cart(
            member,
            use_store=False,
            auto_coupon=False,
            fulfillment=Order.Fulfillment.DELIVERY,
        )
    order = create_order_from_cart(
        member,
        use_store=False,
        auto_coupon=False,
        fulfillment=Order.Fulfillment.DELIVERY,
        receiver_name="林小花",
        receiver_phone="13800001111",
        address="花间路 1 号",
    )
    pay_order(order, success=True)
    with pytest.raises(OrderError, match="先发货"):
        complete_order(order)
    with pytest.raises(OrderError, match="配送单"):
        pickup_order(order)
    order = ship_order(order)
    assert order.status == Order.Status.SHIPPED
    assert order.tracking_no.startswith("FLW")
    from apps.dashboard.services import PAID_STATUSES, dashboard_payload

    assert order.status in PAID_STATUSES
    payload = dashboard_payload()
    assert payload["kpi"]["today_orders"] >= 1
    order = receive_order(order)
    assert order.status == Order.Status.COMPLETED
    assert order.received_at
    add_to_cart(member, product, 1)
    pickup = create_order_from_cart(member, use_store=False, auto_coupon=False)
    assert pickup.fulfillment == Order.Fulfillment.PICKUP
    pay_order(pickup, success=True)
    with pytest.raises(OrderError, match="自提"):
        ship_order(pickup)
    pickup = complete_order(pickup)
    assert pickup.status == Order.Status.COMPLETED


def test_member_can_cancel_paid_before_ship(member, product):
    recharge(member, Decimal("100.00"), remark="测取消")
    add_to_cart(member, product, 1)
    order = create_order_from_cart(
        member,
        use_store=True,
        auto_coupon=False,
        fulfillment=Order.Fulfillment.DELIVERY,
        receiver_name="林小花",
        receiver_phone="13800001111",
        address="花间路 1 号",
    )
    pay_order(order, success=True)
    product.refresh_from_db()
    assert product.stock == 9
    order = cancel_unfulfilled_order(order, remark="不想要了")
    order.refresh_from_db()
    product.refresh_from_db()
    member.refresh_from_db()
    member.store_account.refresh_from_db()
    assert order.status == Order.Status.CANCEL_REQUESTED
    assert product.stock == 9
    assert member.store_balance == Decimal("0.00")
    with pytest.raises(OrderError, match="取消申请"):
        ship_order(order)
    order = approve_cancel(order)
    order.refresh_from_db()
    product.refresh_from_db()
    member.refresh_from_db()
    member.store_account.refresh_from_db()
    assert order.status == Order.Status.REFUNDED
    assert product.stock == 10
    assert member.store_balance == Decimal("100.00")
    add_to_cart(member, product, 1)
    shipped = create_order_from_cart(
        member,
        use_store=False,
        auto_coupon=False,
        fulfillment=Order.Fulfillment.DELIVERY,
        receiver_name="林小花",
        receiver_phone="13800001111",
        address="花间路 1 号",
    )
    pay_order(shipped, success=True)
    ship_order(shipped)
    with pytest.raises(OrderError, match="不能取消"):
        cancel_unfulfilled_order(shipped)


def test_staff_can_reject_or_member_can_withdraw_cancel(member, product):
    add_to_cart(member, product, 1)
    order = create_order_from_cart(
        member,
        use_store=False,
        auto_coupon=False,
        fulfillment=Order.Fulfillment.DELIVERY,
        receiver_name="林小花",
        receiver_phone="13800001111",
        address="花间路 1 号",
    )
    pay_order(order, success=True)
    order = cancel_unfulfilled_order(order)
    order = reject_cancel(order, remark="已开始绑花")
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    product.refresh_from_db()
    assert product.stock == 9
    order = cancel_unfulfilled_order(order)
    order = withdraw_cancel(order)
    order.refresh_from_db()
    assert order.status == Order.Status.PAID
    order = ship_order(order)
    assert order.status == Order.Status.SHIPPED


def test_refund_shipped_order(member, product):
    add_to_cart(member, product, 1)
    order = create_order_from_cart(
        member,
        use_store=False,
        auto_coupon=False,
        fulfillment=Order.Fulfillment.DELIVERY,
        receiver_name="林小花",
        receiver_phone="13800001111",
        address="花间路 1 号",
    )
    pay_order(order, success=True)
    ship_order(order)
    refund_order(order)
    order.refresh_from_db()
    product.refresh_from_db()
    assert order.status == Order.Status.REFUNDED
    assert product.stock == 10
    with pytest.raises(OrderError, match="签收"):
        receive_order(order)


def test_self_recharge_success_fail_timeout_no_points(member):
    from apps.members.models import StoreRecharge
    from apps.members.services import RechargeError, create_store_recharge, pay_store_recharge

    points_before = member.total_points
    item = create_store_recharge(member, "100", operator=member.user)
    assert item.status == StoreRecharge.Status.PENDING
    with pytest.raises(RechargeError, match="上一笔"):
        create_store_recharge(member, "50", operator=member.user)
    pay_store_recharge(item, success=False)
    item.refresh_from_db()
    assert item.status == StoreRecharge.Status.PENDING
    assert member.store_balance == Decimal("0.00")
    pay_store_recharge(item, success=True)
    member.refresh_from_db()
    member.store_account.refresh_from_db()
    assert member.store_balance == Decimal("100.00")
    assert member.total_points == points_before
    item.refresh_from_db()
    assert item.status == StoreRecharge.Status.SUCCESS
    again = create_store_recharge(member, "50", operator=member.user)
    StoreRecharge.objects.filter(pk=again.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    expire_pending_orders()
    again.refresh_from_db()
    assert again.status == StoreRecharge.Status.CLOSED
    with pytest.raises(RechargeError, match="关闭"):
        pay_store_recharge(again, success=True)


def test_staff_has_pay_not_refund(db):
    staff = User.objects.create_user(username="t_staff", password="pass123456", role=User.Role.STAFF)
    staff.refresh_from_db()
    assert staff.is_staff
    assert staff.has_perm("orders.pay_order")
    assert staff.has_perm("orders.ship_order")
    assert staff.has_perm("orders.receive_order")
    assert staff.has_perm("orders.review_cancel")
    assert not staff.has_perm("orders.refund_order")
    assert not staff.has_perm("accounts.view_user")


def test_level_table_seeded(db):
    assert MemberLevel.objects.filter(code="diamond").exists()
    assert MemberLevel.for_points(5000).code == "gold"


def test_member_admin_level_readonly_after_create(member):
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    from apps.members.admin import MemberAdmin

    request = RequestFactory().get("/admin/members/member/")
    request.user = User.objects.create_user(username="lvl_admin", password="pass123456", role=User.Role.ADMIN)
    model_admin = MemberAdmin(member.__class__, site)
    assert "level" not in model_admin.get_readonly_fields(request, None)
    assert "level" in model_admin.get_readonly_fields(request, member)


def test_order_admin_locks_status_and_paid_items(member, product):
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    from apps.orders.admin import OrderAdmin, OrderItemInline
    from apps.orders.services import gen_order_no

    admin_user = User.objects.create_user(username="lock_admin", password="pass123456", role=User.Role.ADMIN)
    add_to_cart(member, product, 1)
    order = create_order_from_cart(member, use_store=False, auto_coupon=False)
    request = RequestFactory().get("/admin/orders/order/")
    request.user = admin_user
    model_admin = OrderAdmin(Order, site)
    inline = OrderItemInline(Order, site)
    assert "status" in model_admin.get_readonly_fields(request, order)
    assert order.stock_reserved
    assert inline.get_readonly_fields(request, order) == inline.fields
    assert inline.has_add_permission(request, order) is False
    assert inline.has_delete_permission(request, order) is False

    draft = Order.objects.create(
        order_no=gen_order_no(),
        member=member,
        status=Order.Status.PENDING,
        stock_reserved=False,
    )
    assert inline.get_readonly_fields(request, draft) == ()
    assert inline.has_add_permission(request, draft) is True

    pay_order(order, success=True)
    order.refresh_from_db()
    assert "status" in model_admin.get_readonly_fields(request, order)
    assert inline.get_readonly_fields(request, order) == inline.fields
    assert inline.has_add_permission(request, order) is False
    assert inline.has_delete_permission(request, order) is False


def test_staff_change_form_does_not_post_reserved_item_quantity(client, member, product):
    User.objects.create_user(username="lock_staff", password="pass123456", role=User.Role.STAFF)
    add_to_cart(member, product, 1)
    order = create_order_from_cart(member, use_store=False, auto_coupon=False)
    assert order.stock_reserved
    assert client.login(username="lock_staff", password="pass123456")
    page = client.get(f"/admin/orders/order/{order.pk}/change/")
    assert page.status_code == 200
    html = page.content.decode()
    assert 'name="items-0-quantity"' not in html
    assert 'name="items-0-id"' in html
