from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .rbac import apply_role, ensure_groups

User = get_user_model()


@receiver(post_save, sender=User)
def sync_user_role(sender, instance, **kwargs):
    apply_role(instance)


@receiver(post_migrate)
def sync_rbac_after_migrate(sender, **kwargs):
    if getattr(sender, "label", "") != "dashboard":
        return
    ensure_groups()
    for user in User.objects.filter(role__in=["admin", "staff"]):
        apply_role(user)
