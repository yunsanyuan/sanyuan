from datetime import timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
import random

from django.db import transaction
from django.utils import timezone

from apps.members.models import PointsRecord, StoreRecord
from apps.members.services import apply_points, apply_store
from apps.products.models import Product

from .models import CartItem, Order, OrderItem, OrderStatusLog, PaymentRecord


class OrderError(Exception):
    pass


PENDING_TIMEOUT_MINUTES = 30


def pending_expire_at(order):
    return order.created_at + timedelta(minutes=PENDING_TIMEOUT_MINUTES)


def expire_pending_orders(now=None) -> int:
    """取消超时未支付订单，并关闭超时充值。访问首页、花市、订单或看板时扫描，不依赖定时任务。"""
    from apps.members.services import expire_pending_recharges

    now = now or timezone.now()
    expire_pending_recharges(now)
    cutoff = now - timedelta(minutes=PENDING_TIMEOUT_MINUTES)
    ids = list(
        Order.objects.filter(status=Order.Status.PENDING, created_at__lt=cutoff).values_list(
            "pk", flat=True
        )
    )
    cancelled = 0
    for pk in ids:
        try:
            cancel_order(Order.objects.get(pk=pk), remark="超时未支付，系统自动取消")
            cancelled += 1
        except (Order.DoesNotExist, OrderError):
            continue
    return cancelled


def gen_order_no() -> str:
    return timezone.now().strftime("FM%Y%m%d%H%M%S") + f"{random.randint(0, 999):03d}"


def _log_status(order: Order, to_status: str, remark: str = "", operator=None):
    OrderStatusLog.objects.create(
        order=order,
        from_status=order.status,
        to_status=to_status,
        remark=remark,
        operator=operator,
    )
    order.status = to_status
    order.save(update_fields=["status", "updated_at"])


def _money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_amounts(member, goods_amount: Decimal, coupon_amount: Decimal = Decimal("0.00")):
    goods_amount = _money(goods_amount)
    coupon_amount = _money(coupon_amount)
    rate = member.level.discount_rate
    discount = _money(goods_amount * (Decimal("1.00") - rate))
    payable = goods_amount - discount - coupon_amount
    if payable < 0:
        payable = Decimal("0.00")
    return goods_amount, discount, coupon_amount, payable


def snapshot_item(item: OrderItem):
    if item.product_id and item.product:
        item.product_name = item.product.name
        item.sku = item.product.sku
        if not item.unit_price:
            item.unit_price = item.product.price
        item.subtotal = _money(item.unit_price * item.quantity)
        item.save()


def recalc_order(order: Order):
    goods = Decimal("0.00")
    for item in order.items.all():
        snapshot_item(item)
        goods += item.subtotal
    goods, discount, coupon, payable = calculate_amounts(order.member, goods, order.coupon_amount)
    order.goods_amount = goods
    order.level_discount_amount = discount
    order.coupon_amount = coupon
    order.payable_amount = payable
    order.save(
        update_fields=[
            "goods_amount",
            "level_discount_amount",
            "coupon_amount",
            "payable_amount",
            "updated_at",
        ]
    )
    return order


def reserve_stock(order: Order):
    if order.stock_reserved:
        return
    for item in order.items.select_related("product"):
        if not item.product_id:
            raise OrderError(f"明细缺少商品：{item.product_name}")
        product = Product.objects.select_for_update().get(pk=item.product_id)
        if not product.is_on_sale:
            raise OrderError(f"{product.name} 已下架")
        if product.stock < item.quantity:
            raise OrderError(f"{product.name} 库存不足（剩余 {product.stock}）")
        product.stock -= item.quantity
        product.save(update_fields=["stock", "updated_at"])
    order.stock_reserved = True
    order.save(update_fields=["stock_reserved", "updated_at"])


def restore_stock(order: Order):
    if not order.stock_reserved:
        return
    for item in order.items.select_related("product"):
        if not item.product_id:
            continue
        product = Product.objects.select_for_update().get(pk=item.product_id)
        product.stock += item.quantity
        product.save(update_fields=["stock", "updated_at"])
    order.stock_reserved = False
    order.save(update_fields=["stock_reserved", "updated_at"])


def _assert_cart_qty(product: Product, quantity: int):
    if not product.is_on_sale:
        raise OrderError(f"{product.name} 已下架")
    if quantity > product.stock:
        raise OrderError(f"{product.name} 库存不足（剩余 {product.stock}）")


@transaction.atomic
def add_to_cart(member, product: Product, quantity: int = 1) -> CartItem:
    if quantity < 1:
        raise OrderError("数量至少为 1")
    locked = Product.objects.select_for_update().get(pk=product.pk)
    item = CartItem.objects.select_for_update().filter(member=member, product=locked).first()
    current = item.quantity if item else 0
    _assert_cart_qty(locked, current + quantity)
    if item is None:
        return CartItem.objects.create(member=member, product=locked, quantity=quantity)
    item.quantity = current + quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item


@transaction.atomic
def set_cart_quantity(member, product: Product, quantity: int) -> CartItem | None:
    if quantity <= 0:
        CartItem.objects.filter(member=member, product=product).delete()
        return None
    locked = Product.objects.select_for_update().get(pk=product.pk)
    _assert_cart_qty(locked, quantity)
    item, _ = CartItem.objects.select_for_update().get_or_create(
        member=member,
        product=locked,
        defaults={"quantity": quantity},
    )
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item


def _normalize_fulfillment(
    fulfillment: str | None,
    receiver_name: str = "",
    receiver_phone: str = "",
    address: str = "",
) -> dict:
    method = fulfillment or Order.Fulfillment.PICKUP
    if method not in {Order.Fulfillment.DELIVERY, Order.Fulfillment.PICKUP}:
        raise OrderError("履约方式无效")
    name = (receiver_name or "").strip()
    phone = (receiver_phone or "").strip()
    addr = (address or "").strip()
    if method == Order.Fulfillment.DELIVERY:
        if not name:
            raise OrderError("请填写收花人")
        if not phone:
            raise OrderError("请填写收花电话")
        if not addr:
            raise OrderError("请填写配送地址")
    return {
        "fulfillment": method,
        "receiver_name": name,
        "receiver_phone": phone,
        "address": addr,
    }


@transaction.atomic
def create_order_from_cart(
    member,
    use_store: bool = True,
    operator=None,
    coupon_issue=None,
    auto_coupon: bool = True,
    fulfillment: str | None = None,
    receiver_name: str = "",
    receiver_phone: str = "",
    address: str = "",
) -> Order:
    cart_qs = CartItem.objects.filter(member=member)
    product_ids = list(cart_qs.order_by("product_id").values_list("product_id", flat=True))
    if not product_ids:
        raise OrderError("购物车为空")
    list(Product.objects.select_for_update().filter(pk__in=product_ids).order_by("pk"))
    items = list(
        CartItem.objects.select_for_update()
        .select_related("product")
        .filter(member=member)
        .order_by("pk")
    )
    if not items:
        raise OrderError("购物车为空")
    snap = _normalize_fulfillment(fulfillment, receiver_name, receiver_phone, address)
    order = Order.objects.create(
        order_no=gen_order_no(),
        member=member,
        use_store=use_store,
        created_by=operator,
        status=Order.Status.PENDING,
        **snap,
    )
    for cart_item in items:
        product = cart_item.product
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            unit_price=product.price,
            quantity=cart_item.quantity,
            subtotal=_money(product.price * cart_item.quantity),
        )
    recalc_order(order)
    reserve_stock(order)
    from apps.marketing.services import CouponError, redeem_on_order

    try:
        if coupon_issue is not None or auto_coupon:
            redeem_on_order(order, coupon_issue)
    except CouponError as exc:
        raise OrderError(str(exc)) from exc
    _log_status(order, Order.Status.PENDING, remark="创建订单", operator=operator)
    CartItem.objects.filter(member=member).delete()
    return order


def pay_order(order: Order, success: bool = True, operator=None) -> Order:
    expire_pending_orders()
    return _pay_order(order, success=success, operator=operator)


@transaction.atomic
def _pay_order(order: Order, success: bool = True, operator=None) -> Order:
    order = Order.objects.select_for_update().select_related("member__level").get(pk=order.pk)
    if order.status == Order.Status.CANCELLED:
        raise OrderError("订单已超时未支付，已自动取消")
    if order.status != Order.Status.PENDING:
        raise OrderError("仅待支付订单可支付")
    if not order.stock_reserved:
        reserve_stock(order)

    if not success:
        PaymentRecord.objects.create(
            order=order,
            method=PaymentRecord.Method.MOCK_GATEWAY,
            amount=order.payable_amount,
            status=PaymentRecord.Status.FAILED,
            trade_no=f"MOCK-FAIL-{order.order_no}",
            remark="模拟网关失败",
        )
        return order

    payable = order.payable_amount
    store_pay = Decimal("0.00")
    member = order.member
    if order.use_store:
        balance = member.store_balance
        store_pay = min(balance, payable)
        if store_pay > 0:
            apply_store(
                member,
                -store_pay,
                StoreRecord.Kind.CONSUME,
                remark="订单储值抵扣",
                order_no=order.order_no,
            )
            PaymentRecord.objects.create(
                order=order,
                method=PaymentRecord.Method.STORE,
                amount=store_pay,
                status=PaymentRecord.Status.SUCCESS,
                trade_no=f"STORE-{order.order_no}",
                remark="储值抵扣",
            )

    gateway_pay = payable - store_pay
    if gateway_pay > 0:
        PaymentRecord.objects.create(
            order=order,
            method=PaymentRecord.Method.MOCK_GATEWAY,
            amount=gateway_pay,
            status=PaymentRecord.Status.SUCCESS,
            trade_no=f"MOCK-OK-{order.order_no}",
            remark="模拟网关成功",
        )

    order.store_paid_amount = store_pay
    order.gateway_paid_amount = gateway_pay
    order.paid_at = timezone.now()
    order.save(
        update_fields=["store_paid_amount", "gateway_paid_amount", "paid_at", "updated_at"]
    )

    multiplier = member.level.points_multiplier
    points = int((payable * multiplier).to_integral_value(rounding=ROUND_FLOOR))
    if points > 0:
        apply_points(
            member,
            points,
            PointsRecord.Source.ORDER_EARN,
            remark="消费获得积分",
            order_no=order.order_no,
        )
    order.points_awarded = points
    order.save(update_fields=["points_awarded", "updated_at"])
    _log_status(order, Order.Status.PAID, remark="支付成功", operator=operator)
    return order


@transaction.atomic
def cancel_order(order: Order, operator=None, remark: str = "取消订单") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PENDING:
        raise OrderError("仅待支付订单可取消")
    restore_stock(order)
    from apps.marketing.services import release_order_coupon

    release_order_coupon(order)
    _log_status(order, Order.Status.CANCELLED, remark=remark, operator=operator)
    return order


def gen_tracking_no(order: Order) -> str:
    tail = (order.order_no or "")[-8:]
    return f"FLW{tail}{random.randint(10, 99)}"


@transaction.atomic
def ship_order(order: Order, operator=None) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.Status.CANCEL_REQUESTED:
        raise OrderError("该单有取消申请，请先同意或驳回")
    if order.status != Order.Status.PAID:
        raise OrderError("仅已支付订单可发货")
    if order.fulfillment != Order.Fulfillment.DELIVERY:
        raise OrderError("自提单请走自提核销")
    if not (order.receiver_name and order.receiver_phone and order.address):
        raise OrderError("配送地址不完整，不能发货")
    now = timezone.now()
    order.tracking_no = order.tracking_no or gen_tracking_no(order)
    order.shipped_at = now
    order.save(update_fields=["tracking_no", "shipped_at", "updated_at"])
    _log_status(order, Order.Status.SHIPPED, remark="店员发货", operator=operator)
    return order


@transaction.atomic
def receive_order(order: Order, operator=None, remark: str = "确认签收") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.SHIPPED:
        raise OrderError("仅配送中订单可签收")
    order.received_at = timezone.now()
    order.save(update_fields=["received_at", "updated_at"])
    _log_status(order, Order.Status.COMPLETED, remark=remark, operator=operator)
    return order


@transaction.atomic
def pickup_order(order: Order, operator=None) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.Status.CANCEL_REQUESTED:
        raise OrderError("该单有取消申请，请先同意或驳回")
    if order.status != Order.Status.PAID:
        raise OrderError("仅已支付订单可自提核销")
    if order.fulfillment != Order.Fulfillment.PICKUP:
        raise OrderError("配送单请先发货再签收")
    now = timezone.now()
    order.received_at = now
    order.save(update_fields=["received_at", "updated_at"])
    _log_status(order, Order.Status.COMPLETED, remark="到店自提核销", operator=operator)
    return order


@transaction.atomic
def complete_order(order: Order, operator=None) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.Status.SHIPPED:
        return receive_order(order, operator=operator, remark="店员代签收")
    if order.status == Order.Status.PAID and order.fulfillment == Order.Fulfillment.PICKUP:
        return pickup_order(order, operator=operator)
    if order.status == Order.Status.PAID:
        raise OrderError("配送单请先发货")
    raise OrderError("当前状态不能签收或自提核销")


def cancel_unfulfilled_order(order: Order, operator=None, remark: str = "") -> Order:
    """会员取消：待支付直接取消；已支付未发货只提交审核，不立刻退款。"""
    current = Order.objects.only("status").get(pk=order.pk)
    if current.status == Order.Status.PENDING:
        return cancel_order(current, operator=operator, remark="取消订单")
    if current.status == Order.Status.PAID:
        return request_cancel(current, operator=operator, remark=remark)
    if current.status == Order.Status.CANCEL_REQUESTED:
        raise OrderError("已提交取消申请，请等待店员审核")
    raise OrderError("已发货或已签收不能取消，请联系管理员退款")


@transaction.atomic
def request_cancel(order: Order, operator=None, remark: str = "") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.PAID:
        raise OrderError("仅已支付未发货订单可申请取消")
    note = (remark or "").strip()[:80]
    _log_status(
        order,
        Order.Status.CANCEL_REQUESTED,
        remark=f"会员申请取消{('：' + note) if note else ''}",
        operator=operator,
    )
    return order


@transaction.atomic
def approve_cancel(order: Order, operator=None) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.CANCEL_REQUESTED:
        raise OrderError("仅待退款审核订单可同意")
    return refund_order(order, operator=operator, remark="审核同意，整单退款")


@transaction.atomic
def reject_cancel(order: Order, operator=None, remark: str = "") -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.CANCEL_REQUESTED:
        raise OrderError("仅待退款审核订单可驳回")
    note = (remark or "").strip()[:80]
    _log_status(
        order,
        Order.Status.PAID,
        remark=f"驳回取消申请{('：' + note) if note else ''}",
        operator=operator,
    )
    return order


@transaction.atomic
def withdraw_cancel(order: Order, operator=None) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != Order.Status.CANCEL_REQUESTED:
        raise OrderError("当前没有待审核的取消申请")
    _log_status(order, Order.Status.PAID, remark="会员撤回取消申请", operator=operator)
    return order


@transaction.atomic
def refund_order(order: Order, operator=None, remark: str = "整单退款") -> Order:
    order = Order.objects.select_for_update().select_related("member").get(pk=order.pk)
    if order.status not in {
        Order.Status.PAID,
        Order.Status.CANCEL_REQUESTED,
        Order.Status.SHIPPED,
        Order.Status.COMPLETED,
    }:
        raise OrderError("仅已支付、待退款审核、配送中或已签收订单可退款")
    restore_stock(order)
    if order.store_paid_amount > 0:
        apply_store(
            order.member,
            order.store_paid_amount,
            StoreRecord.Kind.REFUND,
            remark="订单退款回补储值",
            order_no=order.order_no,
        )
    if order.points_awarded > 0:
        apply_points(
            order.member,
            -int(order.points_awarded),
            PointsRecord.Source.ORDER_REFUND,
            remark="退款扣回积分",
            order_no=order.order_no,
        )
    _log_status(order, Order.Status.REFUNDED, remark=remark, operator=operator)
    return order
