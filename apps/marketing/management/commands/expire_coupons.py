from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketing.services import expire_due_issues


class Command(BaseCommand):
    help = "将已到期未使用的优惠券标记为过期"

    def handle(self, *args, **options):
        n = expire_due_issues(timezone.now())
        self.stdout.write(self.style.SUCCESS(f"已过期 {n} 张"))
