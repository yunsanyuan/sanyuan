from django.apps import AppConfig


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.members"
    label = "members"
    verbose_name = "会员"

    def ready(self):
        from . import signals  # noqa: F401
