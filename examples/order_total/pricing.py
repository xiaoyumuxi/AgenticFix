def subtotal(items):
    return sum(item["unit_price"] for item in items)
