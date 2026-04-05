"""Unit tests: single functions, no Flask, no database."""

from datetime import datetime

import pytest

from app.csv_parse import parse_bool, parse_dt


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2025-05-27 09:46:01", datetime(2025, 5, 27, 9, 46, 1)),
        ("  2024-01-10 12:08:44  ", datetime(2024, 1, 10, 12, 8, 44)),
    ],
)
def test_parse_dt(value, expected):
    assert parse_dt(value) == expected


def test_parse_dt_invalid():
    with pytest.raises(ValueError):
        parse_dt("not-a-date")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("True", True),
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("False", False),
        ("false", False),
        ("0", False),
        ("", False),
    ],
)
def test_parse_bool(value, expected):
    assert parse_bool(value) is expected
