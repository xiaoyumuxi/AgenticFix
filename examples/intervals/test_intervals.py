from intervals import merge_intervals


def test_disjoint():
    assert merge_intervals([[1, 2], [4, 5]]) == [[1, 2], [4, 5]]


def test_empty():
    assert merge_intervals([]) == []


def test_touching():
    assert merge_intervals([[1, 3], [3, 5]]) == [[1, 5]]


def test_nested():
    assert merge_intervals([[1, 10], [2, 3]]) == [[1, 10]]


def test_no_mutation():
    data = [[4, 6], [1, 5]]
    assert merge_intervals(data) == [[1, 6]]
    assert data == [[4, 6], [1, 5]]
