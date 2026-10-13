from django.contrib import admin, messages
from django.template.response import TemplateResponse
from django.utils import timezone

from apps.members.models import Member

from .models import Coupon, CouponIssue
from .services import CouponError, expire_due_issues, issue_coupon


class CouponIssueInline(admin.TabularInline):
    model = CouponIssue
    extra = 0
    can_delete = False
    autocomplete_fields = ("member",)
    readonly_fields = ("member", "status", "source", "expire_at", "claimed_at", "used_at", "order")
    fields = readonly_fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "kind",
        "min_amount",
        "face_value",
        "discount_rate",
        "remaining_display",
        "valid_to",
        "is_active",
    )
    list_filter = ("kind", "is_active")
    search_fields = ("name", "code")
    inlines = (CouponIssueInline,)
    fieldsets = (
        (
            "基本信息",
            {
                "fields": (
                    "name",
                    "code",
                    "kind",
                    "min_amount",
                    "face_value",
                    "discount_rate",
                    "total_count",
                    "per_user_limit",
                    "valid_from",
                    "valid_to",
                    "is_active",
                    "description",
                )
            },
        ),
    )
    actions = ("action_issue_to_members", "action_issue_all_members", "action_expire")

    @admin.display(description="剩余")
    def remaining_display(self, obj):
        return f"{obj.remaining}/{obj.total_count}"

    def _issue_many(self, coupons, members):
        ok = skip = 0
        notes = []
        for coupon in coupons:
            for member in members:
                try:
                    issue_coupon(member, coupon)
                    ok += 1
                except CouponError as exc:
                    skip += 1
                    if len(notes) < 6:
                        notes.append(f"{member} / {coupon.name}：{exc}")
        return ok, skip, notes

    @admin.action(description="发放给指定会员")
    def action_issue_to_members(self, request, queryset):
        if request.POST.get("post") == "yes":
            members = Member.objects.filter(pk__in=request.POST.getlist("member_ids"))
            if not members:
                self.message_user(request, "请勾选至少一位会员", messages.WARNING)
                return None
            ok, skip, notes = self._issue_many(queryset, members)
            text = f"发放成功 {ok} 张，跳过 {skip} 张"
            if notes:
                text += "。" + "；".join(notes)
            self.message_user(request, text, messages.SUCCESS if ok else messages.WARNING)
            return None
        return TemplateResponse(
            request,
            "admin/marketing/issue_coupons.html",
            {
                **self.admin_site.each_context(request),
                "title": "发放优惠券给指定会员",
                "coupons": queryset,
                "members": Member.objects.select_related("user", "level").order_by("id"),
                "opts": self.model._meta,
                "action_name": "action_issue_to_members",
            },
        )

    @admin.action(description="发放给全部会员（受每人限领约束）")
    def action_issue_all_members(self, request, queryset):
        ok, skip, notes = self._issue_many(queryset, Member.objects.all())
        text = f"发放成功 {ok} 张，跳过 {skip} 张"
        if notes:
            text += "。" + "；".join(notes)
        self.message_user(request, text, messages.SUCCESS if ok else messages.WARNING)

    @admin.action(description="扫描并过期已到期未使用券")
    def action_expire(self, request, queryset):
        n = expire_due_issues(timezone.now())
        self.message_user(request, f"已过期 {n} 张领取记录", messages.SUCCESS)


@admin.register(CouponIssue)
class CouponIssueAdmin(admin.ModelAdmin):
    list_display = ("id", "coupon", "member", "status", "source", "order", "expire_at", "used_at")
    list_filter = ("status", "source")
    search_fields = ("coupon__code", "coupon__name", "member__user__username")
    autocomplete_fields = ("coupon", "member", "order")
    readonly_fields = (
        "coupon",
        "member",
        "order",
        "status",
        "source",
        "expire_at",
        "claimed_at",
        "used_at",
        "hold_key",
        "created_at",
        "updated_at",
    )
    fieldsets = (("基本信息", {"fields": readonly_fields}),)
    actions = ("action_expire",)

    def has_add_permission(self, request):
        return False

    @admin.action(description="过期扫描")
    def action_expire(self, request, queryset):
        n = expire_due_issues(timezone.now())
        self.message_user(request, f"已过期 {n} 张领取记录", messages.SUCCESS)
