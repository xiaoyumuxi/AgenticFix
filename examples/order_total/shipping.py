def shipping_fee(amount, free_shipping_at):
    return 0 if amount >= free_shipping_at else 8
