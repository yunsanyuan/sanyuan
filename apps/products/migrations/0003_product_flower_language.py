from django.db import migrations, models

LANGUAGES = {
    "SKU-R12": "热恋与郑重的爱",
    "SKU-S08": "沉默的爱，向着光",
    "SKU-C11": "感恩与长久的惦记",
    "SKU-M16": "把不同的心意收成一束",
    "SKU-B10": "思念如星，细碎而长久",
    "SKU-W12": "纯净、敬重与新的开始",
    "SKU-T10": "高雅的告白",
    "SKU-L08": "百年好合，祝福安然",
    "SKU-H06": "希望与团圆",
    "SKU-P01": "把一小片绿意留给日常",
    "SKU-S03": "坚韧而温柔的陪伴",
    "SKU-A04": "坚毅生长，岁月悠长",
    "SKU-G07": "打开即是心意",
}


def fill_languages(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    for sku, text in LANGUAGES.items():
        Product.objects.filter(sku=sku).update(flower_language=text)


def unfill_languages(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    Product.objects.filter(sku__in=LANGUAGES).update(flower_language="")


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_seed_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="flower_language",
            field=models.CharField(blank=True, max_length=80, verbose_name="花语"),
        ),
        migrations.RunPython(fill_languages, unfill_languages),
    ]
