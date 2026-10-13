from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.services import expire_pending_orders


class Command(BaseCommand):
    help = "将超时未支付的待支付订单自动取消（回库存、退券）"

    def handle(self, *args, **options):
        n = expire_pending_orders(timezone.now())
        self.stdout.write(self.style.SUCCESS(f"已超时取消 {n} 笔"))
