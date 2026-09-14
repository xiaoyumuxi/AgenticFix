"""Fixed independently of the agent output; no official implementation is exposed."""

from decimal import Decimal
from fractions import Fraction

import pytest
from more_itertools import numeric_range


@pytest.mark.parametrize(
    "args",
    [
        (0,),
        (3, 3),
        (2, 1),
        (1, 2, -1),
        (0.0,),
        (Decimal("0"),),
        (Fraction(0),),
    ],
)
def test_empty_reversed(args):
    assert list(reversed(numeric_range(*args))) == []


@pytest.mark.parametrize(
    "args",
    [
        (5,),
        (1, 6, 2),
        (5, 0, -2),
        (0, 1, 0.25),
        (Decimal("0"), Decimal("1"), Decimal("0.25")),
        (Fraction(0), Fraction(1), Fraction(1, 4)),
    ],
)
def test_nonempty_reversed(args):
    value = numeric_range(*args)
    assert list(reversed(value)) == list(value)[::-1]


def test_reversal_does_not_consume_range():
    value = numeric_range(4)
    assert list(reversed(value)) == [3, 2, 1, 0]
    assert list(value) == [0, 1, 2, 3]
    assert list(reversed(value)) == [3, 2, 1, 0]
