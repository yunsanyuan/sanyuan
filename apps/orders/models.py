from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.members.models import Member
from apps.products.models import Product


class CartItem(TimeStampedModel):
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="会员",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="商品",
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="数量")

    class Meta:
        db_table = "order_cart"
        constraints = [
            models.UniqueConstraint(fields=["member", "product"], name="uniq_cart_member_product"),
        ]
        verbose_name = "购物车"
        verbose_name_plural = "购物车"

    def __str__(self):
        return f"{self.member} / {self.product} x{self.quantity}"

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待支付"
        PAID = "paid", "已支付"
        CANCEL_REQUESTED = "cancel_requested", "待退款审核"
        SHIPPED = "shipped", "配送中"
        CANCELLED = "cancelled", "已取消"
        COMPLETED = "completed", "已签收"
        REFUNDED = "refunded", "已退款"

    class Fulfillment(models.TextChoices):
        DELIVERY = "delivery", "送花上门"
        PICKUP = "pickup", "到店自提"

    order_no = models.CharField(max_length=32, unique=True, verbose_name="订单号")
    member = models.ForeignKey(
        Member,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="会员",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="状态",
    )
    goods_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="商品合计"
    )
    level_discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="等级折扣"
    )
    coupon_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="优惠券抵扣"
    )
    payable_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="应付金额"
    )
    store_paid_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="储值支付"
    )
    gateway_paid_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="模拟网关支付"
    )
    use_store = models.BooleanField(default=True, verbose_name="优先使用储值")
    fulfillment = models.CharField(
        max_length=16,
        choices=Fulfillment.choices,
        default=Fulfillment.DELIVERY,
        verbose_name="履约方式",
    )
    receiver_name = models.CharField(max_length=32, blank=True, verbose_name="收花人")
    receiver_phone = models.CharField(max_length=20, blank=True, verbose_name="收花电话")
    address = models.CharField(max_length=200, blank=True, verbose_name="配送地址")
    tracking_no = models.CharField(max_length=32, blank=True, verbose_name="运单号")
    shipped_at = models.DateTimeField(null=True, blank=True, verbose_name="发货时间")
    received_at = models.DateTimeField(null=True, blank=True, verbose_name="签收时间")
    stock_reserved = models.BooleanField(default=False, verbose_name="已预扣库存")
    points_awarded = models.PositiveIntegerField(default=0, verbose_name="发放积分")
    remark = models.CharField(max_length=200, blank=True, verbose_name="备注")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="支付时间")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_orders",
        verbose_name="创建人",
    )

    class Meta:
        db_table = "order_order"
        ordering = ["-created_at"]
        verbose_name = "订单"
        verbose_name_plural = "订单"
        indexes = [
            models.Index(fields=["status"], name="order_status_idx"),
            models.Index(fields=["paid_at"], name="order_paid_at_idx"),
            models.Index(fields=["fulfillment"], name="order_fulfillment_idx"),
        ]
        permissions = [
            ("pay_order", "可以收银/模拟支付"),
            ("refund_order", "可以整单退款"),
            ("ship_order", "可以发货"),
            ("receive_order", "可以签收或自提核销"),
            ("review_cancel", "可以审核取消退款申请"),
        ]

    def __str__(self):
        return self.order_no

    @property
    def actual_paid_amount(self):
        return self.store_paid_amount + self.gateway_paid_amount


class OrderItem(TimeStampedModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="订单",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name="商品",
    )
    product_name = models.CharField(max_length=80, verbose_name="商品名称快照")
    sku = models.CharField(max_length=32, blank=True, verbose_name="SKU快照")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="单价快照")
    quantity = models.PositiveIntegerField(verbose_name="数量")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="小计")

    class Meta:
        db_table = "order_order_item"
        verbose_name = "订单明细"
        verbose_name_plural = "订单明细"

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class OrderStatusLog(TimeStampedModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_logs",
        verbose_name="订单",
    )
    from_status = models.CharField(max_length=16, blank=True, verbose_name="原状态")
    to_status = models.CharField(max_length=16, verbose_name="新状态")
    remark = models.CharField(max_length=200, blank=True, verbose_name="说明")
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人",
    )

    class Meta:
        db_table = "order_status_log"
        ordering = ["-created_at"]
        verbose_name = "订单状态记录"
        verbose_name_plural = "订单状态记录"

    def __str__(self):
        return f"{self.order} {self.from_status}->{self.to_status}"


class PaymentRecord(TimeStampedModel):
    class Method(models.TextChoices):
        STORE = "store", "储值"
        MOCK_GATEWAY = "mock_gateway", "模拟网关"

    class Status(models.TextChoices):
        SUCCESS = "success", "成功"
        FAILED = "failed", "失败"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="订单",
    )
    method = models.CharField(max_length=16, choices=Method.choices, verbose_name="方式")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="金额")
    status = models.CharField(max_length=16, choices=Status.choices, verbose_name="结果")
    trade_no = models.CharField(max_length=64, blank=True, verbose_name="流水号")
    remark = models.CharField(max_length=200, blank=True, verbose_name="备注")

    class Meta:
        db_table = "order_payment"
        ordering = ["-created_at"]
        verbose_name = "支付流水"
        verbose_name_plural = "支付流水"

    def __str__(self):
        return f"{self.order.order_no} {self.method} {self.status}"
