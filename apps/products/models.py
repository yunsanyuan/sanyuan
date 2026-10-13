from django.db import models
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField(max_length=32, unique=True, verbose_name="分类名称")
    slug = models.SlugField(max_length=64, unique=True, blank=True, allow_unicode=True, verbose_name="标识")
    sort_order = models.PositiveSmallIntegerField(default=0, verbose_name="排序")
    is_active = models.BooleanField(default=True, verbose_name="启用")

    class Meta:
        db_table = "product_category"
        ordering = ["sort_order", "id"]
        verbose_name = "商品分类"
        verbose_name_plural = "商品分类"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.slug:
            super().save(*args, **kwargs)
            return
        super().save(*args, **kwargs)
        self.slug = slugify(self.name, allow_unicode=True) or f"cat-{self.pk}"
        super().save(update_fields=["slug"])


class Product(TimeStampedModel):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="分类",
    )
    name = models.CharField(max_length=80, verbose_name="商品名称")
    sku = models.CharField(max_length=32, unique=True, verbose_name="SKU")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="售价")
    stock = models.PositiveIntegerField(default=0, verbose_name="库存")
    unit = models.CharField(max_length=16, default="束", verbose_name="单位")
    image = models.ImageField(upload_to="products/", blank=True, verbose_name="图片")
    description = models.TextField(blank=True, verbose_name="描述")
    flower_language = models.CharField(max_length=80, blank=True, verbose_name="花语")
    is_on_sale = models.BooleanField(default=True, verbose_name="上架")

    class Meta:
        db_table = "product_product"
        ordering = ["-id"]
        verbose_name = "商品"
        verbose_name_plural = "商品"

    def __str__(self):
        return self.name
