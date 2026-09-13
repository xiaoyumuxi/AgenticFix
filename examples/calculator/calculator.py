"""A deliberately broken, trusted fixture for the tool-chain demonstration."""


def add(a: int | float, b: int | float) -> int | float:
    if not isinstance(a, int) or not isinstance(b, int):
        raise TypeError("arguments must be numbers")
    return a + b
