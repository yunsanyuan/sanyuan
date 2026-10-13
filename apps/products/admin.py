from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (("基本信息", {"fields": ("name", "slug", "sort_order", "is_active")}),)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "price", "stock", "is_on_sale", "thumb")
    list_filter = ("category", "is_on_sale")
    search_fields = ("name", "sku")
    list_editable = ("stock", "is_on_sale")
    autocomplete_fields = ("category",)
    readonly_fields = ("thumb",)
    fieldsets = (
        (
            "基本信息",
            {
                "fields": (
                    "category",
                    "name",
                    "sku",
                    ("price", "stock", "unit"),
                    "is_on_sale",
                    "image",
                    "thumb",
                    "flower_language",
                    "description",
                )
            },
        ),
    )

    @admin.display(description="图片")
    def thumb(self, obj):
        if not obj.image:
            return "-"
        return format_html('<img src="{}" style="height:40px;border-radius:4px;" />', obj.image.url)
