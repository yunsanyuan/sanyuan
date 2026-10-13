from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View

from apps.core.cart import refresh_cart_count, safe_next_url
from apps.core.welcome import welcome_payload
from apps.members.services import ensure_member_profile
from apps.orders.services import OrderError, add_to_cart
from apps.products.models import Product

from .forms import MemberLoginForm, MemberRegisterForm
from .models import User


class MemberLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = MemberLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        self._consume_pending_cart()
        payload = welcome_payload(self.request.user)
        messages.success(self.request, payload["home_title"])
        return response

    def _consume_pending_cart(self):
        pending = self.request.session.pop("pending_cart", None)
        if not pending:
            return
        user = self.request.user
        if getattr(user, "role", None) != User.Role.MEMBER:
            return
        member = ensure_member_profile(user)
        product = Product.objects.filter(pk=pending.get("pk"), is_on_sale=True).first()
        if member is None or product is None:
            return
        try:
            qty = max(1, int(pending.get("qty") or 1))
        except (TypeError, ValueError):
            qty = 1
        try:
            add_to_cart(member, product, qty)
            refresh_cart_count(self.request, member)
        except OrderError:
            messages.error(self.request, "登录后未能加入购物车，请再试一次")

    def get_success_url(self):
        user = self.request.user
        if user.role in {User.Role.ADMIN, User.Role.STAFF}:
            return "/admin/"
        nxt = safe_next_url(self.request, self.get_redirect_url())
        if nxt:
            return nxt
        return str(reverse_lazy("members:center"))


class MemberPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("members:center")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and getattr(request.user, "role", None) != User.Role.MEMBER:
            return redirect("/admin/")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "密码已更新")
        return super().form_valid(form)


class MemberLogoutView(LogoutView):
    next_page = reverse_lazy("home")


class MemberRegisterView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("members:center")
        return render(request, "accounts/register.html", {"form": MemberRegisterForm()})

    def post(self, request):
        form = MemberRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            ensure_member_profile(user)
            profile = user.member_profile
            if form.cleaned_data.get("real_name"):
                profile.real_name = form.cleaned_data["real_name"]
                profile.save(update_fields=["real_name", "updated_at"])
            login(request, user)
            payload = welcome_payload(user)
            messages.success(request, "注册成功。" + payload["home_title"])
            return redirect("members:center")
        return render(request, "accounts/register.html", {"form": form})
