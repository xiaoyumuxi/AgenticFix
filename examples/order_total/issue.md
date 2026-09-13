Checkout totals are wrong for orders containing quantities above one. Each item has
unit_price and quantity. The merchandise subtotal must include every unit; shipping
costs 8 unless that subtotal reaches free_shipping_at (default 100). Return the final
amount rounded to two decimals. Preserve the existing API and single-unit behavior.
For two units priced 60 each, the total should be 120 with free shipping, not 68.
