"""Data models and schemas for the Adversarial Red Team Attack Suite."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field


class AttackCategory(str, Enum):
    """Categorical classification of adversarial attack vectors."""
    INSTRUCTION_OVERRIDE = "instruction_override"
    ROLEPLAY_DOCTOR = "roleplay_doctor"
    HIDDEN_WHITE_TEXT = "hidden_white_text"
    SYSTEM_PROMPT_LEAK = "system_prompt_leak"
    CROSS_USER_IDOR = "cross_user_idor"
    MALFORMED_OVERSIZED = "malformed_oversized"
    ENCODED_MULTILINGUAL = "encoded_multilingual"
    DOSAGE_PRESCRIPTION_DEMAND = "dosage_prescription_demand"
    DIAGNOSTIC_ENTRAPMENT = "diagnostic_entrapment"
    MULTI_TURN_ESCALATION = "multi_turn_escalation"


class AttackTargetLayer(str, Enum):
    """The specific defense perimeter tested by the attack vector."""
    UPLOAD_VALIDATION = "upload_validation"
    INJECTION_DETECTOR = "injection_detector"
    OUTPUT_GUARDRAIL = "output_guardrail"
    AUTHORIZATION_IDOR = "authorization_idor"
    PLAUSIBILITY_VALIDATOR = "plausibility_validator"
    FULL_PIPELINE = "full_pipeline"


class AttackCase(BaseModel):
    """Structured representation of a single adversarial test vector."""
    case_id: str = Field(description="Unique identifier, e.g. 'RT-001'")
    name: str = Field(description="Descriptive title of attack vector")
    category: AttackCategory
    target_layer: AttackTargetLayer
    payload: Any = Field(description="String payload, binary bytes, or request dictionary")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    expected_defense_response: str = Field(
        default="BLOCKED",
        description="Expected defense outcome: 'BLOCKED' or 'REDACTED'"
    )


class AttackResult(BaseModel):
    """Evaluated outcome of an executed attack case."""
    case_id: str
    name: str
    category: AttackCategory
    target_layer: AttackTargetLayer
    blocked: bool
    status: str  # 'BLOCKED' or 'SUCCEEDED' (succeeded means vulnerability exists)
    detection_detail: Optional[str] = None
    execution_time_ms: float = 0.0


class RedTeamSummary(BaseModel):
    """Aggregated evaluation metrics for a red team campaign."""
    timestamp: str
    git_commit_hash: str
    total_attacks: int
    total_blocked: int
    total_succeeded: int
    overall_block_rate: float
    category_breakdown: Dict[str, Dict[str, Any]]
    results: List[AttackResult]
