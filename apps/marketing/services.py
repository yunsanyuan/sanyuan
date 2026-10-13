from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Coupon, CouponIssue


class CouponError(Exception):
    pass


def _money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def expire_due_issues(now=None) -> int:
    now = now or timezone.now()
    qs = CouponIssue.objects.filter(
        status=CouponIssue.Status.CLAIMED,
        expire_at__lt=now,
    )
    return qs.update(status=CouponIssue.Status.EXPIRED, hold_key=None)


def compute_discount(coupon: Coupon, goods_amount, after_level_amount) -> Decimal:
    goods_amount = _money(goods_amount)
    after_level_amount = _money(after_level_amount)
    if goods_amount < coupon.min_amount:
        raise CouponError(f"未满 {coupon.min_amount} 元，不能使用 {coupon.name}")
    if coupon.kind == Coupon.Kind.AMOUNT:
        return min(coupon.face_value, after_level_amount)
    cut = _money(after_level_amount * (Decimal("1.00") - coupon.discount_rate))
    return min(cut, after_level_amount)


def _assert_receivable(coupon: Coupon, member, now):
    if not coupon.is_active:
        raise CouponError("优惠券已停用")
    if not coupon.is_in_period(now):
        raise CouponError("不在领取有效期内")
    if coupon.remaining <= 0:
        raise CouponError("优惠券已领完")
    owned = CouponIssue.objects.filter(coupon=coupon, member=member).exclude(
        status=CouponIssue.Status.EXPIRED
    ).count()
    if owned >= coupon.per_user_limit:
        raise CouponError("已达到领取上限")


@transaction.atomic
def receive_coupon(member, coupon: Coupon, source: str = CouponIssue.Source.CLAIM) -> CouponIssue:
    now = timezone.now()
    expire_due_issues(now)
    coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
    _assert_receivable(coupon, member, now)
    try:
        return CouponIssue.objects.create(
            coupon=coupon,
            member=member,
            status=CouponIssue.Status.CLAIMED,
            source=source,
            expire_at=coupon.valid_to,
            claimed_at=now,
        )
    except IntegrityError as exc:
        raise CouponError("已达到领取上限") from exc


def issue_coupon(member, coupon: Coupon) -> CouponIssue:
    return receive_coupon(member, coupon, source=CouponIssue.Source.ISSUE)


def _usable_issue(issue: CouponIssue, member, now):
    expire_due_issues(now)
    issue.refresh_from_db()
    if issue.member_id != member.id:
        raise CouponError("优惠券不属于当前会员")
    if issue.status == CouponIssue.Status.EXPIRED:
        raise CouponError("优惠券已过期")
    if issue.status == CouponIssue.Status.USED:
        raise CouponError("优惠券已核销")
    if issue.status != CouponIssue.Status.CLAIMED:
        raise CouponError("优惠券不可用")
    if not issue.coupon.is_active or issue.expire_at < now:
        issue.status = CouponIssue.Status.EXPIRED
        issue.save(update_fields=["status", "updated_at"])
        raise CouponError("优惠券已过期")
    return issue


@transaction.atomic
def redeem_on_order(order, issue: CouponIssue | None = None) -> CouponIssue | None:
    now = timezone.now()
    expire_due_issues(now)
    member = order.member
    after_level = _money(order.goods_amount - order.level_discount_amount)
    if issue is None:
        best = None
        best_amount = Decimal("0.00")
        candidates = (
            CouponIssue.objects.select_related("coupon")
            .select_for_update()
            .filter(member=member, status=CouponIssue.Status.CLAIMED)
        )
        for item in candidates:
            try:
                _usable_issue(item, member, now)
                amount = compute_discount(item.coupon, order.goods_amount, after_level)
            except CouponError:
                continue
            if amount > best_amount:
                best = item
                best_amount = amount
        issue = best
        if issue is None:
            return None
    else:
        issue = CouponIssue.objects.select_for_update().select_related("coupon").get(pk=issue.pk)
        _usable_issue(issue, member, now)
        best_amount = compute_discount(issue.coupon, order.goods_amount, after_level)

    issue.status = CouponIssue.Status.USED
    issue.order = order
    issue.used_at = now
    issue.save(update_fields=["status", "order", "used_at", "updated_at"])
    order.coupon_amount = best_amount
    from apps.orders.services import calculate_amounts

    _, _, coupon_amount, payable = calculate_amounts(member, order.goods_amount, best_amount)
    order.coupon_amount = coupon_amount
    order.payable_amount = payable
    order.save(update_fields=["coupon_amount", "payable_amount", "updated_at"])
    return issue


@transaction.atomic
def release_order_coupon(order):
    issue = getattr(order, "coupon_issue", None)
    if issue is None:
        return
    if issue.status != CouponIssue.Status.USED:
        return
    now = timezone.now()
    issue.order = None
    issue.used_at = None
    if issue.expire_at < now:
        issue.status = CouponIssue.Status.EXPIRED
    else:
        issue.status = CouponIssue.Status.CLAIMED
    issue.save(update_fields=["status", "order", "used_at", "updated_at"])
    order.coupon_amount = Decimal("0.00")
    order.save(update_fields=["coupon_amount", "updated_at"])
