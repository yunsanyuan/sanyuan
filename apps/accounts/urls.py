from django.urls import path

from .views import MemberLoginView, MemberLogoutView, MemberPasswordChangeView, MemberRegisterView

app_name = "accounts"

urlpatterns = [
    path("login/", MemberLoginView.as_view(), name="login"),
    path("logout/", MemberLogoutView.as_view(), name="logout"),
    path("register/", MemberRegisterView.as_view(), name="register"),
    path("password/change/", MemberPasswordChangeView.as_view(), name="password_change"),
]
