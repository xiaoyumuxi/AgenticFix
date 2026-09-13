from copy import deepcopy

import pytest
from intervals import merge_intervals


@pytest.mark.parametrize(
    "data,expected",
    [
        ([], []),
        ([[0, 0]], [[0, 0]]),
        ([[2, 3], [1, 2]], [[1, 3]]),
        ([[1, 10], [2, 3], [4, 6]], [[1, 10]]),
        ([[1, 2], [1, 2]], [[1, 2]]),
        ([[-5, -1], [-2, 2]], [[-5, 2]]),
        ([[0.5, 1.5], [1.5, 2.5]], [[0.5, 2.5]]),
        ([[1, 2], [3, 4], [2, 3]], [[1, 4]]),
        ([[9, 10], [1, 2]], [[1, 2], [9, 10]]),
        ([[1, 5], [5, 5], [5, 8]], [[1, 8]]),
    ],
)
def test_cases(data, expected):
    before = deepcopy(data)
    assert merge_intervals(data) == expected
    assert data == before
