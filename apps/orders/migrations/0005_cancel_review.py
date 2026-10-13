from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_fulfillment_and_store_recharge"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="order",
            options={
                "ordering": ["-created_at"],
                "permissions": [
                    ("pay_order", "可以收银/模拟支付"),
                    ("refund_order", "可以整单退款"),
                    ("ship_order", "可以发货"),
                    ("receive_order", "可以签收或自提核销"),
                    ("review_cancel", "可以审核取消退款申请"),
                ],
                "verbose_name": "订单",
                "verbose_name_plural": "订单",
            },
        ),
    ]
