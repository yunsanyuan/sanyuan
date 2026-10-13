from apps.core.welcome import SHOP_NAME, SLOGAN, welcome_payload
from apps.members.models import Member


def shop_context(request):
    data = {
        "cart_count": 0,
        "member_profile": None,
        "nav": "",
        "shop_name": SHOP_NAME,
        "shop_slogan": SLOGAN,
        "welcome": welcome_payload(None),
        "member_discount_rate": None,
    }
    path = getattr(request, "path", "") or ""
    if path.startswith("/admin/"):
        return data
    resolver = getattr(request, "resolver_match", None)
    if resolver:
        data["nav"] = resolver.namespace or resolver.url_name or ""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return data
    data["welcome"] = welcome_payload(user)
    if getattr(user, "role", "") != "member":
        return data
    profile = (
        Member.objects.select_related("level").filter(user_id=user.pk).first()
        or getattr(user, "member_profile", None)
    )
    data["member_profile"] = profile
    if not profile:
        return data
    cached = request.session.get("cart_count")
    if cached is None:
        from apps.core.cart import refresh_cart_count

        cached = refresh_cart_count(request, profile)
    data["cart_count"] = cached
    if profile.level_id:
        data["member_discount_rate"] = profile.level.discount_rate
    return data
