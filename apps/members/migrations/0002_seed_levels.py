from decimal import Decimal

from django.db import migrations


LEVELS = [
    {
        "code": "normal",
        "name": "普通",
        "min_points": 0,
        "discount_rate": Decimal("1.00"),
        "points_multiplier": Decimal("1.00"),
        "sort_order": 0,
    },
    {
        "code": "silver",
        "name": "银卡",
        "min_points": 1000,
        "discount_rate": Decimal("0.98"),
        "points_multiplier": Decimal("1.10"),
        "sort_order": 1,
    },
    {
        "code": "gold",
        "name": "金卡",
        "min_points": 5000,
        "discount_rate": Decimal("0.95"),
        "points_multiplier": Decimal("1.20"),
        "sort_order": 2,
    },
    {
        "code": "diamond",
        "name": "钻石",
        "min_points": 10000,
        "discount_rate": Decimal("0.92"),
        "points_multiplier": Decimal("1.50"),
        "sort_order": 3,
    },
]


def seed_levels(apps, schema_editor):
    MemberLevel = apps.get_model("members", "MemberLevel")
    for item in LEVELS:
        MemberLevel.objects.update_or_create(code=item["code"], defaults=item)


def unseed_levels(apps, schema_editor):
    MemberLevel = apps.get_model("members", "MemberLevel")
    MemberLevel.objects.filter(code__in=[item["code"] for item in LEVELS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_levels, unseed_levels),
    ]
