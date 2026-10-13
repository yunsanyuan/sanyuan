from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/<int:pk>/update/", views.cart_update, name="cart_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("", views.order_list, name="list"),
    path("<int:pk>/", views.order_detail, name="detail"),
    path("<int:pk>/pay/", views.order_pay, name="pay"),
    path("<int:pk>/receive/", views.order_receive, name="receive"),
    path("<int:pk>/cancel/", views.order_cancel, name="cancel"),
    path("<int:pk>/withdraw-cancel/", views.order_withdraw_cancel, name="withdraw_cancel"),
]
