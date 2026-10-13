from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.marketing.models import CouponIssue
from apps.members.models import Member, PointsRecord, StoreAccount, StoreRecord
from apps.orders.models import Order, OrderItem
from apps.orders.services import expire_pending_orders
from apps.products.models import Product

PAID_STATUSES = (
    Order.Status.PAID,
    Order.Status.CANCEL_REQUESTED,
    Order.Status.SHIPPED,
    Order.Status.COMPLETED,
)
BRAND = "#355E4B"
LOW_STOCK_THRESHOLD = 8


def staff_desk(limit: int = 8) -> dict:
    expire_pending_orders()
    pending_orders = list(
        Order.objects.filter(status=Order.Status.PENDING)
        .select_related("member", "member__user")
        .prefetch_related("items")[:limit]
    )
    fulfill_orders = list(
        Order.objects.filter(status=Order.Status.PAID)
        .select_related("member", "member__user")
        .prefetch_related("items")[:limit]
    )
    cancel_review_orders = list(
        Order.objects.filter(status=Order.Status.CANCEL_REQUESTED)
        .select_related("member", "member__user")
        .prefetch_related("items")[:limit]
    )
    low_stock = list(
        Product.objects.filter(is_on_sale=True, stock__lte=LOW_STOCK_THRESHOLD)
        .select_related("category")
        .order_by("stock", "id")[:limit]
    )
    return {
        "pending_orders": pending_orders,
        "fulfill_orders": fulfill_orders,
        "cancel_review_orders": cancel_review_orders,
        "low_stock": low_stock,
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
        "pending_count": Order.objects.filter(status=Order.Status.PENDING).count(),
        "fulfill_count": Order.objects.filter(status=Order.Status.PAID).count(),
        "cancel_review_count": Order.objects.filter(status=Order.Status.CANCEL_REQUESTED).count(),
        "low_stock_count": Product.objects.filter(
            is_on_sale=True, stock__lte=LOW_STOCK_THRESHOLD
        ).count(),
    }


def _days(n: int):
    today = timezone.localdate()
    return [today - timedelta(days=n - 1 - i) for i in range(n)]


def _fill(days, mapping, default=0):
    return [mapping.get(d, default) for d in days]


def _money(value) -> float:
    if value is None:
        return 0.0
    return float(Decimal(value))


def _local_day(dt):
    if dt is None:
        return None
    return timezone.localtime(dt).date()


def dashboard_payload(days: int = 14) -> dict:
    labels = _days(days)
    tzinfo = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(labels[0], time.min), tzinfo)
    today = timezone.localdate()
    today_start = timezone.make_aware(datetime.combine(today, time.min), tzinfo)
    today_end = today_start + timedelta(days=1)

    paid_orders = Order.objects.filter(status__in=PAID_STATUSES, paid_at__isnull=False)
    sales_map = {}
    order_map = {}
    for order in paid_orders.filter(paid_at__gte=start).only(
        "paid_at", "store_paid_amount", "gateway_paid_amount"
    ):
        day = _local_day(order.paid_at)
        if day is None:
            continue
        sales_map[day] = sales_map.get(day, 0.0) + _money(
            order.store_paid_amount + order.gateway_paid_amount
        )
        order_map[day] = order_map.get(day, 0) + 1

    member_map = {}
    for created_at in Member.objects.filter(created_at__gte=start).values_list("created_at", flat=True):
        day = _local_day(created_at)
        if day is None:
            continue
        member_map[day] = member_map.get(day, 0) + 1

    level_rows = (
        Member.objects.values("level__name", "level__sort_order")
        .annotate(cnt=Count("id"))
        .order_by("level__sort_order")
    )
    status_rows = Order.objects.values("status").annotate(cnt=Count("id"))
    status_labels = dict(Order.Status.choices)

    bestsellers = list(
        OrderItem.objects.filter(order__status__in=PAID_STATUSES)
        .values("product_name")
        .annotate(qty=Sum("quantity"), amount=Sum("subtotal"))
        .order_by("-qty")[:6]
    )

    points_in = (
        PointsRecord.objects.filter(delta__gt=0).aggregate(s=Sum("delta"))["s"] or 0
    )
    points_out = abs(
        PointsRecord.objects.filter(delta__lt=0).aggregate(s=Sum("delta"))["s"] or 0
    )
    store_kind = {
        row["kind"]: _money(row["s"])
        for row in StoreRecord.objects.values("kind").annotate(s=Sum("delta"))
    }
    coupon_status = {
        row["status"]: row["cnt"]
        for row in CouponIssue.objects.values("status").annotate(cnt=Count("id"))
    }

    today_qs = paid_orders.filter(paid_at__gte=today_start, paid_at__lt=today_end)
    today_sales = today_qs.aggregate(s=Sum(F("store_paid_amount") + F("gateway_paid_amount")))["s"]
    kpi = {
        "today_sales": _money(today_sales),
        "today_orders": today_qs.count(),
        "members": Member.objects.count(),
        "pending": Order.objects.filter(status=Order.Status.PENDING).count(),
        "store_balance": _money(StoreAccount.objects.aggregate(s=Sum("balance"))["s"]),
        "coupon_used": CouponIssue.objects.filter(status=CouponIssue.Status.USED).count(),
    }

    label_text = [d.strftime("%m-%d") for d in labels]
    return {
        "kpi": kpi,
        "days": label_text,
        "sales": _fill(labels, sales_map, 0.0),
        "order_counts": _fill(labels, order_map, 0),
        "member_growth": _fill(labels, member_map, 0),
        "levels": [{"name": r["level__name"] or "未分级", "value": r["cnt"]} for r in level_rows],
        "order_status": [
            {"name": status_labels.get(r["status"], r["status"]), "value": r["cnt"]}
            for r in status_rows
        ],
        "bestsellers": {
            "names": [r["product_name"] for r in bestsellers],
            "qty": [r["qty"] or 0 for r in bestsellers],
        },
        "points": {"earn": int(points_in), "refund": int(points_out)},
        "store": {
            "recharge": abs(store_kind.get(StoreRecord.Kind.RECHARGE, 0.0)),
            "consume": abs(store_kind.get(StoreRecord.Kind.CONSUME, 0.0)),
            "refund": abs(store_kind.get(StoreRecord.Kind.REFUND, 0.0)),
        },
        "coupons": {
            "claimed": coupon_status.get(CouponIssue.Status.CLAIMED, 0),
            "used": coupon_status.get(CouponIssue.Status.USED, 0),
            "expired": coupon_status.get(CouponIssue.Status.EXPIRED, 0),
        },
        "brand": BRAND,
    }
