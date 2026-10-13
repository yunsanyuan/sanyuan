from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html

from apps.marketing.models import Coupon
from apps.marketing.services import CouponError, issue_coupon

from apps.accounts.rbac import is_admin_user

from .models import Member, MemberLevel, PointsRecord, StoreAccount, StoreRecharge, StoreRecord
from .services import InsufficientBalance, RechargeError, apply_points, pay_store_recharge, recharge


@admin.register(MemberLevel)
class MemberLevelAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "min_points", "discount_rate", "points_multiplier", "sort_order")
    search_fields = ("name", "code")
    ordering = ("sort_order",)
    fieldsets = (
        (
            "基本信息",
            {"fields": ("code", "name", "min_points", "discount_rate", "points_multiplier", "sort_order")},
        ),
    )


class MemberAdminForm(forms.ModelForm):
    recharge_amount = forms.DecimalField(
        required=False,
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=12,
        label="储值充值金额",
        help_text="填写正数后保存即入账并写流水，可留空。",
    )
    points_delta = forms.IntegerField(
        required=False,
        label="积分调整",
        help_text="正数增加、负数扣减，保存后写流水并自动升降级。可留空。",
    )
    adjust_remark = forms.CharField(required=False, max_length=200, label="调整备注")

    class Meta:
        model = Member
        fields = "__all__"


class PointsRecordInline(admin.TabularInline):
    model = PointsRecord
    extra = 0
    can_delete = False
    readonly_fields = ("delta", "balance_after", "source", "order_no", "remark", "created_at")
    fields = readonly_fields
    ordering = ("-created_at",)
    max_num = 0
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


class StoreRecordInline(admin.TabularInline):
    model = StoreRecord
    extra = 0
    can_delete = False
    readonly_fields = ("delta", "balance_after", "kind", "order_no", "remark", "created_at")
    fields = readonly_fields
    ordering = ("-created_at",)
    max_num = 0

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    form = MemberAdminForm
    list_display = (
        "id",
        "user",
        "real_name",
        "level",
        "current_points",
        "total_points",
        "colored_balance",
        "created_at",
    )
    list_filter = ("level", "gender")
    search_fields = ("user__username", "user__phone", "real_name")
    readonly_fields = ("current_points", "total_points", "colored_balance", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            fields.append("level")
        return fields
    autocomplete_fields = ("user", "level")
    inlines = (PointsRecordInline, StoreRecordInline)
    actions = ("action_issue_coupon",)
    fieldsets = (
        ("基本信息", {"fields": ("user", "real_name", "gender", "birthday", "default_address", "level", "remark")}),
        ("权益", {"fields": ("current_points", "total_points", "colored_balance")}),
        ("后台调整", {"fields": ("recharge_amount", "points_delta", "adjust_remark")}),
        ("时间", {"fields": ("created_at", "updated_at")}),
    )

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        if not request.user.has_perm("members.change_member"):
            fieldsets = [item for item in fieldsets if item[0] != "后台调整"]
        return fieldsets

    @admin.display(description="储值余额")
    def colored_balance(self, obj):
        balance = obj.store_balance
        return format_html("<strong>¥{}</strong>", balance)

    @admin.action(description="给所选会员发放优惠券")
    def action_issue_coupon(self, request, queryset):
        from django.template.response import TemplateResponse

        if request.POST.get("post") == "yes":
            coupon_id = request.POST.get("coupon_id")
            coupon = Coupon.objects.filter(pk=coupon_id, is_active=True).first()
            if not coupon:
                self.message_user(request, "请选择要发放的优惠券", messages.WARNING)
                return None
            ok = skip = 0
            for member in queryset:
                try:
                    issue_coupon(member, coupon)
                    ok += 1
                except CouponError:
                    skip += 1
            self.message_user(request, f"发放成功 {ok} 张，跳过 {skip} 张", messages.SUCCESS if ok else messages.WARNING)
            return None
        return TemplateResponse(
            request,
            "admin/members/issue_coupon.html",
            {
                **self.admin_site.each_context(request),
                "title": "给所选会员发放优惠券",
                "members": queryset,
                "coupons": Coupon.objects.filter(is_active=True),
                "opts": self.model._meta,
            },
        )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        StoreAccount.objects.get_or_create(member=obj)
        remark = form.cleaned_data.get("adjust_remark") or "后台调整"
        recharge_amount = form.cleaned_data.get("recharge_amount")
        points_delta = form.cleaned_data.get("points_delta")
        try:
            if recharge_amount:
                recharge(obj, recharge_amount, remark=remark)
                self.message_user(request, f"已充值 ¥{recharge_amount}", messages.SUCCESS)
            if points_delta:
                apply_points(obj, int(points_delta), PointsRecord.Source.MANUAL, remark=remark)
                self.message_user(request, f"已调整积分 {points_delta}", messages.SUCCESS)
        except (InsufficientBalance, ValueError) as exc:
            self.message_user(request, str(exc), messages.ERROR)


@admin.register(PointsRecord)
class PointsRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "delta", "balance_after", "source", "order_no", "created_at")
    list_filter = ("source",)
    search_fields = ("member__user__username", "order_no")
    readonly_fields = ("member", "delta", "balance_after", "source", "order_no", "remark", "created_at", "updated_at")
    fieldsets = (("基本信息", {"fields": readonly_fields}),)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StoreAccount)
class StoreAccountAdmin(admin.ModelAdmin):
    list_display = ("member", "balance", "updated_at")
    search_fields = ("member__user__username",)
    readonly_fields = ("member", "balance", "created_at", "updated_at")
    fieldsets = (("基本信息", {"fields": readonly_fields}),)

    def has_add_permission(self, request):
        return False


@admin.register(StoreRecord)
class StoreRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "member", "delta", "balance_after", "kind", "order_no", "created_at")
    list_filter = ("kind",)
    search_fields = ("member__user__username", "order_no")
    readonly_fields = ("member", "delta", "balance_after", "kind", "order_no", "remark", "created_at", "updated_at")
    fieldsets = (("基本信息", {"fields": readonly_fields}),)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(StoreRecharge)
class StoreRechargeAdmin(admin.ModelAdmin):
    list_display = ("recharge_no", "member", "amount", "status", "paid_at", "created_at")
    list_filter = ("status",)
    search_fields = ("recharge_no", "member__user__username", "trade_no")
    readonly_fields = (
        "recharge_no",
        "member",
        "amount",
        "status",
        "hold_key",
        "trade_no",
        "paid_at",
        "remark",
        "created_by",
        "created_at",
        "updated_at",
    )
    fieldsets = (("基本信息", {"fields": readonly_fields}),)
    actions = ("action_pay_ok",)

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_delete_permission(self, request, obj=None):
        return is_admin_user(request.user)

    @admin.action(description="模拟入账成功")
    def action_pay_ok(self, request, queryset):
        if not is_admin_user(request.user):
            self.message_user(request, "仅管理员可操作充值单", messages.ERROR)
            return
        for item in queryset:
            try:
                pay_store_recharge(item, success=True, operator=request.user)
                self.message_user(request, f"{item.recharge_no} 已入账", messages.SUCCESS)
            except RechargeError as exc:
                self.message_user(request, f"{item.recharge_no}：{exc}", messages.ERROR)
