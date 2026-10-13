from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.members.models import Member


class Coupon(TimeStampedModel):
    class Kind(models.TextChoices):
        AMOUNT = "amount", "满减"
        PERCENT = "percent", "折扣"

    name = models.CharField(max_length=64, verbose_name="名称")
    code = models.CharField(max_length=32, unique=True, verbose_name="券码")
    kind = models.CharField(max_length=16, choices=Kind.choices, verbose_name="类型")
    min_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="最低商品合计",
    )
    face_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="满减金额",
        help_text="满减券使用",
    )
    discount_rate = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="折扣率",
        help_text="折扣券使用，0.90 表示九折",
    )
    total_count = models.PositiveIntegerField(default=100, verbose_name="发放总量")
    per_user_limit = models.PositiveIntegerField(default=1, verbose_name="每人限领")
    valid_from = models.DateTimeField(verbose_name="生效时间")
    valid_to = models.DateTimeField(verbose_name="过期时间")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    description = models.CharField(max_length=200, blank=True, verbose_name="说明")

    class Meta:
        db_table = "marketing_coupon"
        ordering = ["-id"]
        verbose_name = "优惠券"
        verbose_name_plural = "优惠券"

    def __str__(self):
        return f"{self.name}({self.code})"

    @property
    def issued_count(self) -> int:
        return self.issues.exclude(status=CouponIssue.Status.EXPIRED).count()

    @property
    def remaining(self) -> int:
        return max(0, self.total_count - self.issued_count)

    def is_in_period(self, now=None) -> bool:
        now = now or timezone.now()
        return self.valid_from <= now <= self.valid_to

    @property
    def benefit_label(self) -> str:
        if self.kind == self.Kind.AMOUNT:
            return f"¥{self.face_value.quantize(Decimal('0.01'))}"
        zhe = self.discount_rate * Decimal("10")
        if zhe == zhe.to_integral_value():
            return f"{int(zhe)}折"
        return f"{zhe.normalize()}折"


class CouponIssue(TimeStampedModel):
    class Status(models.TextChoices):
        UNCLAIMED = "unclaimed", "未领取"
        CLAIMED = "claimed", "已领取"
        USED = "used", "已核销"
        EXPIRED = "expired", "已过期"

    class Source(models.TextChoices):
        CLAIM = "claim", "自行领取"
        ISSUE = "issue", "后台发放"

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        related_name="issues",
        verbose_name="优惠券",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="coupon_issues",
        verbose_name="会员",
    )
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_issue",
        verbose_name="核销订单",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.CLAIMED,
        verbose_name="状态",
    )
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.CLAIM,
        verbose_name="来源",
    )
    expire_at = models.DateTimeField(verbose_name="过期时间")
    claimed_at = models.DateTimeField(null=True, blank=True, verbose_name="领取时间")
    used_at = models.DateTimeField(null=True, blank=True, verbose_name="核销时间")
    hold_key = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        editable=False,
        verbose_name="在手占用键",
        help_text="已领取/已核销为 coupon_id:member_id；过期为空，MySQL 允许多个 NULL，过期后可再领。",
    )

    class Meta:
        db_table = "marketing_coupon_issue"
        ordering = ["-created_at"]
        verbose_name = "券发放/核销"
        verbose_name_plural = "券发放/核销"
        constraints = [
            models.UniqueConstraint(fields=["hold_key"], name="uniq_coupon_issue_hold"),
        ]

    def refresh_hold_key(self):
        if self.member_id and self.status in {self.Status.CLAIMED, self.Status.USED}:
            self.hold_key = f"{self.coupon_id}:{self.member_id}"
        else:
            self.hold_key = None

    def save(self, *args, **kwargs):
        self.refresh_hold_key()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {"hold_key"}
        super().save(*args, **kwargs)

    def __str__(self):
        owner = self.member or "未领取"
        return f"{self.coupon.code} / {owner} / {self.get_status_display()}"
