import random
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Member, MemberLevel, PointsRecord, StoreAccount, StoreRecharge, StoreRecord


class InsufficientBalance(Exception):
    pass


class RechargeError(Exception):
    pass


RECHARGE_TIMEOUT_MINUTES = 30
RECHARGE_MAX_AMOUNT = Decimal("2000.00")
RECHARGE_MIN_AMOUNT = Decimal("1.00")


def ensure_member_profile(user) -> Member | None:
    if getattr(user, "role", None) != user.Role.MEMBER:
        return None
    default_level = MemberLevel.objects.order_by("min_points").first()
    if default_level is None:
        return None
    member, created = Member.objects.get_or_create(
        user=user,
        defaults={"level": default_level},
    )
    StoreAccount.objects.get_or_create(member=member)
    return member


def refresh_level(member: Member) -> Member:
    level = MemberLevel.for_points(member.total_points)
    if level and member.level_id != level.id:
        member.level = level
        member.save(update_fields=["level", "updated_at"])
    return member


@transaction.atomic
def apply_points(
    member: Member,
    delta: int,
    source: str,
    remark: str = "",
    order_no: str = "",
) -> PointsRecord:
    member = Member.objects.select_for_update().get(pk=member.pk)
    new_current = member.current_points + delta
    new_total = member.total_points + delta
    if new_current < 0:
        new_current = 0
    if new_total < 0:
        new_total = 0
    member.current_points = new_current
    member.total_points = new_total
    member.save(update_fields=["current_points", "total_points", "updated_at"])
    refresh_level(member)
    return PointsRecord.objects.create(
        member=member,
        delta=delta,
        balance_after=member.current_points,
        source=source,
        remark=remark,
        order_no=order_no,
    )


@transaction.atomic
def apply_store(
    member: Member,
    delta: Decimal,
    kind: str,
    remark: str = "",
    order_no: str = "",
) -> StoreRecord:
    delta = Decimal(delta)
    member = Member.objects.select_for_update().get(pk=member.pk)
    account, _ = StoreAccount.objects.select_for_update().get_or_create(member=member)
    new_balance = account.balance + delta
    if new_balance < 0:
        raise InsufficientBalance("储值余额不足")
    account.balance = new_balance
    account.save(update_fields=["balance", "updated_at"])
    return StoreRecord.objects.create(
        member=member,
        delta=delta,
        balance_after=account.balance,
        kind=kind,
        remark=remark,
        order_no=order_no,
    )


def recharge(member: Member, amount, remark: str = "后台充值") -> StoreRecord:
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("充值金额必须大于 0")
    return apply_store(member, amount, StoreRecord.Kind.RECHARGE, remark=remark)


def gen_recharge_no() -> str:
    return timezone.now().strftime("RC%Y%m%d%H%M%S") + f"{random.randint(0, 999):03d}"


def expire_pending_recharges(now=None) -> int:
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=RECHARGE_TIMEOUT_MINUTES)
    qs = StoreRecharge.objects.filter(status=StoreRecharge.Status.PENDING, created_at__lt=cutoff)
    n = 0
    for item in qs:
        item.status = StoreRecharge.Status.CLOSED
        item.hold_key = None
        item.remark = item.remark or "超时未入账，已关闭"
        item.save(update_fields=["status", "hold_key", "remark", "updated_at"])
        n += 1
    return n


def _money_amount(raw) -> Decimal:
    amount = Decimal(str(raw)).quantize(Decimal("0.01"))
    if amount < RECHARGE_MIN_AMOUNT:
        raise RechargeError("充值金额至少 1 元")
    if amount > RECHARGE_MAX_AMOUNT:
        raise RechargeError(f"单笔充值不能超过 {RECHARGE_MAX_AMOUNT} 元")
    return amount


@transaction.atomic
def create_store_recharge(member: Member, amount, operator=None) -> StoreRecharge:
    expire_pending_recharges()
    amount = _money_amount(amount)
    try:
        return StoreRecharge.objects.create(
            recharge_no=gen_recharge_no(),
            member=member,
            amount=amount,
            status=StoreRecharge.Status.PENDING,
            created_by=operator,
            remark="会员自助充值",
        )
    except IntegrityError as exc:
        raise RechargeError("请先完成或等待上一笔充值") from exc


@transaction.atomic
def pay_store_recharge(recharge_obj: StoreRecharge, success: bool = True, operator=None) -> StoreRecharge:
    expire_pending_recharges()
    item = StoreRecharge.objects.select_for_update().select_related("member").get(pk=recharge_obj.pk)
    if item.status == StoreRecharge.Status.CLOSED:
        raise RechargeError("充值单已超时关闭")
    if item.status != StoreRecharge.Status.PENDING:
        raise RechargeError("仅待入账充值单可支付")
    if not success:
        item.trade_no = f"MOCK-RC-FAIL-{item.recharge_no}"
        item.remark = "模拟网关失败"
        item.save(update_fields=["trade_no", "remark", "updated_at"])
        return item
    recharge(item.member, item.amount, remark=f"自助充值 {item.recharge_no}")
    item.status = StoreRecharge.Status.SUCCESS
    item.hold_key = None
    item.trade_no = f"MOCK-RC-OK-{item.recharge_no}"
    item.paid_at = timezone.now()
    item.remark = "模拟网关成功"
    item.save(update_fields=["status", "hold_key", "trade_no", "paid_at", "remark", "updated_at"])
    return item
