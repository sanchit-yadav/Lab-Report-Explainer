"""Unit tests for data normalization utilities."""

import pytest
from src.extraction.normalizer import (
    clean_text,
    identify_columns,
    normalize_unit,
    parse_numeric_value,
    parse_reference_range,
)


def test_clean_text():
    assert clean_text("  Hemoglobin   A1c  ") == "Hemoglobin A1c"
    assert clean_text("\n\tBlood   Urea\n") == "Blood Urea"
    assert clean_text(None) == ""


def test_parse_numeric_value_standard():
    assert parse_numeric_value("14.2") == 14.2
    assert parse_numeric_value("0.85") == 0.85
    assert parse_numeric_value("-2.5") == -2.5
    assert parse_numeric_value("120") == 120.0


def test_parse_numeric_value_with_commas_and_thousands():
    assert parse_numeric_value("11,500") == 11500.0
    assert parse_numeric_value("240,000") == 240000.0
    assert parse_numeric_value("5,2") == 5.2  # European decimal comma


def test_parse_numeric_value_inequalities():
    assert parse_numeric_value("< 0.5") == 0.5
    assert parse_numeric_value("> 60") == 60.0
    assert parse_numeric_value("<= 200") == 200.0
    assert parse_numeric_value(">= 50") == 50.0


def test_parse_numeric_value_with_flags():
    assert parse_numeric_value("18.5 (H)") == 18.5
    assert parse_numeric_value("3.2 (L)") == 3.2
    assert parse_numeric_value("248.0*") == 248.0


def test_parse_numeric_value_non_numeric():
    assert parse_numeric_value("Negative") is None
    assert parse_numeric_value("Positive") is None
    assert parse_numeric_value("Non-Reactive") is None
    assert parse_numeric_value("Trace") is None
    assert parse_numeric_value("") is None


def test_parse_reference_range_two_sided():
    assert parse_reference_range("13.0 - 17.0") == (13.0, 17.0)
    assert parse_reference_range("4000 - 11000") == (4000.0, 11000.0)
    assert parse_reference_range("0.45 to 4.50") == (0.45, 4.50)
    assert parse_reference_range("80.0 – 200.0") == (80.0, 200.0)  # en-dash


def test_parse_reference_range_one_sided():
    assert parse_reference_range("< 200") == (None, 200.0)
    assert parse_reference_range("<= 150") == (None, 150.0)
    assert parse_reference_range("> 50") == (50.0, None)
    assert parse_reference_range(">= 60") == (60.0, None)


def test_normalize_unit():
    assert normalize_unit("10^3/ul") == "x10³/µL"
    assert normalize_unit("10^6/ul") == "x10⁶/µL"
    assert normalize_unit("/cumm") == "cells/cumm"
    assert normalize_unit("mg/dL") == "mg/dL"
    assert normalize_unit("-") == ""


def test_identify_columns():
    headers = ["Investigation", "Observed Value", "Unit", "Biological Ref. Interval"]
    col_map = identify_columns(headers)
    assert col_map.get("test_name") == 0
    assert col_map.get("value") == 1
    assert col_map.get("unit") == 2
    assert col_map.get("ref_range") == 3
