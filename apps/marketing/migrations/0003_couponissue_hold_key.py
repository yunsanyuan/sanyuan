from django.db import migrations, models


def fill_hold_keys(apps, schema_editor):
    CouponIssue = apps.get_model("marketing", "CouponIssue")
    seen = set()
    for issue in CouponIssue.objects.order_by("id"):
        if issue.member_id and issue.status in {"claimed", "used"}:
            key = f"{issue.coupon_id}:{issue.member_id}"
            if key in seen:
                issue.status = "expired"
                issue.hold_key = None
            else:
                seen.add(key)
                issue.hold_key = key
        else:
            issue.hold_key = None
        issue.save(update_fields=["status", "hold_key"])


def clear_hold_keys(apps, schema_editor):
    CouponIssue = apps.get_model("marketing", "CouponIssue")
    CouponIssue.objects.update(hold_key=None)


class Migration(migrations.Migration):
    dependencies = [
        ("marketing", "0002_seed_coupons"),
    ]

    operations = [
        migrations.AddField(
            model_name="couponissue",
            name="hold_key",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="已领取/已核销为 coupon_id:member_id；过期为空，MySQL 允许多个 NULL，过期后可再领。",
                max_length=64,
                null=True,
                verbose_name="在手占用键",
            ),
        ),
        migrations.RunPython(fill_hold_keys, clear_hold_keys),
        migrations.AddConstraint(
            model_name="couponissue",
            constraint=models.UniqueConstraint(fields=("hold_key",), name="uniq_coupon_issue_hold"),
        ),
    ]
