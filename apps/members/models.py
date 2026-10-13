from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class MemberLevel(TimeStampedModel):
    code = models.CharField(max_length=32, unique=True, verbose_name="编码")
    name = models.CharField(max_length=32, verbose_name="名称")
    min_points = models.PositiveIntegerField(verbose_name="升级所需累计积分")
    discount_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="折扣（1.00=无折扣）",
    )
    points_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="积分倍率",
    )
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="排序")

    class Meta:
        db_table = "member_level"
        ordering = ["sort_order", "min_points"]
        verbose_name = "会员等级"
        verbose_name_plural = "会员等级"

    def __str__(self):
        return self.name

    @classmethod
    def for_points(cls, total_points: int) -> "MemberLevel | None":
        return (
            cls.objects.filter(min_points__lte=total_points)
            .order_by("-min_points")
            .first()
        )


class Member(TimeStampedModel):
    class Gender(models.TextChoices):
        UNKNOWN = "unknown", "未知"
        MALE = "male", "男"
        FEMALE = "female", "女"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        verbose_name="账号",
    )
    level = models.ForeignKey(
        MemberLevel,
        on_delete=models.PROTECT,
        related_name="members",
        verbose_name="等级",
    )
    real_name = models.CharField(max_length=32, blank=True, verbose_name="姓名")
    gender = models.CharField(
        max_length=16,
        choices=Gender.choices,
        default=Gender.UNKNOWN,
        verbose_name="性别",
    )
    birthday = models.DateField(null=True, blank=True, verbose_name="生日")
    default_address = models.CharField(max_length=200, blank=True, verbose_name="默认地址")
    remark = models.CharField(max_length=200, blank=True, verbose_name="备注")
    current_points = models.PositiveIntegerField(default=0, verbose_name="当前积分")
    total_points = models.PositiveIntegerField(default=0, verbose_name="累计积分")

    class Meta:
        db_table = "member_member"
        verbose_name = "会员"
        verbose_name_plural = "会员"

    def __str__(self):
        return self.real_name or self.user.username

    @property
    def store_balance(self):
        account = getattr(self, "store_account", None)
        return account.balance if account else Decimal("0.00")


class PointsRecord(TimeStampedModel):
    class Source(models.TextChoices):
        ORDER_EARN = "order_earn", "消费获得"
        ORDER_REFUND = "order_refund", "退款扣回"
        MANUAL = "manual", "人工调整"
        REGISTER = "register", "注册赠送"

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="points_records",
        verbose_name="会员",
    )
    delta = models.IntegerField(verbose_name="变动积分")
    balance_after = models.PositiveIntegerField(verbose_name="变动后积分")
    source = models.CharField(max_length=32, choices=Source.choices, verbose_name="来源")
    order_no = models.CharField(max_length=32, blank=True, verbose_name="关联订单号")
    remark = models.CharField(max_length=200, blank=True, verbose_name="备注")

    class Meta:
        db_table = "member_points_record"
        ordering = ["-created_at"]
        verbose_name = "积分流水"
        verbose_name_plural = "积分流水"

    def __str__(self):
        sign = "+" if self.delta >= 0 else ""
        return f"{self.member} {sign}{self.delta}"


class StoreAccount(TimeStampedModel):
    member = models.OneToOneField(
        Member,
        on_delete=models.CASCADE,
        related_name="store_account",
        verbose_name="会员",
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="余额",
    )

    class Meta:
        db_table = "member_store_value"
        verbose_name = "储值账户"
        verbose_name_plural = "储值账户"

    def __str__(self):
        return f"{self.member} ¥{self.balance}"


class StoreRecord(TimeStampedModel):
    class Kind(models.TextChoices):
        RECHARGE = "recharge", "充值"
        CONSUME = "consume", "消费抵扣"
        REFUND = "refund", "退款回补"
        MANUAL = "manual", "人工调整"

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="store_records",
        verbose_name="会员",
    )
    delta = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="变动金额")
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="变动后余额",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, verbose_name="类型")
    order_no = models.CharField(max_length=32, blank=True, verbose_name="关联订单号")
    remark = models.CharField(max_length=200, blank=True, verbose_name="备注")

    class Meta:
        db_table = "member_store_record"
        ordering = ["-created_at"]
        verbose_name = "储值流水"
        verbose_name_plural = "储值流水"

    def __str__(self):
        return f"{self.member} {self.delta}"


class StoreRecharge(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待入账"
        SUCCESS = "success", "已入账"
        CLOSED = "closed", "已关闭"

    recharge_no = models.CharField(max_length=32, unique=True, verbose_name="充值单号")
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="store_recharges",
        verbose_name="会员",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="金额")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="状态",
    )
    hold_key = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        editable=False,
        verbose_name="在手占用键",
    )
    trade_no = models.CharField(max_length=64, blank=True, verbose_name="模拟流水号")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="入账时间")
    remark = models.CharField(max_length=200, blank=True, verbose_name="备注")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_recharges",
        verbose_name="创建人",
    )

    class Meta:
        db_table = "member_store_recharge"
        ordering = ["-created_at"]
        verbose_name = "储值充值单"
        verbose_name_plural = "储值充值单"
        constraints = [
            models.UniqueConstraint(fields=["hold_key"], name="uniq_store_recharge_hold"),
        ]

    def refresh_hold_key(self):
        if self.status == self.Status.PENDING and self.member_id:
            self.hold_key = str(self.member_id)
        else:
            self.hold_key = None

    def save(self, *args, **kwargs):
        self.refresh_hold_key()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"hold_key"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.recharge_no} / {self.member} / {self.get_status_display()}"
