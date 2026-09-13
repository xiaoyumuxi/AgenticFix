from api import checkout_total


def test_single_unit():
    assert checkout_total([{"unit_price": 20, "quantity": 1}]) == 28


def test_quantity_changes_shipping():
    assert checkout_total([{"unit_price": 60, "quantity": 2}]) == 120


def test_mixed_order():
    assert (
        checkout_total([{"unit_price": 12, "quantity": 3}, {"unit_price": 7, "quantity": 2}]) == 58
    )
