from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render

from apps.core.welcome import welcome_payload

from .services import dashboard_payload, staff_desk


@login_required
def dashboard(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("仅管理员与店员可查看看板")
    payload = dashboard_payload()
    return render(
        request,
        "dashboard/index.html",
        {
            "payload": payload,
            "kpi": payload["kpi"],
            "welcome": welcome_payload(request.user),
            "desk": staff_desk(),
        },
    )
