from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import ensure_member_profile

User = get_user_model()


@receiver(post_save, sender=User)
def create_member_profile(sender, instance, **kwargs):
    ensure_member_profile(instance)
