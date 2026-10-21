"""Data models for grading results."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


class Tier(Enum):
    """Grading tier that resolved the decision."""
    TIER_1 = "Tier 1: Smart Hardcoded"
    TIER_2 = "Tier 2: Structural Heuristics"
    TIER_3 = "Tier 3: OpenCV Visual"
    TIER_4 = "Tier 4: AI Visual Assessment"


class ResultStatus(Enum):
    """Grading result status."""
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class GradingResult:
    """Result of grading a single submission."""

    status: ResultStatus
    tier: Tier
    confidence: float  # 0.0 to 1.0
    score: float  # 0 to 100

    # Detailed explanations
    passed_checks: List[str] = field(default_factory=list)
    failed_checks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Tier-specific details
    tier_1_details: Optional[Dict[str, Any]] = None
    tier_2_details: Optional[Dict[str, Any]] = None
    tier_3_details: Optional[Dict[str, Any]] = None

    # Execution details
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Check if submission passed."""
        return self.status == ResultStatus.PASS
