from pricing import subtotal
from shipping import shipping_fee


def checkout_total(items, free_shipping_at=100):
    amount = subtotal(items)
    return round(amount + shipping_fee(amount, free_shipping_at), 2)
