from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.cart import refresh_cart_count
from apps.core.decorators import member_required
from apps.marketing.models import CouponIssue
from apps.marketing.services import expire_due_issues
from apps.orders.services import (
    OrderError,
    calculate_amounts,
    cancel_unfulfilled_order,
    create_order_from_cart,
    withdraw_cancel,
    expire_pending_orders,
    pay_order,
    pending_expire_at,
    receive_order,
    set_cart_quantity,
)

from .models import CartItem, Order


@member_required
def cart_view(request):
    items = CartItem.objects.filter(member=request.member).select_related("product", "product__category")
    goods = sum((item.subtotal for item in items), Decimal("0.00"))
    _, discount, _, payable = calculate_amounts(request.member, goods)
    return render(
        request,
        "orders/cart.html",
        {"items": items, "goods": goods, "discount": discount, "payable": payable},
    )


@member_required
@require_POST
def cart_update(request, pk):
    item = get_object_or_404(CartItem, pk=pk, member=request.member)
    try:
        qty = int(request.POST.get("quantity") or 0)
    except (TypeError, ValueError):
        qty = item.quantity
    try:
        set_cart_quantity(request.member, item.product, max(0, qty))
        refresh_cart_count(request, request.member)
        messages.success(request, "购物车已更新")
    except OrderError as exc:
        messages.error(request, str(exc))
    return redirect("orders:cart")


@member_required
def checkout(request):
    items = list(CartItem.objects.filter(member=request.member).select_related("product"))
    if not items:
        messages.error(request, "购物车为空")
        return redirect("orders:cart")
    expire_due_issues()
    expire_pending_orders()
    coupons = CouponIssue.objects.filter(
        member=request.member, status=CouponIssue.Status.CLAIMED
    ).select_related("coupon")
    goods = sum((item.subtotal for item in items), Decimal("0.00"))
    _, discount, _, payable = calculate_amounts(request.member, goods)
    if request.method == "POST":
        use_store = request.POST.get("use_store") == "1"
        raw = request.POST.get("coupon_issue") or "auto"
        auto_coupon = raw == "auto"
        coupon_issue = None
        if raw not in {"auto", "none"}:
            coupon_issue = get_object_or_404(
                CouponIssue, pk=raw, member=request.member, status=CouponIssue.Status.CLAIMED
            )
            auto_coupon = False
        elif raw == "none":
            auto_coupon = False
        try:
            order = create_order_from_cart(
                request.member,
                use_store=use_store,
                operator=request.user,
                coupon_issue=coupon_issue,
                auto_coupon=auto_coupon,
                fulfillment=request.POST.get("fulfillment") or "delivery",
                receiver_name=request.POST.get("receiver_name") or "",
                receiver_phone=request.POST.get("receiver_phone") or "",
                address=request.POST.get("address") or "",
            )
            refresh_cart_count(request, request.member)
            messages.success(request, f"已生成订单 {order.order_no}")
            return redirect("orders:detail", pk=order.pk)
        except OrderError as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "orders/checkout.html",
        {
            "items": items,
            "goods": goods,
            "discount": discount,
            "payable": payable,
            "coupons": coupons,
            "store_balance": request.member.store_balance,
            "receiver_name": request.member.real_name,
            "receiver_phone": request.user.phone or "",
            "address": request.member.default_address,
        },
    )


@member_required
def order_list(request):
    expire_pending_orders()
    orders = Order.objects.filter(member=request.member).prefetch_related("items__product")
    return render(request, "orders/list.html", {"orders": orders})


@member_required
def order_detail(request, pk):
    expire_pending_orders()
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product", "payments", "status_logs"),
        pk=pk,
        member=request.member,
    )
    expire_at = pending_expire_at(order) if order.status == Order.Status.PENDING else None
    return render(request, "orders/detail.html", {"order": order, "expire_at": expire_at})


@member_required
@require_POST
def order_pay(request, pk):
    order = get_object_or_404(Order, pk=pk, member=request.member)
    success = request.POST.get("success") != "0"
    try:
        pay_order(order, success=success, operator=request.user)
        if success:
            messages.success(request, "模拟支付成功")
        else:
            messages.warning(request, "模拟支付失败，订单仍为待支付")
    except OrderError as exc:
        messages.error(request, str(exc))
    return redirect("orders:detail", pk=order.pk)


@member_required
@require_POST
def order_receive(request, pk):
    order = get_object_or_404(Order, pk=pk, member=request.member)
    try:
        receive_order(order, operator=request.user)
        messages.success(request, "已确认签收")
    except OrderError as exc:
        messages.error(request, str(exc))
    return redirect("orders:detail", pk=order.pk)


@member_required
@require_POST
def order_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk, member=request.member)
    try:
        order = cancel_unfulfilled_order(
            order, operator=request.user, remark=request.POST.get("remark") or ""
        )
        if order.status == Order.Status.CANCEL_REQUESTED:
            messages.success(request, "已提交取消申请，等待店员或管理员审核。通过后才会退回储值与积分，券不退。")
        else:
            messages.success(request, "订单已取消")
    except OrderError as exc:
        messages.error(request, str(exc))
    return redirect("orders:detail", pk=order.pk)


@member_required
@require_POST
def order_withdraw_cancel(request, pk):
    order = get_object_or_404(Order, pk=pk, member=request.member)
    try:
        withdraw_cancel(order, operator=request.user)
        messages.success(request, "已撤回取消申请，订单继续履约")
    except OrderError as exc:
        messages.error(request, str(exc))
    return redirect("orders:detail", pk=order.pk)
