import pytest
from api import checkout_total


@pytest.mark.parametrize(
    "price,quantity,threshold,expected",
    [
        (20, 1, 100, 28),
        (60, 2, 100, 120),
        (25, 4, 100, 100),
        (10, 0, 100, 8),
        (12.5, 3, 100, 45.5),
        (10, 3, 30, 30),
        (10, 2, 30, 28),
        (0, 5, 100, 8),
    ],
)
def test_totals(price, quantity, threshold, expected):
    assert checkout_total([{"unit_price": price, "quantity": quantity}], threshold) == expected


def test_empty():
    assert checkout_total([]) == 8


def test_no_mutation():
    items = [{"unit_price": 9, "quantity": 3}]
    original = [dict(item) for item in items]
    assert checkout_total(items) == 35
    assert items == original
