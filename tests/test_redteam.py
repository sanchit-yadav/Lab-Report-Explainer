"""Unit tests for the Adversarial Red Team Attack Suite and Harness."""

from __future__ import annotations

import pytest

from redteam.cases import get_all_attack_cases
from redteam.harness import RedTeamHarness
from redteam.models import AttackCategory, AttackTargetLayer


def test_redteam_attack_suite_count_and_categories():
    """Verify that red team dataset meets or exceeds the 50-attack threshold across 10 categories."""
    cases = get_all_attack_cases()
    assert len(cases) >= 50, f"Expected at least 50 cases, got {len(cases)}"

    # Ensure all 10 categories are represented
    found_categories = {c.category for c in cases}
    assert len(found_categories) == 10
    for cat in AttackCategory:
        assert cat in found_categories


def test_redteam_harness_blocks_instruction_override():
    """Verify harness blocks system prompt overrides."""
    cases = [c for c in get_all_attack_cases() if c.category == AttackCategory.INSTRUCTION_OVERRIDE]
    harness = RedTeamHarness()
    for case in cases:
        res = harness.run_case(case)
        assert res.blocked is True, f"Failed to block override: {case.name}"
        assert res.status == "BLOCKED"


def test_redteam_harness_blocks_idor():
    """Verify harness catches IDOR and token manipulation."""
    cases = [c for c in get_all_attack_cases() if c.category == AttackCategory.CROSS_USER_IDOR]
    harness = RedTeamHarness()
    for case in cases:
        res = harness.run_case(case)
        assert res.blocked is True, f"Failed to block IDOR case: {case.name}"


def test_redteam_harness_blocks_malformed():
    """Verify harness rejects malformed, oversized, or impossible biomarker values."""
    cases = [c for c in get_all_attack_cases() if c.category == AttackCategory.MALFORMED_OVERSIZED]
    harness = RedTeamHarness()
    for case in cases:
        res = harness.run_case(case)
        assert res.blocked is True, f"Failed to block malformed payload: {case.name}"


def test_redteam_harness_full_campaign_100_percent_defense():
    """Execute full red team campaign and verify 100% block rate with zero breaches."""
    harness = RedTeamHarness()
    summary = harness.run_all_cases()

    assert summary.total_attacks >= 50
    assert summary.total_succeeded == 0, f"{summary.total_succeeded} attacks succeeded!"
    assert summary.overall_block_rate == 1.0
    assert summary.total_blocked == summary.total_attacks
