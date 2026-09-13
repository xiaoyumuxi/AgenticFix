import pytest
from calculator import add

@pytest.mark.parametrize("a", [0, 2, -3, 1.25])
@pytest.mark.parametrize("b", [0, 2, -3, 1.25])
def test_numeric_combinations(a, b):
    assert add(a, b) == a + b

@pytest.mark.parametrize("bad", [None, "2", [], {}])
@pytest.mark.parametrize("reverse", [False, True])
def test_reject_non_numeric(bad, reverse):
    with pytest.raises(TypeError):
        add(bad, 1) if reverse else add(1, bad)
