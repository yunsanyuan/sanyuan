from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class MemberLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="用户名",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username", "placeholder": "用户名"}),
    )
    password = forms.CharField(
        label="密码",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "密码"}),
    )


class MemberRegisterForm(UserCreationForm):
    phone = forms.CharField(
        label="手机号",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "选填", "autocomplete": "tel"}),
    )
    real_name = forms.CharField(
        label="姓名",
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "怎么称呼您", "autocomplete": "name"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"placeholder": "用户名", "autocomplete": "username"})
        self.fields["password1"].widget.attrs.update({"placeholder": "至少 8 位", "autocomplete": "new-password"})
        self.fields["password2"].widget.attrs.update({"placeholder": "再输入一次", "autocomplete": "new-password"})

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "phone", "real_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.MEMBER
        user.phone = self.cleaned_data.get("phone") or None
        if commit:
            user.save()
        return user
