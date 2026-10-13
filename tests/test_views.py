from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.welcome import SHOP_NAME, SLOGAN, level_catalog, welcome_payload
from apps.marketing.models import Coupon, CouponIssue
from apps.members.models import MemberLevel
from apps.members.services import apply_points, ensure_member_profile
from apps.orders.models import Order

User = get_user_model()


def test_public_pages(client, db):
    assert client.get("/").status_code == 200
    assert client.get("/shop/").status_code == 200
    assert client.get("/accounts/login/").status_code == 200
    assert client.get("/member/").status_code == 302
    assert client.get("/dashboard/").status_code == 302


def test_home_and_shop_expire_pending_orders(client, db):
    from decimal import Decimal

    from apps.orders.models import Order
    from apps.orders.services import add_to_cart, create_order_from_cart
    from apps.products.models import Category, Product

    user = User.objects.create_user(username="exp_home", password="pass123456", role=User.Role.MEMBER)
    member = ensure_member_profile(user)
    cat, _ = Category.objects.get_or_create(slug="exp-home", defaults={"name": "超时扫描"})
    product = Product.objects.create(
        category=cat,
        name="超时扫描花束",
        sku="SKU-EXP-HOME",
        price=Decimal("50.00"),
        stock=5,
        is_on_sale=True,
    )
    add_to_cart(member, product, 1)
    order = create_order_from_cart(member, use_store=False, auto_coupon=False)
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    assert client.get("/").status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    add_to_cart(member, product, 1)
    order2 = create_order_from_cart(member, use_store=False, auto_coupon=False)
    Order.objects.filter(pk=order2.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    assert client.get("/shop/").status_code == 200
    order2.refresh_from_db()
    assert order2.status == Order.Status.CANCELLED
    add_to_cart(member, product, 1)
    order3 = create_order_from_cart(member, use_store=False, auto_coupon=False)
    Order.objects.filter(pk=order3.pk).update(created_at=timezone.now() - timedelta(minutes=31))
    assert client.get(f"/shop/{product.pk}/").status_code == 200
    order3.refresh_from_db()
    assert order3.status == Order.Status.CANCELLED


def test_member_center_and_shop(client, db):
    user = User.objects.create_user(username="v_member", password="pass123456", role=User.Role.MEMBER)
    ensure_member_profile(user)
    assert client.login(username="v_member", password="pass123456")
    assert client.get("/member/").status_code == 200
    assert client.get("/member/coupons/").status_code == 200
    assert client.get("/member/profile/").status_code == 200
    assert client.get("/member/ledger/").status_code == 200
    assert client.get("/orders/cart/").status_code == 200
    assert client.get("/dashboard/").status_code == 403


def test_staff_dashboard(client, db):
    User.objects.create_user(username="v_staff", password="pass123456", role=User.Role.STAFF)
    assert client.login(username="v_staff", password="pass123456")
    page = client.get("/dashboard/")
    assert page.status_code == 200
    assert "pending_orders" in page.context["desk"]
    assert "fulfill_orders" in page.context["desk"]
    assert "cancel_review_orders" in page.context["desk"]
    assert "low_stock" in page.context["desk"]
    assert page.context["desk"]["low_stock_threshold"] == 8


def test_welcome_by_role_and_level(db):
    admin = User.objects.create_user(username="w_admin", password="pass123456", role=User.Role.ADMIN)
    staff = User.objects.create_user(username="w_staff", password="pass123456", role=User.Role.STAFF)
    member_user = User.objects.create_user(username="w_member", password="pass123456", role=User.Role.MEMBER)
    member = ensure_member_profile(member_user)
    assert SHOP_NAME == "花间集"
    assert SLOGAN in welcome_payload(admin)["text"]
    assert welcome_payload(staff)["role"] == "staff"
    assert welcome_payload(member_user)["level_code"] == "normal"
    gold = MemberLevel.objects.get(code="gold")
    apply_points(member, gold.min_points, "manual", remark="测试升级")
    member_user = User.objects.select_related("member_profile__level").get(pk=member_user.pk)
    assert welcome_payload(member_user)["level_code"] == "gold"


def test_member_center_level_preview(client, db):
    user = User.objects.create_user(username="v_preview", password="pass123456", role=User.Role.MEMBER)
    ensure_member_profile(user)
    assert client.login(username="v_preview", password="pass123456")
    page = client.get("/member/?preview=diamond")
    assert page.status_code == 200
    assert page.context["previewing"] is True
    assert page.context["selected_level"]["code"] == "diamond"
    assert page.context["actual_welcome"]["level_code"] == "normal"
    assert page.context["welcome"]["badge_class"] == "lv-diamond"
    assert page.context["selected_level"]["is_mine"] is False
    assert any(item["is_mine"] for item in page.context["levels"])
    assert len(level_catalog()) == 4
    own = client.get("/member/")
    assert own.context["previewing"] is False
    assert own.context["welcome"]["level_code"] == "normal"


def test_staff_can_issue_selected_coupon(client, db):
    staff = User.objects.create_user(username="issue_staff", password="pass123456", role=User.Role.STAFF)
    member_user = User.objects.create_user(username="issue_member", password="pass123456", role=User.Role.MEMBER)
    member = ensure_member_profile(member_user)
    now = timezone.now()
    coupon = Coupon.objects.create(
        name="店员发放券",
        code="STAFF-ISSUE",
        kind=Coupon.Kind.AMOUNT,
        min_amount=0,
        face_value=10,
        total_count=20,
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=10),
        is_active=True,
    )
    assert client.login(username="issue_staff", password="pass123456")
    response = client.post(
        "/admin/marketing/coupon/",
        {
            "action": "action_issue_to_members",
            "index": "0",
            "_selected_action": str(coupon.pk),
            "post": "yes",
            "member_ids": str(member.pk),
        },
        follow=True,
    )
    assert response.status_code == 200
    assert CouponIssue.objects.filter(coupon=coupon, member=member).exists()


def test_member_profile_update(client, db):
    user = User.objects.create_user(username="v_profile", password="pass123456", role=User.Role.MEMBER)
    ensure_member_profile(user)
    assert client.login(username="v_profile", password="pass123456")
    response = client.post(
        "/member/profile/",
        {
            "real_name": "林小花",
            "phone": "13800001111",
            "gender": "female",
            "birthday": "2000-05-20",
        },
        follow=True,
    )
    assert response.status_code == 200
    user.refresh_from_db()
    member = user.member_profile
    member.refresh_from_db()
    assert member.real_name == "林小花"
    assert user.phone == "13800001111"
    assert member.gender == "female"
    assert str(member.birthday) == "2000-05-20"


def test_member_cannot_view_other_member_order(client, db):
    from decimal import Decimal

    from apps.orders.services import add_to_cart, create_order_from_cart
    from apps.products.models import Category, Product

    owner = User.objects.create_user(username="idor_owner", password="pass123456", role=User.Role.MEMBER)
    other = User.objects.create_user(username="idor_other", password="pass123456", role=User.Role.MEMBER)
    owner_profile = ensure_member_profile(owner)
    ensure_member_profile(other)
    cat, _ = Category.objects.get_or_create(slug="idor-cat", defaults={"name": "越权测试"})
    product = Product.objects.create(
        category=cat,
        name="越权测试花束",
        sku="SKU-IDOR-1",
        price=Decimal("88.00"),
        stock=5,
        is_on_sale=True,
    )
    add_to_cart(owner_profile, product, 1)
    order = create_order_from_cart(owner_profile, use_store=False, auto_coupon=False)
    assert client.login(username="idor_other", password="pass123456")
    assert client.get(f"/orders/{order.pk}/").status_code == 404
    assert client.post(f"/orders/{order.pk}/pay/", {"success": "1"}).status_code == 404


def test_member_cannot_open_admin(client, db):
    User.objects.create_user(username="no_admin", password="pass123456", role=User.Role.MEMBER)
    assert client.login(username="no_admin", password="pass123456")
    page = client.get("/admin/")
    assert page.status_code == 302
    assert "/admin/login" in page["Location"]


def test_shop_keyword_search(client, db):
    from decimal import Decimal

    from apps.products.models import Category, Product

    cat, _ = Category.objects.get_or_create(slug="search-cat", defaults={"name": "搜索分类"})
    Product.objects.create(
        category=cat,
        name="红玫瑰花束",
        sku="SKU-SEARCH-R",
        price=Decimal("99.00"),
        stock=10,
        flower_language="热恋与郑重的爱",
        is_on_sale=True,
    )
    page = client.get("/shop/?q=玫瑰")
    assert page.status_code == 200
    assert page.context["q"] == "玫瑰"
    names = [p.name for p in page.context["products"]]
    assert any("玫瑰" in name for name in names)
    empty = client.get("/shop/?q=不存在的花xyz")
    assert list(empty.context["products"]) == []


def test_guest_buy_now_login_returns_to_checkout(client, db):
    from decimal import Decimal
    from urllib.parse import unquote

    from apps.orders.models import CartItem
    from apps.products.models import Category, Product

    user = User.objects.create_user(username="guest_buy", password="pass123456", role=User.Role.MEMBER)
    member = ensure_member_profile(user)
    cat, _ = Category.objects.get_or_create(slug="guest-buy", defaults={"name": "游客购买"})
    product = Product.objects.create(
        category=cat,
        name="游客结算花束",
        sku="SKU-GUEST-1",
        price=Decimal("66.00"),
        stock=8,
        is_on_sale=True,
    )
    add = client.post(f"/shop/{product.pk}/add/", {"quantity": "1", "next": "/orders/checkout/"})
    assert add.status_code == 302
    location = unquote(add["Location"])
    assert "/accounts/login/" in location
    assert "next=/orders/checkout/" in location
    login = client.post(
        "/accounts/login/",
        {"username": "guest_buy", "password": "pass123456", "next": "/orders/checkout/"},
    )
    assert login.status_code == 302
    assert login["Location"] == "/orders/checkout/"
    assert CartItem.objects.filter(member=member, product=product, quantity=1).exists()


def test_member_password_change(client, db):
    User.objects.create_user(username="pwd_member", password="pass123456", role=User.Role.MEMBER)
    assert client.get("/accounts/password/change/").status_code == 302
    assert client.login(username="pwd_member", password="pass123456")
    page = client.get("/accounts/password/change/")
    assert page.status_code == 200
    changed = client.post(
        "/accounts/password/change/",
        {
            "old_password": "pass123456",
            "new_password1": "newpass123456",
            "new_password2": "newpass123456",
        },
    )
    assert changed.status_code == 302
    assert changed["Location"] == "/member/"
    client.logout()
    assert client.login(username="pwd_member", password="newpass123456")


def test_member_cannot_receive_other_order(client, db):
    from decimal import Decimal

    from apps.orders.services import add_to_cart, create_order_from_cart, pay_order, ship_order
    from apps.products.models import Category, Product

    owner = User.objects.create_user(username="ship_owner", password="pass123456", role=User.Role.MEMBER)
    other = User.objects.create_user(username="ship_other", password="pass123456", role=User.Role.MEMBER)
    owner_m = ensure_member_profile(owner)
    ensure_member_profile(other)
    cat, _ = Category.objects.get_or_create(slug="ship-cat", defaults={"name": "签收测试"})
    product = Product.objects.create(
        category=cat, name="签收花束", sku="SKU-SHIP-1", price=Decimal("80.00"), stock=5, is_on_sale=True
    )
    add_to_cart(owner_m, product, 1)
    order = create_order_from_cart(
        owner_m,
        use_store=False,
        auto_coupon=False,
        fulfillment=Order.Fulfillment.DELIVERY,
        receiver_name="主人",
        receiver_phone="13800002222",
        address="花间路 2 号",
    )
    pay_order(order, success=True)
    ship_order(order)
    assert client.login(username="ship_other", password="pass123456")
    assert client.post(f"/orders/{order.pk}/receive/").status_code == 404
    assert client.login(username="ship_owner", password="pass123456")
    ok = client.post(f"/orders/{order.pk}/receive/")
    assert ok.status_code == 302
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


def test_member_self_recharge_page(client, db):
    user = User.objects.create_user(username="rc_member", password="pass123456", role=User.Role.MEMBER)
    member = ensure_member_profile(user)
    assert client.get("/member/recharge/").status_code == 302
    assert client.login(username="rc_member", password="pass123456")
    assert client.get("/member/recharge/").status_code == 200
    created = client.post("/member/recharge/", {"preset": "100"})
    assert created.status_code == 302
    from apps.members.models import StoreRecharge

    item = StoreRecharge.objects.get(member=member)
    paid = client.post(f"/member/recharge/{item.pk}/pay/", {"success": "1"})
    assert paid.status_code == 302
    member.refresh_from_db()
    assert member.store_balance == 100


def test_media_url_mounted_when_debug_false(settings):
    from django.conf import settings as django_settings
    from django.urls import resolve
    from django.views.static import serve

    settings.DEBUG = False
    match = resolve("/media/products/probe.jpg")
    assert match.func is serve
    assert match.kwargs["document_root"] == django_settings.MEDIA_ROOT
