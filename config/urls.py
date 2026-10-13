from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("shop/", include("apps.products.urls")),
    path("orders/", include("apps.orders.urls")),
    path("member/", include("apps.members.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("", include("apps.core.urls")),
]

# static() 在 DEBUG=False 时返回空列表；演示 runserver 需要始终能读商品图。
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
