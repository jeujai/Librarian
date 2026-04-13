"""Quality gate for per-document model failure rate evaluation.

Tracks NER, LLM, and bridge failure rates during KG extraction and bridge
generation, computes a weighted composite failure rate, and enforces
domain-specific thresholds.
"""

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict

from multimodal_librarian.config.scoring_weights import BRIDGE_WEIGHT, KG_WEIGHT
from multimodal_librarian.models.core import ContentType

# Default composite failure rate thresholds per content type.
# Keyed by string value (not enum) to avoid identity mismatches
# across celery worker forks.
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "medical": 0.05,
    "legal": 0.10,
    "technical": 0.15,
    "academic": 0.15,
    "narrative": 0.25,
    "general": 0.20,
}

_DEFAULT_FALLBACK = 0.20


@dataclass
class QualityGateResult:
    """Result of quality gate evaluation for a document."""

    composite_rate: float   # 0.0-1.0
    threshold: float        # 0.0-1.0
    passed: bool
    content_type: str       # ContentType.value
    ner_rate: float
    llm_rate: float
    bridge_rate: float
    ner_failures: int
    ner_total: int
    llm_failures: int
    llm_total: int
    bridge_failures: int
    bridge_total: int
    worst_model: str        # "ner", "llm", or "bridge"
    kg_weight: float = KG_WEIGHT
    bridge_weight: float = BRIDGE_WEIGHT

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for job_metadata persistence."""
        return asdict(self)

    def error_message(self) -> str:
        """Human-readable error for a failed gate."""
        pct = f"{self.composite_rate * 100:.0f}%"
        limit = f"{self.threshold * 100:.0f}%"
        worst_rate = max(
            self.ner_rate, self.llm_rate, self.bridge_rate
        )
        worst_pct = f"{worst_rate * 100:.0f}%"
        return (
            f"Model quality below threshold: {pct} failed "
            f"(limit: {limit} for "
            f"{self.content_type.upper()}, "
            f"worst: {self.worst_model.upper()} "
            f"at {worst_pct})"
        )


def get_quality_threshold(content_type: ContentType) -> float:
    """Get composite failure rate threshold for a content type.

    Checks ``MODEL_FAIL_THRESHOLD_{TYPE}`` env var first,
    falls back to the hardcoded default.  The env var value
    is an integer percentage (e.g. ``5`` means 5 %).
    """
    env_key = (
        f"MODEL_FAIL_THRESHOLD_"
        f"{content_type.value.upper()}"
    )
    env_val = os.environ.get(env_key)
    if env_val is not None:
        try:
            return int(env_val) / 100.0
        except ValueError:
            pass
    result = DEFAULT_THRESHOLDS.get(
        content_type.value, _DEFAULT_FALLBACK
    )
    return result


def _safe_rate(failures: int, total: int) -> float:
    """Return 0.0 when *total* is zero."""
    if total == 0:
        return 0.0
    return failures / total


def compute_quality_gate(
    kg_failures: Dict[str, int],
    bridge_failures: Dict[str, int],
    content_type: ContentType,
) -> QualityGateResult:
    """Compute composite failure rate and quality gate decision.

    Parameters
    ----------
    kg_failures:
        ``{"ner_failures": int, "llm_failures": int,
        "total_chunks": int}``
    bridge_failures:
        ``{"failed_bridges": int, "total_bridges": int}``
    content_type:
        Document content type for threshold lookup.
    """
    ner_failures = kg_failures.get("ner_failures", 0)
    llm_failures = kg_failures.get("llm_failures", 0)
    total_chunks = kg_failures.get("total_chunks", 0)
    failed_bridges = bridge_failures.get(
        "failed_bridges", 0
    )
    total_bridges = bridge_failures.get(
        "total_bridges", 0
    )

    ner_rate = _safe_rate(ner_failures, total_chunks)
    llm_rate = _safe_rate(llm_failures, total_chunks)
    bridge_rate = _safe_rate(failed_bridges, total_bridges)

    composite = (
        max(ner_rate, llm_rate) * KG_WEIGHT
        + bridge_rate * BRIDGE_WEIGHT
    )
    threshold = get_quality_threshold(content_type)

    # Determine worst model by individual rate.
    rates = {
        "ner": ner_rate,
        "llm": llm_rate,
        "bridge": bridge_rate,
    }
    worst_model = max(
        rates, key=rates.get  # type: ignore[arg-type]
    )

    # If KG extraction never ran (zero chunks processed),
    # the document cannot pass the quality gate.
    kg_missing = total_chunks == 0

    return QualityGateResult(
        composite_rate=composite,
        threshold=threshold,
        passed=(not kg_missing and composite <= threshold),
        content_type=content_type.value,
        ner_rate=ner_rate,
        llm_rate=llm_rate,
        bridge_rate=bridge_rate,
        ner_failures=ner_failures,
        ner_total=total_chunks,
        llm_failures=llm_failures,
        llm_total=total_chunks,
        bridge_failures=failed_bridges,
        bridge_total=total_bridges,
        worst_model=worst_model,
    )
