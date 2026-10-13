from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_rbac(apps, schema_editor):
    from apps.accounts.rbac import apply_role, ensure_groups

    ensure_groups()
    User = apps.get_model("accounts", "User")
    if not User.objects.filter(username="staff").exists():
        staff = User(
            username="staff",
            role="staff",
            is_staff=True,
            is_superuser=False,
            is_active=True,
            email="staff@example.com",
        )
        staff.password = make_password("staff123456")
        staff.save()
    for user in User.objects.all():
        if user.is_superuser:
            user.role = "admin"
            user.is_staff = True
            user.save()
        apply_role(user)


def unseed_rbac(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(username="staff").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("members", "0002_seed_levels"),
        ("products", "0002_seed_catalog"),
        ("orders", "0002_order_permissions"),
        ("marketing", "0002_seed_coupons"),
    ]

    operations = [
        migrations.RunPython(seed_rbac, unseed_rbac),
    ]
