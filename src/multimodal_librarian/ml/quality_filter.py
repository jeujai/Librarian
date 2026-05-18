"""
Quality Filter — evaluates training pairs against quality criteria.

Rejects MCQ-style, textbook-style, and malformed training pairs before
they enter the fine-tuning dataset.  Designed to run inside the
``RAGQAStrategy._process_seed()`` loop so rejected pairs are replaced
by processing additional seeds rather than discarded post-hoc.

The filter applies six checks in order:

1. **MCQ markers** — 3+ multiple-choice markers in the response.
2. **LOINC instruction** — uncleaned LOINC-coded terms in the instruction.
3. **Uncited long response** — response >800 est. tokens with no citations.
4. **Response too short** — response <50 est. tokens (refusals exempt).
5. **Textbook style** — instruction classified as textbook/exam style.
6. **Production-divergent style** — bullet-only, "student", or "exam"
   phrasing in the response.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List

from .loinc_cleaner import is_loinc_coded
from .models import InstructionTuningPair

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token estimation heuristic
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN: float = 4.0


def estimate_tokens(text: str) -> int:
    """Estimate token count using a chars / 4 heuristic.

    The Llama 3 tokenizer averages ~3.5–4.2 chars per token for
    English medical text.  A conservative 4.0 ratio avoids adding
    ``transformers`` as a runtime dependency.
    """
    return int(len(text) / _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# MCQ marker detection
# ---------------------------------------------------------------------------

# Individual multiple-choice markers.  A response is flagged when 3+
# distinct markers are present (Requirement 4.1).
_MCQ_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\bA\.\s"),
    re.compile(r"\bB\.\s"),
    re.compile(r"\bC\.\s"),
    re.compile(r"\bD\.\s"),
    re.compile(r"\(a\)\s"),
    re.compile(r"\(b\)\s"),
    re.compile(r"\(c\)\s"),
    re.compile(r"\(d\)\s"),
    re.compile(
        r"correct answer is", re.IGNORECASE
    ),
]

_MCQ_THRESHOLD: int = 3


def _count_mcq_markers(text: str) -> int:
    """Count distinct MCQ markers present in *text*."""
    return sum(1 for p in _MCQ_PATTERNS if p.search(text))


# ---------------------------------------------------------------------------
# Citation detection
# ---------------------------------------------------------------------------

_CITATION_PATTERN: re.Pattern[str] = re.compile(
    r"\[Source\s*\d+\]", re.IGNORECASE
)


def _has_citations(text: str) -> bool:
    """Return True if *text* contains at least one ``[Source N]`` marker."""
    return bool(_CITATION_PATTERN.search(text))


# ---------------------------------------------------------------------------
# Textbook / exam-style classification
# ---------------------------------------------------------------------------

# Stems extracted from ``TEMPLATES_BY_SEMANTIC_TYPE`` in
# ``rag_qa_strategy.py`` and common exam-style patterns.
# Matching is case-insensitive and anchored to the start of the
# instruction after stripping leading whitespace.
_TEXTBOOK_STEMS: List[str] = [
    "what is the mechanism of action of",
    "what is the pathophysiology of",
    "what are the indications and contraindications for",
    "describe the",
    "what are the most common adverse effects of",
    "what are the most common clinical presentations of",
    "how is {concept_name} diagnosed",
    "what are the current evidence-based treatment guidelines for",
    "what are the risk factors and predisposing conditions for",
    "what complications can arise from",
    "describe the epidemiology and prevalence of",
    "what is the differential diagnosis for",
    "what are the indications for performing",
    "describe the key steps involved in",
    "what are the most common complications associated with",
    "what contraindications should be evaluated before",
    "what is the appropriate diagnostic workup for",
    "how does {concept_name} help narrow the differential diagnosis",
    "what red-flag features associated with",
    "what is the clinical significance of {concept_name} in the context of",
    "how is {concept_name} graded or classified in clinical practice",
    "what is the sensitivity and specificity of",
    "what patient preparation is required before",
    "what are the limitations and potential false positives of",
    "what is the anatomical structure and function of",
    "what are the most common pathologies affecting",
    "how does the blood supply and innervation of",
    "what imaging modalities are most useful for evaluating",
    "what surgical approaches are used for procedures involving",
    "how does embryological development of",
    (
        "what is the clinical significance of"
        " {concept_name} in patient assessment"
    ),
    "how is {concept_name} measured and what are the normal reference ranges",
    "what conditions are associated with abnormal values of",
    "what factors can cause falsely elevated or decreased",
    "what is the most likely diagnosis when",
    "what additional tests should be ordered when",
    "what pre-analytical factors can affect",
    "what is the underlying mechanism of",
    "what diseases or conditions are most commonly associated with",
    "how does {concept_name} manifest at the cellular and tissue level",
    "what laboratory or imaging findings are characteristic of",
    "what therapeutic interventions target",
    "what are the risk factors and etiology of",
    "what is the typical histological appearance of",
    "how is {concept_name} staged and what is the prognosis",
    "what are the current first-line treatment options for",
    "what tumor markers or molecular features are associated with",
    "what screening recommendations exist for early detection of",
    "what are the most common sites of metastasis for",
]

# Compile stems into a single regex for fast matching.
# We strip ``{concept_name}`` placeholders and collapse whitespace so
# the patterns match regardless of the concept name that was filled in.
_TEXTBOOK_STEM_PATTERNS: List[re.Pattern[str]] = []
for _stem in _TEXTBOOK_STEMS:
    # Replace template placeholders with a wildcard
    _escaped = re.escape(
        _stem.replace("{concept_name}", "")
    ).replace(r"\ ", r"\s+")
    # Allow arbitrary text where the placeholder was
    _pattern_str = _escaped.replace(
        re.escape(""), ""
    )
    _TEXTBOOK_STEM_PATTERNS.append(
        re.compile(r"^\s*" + _pattern_str, re.IGNORECASE)
    )

# Additional exam-style structural patterns (not tied to specific stems)
_EXAM_STYLE_PATTERNS: List[re.Pattern[str]] = [
    # "Which of the following …"
    re.compile(r"^\s*which\s+of\s+the\s+following", re.IGNORECASE),
    # "All of the following EXCEPT …"
    re.compile(
        r"^\s*all\s+of\s+the\s+following\s+except",
        re.IGNORECASE,
    ),
    # "A 45-year-old male presents with …" (clinical vignette)
    re.compile(
        r"^\s*a\s+\d+-year-old\s+(male|female|man|woman|patient)",
        re.IGNORECASE,
    ),
    # "The most likely diagnosis is …"
    re.compile(
        r"^\s*the\s+most\s+likely\s+diagnosis",
        re.IGNORECASE,
    ),
    # "Select the best answer …"
    re.compile(r"^\s*select\s+the\s+best\s+answer", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Production-divergent response patterns
# ---------------------------------------------------------------------------

# Responses that address the user as "student" or reference an "exam"
_STUDENT_EXAM_PATTERN: re.Pattern[str] = re.compile(
    r"\bstudent\b|\bexam\b|\btest\s+question\b",
    re.IGNORECASE,
)

# Bullet-only responses: every non-empty line starts with a bullet
# marker and there is no prose paragraph.
_BULLET_MARKER: re.Pattern[str] = re.compile(
    r"^\s*[-•*]\s|^\s*\d+[.)]\s"
)


def _is_bullet_only(text: str) -> bool:
    """Return True if *text* consists entirely of bullet-point lines."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    return all(_BULLET_MARKER.match(ln) for ln in lines)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FilterResult:
    """Result of evaluating a single training pair."""

    passed: bool
    rejection_reasons: List[str] = field(default_factory=list)


@dataclass
class FilterSummary:
    """Aggregate statistics from a quality filter run."""

    total_evaluated: int
    total_passed: int
    total_rejected: int
    rejections_by_reason: Dict[str, int] = field(default_factory=dict)
    pass_rate: float = 0.0


# ---------------------------------------------------------------------------
# QualityFilter
# ---------------------------------------------------------------------------


class QualityFilter:
    """Evaluates training pairs against conversational quality criteria.

    Instantiate once per generation run.  Call :meth:`evaluate` for each
    pair inside the generation loop, then :meth:`summarize` at the end
    to get aggregate statistics.

    Parameters
    ----------
    min_response_tokens:
        Minimum estimated token count for a non-refusal response.
        Pairs below this threshold are rejected with reason
        ``"response_too_short"`` (default 50).
    max_uncited_tokens:
        Maximum estimated token count for a response without citations.
        Responses exceeding this are rejected with reason
        ``"uncited_long_response"`` (default 800).
    """

    def __init__(
        self,
        min_response_tokens: int = 50,
        max_uncited_tokens: int = 800,
    ) -> None:
        self._min_response_tokens = min_response_tokens
        self._max_uncited_tokens = max_uncited_tokens

        # Running counters for summarize()
        self._total_evaluated: int = 0
        self._total_passed: int = 0
        self._total_rejected: int = 0
        self._rejections_by_reason: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        pair: InstructionTuningPair,
        is_refusal: bool = False,
    ) -> FilterResult:
        """Evaluate a single pair against all quality criteria.

        Checks are applied in order.  A pair may trigger multiple
        rejection reasons — all are recorded.

        Parameters
        ----------
        pair:
            The instruction-tuning pair to evaluate.
        is_refusal:
            If ``True``, the pair is a refusal response and is exempt
            from the minimum-length check.

        Returns
        -------
        FilterResult
            ``passed=True`` if the pair passes all checks, otherwise
            ``passed=False`` with a list of rejection reason codes.
        """
        reasons: List[str] = []

        # 1. MCQ markers in response
        if _count_mcq_markers(pair.response) >= _MCQ_THRESHOLD:
            reasons.append("mcq_markers")

        # 2. LOINC-coded terms in instruction
        if is_loinc_coded(pair.instruction):
            reasons.append("loinc_instruction")

        # 3. Uncited long response
        resp_tokens = estimate_tokens(pair.response)
        if (
            resp_tokens > self._max_uncited_tokens
            and not _has_citations(pair.response)
        ):
            reasons.append("uncited_long_response")

        # 4. Response too short (refusals exempt)
        if (
            not is_refusal
            and resp_tokens < self._min_response_tokens
        ):
            reasons.append("response_too_short")

        # 5. Textbook-style instruction
        if self.classify_question_style(pair.instruction) == "textbook":
            reasons.append("textbook_style")

        # 6. Production-divergent response style
        if self._is_production_divergent(pair.response):
            reasons.append("production_divergent")

        passed = len(reasons) == 0
        result = FilterResult(passed=passed, rejection_reasons=reasons)

        # Update running counters
        self._total_evaluated += 1
        if passed:
            self._total_passed += 1
        else:
            self._total_rejected += 1
            for reason in reasons:
                self._rejections_by_reason[reason] = (
                    self._rejections_by_reason.get(reason, 0) + 1
                )

        # Log rejections for auditing (Requirement 4.6)
        if not passed:
            logger.info(
                "Quality filter rejected pair: reasons=%s instruction=%s",
                reasons,
                pair.instruction[:120],
            )

        return result

    def classify_question_style(self, instruction: str) -> str:
        """Classify an instruction as ``'conversational'`` or ``'textbook'``.

        Uses regex matching against known textbook stems from
        ``TEMPLATES_BY_SEMANTIC_TYPE`` and common exam-style patterns.
        This is deterministic and fast — no LLM call needed.

        Parameters
        ----------
        instruction:
            The question / instruction text to classify.

        Returns
        -------
        str
            ``"textbook"`` if the instruction matches a known stem or
            exam pattern, ``"conversational"`` otherwise.
        """
        for pattern in _TEXTBOOK_STEM_PATTERNS:
            if pattern.search(instruction):
                return "textbook"

        for pattern in _EXAM_STYLE_PATTERNS:
            if pattern.search(instruction):
                return "textbook"

        return "conversational"

    def summarize(self) -> FilterSummary:
        """Return aggregate statistics for all evaluated pairs.

        The summary satisfies the count invariant (Property 10):
        ``total_evaluated == total_passed + total_rejected`` and
        ``sum(rejections_by_reason.values()) >= total_rejected``
        (a pair with multiple reasons increments each reason counter).

        Returns
        -------
        FilterSummary
        """
        pass_rate = 0.0
        if self._total_evaluated > 0:
            pass_rate = self._total_passed / self._total_evaluated

        return FilterSummary(
            total_evaluated=self._total_evaluated,
            total_passed=self._total_passed,
            total_rejected=self._total_rejected,
            rejections_by_reason=dict(self._rejections_by_reason),
            pass_rate=pass_rate,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_production_divergent(response: str) -> bool:
        """Check for response styles that diverge from production output.

        Detects:
        - Bullet-point-only responses without prose
        - Responses that address the user as "student"
        - Responses that reference an "exam" or "test question"
        """
        if _STUDENT_EXAM_PATTERN.search(response):
            return True
        if _is_bullet_only(response):
            return True
        return False
