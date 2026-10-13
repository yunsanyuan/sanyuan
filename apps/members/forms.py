from django import forms

from apps.accounts.models import User

from .models import Member


class MemberProfileForm(forms.Form):
    real_name = forms.CharField(
        label="姓名",
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "怎么称呼您", "autocomplete": "name"}),
    )
    phone = forms.CharField(
        label="手机号",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "选填", "autocomplete": "tel"}),
    )
    gender = forms.ChoiceField(label="性别", choices=Member.Gender.choices)
    birthday = forms.DateField(
        label="生日",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    default_address = forms.CharField(
        label="默认地址",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "送花上门时预填，以下单快照为准"}),
    )

    def __init__(self, *args, user=None, member=None, **kwargs):
        self.user = user
        self.member = member
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone:
            return None
        qs = User.objects.filter(phone=phone)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError("该手机号已被使用")
        return phone

    def save(self):
        user = self.user
        user.phone = self.cleaned_data.get("phone")
        user.save(update_fields=["phone"])
        member = self.member
        member.real_name = self.cleaned_data.get("real_name") or ""
        member.gender = self.cleaned_data["gender"]
        member.birthday = self.cleaned_data.get("birthday")
        member.default_address = self.cleaned_data.get("default_address") or ""
        member.save(update_fields=["real_name", "gender", "birthday", "default_address", "updated_at"])
        return member
