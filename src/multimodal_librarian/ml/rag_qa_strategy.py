"""
RAG-Generated Gold Answer Q&A Pair Generation Strategy.

Generates medical Q&A instruction-tuning pairs by running seed questions
through the existing RAG pipeline and capturing cited responses as
gold-standard training targets. Seed questions are generated from two
sources: UMLS concept names with clinical semantic types, and
semantic-type-aware medical question templates.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import threading
from typing import Any, Callable, Dict, List, Optional

from .loinc_cleaner import clean_concept_name
from .models import InstructionTuningPair, PairMetadata, SeedQuestion
from .quality_filter import QualityFilter
from .question_rewriter import LLMQuestionRewriter
from .refusal_formatter import (
    format_refusal,
    has_refusal_then_fabrication,
    is_refusal_response,
)
from .token_budget import TokenBudgetManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Clinical semantic types used for seed question generation
# ---------------------------------------------------------------------------

CLINICAL_SEMANTIC_TYPES: List[str] = [
    # --- Original 10 types ---
    "Pharmacologic Substance",
    "Disease or Syndrome",
    "Therapeutic or Preventive Procedure",
    "Sign or Symptom",
    "Diagnostic Procedure",
    "Body Part, Organ, or Organ Component",
    "Clinical Attribute",
    "Laboratory or Test Result",
    "Pathologic Function",
    "Neoplastic Process",
    # --- Expanded: high-count clinically relevant types ---
    "Organic Chemical",
    "Clinical Drug",
    "Amino Acid, Peptide, or Protein",
    "Injury or Poisoning",
    "Finding",
    "Biologically Active Substance",
    "Bacterium",
    "Enzyme",
    "Immunologic Factor",
    "Laboratory Procedure",
    "Medical Device",
    "Congenital Abnormality",
    "Hazardous or Poisonous Substance",
    "Antibiotic",
    "Mental or Behavioral Dysfunction",
    "Anatomical Abnormality",
    "Virus",
    "Body Location or Region",
]

# ---------------------------------------------------------------------------
# Semantic types exercised by the 50-question fine-tuned-model-regression
# evaluation set. These are the "target" types that receive a per-type floor
# in ``RAGQAStrategy._compute_type_allocation`` so that no eval type is
# starved (fine-tuned-model-regression Property 3 / Requirements 2.2–2.5).
# ---------------------------------------------------------------------------

EVAL_SEMANTIC_TYPES: List[str] = [
    "Pharmacologic Substance",
    "Disease or Syndrome",
    "Therapeutic or Preventive Procedure",
    "Sign or Symptom",
    "Diagnostic Procedure",
]

# ---------------------------------------------------------------------------
# Medical question templates organised by UMLS semantic type
# ---------------------------------------------------------------------------
# Derived from common question-stem patterns in MedQA (USMLE-style),
# MedMCQA (AIIMS/NEET PG), and PubMedQA benchmarks.  Each semantic type
# gets templates that are clinically appropriate for that category —
# e.g. "mechanism of action" only appears under Pharmacologic Substance,
# "pathophysiology" only under Disease or Syndrome, etc.
#
# Sources (content rephrased for compliance with licensing restrictions):
#   - MedQA: ~12.7k USMLE-style clinical vignette MCQs (Jin et al. 2021)
#   - MedMCQA: ~194k AIIMS/NEET PG MCQs across 21 subjects (Pal et al. 2022)
#   - PubMedQA: ~211k biomedical research yes/no/maybe QAs (Jin et al. 2019)
#   - USMLE signal-word analysis: Knoedler et al. 2024 (Sci Rep 14:13553)
# ---------------------------------------------------------------------------

TEMPLATES_BY_SEMANTIC_TYPE: Dict[str, List[str]] = {
    "Pharmacologic Substance": [
        "What is the mechanism of action of {concept_name}?",
        (
            "What are the indications and contraindications"
            " for {concept_name}?"
        ),
        "What are the most common adverse effects of {concept_name}?",
        (
            "How does {concept_name} interact with other commonly"
            " prescribed medications?"
        ),
        (
            "What is the recommended dosing and route of"
            " administration for {concept_name}?"
        ),
        (
            "In which clinical scenarios is {concept_name}"
            " considered first-line therapy?"
        ),
        (
            "What pharmacokinetic properties of {concept_name}"
            " are clinically significant?"
        ),
        (
            "What monitoring parameters should be followed"
            " when prescribing {concept_name}?"
        ),
    ],
    "Disease or Syndrome": [
        "What is the pathophysiology of {concept_name}?",
        (
            "What are the most common clinical presentations"
            " of {concept_name}?"
        ),
        (
            "How is {concept_name} diagnosed and what are"
            " the key diagnostic criteria?"
        ),
        (
            "What are the current evidence-based treatment"
            " guidelines for {concept_name}?"
        ),
        (
            "What are the risk factors and predisposing"
            " conditions for {concept_name}?"
        ),
        (
            "What complications can arise from untreated"
            " or poorly managed {concept_name}?"
        ),
        "Describe the epidemiology and prevalence of {concept_name}.",
        (
            "What is the differential diagnosis for a patient"
            " presenting with features of {concept_name}?"
        ),
    ],
    "Therapeutic or Preventive Procedure": [
        "What are the indications for performing {concept_name}?",
        "Describe the key steps involved in {concept_name}.",
        (
            "What are the most common complications"
            " associated with {concept_name}?"
        ),
        (
            "What contraindications should be evaluated"
            " before {concept_name}?"
        ),
        (
            "How does {concept_name} compare to alternative"
            " therapeutic approaches?"
        ),
        (
            "What post-procedural care is recommended"
            " after {concept_name}?"
        ),
    ],
    "Sign or Symptom": [
        "What are the most likely causes of {concept_name}?",
        (
            "What is the appropriate diagnostic workup for a"
            " patient presenting with {concept_name}?"
        ),
        (
            "How does {concept_name} help narrow the"
            " differential diagnosis?"
        ),
        (
            "What red-flag features associated with"
            " {concept_name} require urgent evaluation?"
        ),
        (
            "What is the clinical significance of {concept_name}"
            " in the context of systemic disease?"
        ),
        (
            "How is {concept_name} graded or classified"
            " in clinical practice?"
        ),
    ],
    "Diagnostic Procedure": [
        (
            "What are the clinical indications for"
            " ordering {concept_name}?"
        ),
        "How should the results of {concept_name} be interpreted?",
        (
            "What is the sensitivity and specificity of"
            " {concept_name} for its primary indication?"
        ),
        (
            "What patient preparation is required"
            " before {concept_name}?"
        ),
        (
            "What are the limitations and potential"
            " false positives of {concept_name}?"
        ),
        (
            "When is {concept_name} preferred over"
            " alternative diagnostic methods?"
        ),
    ],
    "Body Part, Organ, or Organ Component": [
        (
            "What is the anatomical structure and"
            " function of {concept_name}?"
        ),
        (
            "What are the most common pathologies"
            " affecting {concept_name}?"
        ),
        (
            "How does the blood supply and innervation of"
            " {concept_name} relate to clinical presentations?"
        ),
        (
            "What imaging modalities are most useful"
            " for evaluating {concept_name}?"
        ),
        (
            "What surgical approaches are used for"
            " procedures involving {concept_name}?"
        ),
        (
            "How does embryological development of"
            " {concept_name} explain congenital anomalies?"
        ),
    ],
    "Clinical Attribute": [
        (
            "What is the clinical significance of"
            " {concept_name} in patient assessment?"
        ),
        (
            "How is {concept_name} measured and what"
            " are the normal reference ranges?"
        ),
        (
            "What conditions are associated with"
            " abnormal values of {concept_name}?"
        ),
        "How does {concept_name} influence treatment decisions?",
        (
            "What factors can cause falsely elevated"
            " or decreased {concept_name}?"
        ),
    ],
    "Laboratory or Test Result": [
        (
            "What conditions are associated with"
            " abnormal {concept_name}?"
        ),
        (
            "How should {concept_name} be interpreted"
            " in the clinical context?"
        ),
        (
            "What is the most likely diagnosis when"
            " {concept_name} is significantly elevated?"
        ),
        (
            "What additional tests should be ordered"
            " when {concept_name} is abnormal?"
        ),
        "What pre-analytical factors can affect {concept_name}?",
        (
            "How does {concept_name} change during the"
            " course of disease progression?"
        ),
    ],
    "Pathologic Function": [
        "What is the underlying mechanism of {concept_name}?",
        (
            "What diseases or conditions are most commonly"
            " associated with {concept_name}?"
        ),
        (
            "How does {concept_name} manifest at the"
            " cellular and tissue level?"
        ),
        (
            "What laboratory or imaging findings are"
            " characteristic of {concept_name}?"
        ),
        "What therapeutic interventions target {concept_name}?",
        (
            "How does {concept_name} contribute to"
            " disease progression?"
        ),
    ],
    "Neoplastic Process": [
        "What are the risk factors and etiology of {concept_name}?",
        (
            "What is the typical histological appearance"
            " of {concept_name}?"
        ),
        (
            "How is {concept_name} staged and what is"
            " the prognosis at each stage?"
        ),
        (
            "What are the current first-line treatment"
            " options for {concept_name}?"
        ),
        (
            "What tumor markers or molecular features"
            " are associated with {concept_name}?"
        ),
        (
            "What screening recommendations exist for"
            " early detection of {concept_name}?"
        ),
        (
            "What are the most common sites of metastasis"
            " for {concept_name}?"
        ),
    ],
    # --- Expanded types below ---
    "Organic Chemical": [
        (
            "What is the chemical structure and"
            " classification of {concept_name}?"
        ),
        (
            "What are the known biological effects"
            " of {concept_name}?"
        ),
        (
            "How is {concept_name} used in pharmaceutical"
            " or clinical applications?"
        ),
        (
            "What toxicity or safety concerns are"
            " associated with {concept_name}?"
        ),
    ],
    "Clinical Drug": [
        (
            "What are the approved indications"
            " for {concept_name}?"
        ),
        (
            "What is the standard dosing regimen"
            " for {concept_name}?"
        ),
        (
            "What drug interactions should be considered"
            " when prescribing {concept_name}?"
        ),
        (
            "What are the most common adverse reactions"
            " reported with {concept_name}?"
        ),
        (
            "What patient populations require dose"
            " adjustment for {concept_name}?"
        ),
    ],
    "Amino Acid, Peptide, or Protein": [
        (
            "What is the biological function"
            " of {concept_name}?"
        ),
        (
            "How is {concept_name} used as a biomarker"
            " in clinical practice?"
        ),
        (
            "What diseases are associated with"
            " abnormal levels of {concept_name}?"
        ),
        (
            "What is the role of {concept_name}"
            " in cellular signaling or metabolism?"
        ),
    ],
    "Injury or Poisoning": [
        (
            "What is the clinical presentation"
            " of {concept_name}?"
        ),
        (
            "What is the recommended initial management"
            " for {concept_name}?"
        ),
        (
            "What complications can arise"
            " from {concept_name}?"
        ),
        (
            "What are the most common mechanisms"
            " or causes of {concept_name}?"
        ),
        (
            "What imaging or diagnostic studies are"
            " indicated for {concept_name}?"
        ),
    ],
    "Finding": [
        (
            "What is the clinical significance"
            " of {concept_name}?"
        ),
        (
            "What conditions should be considered when"
            " {concept_name} is identified?"
        ),
        (
            "How does {concept_name} influence"
            " the diagnostic workup?"
        ),
        (
            "What follow-up is recommended when"
            " {concept_name} is detected?"
        ),
    ],
    "Biologically Active Substance": [
        (
            "What is the physiological role"
            " of {concept_name}?"
        ),
        (
            "How do abnormal levels of {concept_name}"
            " manifest clinically?"
        ),
        (
            "What therapeutic agents target or modulate"
            " {concept_name}?"
        ),
        (
            "How is {concept_name} measured"
            " in clinical settings?"
        ),
    ],
    "Bacterium": [
        (
            "What infections are commonly caused"
            " by {concept_name}?"
        ),
        (
            "What is the recommended antibiotic therapy"
            " for {concept_name} infections?"
        ),
        (
            "What are the virulence factors"
            " of {concept_name}?"
        ),
        (
            "How is {concept_name} identified"
            " in the clinical laboratory?"
        ),
        (
            "What antibiotic resistance patterns are"
            " associated with {concept_name}?"
        ),
    ],
    "Enzyme": [
        (
            "What biochemical reaction does"
            " {concept_name} catalyze?"
        ),
        (
            "What clinical conditions are associated"
            " with deficiency of {concept_name}?"
        ),
        (
            "How is {concept_name} used as a diagnostic"
            " marker in clinical practice?"
        ),
        (
            "What drugs inhibit or induce"
            " {concept_name}?"
        ),
    ],
    "Immunologic Factor": [
        (
            "What is the role of {concept_name}"
            " in the immune response?"
        ),
        (
            "How is {concept_name} used in diagnostic"
            " or therapeutic applications?"
        ),
        (
            "What diseases are associated with"
            " dysregulation of {concept_name}?"
        ),
        (
            "How does {concept_name} interact with"
            " other components of the immune system?"
        ),
    ],
    "Laboratory Procedure": [
        (
            "What are the clinical indications"
            " for performing {concept_name}?"
        ),
        (
            "How are the results of {concept_name}"
            " interpreted clinically?"
        ),
        (
            "What specimen requirements and"
            " pre-analytical factors affect {concept_name}?"
        ),
        (
            "What are the limitations"
            " of {concept_name}?"
        ),
    ],
    "Medical Device": [
        (
            "What are the clinical indications"
            " for using {concept_name}?"
        ),
        (
            "What complications are associated"
            " with {concept_name}?"
        ),
        (
            "How does {concept_name} compare to"
            " alternative devices or approaches?"
        ),
        (
            "What patient selection criteria apply"
            " for {concept_name}?"
        ),
    ],
    "Congenital Abnormality": [
        (
            "What is the embryological basis"
            " of {concept_name}?"
        ),
        (
            "How is {concept_name} diagnosed"
            " prenatally and postnatally?"
        ),
        (
            "What are the associated anomalies"
            " commonly seen with {concept_name}?"
        ),
        (
            "What are the current management options"
            " for {concept_name}?"
        ),
        (
            "What genetic or environmental factors"
            " contribute to {concept_name}?"
        ),
    ],
    "Hazardous or Poisonous Substance": [
        (
            "What are the toxic effects"
            " of {concept_name} on the human body?"
        ),
        (
            "What is the recommended treatment"
            " for {concept_name} exposure?"
        ),
        (
            "What are the routes of exposure"
            " for {concept_name}?"
        ),
        (
            "What laboratory findings are characteristic"
            " of {concept_name} poisoning?"
        ),
    ],
    "Antibiotic": [
        (
            "What is the spectrum of activity"
            " of {concept_name}?"
        ),
        (
            "What are the primary clinical indications"
            " for {concept_name}?"
        ),
        (
            "What resistance mechanisms affect"
            " the efficacy of {concept_name}?"
        ),
        (
            "What are the major adverse effects"
            " of {concept_name}?"
        ),
        (
            "How should {concept_name} be dosed"
            " in renal or hepatic impairment?"
        ),
    ],
    "Mental or Behavioral Dysfunction": [
        (
            "What are the diagnostic criteria"
            " for {concept_name}?"
        ),
        (
            "What are the first-line pharmacological"
            " treatments for {concept_name}?"
        ),
        (
            "What psychotherapeutic approaches are"
            " effective for {concept_name}?"
        ),
        (
            "What are the risk factors and"
            " comorbidities of {concept_name}?"
        ),
        (
            "How is {concept_name} differentiated"
            " from related conditions?"
        ),
    ],
    "Anatomical Abnormality": [
        (
            "What is the clinical significance"
            " of {concept_name}?"
        ),
        (
            "How is {concept_name} typically"
            " diagnosed on imaging?"
        ),
        (
            "What symptoms or complications"
            " are associated with {concept_name}?"
        ),
        (
            "What treatment options exist"
            " for {concept_name}?"
        ),
    ],
    "Virus": [
        (
            "What diseases are caused"
            " by {concept_name}?"
        ),
        (
            "How is {concept_name} transmitted"
            " and what are the risk factors?"
        ),
        (
            "What is the recommended treatment"
            " or prophylaxis for {concept_name}?"
        ),
        (
            "How is {concept_name} diagnosed"
            " in the clinical laboratory?"
        ),
        (
            "What vaccines are available"
            " against {concept_name}?"
        ),
    ],
    "Body Location or Region": [
        (
            "What are the anatomical boundaries"
            " of {concept_name}?"
        ),
        (
            "What clinically important structures"
            " are found in {concept_name}?"
        ),
        (
            "What pathologies commonly affect"
            " {concept_name}?"
        ),
        (
            "What surgical approaches are used"
            " to access {concept_name}?"
        ),
    ],
}

# Fallback templates for semantic types not in the map above
DEFAULT_QUESTION_TEMPLATES: List[str] = [
    "What is {concept_name} and what is its clinical significance?",
    "Describe the role of {concept_name} in clinical practice.",
    "What are the current evidence-based guidelines regarding {concept_name}?",
    "How does {concept_name} relate to patient outcomes?",
]

# Flat list kept for backward compatibility (union of all type-specific
# templates).  Used only by _generate_template_seeds when semantic type
# is unknown.
MEDICAL_QUESTION_TEMPLATES: List[str] = DEFAULT_QUESTION_TEMPLATES + [
    t
    for templates in TEMPLATES_BY_SEMANTIC_TYPE.values()
    for t in templates
]

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

_UMLS_CONCEPTS_BY_SEMANTIC_TYPE_QUERY = """\
MATCH (c:UMLSConcept)-[:HAS_SEMANTIC_TYPE]->(st:UMLSSemanticType)
WHERE st.type_name = $semantic_type
  AND c.preferred_name IS NOT NULL
  AND size(c.preferred_name) > 3
RETURN c.preferred_name AS preferred_name,
       c.cui AS cui,
       st.type_name AS semantic_type
ORDER BY rand()
LIMIT $limit
"""


def _count_citations(rag_response: Any) -> int:
    """Count the number of source citations in a RAG response.

    Supports the ``RAGResponse`` dataclass (``sources`` attribute)
    and plain dicts with a ``sources`` key.
    """
    sources = getattr(rag_response, "sources", None)
    if sources is None and isinstance(rag_response, dict):
        sources = rag_response.get("sources", [])
    if sources is None:
        return 0
    return len(sources)


def compute_confidence_score(
    citation_count: int,
    min_citations: int,
) -> float:
    """Compute a confidence score based on citation count.

    The score is bounded in [0.0, 1.0] and monotonically
    non-decreasing with respect to ``citation_count``.

    Parameters
    ----------
    citation_count:
        Number of citations found (non-negative integer).
    min_citations:
        Minimum citation threshold (positive integer).

    Returns
    -------
    float
        Confidence score in [0.0, 1.0].
    """
    if citation_count < min_citations:
        ratio = citation_count / max(min_citations, 1)
        return max(0.3 * ratio, 0.0)
    else:
        denom = max(citation_count + 2, 1)
        return min(
            0.7 + 0.3 * (citation_count / denom),
            1.0,
        )


def _extract_response_text(rag_response: Any) -> str:
    """Extract the response text from a RAG response object."""
    text = getattr(rag_response, "response", None)
    if text is None and isinstance(rag_response, dict):
        text = rag_response.get("response", "")
    return text or ""


def _extract_citations(rag_response: Any) -> List[str]:
    """Extract citation strings from a RAG response.

    Returns a list of ``"document_title (chunk_id)"`` strings.
    """
    sources = getattr(rag_response, "sources", None)
    if sources is None and isinstance(rag_response, dict):
        sources = rag_response.get("sources", [])
    if not sources:
        return []

    citations: List[str] = []
    for src in sources:
        title = getattr(src, "document_title", None)
        if title is None and isinstance(src, dict):
            title = src.get("document_title", "")
        chunk_id = getattr(src, "chunk_id", None)
        if chunk_id is None and isinstance(src, dict):
            chunk_id = src.get("chunk_id", "")
        if title:
            citation = f"{title} ({chunk_id})" if chunk_id else title
            citations.append(citation)
    return citations


def _build_context_summary(rag_response: Any) -> str:
    """Build a context summary from the RAG response sources.

    Concatenates source excerpts into a single context string.
    """
    sources = getattr(rag_response, "sources", None)
    if sources is None and isinstance(rag_response, dict):
        sources = rag_response.get("sources", [])
    if not sources:
        return ""

    excerpts: List[str] = []
    for src in sources:
        excerpt = getattr(src, "excerpt", None)
        if excerpt is None and isinstance(src, dict):
            excerpt = src.get("excerpt", "")
        if excerpt:
            excerpts.append(excerpt.strip())
    return "\n\n".join(excerpts)


def _absorb_remainder(
    allocation: Dict[str, int],
    ordered_types: List[str],
    target_count: int,
) -> Dict[str, int]:
    """Adjust ``allocation`` so values sum to exactly ``target_count``.

    Any positive rounding remainder is added to the largest current
    allocation (ties broken by the order in ``ordered_types``); any
    negative overshoot is subtracted from the largest allocation.

    This is the "remainder absorbed by the largest allocation" rule
    called out in the fine-tuned-model-regression design (A1 item 1).
    """
    current_sum = sum(allocation.values())
    delta = target_count - current_sum
    if delta == 0 or not ordered_types:
        return allocation

    # Find the type with the largest current allocation (stable by
    # ordered_types so the tiebreak is deterministic).
    largest_type = ordered_types[0]
    for t in ordered_types[1:]:
        if allocation[t] > allocation[largest_type]:
            largest_type = t

    allocation[largest_type] = max(
        allocation[largest_type] + delta, 0
    )
    return allocation


# ---------------------------------------------------------------------------
# RAGQAStrategy
# ---------------------------------------------------------------------------


class RAGQAStrategy:
    """Generate Q&A pairs using RAG pipeline gold answers.

    This strategy generates seed medical questions from two sources
    (UMLS concept names and semantic-type-aware question templates),
    runs them through the existing RAG pipeline, and captures the
    cited responses as high-quality training targets.

    Pairs with fewer than ``min_citations`` source citations are flagged
    as low-confidence. Questions where the RAG pipeline fails are
    skipped with the failure reason logged.
    """

    def __init__(
        self,
        rag_service: Any,
        neo4j_client: Any,
        umls_client: Any,
        question_rewriter: Optional[LLMQuestionRewriter] = None,
        quality_filter: Optional[QualityFilter] = None,
        token_budget_manager: Optional[TokenBudgetManager] = None,
    ) -> None:
        """Initialise the strategy.

        Args:
            rag_service: The existing ``RAGService`` instance for
                generating cited responses.
            neo4j_client: A Neo4j client with an async ``execute_query``
                method for querying UMLS concepts and chapter headings.
            umls_client: The ``UMLSClient`` for UMLS concept lookups.
            question_rewriter: Optional ``LLMQuestionRewriter`` for
                transforming template questions into conversational
                phrasing.  When ``None``, seed questions are used as-is.
            quality_filter: Optional ``QualityFilter`` for rejecting
                MCQ-style, textbook-style, and malformed pairs.  When
                ``None``, no quality filtering is applied.
            token_budget_manager: Optional ``TokenBudgetManager`` for
                checking and enforcing token budget limits.  When
                ``None``, no token budget checks are applied.
        """
        self._rag = rag_service
        self._neo4j = neo4j_client
        self._umls = umls_client
        self._question_rewriter = question_rewriter
        self._quality_filter = quality_filter
        self._token_budget_manager = token_budget_manager

    # ------------------------------------------------------------------
    # Per-type allocation helper (fine-tuned-model-regression Property 3)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_type_allocation(
        target_count: int,
        types: List[str],
        target_types: Optional[List[str]] = None,
        per_type_floor: float = 0.10,
    ) -> Dict[str, int]:
        """Compute per-semantic-type seed budget with an enforced floor.

        Allocates ``target_count`` seeds across ``types`` so that each
        member of ``target_types`` (the semantic types exercised by the
        evaluation set) receives at least
        ``ceil(target_count * per_type_floor)`` seeds, while the
        remaining budget is split proportionally across the remaining
        ("non-target") types.

        The returned dict is keyed by semantic type. Its values sum to
        exactly ``target_count`` — any rounding remainder is absorbed by
        the largest allocation (the type with the most seeds after the
        proportional split) so the total budget is preserved.

        Args:
            target_count: Total seeds to allocate across all types.
            types: All semantic types that should receive a budget
                (typically the ``active_types`` list used by
                ``generate_seed_questions``).
            target_types: The types subject to the per-type floor
                (defaults to :data:`EVAL_SEMANTIC_TYPES` — the five
                semantic types exercised by the 50-question evaluation
                set). Any ``target_types`` entry that is not in
                ``types`` is ignored.
            per_type_floor: Fraction of ``target_count`` reserved for
                each target type (defaults to ``0.10``, i.e. 10%).

        Returns:
            ``Dict[str, int]`` mapping every member of ``types`` to a
            non-negative seed count. Values sum to ``target_count``.

        Notes:
            * When ``target_count`` is too small to satisfy the floor
              for every target type (e.g. ``target_count=3`` with a
              0.10 floor on 5 target types would require ≥ 5 seeds
              total), target-type allocations are clamped and shared as
              evenly as possible — the final sum still equals
              ``target_count``. This matches the practical case where
              small smoke-test runs still exercise a subset of types.
            * Non-target types always receive the residual budget split
              proportionally (minimum one seed per non-target type when
              any residual remains).
        """
        if target_count <= 0 or not types:
            return {t: 0 for t in types}

        # De-duplicate while preserving caller order so the largest
        # allocation tiebreak (remainder absorption) is deterministic.
        seen: set = set()
        ordered_types: List[str] = []
        for t in types:
            if t not in seen:
                seen.add(t)
                ordered_types.append(t)

        if target_types is None:
            target_types = list(EVAL_SEMANTIC_TYPES)

        target_set = set(target_types) & set(ordered_types)
        non_target = [t for t in ordered_types if t not in target_set]
        target_in_order = [t for t in ordered_types if t in target_set]

        allocation: Dict[str, int] = {t: 0 for t in ordered_types}

        if not target_in_order:
            # No eval types among the active types — fall back to an
            # even split across all active types (matches the legacy
            # ``budget // len(active_types)`` shape).
            base = target_count // len(ordered_types)
            remainder = target_count - base * len(ordered_types)
            for t in ordered_types:
                allocation[t] = base
            # Spread the remainder onto the first ``remainder`` types.
            for t in ordered_types[:remainder]:
                allocation[t] += 1
            return allocation

        # --- Reserve the per-type floor for each target type. --------
        floor = max(math.ceil(target_count * per_type_floor), 1)
        reserved_total = floor * len(target_in_order)

        if reserved_total >= target_count:
            # Not enough total budget to satisfy every floor; share the
            # available budget as evenly as possible across target
            # types and leave non-target types with zero.
            base = target_count // len(target_in_order)
            remainder = target_count - base * len(target_in_order)
            for t in target_in_order:
                allocation[t] = base
            for t in target_in_order[:remainder]:
                allocation[t] += 1
            # Non-target types stay at zero (initialised above).
            return _absorb_remainder(allocation, ordered_types, target_count)

        # Reserve the floor for each target type up-front.
        for t in target_in_order:
            allocation[t] = floor

        residual = target_count - reserved_total

        # --- Split residual budget across non-target types ---------------
        # When there are no non-target types, the residual goes back
        # into the target types so the sum equals ``target_count``.
        if non_target and residual > 0:
            base = residual // len(non_target)
            remainder = residual - base * len(non_target)
            for t in non_target:
                allocation[t] = base
            for t in non_target[:remainder]:
                allocation[t] += 1
        elif residual > 0:
            # No non-target types: spread the residual across the target
            # types evenly (on top of the reserved floor).
            base = residual // len(target_in_order)
            remainder = residual - base * len(target_in_order)
            for t in target_in_order:
                allocation[t] += base
            for t in target_in_order[:remainder]:
                allocation[t] += 1

        return _absorb_remainder(allocation, ordered_types, target_count)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_seed_questions(
        self,
        target_count: int,
        semantic_types: Optional[List[str]] = None,
        rewrite_progress_callback: Optional[Callable[[int, int], None]] = None,
        type_allocation: Optional[Dict[str, int]] = None,
    ) -> List[SeedQuestion]:
        """Generate seed questions from two sources.

        Sources:
            1. UMLS concept names with clinical semantic types
               (using TEMPLATES_BY_SEMANTIC_TYPE for
               type-appropriate questions)
            2. Semantic-type-aware medical question templates
               filled with concept names (derived from MedQA,
               MedMCQA, PubMedQA benchmark question-stem patterns)

        Args:
            target_count: Total number of seed questions to produce.
                The budget is split evenly across the two sources.
            semantic_types: Optional list of UMLS semantic type strings
                to include. When provided, only these types are used
                for seed generation with stratified budget allocation.
                When ``None`` or empty, all CLINICAL_SEMANTIC_TYPES
                are used (preserving backward compatibility).
            type_allocation: Optional per-semantic-type budget
                (produced by :meth:`_compute_type_allocation`) that
                overrides the implicit ``budget // len(active_types)``
                allocation. When provided, each type's budget is split
                evenly across the two sources so every target type
                receives at least the configured floor. When ``None``,
                the legacy proportional allocation is used.

        Returns:
            A list of ``SeedQuestion`` objects.
        """
        from collections import Counter

        # Resolve active type list (empty list treated as None)
        active_types = (
            semantic_types
            if semantic_types
            else CLINICAL_SEMANTIC_TYPES
        )

        logger.info(
            "RAG Q&A: Seed generation — active_types=%d, target=%d, "
            "per_type_budget=%d",
            len(active_types),
            target_count,
            target_count // len(active_types) if active_types else 0,
        )

        # Split the per-type allocation across the two sources (UMLS
        # concept + template) so each source gets roughly half. Source 1
        # (UMLS concept seeds) receives the floor(alloc/2) and source 2
        # (templates) absorbs the remainder. This preserves the existing
        # "budget split 50/50 across sources" behaviour while keeping
        # the per-type floor.
        umls_type_allocation: Optional[Dict[str, int]] = None
        template_type_allocation: Optional[Dict[str, int]] = None
        if type_allocation is not None:
            umls_type_allocation = {}
            template_type_allocation = {}
            for t in active_types:
                alloc = type_allocation.get(t, 0)
                umls_share = alloc // 2
                umls_type_allocation[t] = umls_share
                template_type_allocation[t] = alloc - umls_share

        # Split budget across two sources
        umls_budget = target_count // 2
        template_budget = target_count - umls_budget

        seeds: List[SeedQuestion] = []

        # Source 1: UMLS concept names with clinical semantic types
        umls_seeds = await self._generate_umls_concept_seeds(
            umls_budget,
            semantic_types=active_types,
            type_allocation=umls_type_allocation,
        )
        seeds.extend(umls_seeds)
        logger.info(
            "RAG Q&A: Generated %d UMLS concept seed questions",
            len(umls_seeds),
        )

        # Source 2: Medical question templates
        template_seeds = await self._generate_template_seeds(
            template_budget,
            semantic_types=active_types,
            type_allocation=template_type_allocation,
        )
        seeds.extend(template_seeds)
        logger.info(
            "RAG Q&A: Generated %d template seed questions",
            len(template_seeds),
        )

        # Log per-type distribution
        type_counts = Counter(
            s.semantic_type for s in seeds if s.semantic_type
        )
        logger.info(
            "RAG Q&A: Seed distribution — types=%s, counts=%s, "
            "total=%d (target: %d)",
            [t for t in active_types],
            dict(type_counts),
            len(seeds),
            target_count,
        )

        # Rewrite template questions into conversational phrasing
        if self._question_rewriter is not None and seeds:
            logger.info(
                "RAG Q&A: Rewriting %d seed questions via LLM",
                len(seeds),
            )
            seeds = await self._question_rewriter.rewrite_questions(
                seeds, progress_callback=rewrite_progress_callback
            )
            logger.info(
                "RAG Q&A: Rewriting complete — %d succeeded, %d failed",
                self._question_rewriter.success_count,
                self._question_rewriter.failure_count,
            )

        return seeds

    async def generate(
        self,
        target_count: int,
        semantic_types: Optional[List[str]] = None,
        min_citations: int = 2,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        rewrite_progress_callback: Optional[Callable[[int, int], None]] = None,
        partial_save_path: Optional[Any] = None,
        per_type_floor: float = 0.10,
    ) -> List[InstructionTuningPair]:
        """Generate RAG-based Q&A instruction-tuning pairs.

        Runs seed questions through the RAG pipeline, captures cited
        responses as gold answers, and produces instruction-tuning pairs.

        Args:
            target_count: Desired number of pairs to produce.
            semantic_types: Optional list of UMLS semantic type strings
                to include. When provided, seed questions are generated
                only from these types with stratified budget allocation.
                When ``None``, all CLINICAL_SEMANTIC_TYPES are used.
            min_citations: Minimum number of source citations for a
                response to be considered high-confidence. Responses
                with fewer citations are flagged as low-confidence
                (Requirement 2.3).
            progress_callback: Optional ``(generated, target)`` callback
                invoked after each pair is produced.
            rewrite_progress_callback: Optional ``(completed, total)``
                callback invoked during the LLM question rewriting phase.
            per_type_floor: Minimum fraction of the seed pool reserved
                for each semantic type exercised by the evaluation set
                (see :data:`EVAL_SEMANTIC_TYPES`). Defaults to ``0.10``
                — this enforces the per-type training-data balance
                required by fine-tuned-model-regression Property 3
                (Requirements 2.2–2.5), so no single eval type is
                starved by the underlying `//` allocation.

        Returns:
            A list of ``InstructionTuningPair`` objects with
            ``metadata.strategy == "rag"``.
        """
        # Generate more seeds than target to account for RAG failures
        # (same multiplier as before — preserved by design spec A1).
        seed_count = int(target_count * 1.5)

        # Resolve active type list (empty list treated as None) so the
        # allocation dict keys match the types actually queried downstream.
        active_types: List[str] = (
            list(semantic_types)
            if semantic_types
            else list(CLINICAL_SEMANTIC_TYPES)
        )

        # Compute the per-type allocation ONCE here. Each target
        # (eval) type receives at least ``ceil(seed_count * per_type_floor)``
        # seeds; any remainder is absorbed by the largest allocation.
        type_allocation = self._compute_type_allocation(
            target_count=seed_count,
            types=active_types,
            target_types=EVAL_SEMANTIC_TYPES,
            per_type_floor=per_type_floor,
        )

        logger.info(
            "RAG Q&A: Per-type seed allocation (floor=%.2f, "
            "seed_count=%d): %s",
            per_type_floor,
            seed_count,
            {
                t: type_allocation[t]
                for t in active_types
                if type_allocation.get(t, 0) > 0
            },
        )

        seeds = await self.generate_seed_questions(
            seed_count,
            semantic_types=active_types,
            rewrite_progress_callback=rewrite_progress_callback,
            type_allocation=type_allocation,
        )

        if not seeds:
            logger.warning("RAG Q&A: No seed questions generated")
            return []

        # Persist rewritten seeds to disk so they survive crashes.
        # Saves to a sibling file next to the partial save path.
        if partial_save_path is not None:
            from pathlib import Path as _Path
            seeds_path = _Path(str(partial_save_path)).parent / "rewritten_seeds.jsonl"
            try:
                with seeds_path.open("w", encoding="utf-8") as fh:
                    for seed in seeds:
                        import json as _json
                        fh.write(_json.dumps({
                            "question": seed.question,
                            "source": seed.source,
                            "semantic_type": seed.semantic_type,
                            "concept_name": seed.concept_name,
                        }, ensure_ascii=False) + "\n")
                logger.info(
                    "RAG Q&A: Persisted %d rewritten seeds to %s",
                    len(seeds), seeds_path,
                )
            except Exception as exc:
                logger.warning(
                    "RAG Q&A: Failed to persist rewritten seeds: %s", exc
                )

        logger.info(
            "RAG Q&A: Running %d seed questions through RAG pipeline, "
            "targeting %d pairs",
            len(seeds),
            target_count,
        )

        pairs: List[InstructionTuningPair] = []
        _refusal_count = 0
        _summarized_count = 0

        # ---------------------------------------------------------------
        # Per-type yield tracking for the top-up loop
        # (fine-tuned-model-regression Task 5.3, Requirements 2.2–2.5).
        #
        # ``_allocated_by_type`` snapshots the seed-level per-type floor
        # computed by ``_compute_type_allocation``. ``_accepted_by_type``
        # counts accepted pairs per type so we can detect types that
        # fall below 80% of their allocation and enqueue top-up seeds
        # from Neo4j for *just those types*.
        #
        # ``_seeds_consumed`` tracks how many seeds we have handed to
        # ``_process_seed`` across both the initial pool and any top-up
        # pass.  The 4× ``target_count`` cap below bounds runtime so a
        # stubborn type (e.g. LOINC-heavy Diagnostic Procedure) cannot
        # drive an unbounded top-up loop.
        # ---------------------------------------------------------------
        _target_types: List[str] = [
            t for t in active_types if t in EVAL_SEMANTIC_TYPES
        ]
        _allocated_by_type: Dict[str, int] = {
            t: type_allocation.get(t, 0) for t in _target_types
        }
        _accepted_by_type: Dict[str, int] = {t: 0 for t in _target_types}
        _TOPUP_FLOOR: float = 0.80
        _MAX_TOTAL_SEEDS: int = int(target_count * 4.0)
        _seeds_consumed: int = 0

        def _track_acceptance(pair: InstructionTuningPair) -> None:
            """Record an accepted pair against its semantic type."""
            st = getattr(pair.metadata, "semantic_type", None)
            if st in _accepted_by_type:
                _accepted_by_type[st] += 1

        # System prompt for token budget estimation — matches production
        # usage in qlora_trainer.py.
        from .qlora_trainer import _SYSTEM_PROMPT

        # Open partial save file for incremental writing
        partial_fh = None
        _write_lock = threading.Lock()
        if partial_save_path is not None:
            try:
                from pathlib import Path as _P
                _P(partial_save_path).parent.mkdir(
                    parents=True, exist_ok=True
                )
                partial_fh = open(
                    partial_save_path, "w", encoding="utf-8"
                )
            except Exception as exc:
                logger.warning(
                    "RAG Q&A: Could not open partial save file: %s",
                    exc,
                )

        # Concurrency control — limit parallel DeepSeek calls
        _MAX_CONCURRENT = 8
        _sem = asyncio.Semaphore(_MAX_CONCURRENT)
        _pairs_count = 0  # atomic-ish counter for early stop

        async def _process_seed(seed: "SeedQuestion") -> Optional[InstructionTuningPair]:
            nonlocal _pairs_count, _refusal_count, _summarized_count
            # Early exit if we already have enough pairs
            if _pairs_count >= target_count:
                return None

            async with _sem:
                if _pairs_count >= target_count:
                    return None

                try:
                    rag_response = await self._rag.generate_response(
                        query=seed.question,
                        user_id="ml-training-pipeline",
                        skip_query_classification=True,
                    )
                except Exception as exc:
                    logger.warning(
                        "RAG Q&A: RAG failed for '%s' — skipping: %s",
                        seed.question[:80],
                        exc,
                    )
                    return None

                response_text = _extract_response_text(rag_response)
                if not response_text.strip():
                    logger.warning(
                        "RAG Q&A: Empty response for '%s' — skipping",
                        seed.question[:80],
                    )
                    return None

                citation_count = _count_citations(rag_response)
                citations = _extract_citations(rag_response)
                context_summary = _build_context_summary(rag_response)

                # ---- Refusal detection and formatting ----
                pair_is_refusal = False

                if is_refusal_response(response_text):
                    # Check for refusal-then-fabrication pattern
                    if has_refusal_then_fabrication(response_text):
                        logger.info(
                            "RAG Q&A: Refusal-then-fabrication detected "
                            "for '%s' — skipping",
                            seed.question[:80],
                        )
                        return None

                    # Format as a concise conversational refusal
                    response_text = format_refusal(
                        seed.question, response_text
                    )
                    pair_is_refusal = True
                    _refusal_count += 1

                confidence = compute_confidence_score(
                    citation_count, min_citations
                )

                source_concepts: List[str] = []
                if seed.concept_name:
                    source_concepts.append(seed.concept_name)

                pair = InstructionTuningPair(
                    instruction=seed.question,
                    context=(
                        context_summary
                        if context_summary
                        else response_text[:500]
                    ),
                    response=response_text,
                    metadata=PairMetadata(
                        strategy="rag",
                        source_concepts=source_concepts,
                        confidence_score=round(confidence, 4),
                        source_document=(
                            citations[0] if citations else None
                        ),
                        chunk_ids=[
                            c.split("(")[-1].rstrip(")")
                            for c in citations
                            if "(" in c
                        ] or None,
                        semantic_type=seed.semantic_type,
                    ),
                )

                # ---- Token budget check (non-refusal pairs) ----
                if (
                    not pair_is_refusal
                    and self._token_budget_manager is not None
                ):
                    if not self._token_budget_manager.fits_budget(
                        pair, _SYSTEM_PROMPT
                    ):
                        # Attempt to summarize the response
                        target_response_tokens = (
                            self._token_budget_manager.max_tokens
                            - self._token_budget_manager.estimate_tokens(
                                _SYSTEM_PROMPT
                            )
                            - self._token_budget_manager.estimate_tokens(
                                pair.instruction
                            )
                            - self._token_budget_manager.estimate_tokens(
                                pair.context or ""
                            )
                            - 20  # chat template overhead
                        )
                        summarized = (
                            await self._token_budget_manager.summarize_response(
                                pair.response,
                                max(target_response_tokens, 100),
                            )
                        )
                        if summarized is not None:
                            pair = InstructionTuningPair(
                                instruction=pair.instruction,
                                context=pair.context,
                                response=summarized,
                                metadata=pair.metadata,
                            )
                            _summarized_count += 1
                        else:
                            logger.info(
                                "RAG Q&A: Token budget exceeded for "
                                "'%s' — skipping",
                                seed.question[:80],
                            )
                            return None

                # ---- Quality filtering ----
                if self._quality_filter is not None:
                    filter_result = self._quality_filter.evaluate(
                        pair, is_refusal=pair_is_refusal
                    )
                    if not filter_result.passed:
                        return None

                return pair

        async def _drain_seed_batch(
            seed_list: List["SeedQuestion"],
        ) -> None:
            """Run ``_process_seed`` over ``seed_list`` in concurrent batches.

            Preserves the existing ``asyncio.Semaphore(8)`` concurrency
            pattern, the partial-save-per-accepted-pair contract, and
            the per-type acceptance tracking needed by the top-up
            loop. Stops early once ``_pairs_count`` reaches
            ``target_count`` so the cap is honoured both during the
            initial pool and any top-up pass.
            """
            nonlocal _pairs_count, _seeds_consumed

            for batch_start in range(0, len(seed_list), _MAX_CONCURRENT * 2):
                if _pairs_count >= target_count:
                    break

                batch = seed_list[
                    batch_start : batch_start + _MAX_CONCURRENT * 2
                ]
                _seeds_consumed += len(batch)
                results = await asyncio.gather(
                    *[_process_seed(s) for s in batch],
                    return_exceptions=True,
                )

                for result in results:
                    if _pairs_count >= target_count:
                        break
                    if isinstance(result, BaseException):
                        logger.warning(
                            "RAG Q&A: Batch item failed: %s", result
                        )
                        continue
                    if result is None:
                        continue

                    pair = result  # type: InstructionTuningPair
                    pairs.append(pair)
                    _pairs_count = len(pairs)
                    _track_acceptance(pair)

                    # Write to disk immediately
                    if partial_fh is not None:
                        try:
                            with _write_lock:
                                partial_fh.write(
                                    pair.to_jsonl_line() + "\n"
                                )
                                partial_fh.flush()
                        except Exception:
                            pass

                    if progress_callback is not None:
                        progress_callback(len(pairs), target_count)

        # ---- Phase 1: Drain the initial seed pool -----------------------
        await _drain_seed_batch(seeds)

        # ---- Phase 2: Top-up loop for under-yielding target types -------
        # (fine-tuned-model-regression Task 5.3, Requirements 2.2–2.5)
        #
        # After the initial seed pool is exhausted, re-check each target
        # type's yield.  Any type whose ``accepted / allocated`` ratio
        # is below ``_TOPUP_FLOOR`` (0.80) receives a fresh batch of
        # Neo4j-sourced seeds whose size is proportional to the shortfall
        # plus a 50% over-fetch buffer to absorb RAG / quality-filter
        # dropout.  We repeat this up to a few rounds, stopping as soon
        # as every target type clears the floor *or* the total seeds
        # handed to ``_process_seed`` hits the 4× ``target_count``
        # cap.  The cap bounds runtime so LOINC-heavy Diagnostic
        # Procedure concepts that disproportionately fail LOINC cleaning
        # and the quality filter cannot drive an unbounded loop.
        _MAX_TOPUP_ROUNDS: int = 5
        for _round in range(_MAX_TOPUP_ROUNDS):
            if _pairs_count >= target_count:
                break
            if _seeds_consumed >= _MAX_TOTAL_SEEDS:
                logger.info(
                    "RAG Q&A: Top-up loop stopping — seed budget cap "
                    "reached (%d >= %d)",
                    _seeds_consumed,
                    _MAX_TOTAL_SEEDS,
                )
                break

            # Identify the types that are still below the 80% floor.
            under_yield: Dict[str, int] = {}
            for t in _target_types:
                allocated = _allocated_by_type.get(t, 0)
                if allocated <= 0:
                    continue
                accepted = _accepted_by_type.get(t, 0)
                floor = int(math.ceil(allocated * _TOPUP_FLOOR))
                shortfall = floor - accepted
                if shortfall > 0:
                    # Over-fetch by 50% so RAG failures, empty
                    # responses, refusals-then-fabrication,
                    # token-budget skips, and quality-filter
                    # rejections do not starve the type on this round.
                    under_yield[t] = int(
                        math.ceil(shortfall * 1.5)
                    )

            if not under_yield:
                logger.info(
                    "RAG Q&A: Top-up loop — every target type met the "
                    "%.0f%% floor on round %d",
                    _TOPUP_FLOOR * 100.0,
                    _round,
                )
                break

            # Respect the global 4× ``target_count`` cap by trimming
            # the total top-up request to the remaining budget.
            remaining_seed_budget = _MAX_TOTAL_SEEDS - _seeds_consumed
            total_requested = sum(under_yield.values())
            if total_requested > remaining_seed_budget > 0:
                scale = remaining_seed_budget / max(total_requested, 1)
                under_yield = {
                    t: max(int(math.ceil(n * scale)), 1)
                    for t, n in under_yield.items()
                }
                # Recompute total after scaling so logs match reality.
                total_requested = sum(under_yield.values())

            logger.info(
                "RAG Q&A: Top-up round %d — enqueuing %d additional "
                "seeds for under-yielding types: %s (accepted so far: "
                "%s, allocated: %s)",
                _round + 1,
                total_requested,
                under_yield,
                {t: _accepted_by_type[t] for t in under_yield},
                {t: _allocated_by_type[t] for t in under_yield},
            )

            # Fetch fresh seeds from Neo4j biased to the under-yielding
            # types.  We reuse ``generate_seed_questions`` with a
            # targeted allocation so the existing LLM rewriter,
            # question-template, and Neo4j-query paths are exercised
            # exactly as in Phase 1 — no pair bypasses existing
            # invariants (quality filter, token budget, refusal
            # formatter still apply downstream in ``_process_seed``).
            topup_allocation: Dict[str, int] = {
                t: under_yield.get(t, 0) for t in under_yield
            }
            topup_total: int = sum(topup_allocation.values())
            if topup_total <= 0:
                break
            try:
                topup_seeds = await self.generate_seed_questions(
                    topup_total,
                    semantic_types=list(under_yield.keys()),
                    rewrite_progress_callback=rewrite_progress_callback,
                    type_allocation=topup_allocation,
                )
            except Exception as exc:
                logger.warning(
                    "RAG Q&A: Top-up seed generation failed on "
                    "round %d: %s — aborting top-up",
                    _round + 1,
                    exc,
                )
                break

            if not topup_seeds:
                logger.info(
                    "RAG Q&A: Top-up round %d — Neo4j returned no "
                    "additional seeds for under-yielding types; "
                    "aborting top-up",
                    _round + 1,
                )
                break

            await _drain_seed_batch(topup_seeds)

        if partial_fh is not None:
            try:
                partial_fh.close()
            except Exception:
                pass

        # ---- Post-generation logging ----
        total_pairs = len(pairs)

        # Compute mean confidence score
        mean_confidence = 0.0
        if total_pairs > 0:
            mean_confidence = sum(
                p.metadata.confidence_score
                for p in pairs
                if p.metadata and p.metadata.confidence_score is not None
            ) / total_pairs

        # Refusal statistics
        refusal_pct = (
            (_refusal_count / total_pairs * 100.0)
            if total_pairs > 0
            else 0.0
        )

        # Quality filter summary
        filter_summary_dict: Dict[str, Any] = {}
        if self._quality_filter is not None:
            summary = self._quality_filter.summarize()
            filter_summary_dict = {
                "total_evaluated": summary.total_evaluated,
                "total_passed": summary.total_passed,
                "total_rejected": summary.total_rejected,
                "rejections_by_reason": summary.rejections_by_reason,
                "pass_rate": round(summary.pass_rate, 4),
            }

        logger.info(
            "RAG Q&A: Generation complete — total_pairs=%d, "
            "refusal_count=%d (%.1f%%), "
            "summarized_count=%d, "
            "mean_confidence=%.4f, "
            "filter_summary=%s",
            total_pairs,
            _refusal_count,
            refusal_pct,
            _summarized_count,
            mean_confidence,
            filter_summary_dict or "N/A",
        )

        # Per-type yield summary (fine-tuned-model-regression Task 5.3,
        # Requirements 2.2–2.5).  Emit one line per target type showing
        # how many pairs were accepted versus the allocation floor, plus
        # a WARNING when a type still sits below the 80% top-up floor
        # (typically because the 4× seed cap was hit or Neo4j ran out
        # of candidate concepts for the type).
        if _target_types:
            per_type_summary = {
                t: {
                    "accepted": _accepted_by_type.get(t, 0),
                    "allocated": _allocated_by_type.get(t, 0),
                }
                for t in _target_types
            }
            logger.info(
                "RAG Q&A: Per-type yield (seeds_consumed=%d, "
                "cap=%d): %s",
                _seeds_consumed,
                _MAX_TOTAL_SEEDS,
                per_type_summary,
            )
            for t in _target_types:
                allocated = _allocated_by_type.get(t, 0)
                if allocated <= 0:
                    continue
                accepted = _accepted_by_type.get(t, 0)
                ratio = accepted / allocated
                if ratio < _TOPUP_FLOOR:
                    logger.warning(
                        "RAG Q&A: Target type '%s' accepted %d/%d "
                        "pairs (%.1f%%) — below the %.0f%% top-up "
                        "floor",
                        t,
                        accepted,
                        allocated,
                        ratio * 100.0,
                        _TOPUP_FLOOR * 100.0,
                    )

        # Warn if refusal percentage is outside 15%–30%
        if total_pairs > 0 and (refusal_pct < 15.0 or refusal_pct > 30.0):
            logger.warning(
                "RAG Q&A: Refusal percentage %.1f%% is outside the "
                "target range of 15%%–30%%",
                refusal_pct,
            )

        # Warn if quality filter rejection rate exceeds 40%
        if self._quality_filter is not None:
            summary = self._quality_filter.summarize()
            if (
                summary.total_evaluated > 0
                and (1.0 - summary.pass_rate) > 0.40
            ):
                logger.warning(
                    "RAG Q&A: Quality filter rejection rate %.1f%% "
                    "exceeds 40%% — potential issue with seed question "
                    "quality",
                    (1.0 - summary.pass_rate) * 100.0,
                )

        return pairs

    # ------------------------------------------------------------------
    # Seed generation helpers
    # ------------------------------------------------------------------

    async def _generate_umls_concept_seeds(
        self,
        budget: int,
        semantic_types: Optional[List[str]] = None,
        type_allocation: Optional[Dict[str, int]] = None,
    ) -> List[SeedQuestion]:
        """Generate seed questions from UMLS concept names.

        Queries Neo4j for UMLSConcept nodes with clinical semantic types
        and generates questions using the concept's preferred name.

        Args:
            budget: Total number of seed questions to produce.
            semantic_types: Optional list of semantic types to use.
                When provided, only these types are queried.
                When ``None``, all CLINICAL_SEMANTIC_TYPES are used.
            type_allocation: Optional per-type seed budget. When
                provided, each type's Neo4j query uses that type's
                allocation as the ``LIMIT`` (with an over-fetch factor
                so downstream filtering does not starve the type). The
                allocation acts as a *floor hint* — eval-set types get
                at least their floor's worth of candidate concepts —
                rather than a strict per-type cap, so the legacy
                behaviour of back-filling the overall budget from
                whichever types produce seeds first is preserved.
                When ``None``, falls back to the legacy
                ``budget // len(active_types)`` proportional
                allocation.
        """
        active_types = (
            semantic_types if semantic_types else CLINICAL_SEMANTIC_TYPES
        )
        seeds: List[SeedQuestion] = []
        # Legacy fallback: even-split allocation (preserves pre-fix
        # behaviour when no allocation is provided).
        per_type_limit = max(budget // len(active_types), 5)

        for semantic_type in active_types:
            if len(seeds) >= budget:
                break

            if type_allocation is not None:
                # Honour the per-type floor as a LIMIT hint; always
                # fetch at least 1 so the Neo4j query is valid, and at
                # least the allocated share so under-represented types
                # actually get the concepts they need.
                per_type_limit_for_query = max(
                    type_allocation.get(semantic_type, 0), 1
                )
            else:
                per_type_limit_for_query = per_type_limit

            try:
                results = await self._neo4j.execute_query(
                    _UMLS_CONCEPTS_BY_SEMANTIC_TYPE_QUERY,
                    {
                        "semantic_type": semantic_type,
                        "limit": per_type_limit_for_query,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "RAG Q&A: Failed to query UMLS concepts for type "
                    "'%s': %s",
                    semantic_type,
                    exc,
                )
                continue

            if not results:
                continue

            for record in results:
                if len(seeds) >= budget:
                    break

                preferred_name = (
                    record.get("preferred_name", "")
                    if isinstance(record, dict)
                    else getattr(record, "preferred_name", "")
                )
                if not preferred_name:
                    continue

                # Clean LOINC-coded fields from the concept name
                preferred_name = clean_concept_name(preferred_name)
                if not preferred_name:
                    continue

                # Pick a template matched to the semantic type
                type_templates = TEMPLATES_BY_SEMANTIC_TYPE.get(
                    semantic_type, DEFAULT_QUESTION_TEMPLATES
                )
                template_idx = len(seeds) % len(type_templates)
                question = type_templates[template_idx].format(
                    concept_name=preferred_name
                )

                seeds.append(
                    SeedQuestion(
                        question=question,
                        source="umls_concept",
                        semantic_type=semantic_type,
                        concept_name=preferred_name,
                    )
                )

        return seeds

    async def _generate_template_seeds(
        self,
        budget: int,
        semantic_types: Optional[List[str]] = None,
        type_allocation: Optional[Dict[str, int]] = None,
    ) -> List[SeedQuestion]:
        """Generate seed questions from medical question templates.

        Uses UMLS concept names to fill in template placeholders,
        producing diverse medical questions.

        Args:
            budget: Total number of seed questions to produce.
            semantic_types: Optional list of semantic types to use.
                When provided, only concepts from these types are
                fetched. When ``None``, all CLINICAL_SEMANTIC_TYPES
                are used.
            type_allocation: Optional per-type seed budget. When
                provided, the underlying concept fetch is biased to
                over-sample under-represented types so the allocation
                floor is honoured. The allocation is a floor hint, not
                a strict per-type cap, so overall budget still drains
                in iteration order when a type yields no usable
                concepts.
        """
        seeds: List[SeedQuestion] = []

        # Fetch a pool of concept names to fill templates. The over-
        # fetch factor (budget * 2) mirrors the legacy behaviour and
        # gives the cleaner/filter headroom.
        concept_pool = await self._fetch_concept_names_for_templates(
            budget * 2,
            semantic_types=semantic_types,
            type_allocation=type_allocation,
        )

        if not concept_pool:
            logger.info(
                "RAG Q&A: No concepts available for template seeds"
            )
            return seeds

        for i, concept_info in enumerate(concept_pool):
            if len(seeds) >= budget:
                break

            name = concept_info.get("preferred_name", "")
            if not name:
                continue

            # Clean LOINC-coded fields from the concept name
            name = clean_concept_name(name)
            if not name:
                continue

            sem_type = concept_info.get("semantic_type")

            # Use semantic-type-aware templates when type is known
            type_templates = (
                TEMPLATES_BY_SEMANTIC_TYPE.get(
                    sem_type, DEFAULT_QUESTION_TEMPLATES
                )
                if sem_type
                else DEFAULT_QUESTION_TEMPLATES
            )
            template_idx = i % len(type_templates)
            question = type_templates[template_idx].format(
                concept_name=name
            )

            seeds.append(
                SeedQuestion(
                    question=question,
                    source="template",
                    semantic_type=sem_type,
                    concept_name=name,
                )
            )

        return seeds

    # ------------------------------------------------------------------
    # Data fetching helpers
    # ------------------------------------------------------------------

    async def _fetch_concept_names_for_templates(
        self,
        limit: int,
        semantic_types: Optional[List[str]] = None,
        type_allocation: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch a diverse pool of UMLS concept names for templates.

        Samples across multiple clinical semantic types for diversity.

        Args:
            limit: Maximum number of concepts to fetch.
            semantic_types: Optional list of semantic types to use.
                When provided, only these types are queried.
                When ``None``, all CLINICAL_SEMANTIC_TYPES are used.
            type_allocation: Optional per-type template-seed budget.
                When provided, each type's Neo4j fetch uses roughly
                ``2 * allocation`` concepts as the pool (the factor-2
                over-fetch mirrors ``_generate_template_seeds`` which
                requests ``budget * 2`` concepts so template dropout
                does not starve any type).
        """
        active_types = semantic_types if semantic_types else CLINICAL_SEMANTIC_TYPES
        concepts: List[Dict[str, Any]] = []
        # Legacy fallback for even-split allocation.
        per_type = max(limit // len(active_types), 3)

        # Shuffle semantic types for variety across runs
        shuffled_types = list(active_types)
        random.shuffle(shuffled_types)

        for semantic_type in shuffled_types:
            if len(concepts) >= limit:
                break

            if type_allocation is not None:
                # Fetch at least twice the allocated share so later
                # filtering does not starve the type. Minimum of 3 to
                # keep parity with the legacy floor.
                per_type_fetch = max(
                    type_allocation.get(semantic_type, 0) * 2, 3
                )
            else:
                per_type_fetch = per_type

            try:
                results = await self._neo4j.execute_query(
                    _UMLS_CONCEPTS_BY_SEMANTIC_TYPE_QUERY,
                    {
                        "semantic_type": semantic_type,
                        "limit": per_type_fetch,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "RAG Q&A: Failed to fetch concepts for type '%s': %s",
                    semantic_type,
                    exc,
                )
                continue

            if results:
                for r in results:
                    record = dict(r) if not isinstance(r, dict) else r
                    concepts.append(record)

        return concepts[:limit]
