from django.contrib import admin, messages

from .models import CartItem, Order, OrderItem, OrderStatusLog, PaymentRecord
from .services import (
    OrderError,
    approve_cancel,
    cancel_order,
    complete_order,
    create_order_from_cart,
    pay_order,
    pickup_order,
    recalc_order,
    refund_order,
    reject_cancel,
    reserve_stock,
    ship_order,
)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("member", "product", "quantity", "updated_at")
    autocomplete_fields = ("member", "product")
    search_fields = ("member__user__username", "product__name")
    fieldsets = (("基本信息", {"fields": ("member", "product", "quantity")}),)
    actions = ("action_checkout",)

    @admin.action(description="从所选购物车生成待支付订单（按会员合并）")
    def action_checkout(self, request, queryset):
        member_ids = queryset.values_list("member_id", flat=True).distinct()
        count = 0
        for member_id in member_ids:
            member = queryset.filter(member_id=member_id).first().member
            try:
                order = create_order_from_cart(member, use_store=True, operator=request.user)
                self.message_user(request, f"{member} 已下单 {order.order_no}", messages.SUCCESS)
                count += 1
            except OrderError as exc:
                self.message_user(request, f"{member} 下单失败：{exc}", messages.ERROR)
        if count == 0:
            self.message_user(request, "没有成功生成的订单", messages.WARNING)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    autocomplete_fields = ("product",)
    fields = ("product", "product_name", "sku", "unit_price", "quantity", "subtotal")

    def _items_locked(self, obj):
        # 已预扣后改数量不会走库存差额；待支付一旦预扣，明细与已支付一样只读。
        return bool(obj and (obj.status != Order.Status.PENDING or obj.stock_reserved))

    def get_extra(self, request, obj=None, **kwargs):
        return 0 if self._items_locked(obj) else 1

    def get_readonly_fields(self, request, obj=None):
        if self._items_locked(obj):
            return self.fields
        return ()

    def has_add_permission(self, request, obj=None):
        if self._items_locked(obj):
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._items_locked(obj):
            return False
        return super().has_delete_permission(request, obj)


class OrderStatusLogInline(admin.TabularInline):
    model = OrderStatusLog
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "remark", "operator", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


class PaymentRecordInline(admin.TabularInline):
    model = PaymentRecord
    extra = 0
    can_delete = False
    readonly_fields = ("method", "amount", "status", "trade_no", "remark", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_no",
        "member",
        "status",
        "fulfillment",
        "payable_amount",
        "coupon_amount",
        "store_paid_amount",
        "gateway_paid_amount",
        "points_awarded",
        "created_at",
    )
    list_filter = ("status", "fulfillment")
    search_fields = ("order_no", "member__user__username")
    autocomplete_fields = ("member",)
    readonly_fields = (
        "order_no",
        "status",
        "goods_amount",
        "level_discount_amount",
        "coupon_amount",
        "payable_amount",
        "store_paid_amount",
        "gateway_paid_amount",
        "stock_reserved",
        "points_awarded",
        "fulfillment",
        "receiver_name",
        "receiver_phone",
        "address",
        "tracking_no",
        "shipped_at",
        "received_at",
        "paid_at",
        "created_at",
        "updated_at",
    )
    inlines = (OrderItemInline, PaymentRecordInline, OrderStatusLogInline)
    actions = (
        "action_pay_ok",
        "action_pay_fail",
        "action_cancel",
        "action_ship",
        "action_receive",
        "action_pickup",
        "action_approve_cancel",
        "action_reject_cancel",
        "action_refund",
        "action_best_coupon",
    )
    fieldsets = (
        ("基本信息", {"fields": ("order_no", "member", "status", "use_store", "remark", "created_by")}),
        (
            "金额",
            {
                "fields": (
                    "goods_amount",
                    "level_discount_amount",
                    "coupon_amount",
                    "payable_amount",
                    "store_paid_amount",
                    "gateway_paid_amount",
                )
            },
        ),
        (
            "履约",
            {
                "fields": (
                    "fulfillment",
                    "receiver_name",
                    "receiver_phone",
                    "address",
                    "tracking_no",
                    "shipped_at",
                    "received_at",
                    "stock_reserved",
                    "points_awarded",
                    "paid_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        if not obj.order_no:
            from .services import gen_order_no

            obj.order_no = gen_order_no()
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        order = form.instance
        if order.status != Order.Status.PENDING:
            return
        try:
            recalc_order(order)
            if order.items.exists() and not order.stock_reserved:
                reserve_stock(order)
        except OrderError as exc:
            self.message_user(request, str(exc), messages.ERROR)

    def get_actions(self, request):
        actions = super().get_actions(request)
        from apps.accounts.rbac import is_admin_user

        if not is_admin_user(request.user) and not request.user.has_perm("orders.refund_order"):
            actions.pop("action_refund", None)
        if not is_admin_user(request.user) and not request.user.has_perm("orders.review_cancel"):
            actions.pop("action_approve_cancel", None)
            actions.pop("action_reject_cancel", None)
        return actions

    def _run(self, request, queryset, func, label):
        for order in queryset:
            try:
                func(order, operator=request.user)
                self.message_user(request, f"{order.order_no} {label}成功", messages.SUCCESS)
            except OrderError as exc:
                self.message_user(request, f"{order.order_no}：{exc}", messages.ERROR)

    @admin.action(description="模拟支付成功")
    def action_pay_ok(self, request, queryset):
        self._run(request, queryset, lambda o, operator: pay_order(o, True, operator), "支付")

    @admin.action(description="模拟支付失败")
    def action_pay_fail(self, request, queryset):
        self._run(request, queryset, lambda o, operator: pay_order(o, False, operator), "模拟失败")

    @admin.action(description="取消待支付订单")
    def action_cancel(self, request, queryset):
        self._run(request, queryset, cancel_order, "取消")

    @admin.action(description="发货")
    def action_ship(self, request, queryset):
        self._run(request, queryset, ship_order, "发货")

    @admin.action(description="确认签收")
    def action_receive(self, request, queryset):
        self._run(request, queryset, lambda o, operator: complete_order(o, operator=operator), "签收")

    @admin.action(description="自提核销")
    def action_pickup(self, request, queryset):
        self._run(request, queryset, pickup_order, "自提核销")

    @admin.action(description="同意取消退款")
    def action_approve_cancel(self, request, queryset):
        from apps.accounts.rbac import is_admin_user

        if not is_admin_user(request.user) and not request.user.has_perm("orders.review_cancel"):
            self.message_user(request, "无权审核取消申请", messages.ERROR)
            return
        self._run(request, queryset, approve_cancel, "同意取消退款")

    @admin.action(description="驳回取消申请")
    def action_reject_cancel(self, request, queryset):
        from apps.accounts.rbac import is_admin_user

        if not is_admin_user(request.user) and not request.user.has_perm("orders.review_cancel"):
            self.message_user(request, "无权审核取消申请", messages.ERROR)
            return
        self._run(request, queryset, reject_cancel, "驳回取消申请")

    @admin.action(description="整单退款")
    def action_refund(self, request, queryset):
        from apps.accounts.rbac import is_admin_user

        if not is_admin_user(request.user) and not request.user.has_perm("orders.refund_order"):
            self.message_user(request, "店员无权退款，请联系管理员", messages.ERROR)
            return
        self._run(request, queryset, refund_order, "退款")

    @admin.action(description="选用最优可用优惠券并核销")
    def action_best_coupon(self, request, queryset):
        from apps.marketing.services import CouponError, redeem_on_order

        for order in queryset:
            if order.status != Order.Status.PENDING:
                self.message_user(request, f"{order.order_no} 非待支付，跳过", messages.WARNING)
                continue
            try:
                issue = redeem_on_order(order)
                if issue:
                    self.message_user(request, f"{order.order_no} 已用 {issue.coupon.name}", messages.SUCCESS)
                else:
                    self.message_user(request, f"{order.order_no} 无可用优惠券", messages.WARNING)
            except CouponError as exc:
                self.message_user(request, f"{order.order_no}：{exc}", messages.ERROR)


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ("trade_no", "order", "method", "amount", "status", "created_at")
    list_filter = ("method", "status")
    search_fields = ("trade_no", "order__order_no")
    readonly_fields = ("order", "method", "amount", "status", "trade_no", "remark", "created_at", "updated_at")
    fieldsets = (("基本信息", {"fields": readonly_fields}),)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
