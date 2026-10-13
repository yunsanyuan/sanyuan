from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("", views.center, name="center"),
    path("profile/", views.profile, name="profile"),
    path("ledger/", views.ledger, name="ledger"),
    path("recharge/", views.recharge_page, name="recharge"),
    path("recharge/<int:pk>/pay/", views.recharge_pay, name="recharge_pay"),
    path("coupons/", views.coupon_list, name="coupons"),
    path("coupons/<int:pk>/claim/", views.coupon_claim, name="claim"),
]
