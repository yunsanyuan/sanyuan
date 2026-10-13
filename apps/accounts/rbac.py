from django.contrib.auth.models import Group, Permission

STAFF_GROUP = "店员"
ADMIN_GROUP = "管理员"

STAFF_PERMISSIONS = [
    "products.view_category",
    "products.add_category",
    "products.change_category",
    "products.view_product",
    "products.add_product",
    "products.change_product",
    "orders.view_cartitem",
    "orders.add_cartitem",
    "orders.change_cartitem",
    "orders.delete_cartitem",
    "orders.view_order",
    "orders.add_order",
    "orders.change_order",
    "orders.pay_order",
    "orders.ship_order",
    "orders.receive_order",
    "orders.review_cancel",
    "orders.view_orderitem",
    "orders.add_orderitem",
    "orders.change_orderitem",
    "orders.view_orderstatuslog",
    "orders.view_paymentrecord",
    "members.view_member",
    "members.view_memberlevel",
    "members.view_pointsrecord",
    "members.view_storeaccount",
    "members.view_storerecord",
    "marketing.view_coupon",
    "marketing.view_couponissue",
    "marketing.add_couponissue",
    "marketing.change_couponissue",
]


def _perm(codename_full: str) -> Permission | None:
    app_label, codename = codename_full.split(".", 1)
    return Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()


def ensure_groups() -> tuple[Group, Group]:
    staff_group, _ = Group.objects.get_or_create(name=STAFF_GROUP)
    admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
    staff_perms = [p for p in (_perm(code) for code in STAFF_PERMISSIONS) if p]
    staff_group.permissions.set(staff_perms)
    admin_group.permissions.set(Permission.objects.all())
    return admin_group, staff_group


def is_admin_user(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, "role", "") == "admin")
    )


def apply_role(user) -> None:
    from django.contrib.auth import get_user_model

    if not user.pk:
        return
    User = get_user_model()
    user = User.objects.get(pk=user.pk)
    admin_group, staff_group = ensure_groups()
    kept = list(user.groups.exclude(name__in=[ADMIN_GROUP, STAFF_GROUP]))
    role = getattr(user, "role", "member")
    if role == "admin":
        kept.append(admin_group)
    elif role == "staff":
        kept.append(staff_group)
    user.groups.set(kept)
