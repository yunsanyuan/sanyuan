from decimal import Decimal

from django.db import migrations


def seed_catalog(apps, schema_editor):
    Category = apps.get_model("products", "Category")
    Product = apps.get_model("products", "Product")
    bouquet, _ = Category.objects.get_or_create(
        slug="bouquet",
        defaults={"name": "花束", "sort_order": 0, "is_active": True},
    )
    green, _ = Category.objects.get_or_create(
        slug="green",
        defaults={"name": "绿植", "sort_order": 1, "is_active": True},
    )
    items = [
        ("bouquet", "红玫瑰花束", "SKU-R12", Decimal("128.00"), 30, "12 枝红玫瑰，适合纪念日。"),
        ("bouquet", "向日葵花束", "SKU-S08", Decimal("88.00"), 20, "8 枝向日葵，明亮治愈。"),
        ("green", "小型观叶盆栽", "SKU-P01", Decimal("56.00"), 15, "桌面绿植，易养护。"),
    ]
    cats = {"bouquet": bouquet, "green": green}
    for cat_key, name, sku, price, stock, desc in items:
        Product.objects.update_or_create(
            sku=sku,
            defaults={
                "category": cats[cat_key],
                "name": name,
                "price": price,
                "stock": stock,
                "description": desc,
                "is_on_sale": True,
            },
        )


def unseed_catalog(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Category = apps.get_model("products", "Category")
    Product.objects.filter(sku__in=["SKU-R12", "SKU-S08", "SKU-P01"]).delete()
    Category.objects.filter(slug__in=["bouquet", "green"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_catalog, unseed_catalog),
    ]
