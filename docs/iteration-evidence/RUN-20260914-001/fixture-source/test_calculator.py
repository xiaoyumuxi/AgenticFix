import pytest
from calculator import add


def test_integers():
    assert add(2, 3) == 5


def test_negative_integers():
    assert add(-2, 1) == -1


def test_float_inputs():
    assert add(1.5, 2.25) == 3.75


def test_mixed_inputs():
    assert add(1, 2.5) == 3.5


def test_rejects_text():
    with pytest.raises(TypeError):
        add("1", 2)
