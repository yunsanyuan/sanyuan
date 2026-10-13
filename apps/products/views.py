from urllib.parse import quote, urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.cart import refresh_cart_count, safe_next_url
from apps.members.services import ensure_member_profile
from apps.orders.services import OrderError, add_to_cart, expire_pending_orders

from .models import Category, Product

SORTS = {
    "default": ("category__sort_order", "id"),
    "price": ("price", "id"),
    "price_desc": ("-price", "id"),
    "stock": ("stock", "id"),
}


def product_list(request):
    expire_pending_orders()
    qs = Product.objects.filter(is_on_sale=True, category__is_active=True).select_related("category")
    slug = request.GET.get("cat")
    q = (request.GET.get("q") or "").strip()
    sort = request.GET.get("sort") or "default"
    if slug:
        qs = qs.filter(category__slug=slug)
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(sku__icontains=q)
            | Q(flower_language__icontains=q)
            | Q(description__icontains=q)
        )
    qs = qs.order_by(*SORTS.get(sort, SORTS["default"]))
    page_obj = Paginator(qs, 12).get_page(request.GET.get("page"))
    params = {}
    if slug:
        params["cat"] = slug
    if q:
        params["q"] = q
    if sort and sort != "default":
        params["sort"] = sort
    params_all = {k: v for k, v in params.items() if k != "cat"}
    return render(
        request,
        "products/list.html",
        {
            "products": page_obj.object_list,
            "page_obj": page_obj,
            "categories": Category.objects.filter(is_active=True),
            "current_cat": slug,
            "q": q,
            "sort": sort,
            "query": urlencode(params),
            "query_all": urlencode(params_all),
            "result_count": page_obj.paginator.count,
        },
    )


def product_detail(request, pk):
    expire_pending_orders()
    product = get_object_or_404(
        Product.objects.select_related("category"),
        pk=pk,
        is_on_sale=True,
    )
    related = (
        Product.objects.filter(category=product.category, is_on_sale=True)
        .exclude(pk=product.pk)
        .select_related("category")[:4]
    )
    return render(request, "products/detail.html", {"product": product, "related": related})


@require_POST
def product_add_cart(request, pk):
    product = get_object_or_404(Product, pk=pk, is_on_sale=True)
    try:
        qty = int(request.POST.get("quantity") or 1)
    except (TypeError, ValueError):
        qty = 1
    qty = max(1, min(qty, 99))
    next_url = safe_next_url(request, request.POST.get("next"))
    if qty > product.stock:
        messages.error(request, f"{product.name} 库存不足（剩余 {product.stock}）")
        return redirect(next_url or "products:list")
    if not request.user.is_authenticated:
        request.session["pending_cart"] = {"pk": product.pk, "qty": qty, "next": next_url}
        after = next_url or reverse("products:detail", args=[product.pk])
        return redirect(f"{reverse('accounts:login')}?next={quote(after, safe='/')}")
    if getattr(request.user, "role", None) != request.user.Role.MEMBER:
        messages.error(request, "请使用会员账号访问商城功能")
        return redirect("/admin/")
    member = ensure_member_profile(request.user)
    if member is None:
        messages.error(request, "请使用会员账号访问商城功能")
        return redirect("accounts:login")
    try:
        add_to_cart(member, product, qty)
        refresh_cart_count(request, member)
        messages.success(request, f"已加入购物车：{product.name}")
    except OrderError as exc:
        messages.error(request, str(exc))
    return redirect(next_url or "products:list")
