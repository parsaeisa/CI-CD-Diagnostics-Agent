import pytest
from app.calculator import calculate_discount, get_average_latency


def test_calculate_standard_discount():
    assert calculate_discount(100.0, 20.0) == 80.0


def test_calculate_invalid_discount():
    with pytest.raises(ValueError):
        calculate_discount(100.0, -10.0)


def test_average_latency_empty_list():
    assert get_average_latency([]) == 0.0