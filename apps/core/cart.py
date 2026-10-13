from django.db.models import Sum
from django.utils.http import url_has_allowed_host_and_scheme

from apps.orders.models import CartItem


def refresh_cart_count(request, member) -> int:
    count = CartItem.objects.filter(member=member).aggregate(s=Sum("quantity"))["s"] or 0
    request.session["cart_count"] = count
    return count


def safe_next_url(request, raw: str | None) -> str:
    """Allow only same-host relative URLs; reject POST-only 加购路径。"""
    url = (raw or "").strip()
    if not url or url.rstrip("/").endswith("/add"):
        return ""
    if url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url
    return ""
