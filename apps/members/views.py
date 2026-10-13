from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import member_required
from apps.core.templatetags.shop_extras import member_price
from apps.core.welcome import display_name, level_catalog, welcome_payload
from apps.marketing.models import Coupon, CouponIssue
from apps.marketing.services import CouponError, expire_due_issues, receive_coupon
from apps.orders.models import Order
from apps.orders.services import expire_pending_orders
from apps.products.models import Product

from .forms import MemberProfileForm
from .models import StoreRecharge
from .services import (
    RECHARGE_MAX_AMOUNT,
    RECHARGE_TIMEOUT_MINUTES,
    RechargeError,
    create_store_recharge,
    pay_store_recharge,
)

RECHARGE_PRESETS = ("50", "100", "200", "500", "1000", "2000")


@member_required
def center(request):
    expire_due_issues()
    expire_pending_orders()
    member = request.member
    orders = Order.objects.filter(member=member).prefetch_related("items__product")[:5]
    coupons = CouponIssue.objects.filter(member=member).select_related("coupon")[:8]
    catalog = level_catalog()
    actual = welcome_payload(request.user, with_progress=True)
    preview_code = (request.GET.get("preview") or "").strip()
    preview_item = next((item for item in catalog if item["code"] == preview_code), None)
    previewing = bool(preview_item) and preview_item["code"] != actual["level_code"]
    selected = preview_item or next((item for item in catalog if item["code"] == actual["level_code"]), None)
    display = actual
    if previewing and selected:
        display = {
            **actual,
            "title": f"预览{selected['name']}会员",
            "text": f"这是{selected['name']}会员的界面与礼遇，不影响您当前的{actual['level_name']}账户。",
            "level_code": selected["code"],
            "level_name": f"{selected['name']}会员",
            "badge_class": selected["badge_class"],
            "perk": selected["perk"],
            "progress": None,
        }
    sample = (
        Product.objects.filter(is_on_sale=True, category__is_active=True)
        .order_by("category__sort_order", "id")
        .first()
    )
    for item in catalog:
        item["is_mine"] = item["code"] == actual["level_code"]
        item["need_points"] = max(0, item["min_points"] - member.total_points)
        item["reached"] = member.total_points >= item["min_points"]
        item["gap_percent"] = (
            100
            if item["min_points"] <= 0
            else min(100, int(member.total_points * 100 / item["min_points"]))
        )
        item["sample_price"] = member_price(sample.price, item["discount_rate"]) if sample else None
        if item["is_mine"]:
            item["pane_title"] = actual["title"]
            item["pane_text"] = actual["text"]
        else:
            item["pane_title"] = f"{item['name']}会员长什么样"
            item["pane_text"] = (
                f"预览{item['name']}礼遇。您当前是{actual['level_name']}，"
                f"{display_name(request.user)}的积分与储值不会因此改变。"
            )
    return render(
        request,
        "members/center.html",
        {
            "member": member,
            "orders": orders,
            "coupons": coupons,
            "welcome": display,
            "actual_welcome": actual,
            "levels": catalog,
            "selected_level": selected,
            "previewing": previewing,
            "sample_product": sample,
        },
    )


@member_required
def coupon_list(request):
    expire_due_issues()
    mine = CouponIssue.objects.filter(member=request.member).select_related("coupon")
    available = Coupon.objects.filter(is_active=True)
    return render(request, "members/coupons.html", {"mine": mine, "available": available})


@member_required
@require_POST
def coupon_claim(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk, is_active=True)
    try:
        receive_coupon(request.member, coupon)
        messages.success(request, f"已领取 {coupon.name}")
    except CouponError as exc:
        messages.error(request, str(exc))
    return redirect("members:coupons")


@member_required
def profile(request):
    member = request.member
    initial = {
        "real_name": member.real_name,
        "phone": request.user.phone or "",
        "gender": member.gender,
        "birthday": member.birthday,
        "default_address": member.default_address,
    }
    if request.method == "POST":
        form = MemberProfileForm(request.POST, user=request.user, member=member)
        if form.is_valid():
            form.save()
            messages.success(request, "资料已更新")
            return redirect("members:profile")
    else:
        form = MemberProfileForm(initial=initial, user=request.user, member=member)
    return render(request, "members/profile.html", {"form": form, "member": member})


@member_required
def recharge_page(request):
    expire_pending_orders()
    member = request.member
    pending = StoreRecharge.objects.filter(member=member, status=StoreRecharge.Status.PENDING).first()
    if request.method == "POST" and not pending:
        raw = (request.POST.get("amount") or request.POST.get("preset") or "").strip()
        try:
            pending = create_store_recharge(member, raw, operator=request.user)
            messages.success(request, f"已生成充值单 {pending.recharge_no}")
            return redirect("members:recharge")
        except RechargeError as exc:
            messages.error(request, str(exc))
    expire_at = None
    if pending:
        expire_at = pending.created_at + timedelta(minutes=RECHARGE_TIMEOUT_MINUTES)
    return render(
        request,
        "members/recharge.html",
        {
            "member": member,
            "pending": pending,
            "presets": RECHARGE_PRESETS,
            "max_amount": RECHARGE_MAX_AMOUNT,
            "expire_at": expire_at,
        },
    )


@member_required
@require_POST
def recharge_pay(request, pk):
    item = get_object_or_404(StoreRecharge, pk=pk, member=request.member)
    success = request.POST.get("success") != "0"
    try:
        pay_store_recharge(item, success=success, operator=request.user)
        if success:
            messages.success(request, "储值已入账")
            return redirect("members:ledger")
        messages.warning(request, "模拟支付失败，充值单仍为待入账")
    except RechargeError as exc:
        messages.error(request, str(exc))
    return redirect("members:recharge")


@member_required
def ledger(request):
    member = request.member
    return render(
        request,
        "members/ledger.html",
        {
            "member": member,
            "points_records": member.points_records.all()[:50],
            "store_records": member.store_records.all()[:50],
        },
    )
