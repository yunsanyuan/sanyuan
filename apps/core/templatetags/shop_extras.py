from decimal import ROUND_HALF_UP, Decimal

from django import template

register = template.Library()


@register.filter
def member_price(price, rate):
    if price is None or not rate:
        return price
    return (Decimal(str(price)) * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
