from datetime import timedelta
from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def seed_coupons(apps, schema_editor):
    Coupon = apps.get_model("marketing", "Coupon")
    now = timezone.now()
    Coupon.objects.update_or_create(
        code="FULL100-10",
        defaults={
            "name": "满100减10",
            "kind": "amount",
            "min_amount": Decimal("100.00"),
            "face_value": Decimal("10.00"),
            "discount_rate": Decimal("1.00"),
            "total_count": 200,
            "per_user_limit": 1,
            "valid_from": now - timedelta(days=1),
            "valid_to": now + timedelta(days=365),
            "is_active": True,
            "description": "商品合计满 100 元减 10 元",
        },
    )
    Coupon.objects.update_or_create(
        code="OFF10-50",
        defaults={
            "name": "满50打九折",
            "kind": "percent",
            "min_amount": Decimal("50.00"),
            "face_value": Decimal("0.00"),
            "discount_rate": Decimal("0.90"),
            "total_count": 200,
            "per_user_limit": 1,
            "valid_from": now - timedelta(days=1),
            "valid_to": now + timedelta(days=365),
            "is_active": True,
            "description": "商品合计满 50 元享九折（在等级折扣后计算）",
        },
    )


def unseed_coupons(apps, schema_editor):
    Coupon = apps.get_model("marketing", "Coupon")
    Coupon.objects.filter(code__in=["FULL100-10", "OFF10-50"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_coupons, unseed_coupons),
    ]
