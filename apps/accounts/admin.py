from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from .models import User
from .rbac import is_admin_user


def _named_fieldsets(fieldsets, untitled="基本信息"):
    return tuple((untitled if name is None else name, opts) for name, opts in fieldsets)


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(DjangoGroupAdmin):
    fieldsets = (
        ("基本信息", {"fields": ("name",)}),
        ("权限", {"fields": ("permissions",)}),
    )


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "role", "phone", "email", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "phone", "email")
    fieldsets = _named_fieldsets(DjangoUserAdmin.fieldsets) + (("业务信息", {"fields": ("role", "phone")}),)
    add_fieldsets = _named_fieldsets(DjangoUserAdmin.add_fieldsets) + (("业务信息", {"fields": ("role", "phone")}),)

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_add_permission(self, request):
        return is_admin_user(request.user)

    def has_change_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_user(request.user)
