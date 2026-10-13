from django.shortcuts import render

from apps.orders.services import expire_pending_orders
from apps.products.models import Category, Product


def home(request):
    expire_pending_orders()
    products = list(
        Product.objects.filter(is_on_sale=True, category__is_active=True)
        .select_related("category")
        .order_by("category__sort_order", "id")[:8]
    )
    categories = list(Category.objects.filter(is_active=True))
    covers = {}
    for product in Product.objects.filter(
        is_on_sale=True, category__is_active=True
    ).exclude(image="").order_by("category__sort_order", "id"):
        if product.category_id not in covers:
            covers[product.category_id] = product
    for category in categories:
        category.cover = covers.get(category.id)
    return render(
        request,
        "home.html",
        {
            "products": products,
            "categories": categories,
            "hero_product": products[0] if products else None,
        },
    )
