from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from apps.members.services import ensure_member_profile


def member_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if getattr(request.user, "role", None) != request.user.Role.MEMBER:
            messages.error(request, "请使用会员账号访问商城功能")
            if request.user.is_staff:
                return redirect("/admin/")
            return redirect("accounts:login")
        ensure_member_profile(request.user)
        request.member = request.user.member_profile
        return view_func(request, *args, **kwargs)

    return _wrapped
