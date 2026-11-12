"""Data normalization utilities for laboratory reports.

Handles dirty numbers, international decimal commas, inequalities,
multi-format reference ranges, and header heuristic identification.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from src.config import get_config


# Regex patterns compiled for performance
RE_CLEAN_TEXT = re.compile(r"\s+")
RE_NUMBER_SIMPLE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
RE_NUMBER_WITH_COMMA_DECIMAL = re.compile(r"^[+-]?\d+,\d+$")
RE_NUMBER_WITH_THOUSANDS = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
RE_INEQUALITY = re.compile(r"^(?:<=|>=|\u2264|\u2265|<|>)\s*([+-]?\d+(?:[.,]\d+)?)$")
RE_RANGE_HYPHEN = re.compile(
    r"([+-]?\d+(?:[.,]\d+)?)\s*(?:-|\u2013|\u2014|to)\s*([+-]?\d+(?:[.,]\d+)?)"
)
RE_RANGE_LESS = re.compile(
    r"(?:<|<=|\u2264|up\s*to|less\s*than|upto)\s*([+-]?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
RE_RANGE_GREATER = re.compile(
    r"(?:>|>=|\u2265|greater\s*than|more\s*than)\s*([+-]?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
# Strips a leading label like "Desirable:", "Male:", etc., before the numeric part
RE_RANGE_LABEL_PREFIX = re.compile(r"^[A-Za-z][A-Za-z\s./]*:\s*")

# Non-numeric sentinel words that should return None
_NON_NUMERIC_SENTINELS = frozenset([
    "nil", "absent", "trace", "nd", "bdl", "not done", "see note",
    "positive", "negative", "reactive", "non-reactive", "detected",
    "not detected",
])

# Range-like heuristic — does a cell contain a numeric range pattern?
RE_RANGE_HINT = re.compile(r"\d\s*[-\u2013\u2014]\s*\d|[<>]\s*\d|up\s*to\s*\d", re.IGNORECASE)


def clean_text(text: Optional[str]) -> str:
    """Strip leading/trailing whitespace and collapse internal consecutive whitespaces."""
    if not text:
        return ""
    return RE_CLEAN_TEXT.sub(" ", str(text)).strip()


def parse_numeric_value(raw_val: str) -> Optional[float]:
    """Parse a float from a raw string value extracted from a report.

    Handles:
    - Standard floats: '14.2' -> 14.2
    - Thousands separators: '11,500' -> 11500.0
    - Comma decimals: '5,2' -> 5.2
    - Inequalities: '< 0.5' -> 0.5, '> 60' -> 60.0
    - Flags/asterisks appended: '18.5 (H)' or '18.5*' -> 18.5
    - Bracket flags: '5.6 [H]' -> 5.6
    - Slash values (blood pressure): '120/80' -> 120.0
    - Non-numeric strings ('Positive', 'Absent', 'NIL', 'Not Done') -> None
    """
    cleaned = clean_text(raw_val)
    if not cleaned:
        return None

    # Check sentinel words (whole-string match, case-insensitive)
    if cleaned.lower() in _NON_NUMERIC_SENTINELS:
        return None

    # Strip common visual flags like '*', 'H', 'L', '(H)', '(L)' at the end
    cleaned = re.sub(r"[\s*]+$", "", cleaned)
    cleaned = re.sub(r"\s*\([A-Za-z]+\)\s*$", "", cleaned)   # (H), (L), (High), etc.
    cleaned = re.sub(r"\s*\[[A-Za-z]+\]\s*$", "", cleaned)   # [H], [L], etc.
    cleaned = re.sub(r"\s+[HLhl]$", "", cleaned)

    # Re-check sentinels after stripping (edge case: "NIL ()")
    if cleaned.lower() in _NON_NUMERIC_SENTINELS:
        return None

    # Slash values like "120/80" — take first number
    if "/" in cleaned:
        parts = cleaned.split("/", 1)
        try:
            return float(parts[0].strip())
        except ValueError:
            pass

    # Check for inequality prefix (< 0.5 or > 60)
    match_ineq = RE_INEQUALITY.match(cleaned)
    if match_ineq:
        num_str = match_ineq.group(1).replace(",", ".")
        try:
            return float(num_str)
        except ValueError:
            return None

    # Check thousands separator e.g. 11,500
    if RE_NUMBER_WITH_THOUSANDS.match(cleaned):
        try:
            return float(cleaned.replace(",", ""))
        except ValueError:
            return None

    # Check comma as decimal separator e.g. 5,2
    if RE_NUMBER_WITH_COMMA_DECIMAL.match(cleaned):
        try:
            return float(cleaned.replace(",", "."))
        except ValueError:
            return None

    # Check standard number format
    if RE_NUMBER_SIMPLE.match(cleaned):
        try:
            return float(cleaned)
        except ValueError:
            return None

    # Attempt to extract leading number if words trail: e.g. '14.2 g/dL'
    match_lead = re.match(r"^([+-]?\d+(?:\.\d+)?)\b", cleaned)
    if match_lead:
        try:
            return float(match_lead.group(1))
        except ValueError:
            return None

    return None


def parse_reference_range(raw_range: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract low and high reference limits from a range string.

    Supports:
    - '13.0 - 17.0', '13.0-17.0', '13.0 to 17.0' -> (13.0, 17.0)
    - '< 200', '<= 200', 'Up to 200', 'Upto 200' -> (None, 200.0)
    - '> 60', '>= 60', 'More than 60' -> (60.0, None)
    - 'Desirable: < 200' -> (None, 200.0)  [label prefix stripped]
    - 'Male: 13.0 - 17.0 / Female: ...' -> (13.0, 17.0)  [first pair]
    - Unparseable or empty -> (None, None)
    """
    cleaned = clean_text(raw_range)
    if not cleaned:
        return None, None

    # Strip a leading label like "Desirable:", "Male:", "Normal:" etc.
    cleaned_no_label = RE_RANGE_LABEL_PREFIX.sub("", cleaned).strip()

    # If there's a slash separating gender-specific ranges, take the first segment
    if "/" in cleaned_no_label:
        first_segment = cleaned_no_label.split("/")[0].strip()
        # Try to parse the first segment recursively
        result = parse_reference_range(first_segment)
        if result != (None, None):
            return result

    # Check for two-sided range (try label-stripped first, fall back to original)
    for candidate in (cleaned_no_label, cleaned):
        match_hyphen = RE_RANGE_HYPHEN.search(candidate)
        if match_hyphen:
            low_str = match_hyphen.group(1).replace(",", ".")
            high_str = match_hyphen.group(2).replace(",", ".")
            try:
                low = float(low_str)
                high = float(high_str)
                return (low, high) if low <= high else (high, low)
            except ValueError:
                pass

    # Check for upper-bound only (< 200, Upto 200, etc.)
    for candidate in (cleaned_no_label, cleaned):
        match_less = RE_RANGE_LESS.search(candidate)
        if match_less:
            high_str = match_less.group(1).replace(",", ".")
            try:
                return None, float(high_str)
            except ValueError:
                pass

    # Check for lower-bound only (> 60)
    for candidate in (cleaned_no_label, cleaned):
        match_greater = RE_RANGE_GREATER.search(candidate)
        if match_greater:
            low_str = match_greater.group(1).replace(",", ".")
            try:
                return float(low_str), None
            except ValueError:
                pass

    return None, None


def normalize_unit(raw_unit: str) -> str:
    """Standardize common laboratory measurement units."""
    unit = clean_text(raw_unit)
    if not unit or unit.lower() in ("-", "nil", "n/a", "none"):
        return ""

    replacements = {
        "10^3/ul": "x10\u00b3/\u00b5L",
        "10^6/ul": "x10\u2076/\u00b5L",
        "/cumm": "cells/cumm",
        "/ul": "cells/\u00b5L",
        "ug/dl": "\u00b5g/dL",
        "umol/l": "\u00b5mol/L",
        "ui/l": "IU/L",
        "u/l": "U/L",
    }
    unit_lower = unit.lower()
    return replacements.get(unit_lower, unit)


def identify_columns(headers: List[Optional[str]]) -> Dict[str, int]:
    """Map logical field names to column indices based on configured header patterns.

    Returns mapping like: {'test_name': 0, 'value': 1, 'unit': 2, 'ref_range': 3}

    If no headers match (e.g. the table has no recognized header row) but we have
    3-4 columns, a POSITIONAL FALLBACK is applied:
      col 0 -> test_name
      col 1 -> value
      col 2 -> unit  OR  ref_range  (heuristic: if cell contains range patterns -> ref_range)
      col 3 -> ref_range (if present)
    """
    config = get_config()
    patterns = config.extraction.header_patterns

    mapping: Dict[str, int] = {}
    cleaned_headers = [clean_text(h).lower() for h in headers]

    for idx, header in enumerate(cleaned_headers):
        if not header:
            continue

        # Match test name column
        if "test_name" not in mapping and any(p in header for p in patterns.test_name):
            mapping["test_name"] = idx
            continue

        # Match value column
        if "value" not in mapping and any(p in header for p in patterns.value):
            mapping["value"] = idx
            continue

        # Match unit column
        if "unit" not in mapping and any(p in header for p in patterns.unit):
            mapping["unit"] = idx
            continue

        # Match reference range column
        if "ref_range" not in mapping and any(p in header for p in patterns.ref_range):
            mapping["ref_range"] = idx
            continue

    # --- Positional fallback ---
    # If we got no matches at all and there are 3-4 columns, use positional heuristic
    if not mapping and 3 <= len(cleaned_headers) <= 5:
        mapping["test_name"] = 0
        mapping["value"] = 1
        if len(cleaned_headers) >= 4:
            # col 2 = unit, col 3 = ref_range
            mapping["unit"] = 2
            mapping["ref_range"] = 3
        else:
            # col 2: decide unit vs ref_range by content heuristic (range hint)
            col2_header = cleaned_headers[2] if len(cleaned_headers) > 2 else ""
            if RE_RANGE_HINT.search(col2_header):
                mapping["ref_range"] = 2
            else:
                # default: treat col 2 as unit; ref_range absent
                mapping["unit"] = 2

    return mapping
