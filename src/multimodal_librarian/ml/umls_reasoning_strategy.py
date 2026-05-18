"""
UMLS Relationship Reasoning Q&A Pair Generation Strategy.

Generates multi-hop reasoning Q&A instruction-tuning pairs by traversing
UMLS relationship edges (CAUSES, TREATS, TREATED_BY, PRESENTS_WITH, IS_A,
PART_OF) between concepts. For each relationship path the strategy generates
a question that references all concepts in the path and produces a reasoning
answer with supporting chunk content from EXTRACTED_FROM edges.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import InstructionTuningPair, PairMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default relationship types for traversal
# ---------------------------------------------------------------------------

DEFAULT_RELATIONSHIP_TYPES: List[str] = [
    "cause_of",
    "may_treat",
    "may_be_treated_by",
    "has_finding_site",
    "isa",
    "component_of",
]

# Map from UMLS rela_type values to the template keys used in question
# generation. This lets us keep the human-readable template dictionaries
# keyed by clinical relationship names while querying with actual UMLS
# rela_type values.
_RELA_TO_TEMPLATE_KEY: Dict[str, str] = {
    "cause_of": "CAUSES",
    "has_causative_agent": "CAUSES",
    "may_treat": "TREATS",
    "may_be_treated_by": "TREATED_BY",
    "has_finding_site": "PRESENTS_WITH",
    "finding_site_of": "PRESENTS_WITH",
    "isa": "IS_A",
    "inverse_isa": "IS_A",
    "component_of": "PART_OF",
    "has_component": "PART_OF",
}

# ---------------------------------------------------------------------------
# Valid question styles
# ---------------------------------------------------------------------------

VALID_QUESTION_STYLES = (
    "mixed",
    "conversational",
    "medqa",
    "medmcqa",
    "pubmedqa",
)

# ---------------------------------------------------------------------------
# Question templates keyed by (style, relationship_type)
#
# Each style targets a different benchmark flavour:
#   conversational — open-ended explanatory (original style)
#   medqa          — USMLE vignette / clinical reasoning
#   medmcqa        — direct factual recall (AIIMS/NEET)
#   pubmedqa       — evidence-based yes/no/maybe with context
# ---------------------------------------------------------------------------

# -- Conversational (original) templates -----------------------------------

_CONV_ONE_HOP: Dict[str, List[str]] = {
    "CAUSES": [
        (
            "How does {concept_a} cause {concept_b}, "
            "and what is the underlying mechanism?"
        ),
        (
            "What is the relationship between {concept_a} "
            "and {concept_b} in terms of causation?"
        ),
    ],
    "TREATS": [
        (
            "How does {concept_a} treat {concept_b}, "
            "and what is the evidence for its efficacy?"
        ),
        (
            "What is the therapeutic role of {concept_a} "
            "in managing {concept_b}?"
        ),
    ],
    "TREATED_BY": [
        (
            "What treatments are available for {concept_a}, "
            "and how does {concept_b} address it?"
        ),
        (
            "How is {concept_a} treated by {concept_b} "
            "in clinical practice?"
        ),
    ],
    "PRESENTS_WITH": [
        (
            "What symptoms does {concept_a} present with, "
            "specifically {concept_b}?"
        ),
        (
            "How does {concept_b} manifest as a "
            "presentation of {concept_a}?"
        ),
    ],
    "IS_A": [
        (
            "How is {concept_b} classified as a type of "
            "{concept_a}, and what distinguishes it?"
        ),
        (
            "What is the taxonomic relationship between "
            "{concept_a} and {concept_b}?"
        ),
    ],
    "PART_OF": [
        (
            "How is {concept_b} a component of {concept_a}, "
            "and what is its functional role?"
        ),
        (
            "What is the structural relationship between "
            "{concept_a} and {concept_b}?"
        ),
    ],
}

_CONV_ONE_HOP_DEFAULT: List[str] = [
    (
        "What is the clinical relationship between "
        "{concept_a} and {concept_b}?"
    ),
    (
        "How are {concept_a} and {concept_b} related "
        "in medical practice?"
    ),
]

_CONV_TWO_HOP: List[str] = [
    (
        "Explain the clinical chain: "
        "{concept_a} {relationship_1} {concept_b}, "
        "and {concept_b} {relationship_2} {concept_c}. "
        "How do these relationships connect in clinical reasoning?"
    ),
    (
        "Given that {concept_a} {relationship_1} {concept_b} and "
        "{concept_b} {relationship_2} {concept_c}, what is the "
        "multi-step clinical reasoning that links "
        "{concept_a} to {concept_c}?"
    ),
    (
        "How does the pathway from {concept_a} through "
        "{concept_b} to {concept_c} illustrate the relationship "
        "chain {concept_a} {relationship_1} {concept_b} "
        "{relationship_2} {concept_c}?"
    ),
]

# -- MedQA (USMLE vignette / clinical reasoning) --------------------------

_MEDQA_ONE_HOP: Dict[str, List[str]] = {
    "CAUSES": [
        (
            "A patient presents with {concept_b}. Which of the "
            "following is the most likely underlying cause? "
            "Explain why {concept_a} leads to {concept_b}."
        ),
        (
            "A 55-year-old patient is diagnosed with {concept_b}. "
            "What pathophysiological mechanism links {concept_a} "
            "to the development of {concept_b}?"
        ),
    ],
    "TREATS": [
        (
            "A patient with {concept_b} is started on {concept_a}. "
            "What is the mechanism of action of {concept_a} and "
            "why is it appropriate for {concept_b}?"
        ),
        (
            "Which pharmacological agent is most appropriate for "
            "treating {concept_b}, and how does {concept_a} "
            "achieve its therapeutic effect?"
        ),
    ],
    "TREATED_BY": [
        (
            "A patient presents with {concept_a}. What is the "
            "first-line treatment, and how does {concept_b} "
            "address the underlying pathology?"
        ),
        (
            "For a patient diagnosed with {concept_a}, explain "
            "the rationale for using {concept_b} as a "
            "therapeutic intervention."
        ),
    ],
    "PRESENTS_WITH": [
        (
            "A patient with {concept_a} presents to the "
            "emergency department. Which clinical finding, "
            "specifically {concept_b}, would you most expect, "
            "and why?"
        ),
        (
            "What is the pathophysiological basis for "
            "{concept_a} presenting with {concept_b}?"
        ),
    ],
    "IS_A": [
        (
            "A pathology report classifies a lesion as "
            "{concept_b}. Explain how {concept_b} is a subtype "
            "of {concept_a} and what distinguishes it "
            "from other subtypes."
        ),
        (
            "In the classification of {concept_a}, where does "
            "{concept_b} fit, and what are its distinguishing "
            "clinical features?"
        ),
    ],
    "PART_OF": [
        (
            "During a surgical procedure involving {concept_a}, "
            "the surgeon identifies {concept_b}. What is the "
            "anatomical relationship and functional significance "
            "of {concept_b} within {concept_a}?"
        ),
        (
            "Explain the structural role of {concept_b} as a "
            "component of {concept_a} and its clinical relevance."
        ),
    ],
}

_MEDQA_ONE_HOP_DEFAULT: List[str] = [
    (
        "A patient's workup reveals a connection between "
        "{concept_a} and {concept_b}. What is the most likely "
        "clinical explanation for this relationship?"
    ),
    (
        "On clinical examination, findings suggest a link "
        "between {concept_a} and {concept_b}. Explain the "
        "underlying mechanism."
    ),
]

_MEDQA_TWO_HOP: List[str] = [
    (
        "A patient is diagnosed with {concept_a}, which "
        "{relationship_1} {concept_b}. Subsequently, "
        "{concept_b} {relationship_2} {concept_c}. Trace "
        "the clinical reasoning chain from {concept_a} "
        "to {concept_c}."
    ),
    (
        "Given the pathway {concept_a} {relationship_1} "
        "{concept_b} {relationship_2} {concept_c}, a patient "
        "with {concept_a} develops {concept_c}. What is the "
        "step-by-step pathophysiological explanation?"
    ),
    (
        "A clinical scenario involves {concept_a}, {concept_b}, "
        "and {concept_c}. Knowing that {concept_a} "
        "{relationship_1} {concept_b} and {concept_b} "
        "{relationship_2} {concept_c}, what is the most "
        "likely clinical reasoning?"
    ),
]

# -- MedMCQA (direct factual recall) --------------------------------------

_MEDMCQA_ONE_HOP: Dict[str, List[str]] = {
    "CAUSES": [
        (
            "Which condition is directly caused by "
            "{concept_a}? Explain the role of {concept_a} "
            "in producing {concept_b}."
        ),
        (
            "What is the primary etiological factor linking "
            "{concept_a} to {concept_b}?"
        ),
    ],
    "TREATS": [
        (
            "What is the first-line pharmacological treatment "
            "for {concept_b}? Describe how {concept_a} is used."
        ),
        (
            "Name the drug used to treat {concept_b} and "
            "explain the mechanism of {concept_a}."
        ),
    ],
    "TREATED_BY": [
        (
            "What is the standard treatment for {concept_a}? "
            "Describe the role of {concept_b}."
        ),
        (
            "{concept_a} is managed by which therapeutic "
            "agent? Explain how {concept_b} works."
        ),
    ],
    "PRESENTS_WITH": [
        (
            "What is the characteristic clinical presentation "
            "of {concept_a}? Describe the role of {concept_b} "
            "as a presenting feature."
        ),
        (
            "Name the hallmark sign or symptom of {concept_a}. "
            "How does {concept_b} manifest clinically?"
        ),
    ],
    "IS_A": [
        (
            "{concept_b} belongs to which broader category? "
            "Explain its classification under {concept_a}."
        ),
        (
            "Under the classification of {concept_a}, "
            "identify {concept_b} and its key features."
        ),
    ],
    "PART_OF": [
        (
            "Which structure is a component of {concept_a}? "
            "Describe the role of {concept_b}."
        ),
        (
            "Identify the anatomical component {concept_b} "
            "within {concept_a} and state its function."
        ),
    ],
}

_MEDMCQA_ONE_HOP_DEFAULT: List[str] = [
    (
        "What is the direct clinical association between "
        "{concept_a} and {concept_b}?"
    ),
    (
        "State the relationship between {concept_a} and "
        "{concept_b} in clinical medicine."
    ),
]

_MEDMCQA_TWO_HOP: List[str] = [
    (
        "{concept_a} {relationship_1} {concept_b}, which in "
        "turn {relationship_2} {concept_c}. What is the "
        "complete clinical chain?"
    ),
    (
        "Identify the multi-step relationship: {concept_a} "
        "{relationship_1} {concept_b} and {concept_b} "
        "{relationship_2} {concept_c}. Explain each link."
    ),
    (
        "Trace the factual chain from {concept_a} through "
        "{concept_b} to {concept_c}, given {concept_a} "
        "{relationship_1} {concept_b} and {concept_b} "
        "{relationship_2} {concept_c}."
    ),
]

# -- PubMedQA (evidence-based, research-oriented) -------------------------

_PUBMEDQA_ONE_HOP: Dict[str, List[str]] = {
    "CAUSES": [
        (
            "Based on current evidence, does {concept_a} "
            "cause {concept_b}? Summarize the supporting "
            "findings."
        ),
        (
            "Is there sufficient evidence to establish a "
            "causal link between {concept_a} and {concept_b}? "
            "Explain."
        ),
    ],
    "TREATS": [
        (
            "Does {concept_a} improve outcomes in patients "
            "with {concept_b}? Summarize the evidence."
        ),
        (
            "Is {concept_a} effective for the treatment of "
            "{concept_b} based on available clinical data?"
        ),
    ],
    "TREATED_BY": [
        (
            "Is {concept_b} an effective intervention for "
            "{concept_a}? Review the evidence."
        ),
        (
            "Does treatment with {concept_b} lead to "
            "improved outcomes in {concept_a}? Summarize "
            "the findings."
        ),
    ],
    "PRESENTS_WITH": [
        (
            "Is {concept_b} a reliable clinical indicator "
            "of {concept_a}? What does the evidence show?"
        ),
        (
            "Does the presence of {concept_b} predict "
            "{concept_a}? Summarize the clinical evidence."
        ),
    ],
    "IS_A": [
        (
            "Is the classification of {concept_b} as a "
            "subtype of {concept_a} supported by current "
            "evidence? Explain."
        ),
        (
            "Does current taxonomy support {concept_b} "
            "being categorized under {concept_a}? "
            "Review the evidence."
        ),
    ],
    "PART_OF": [
        (
            "Is {concept_b} consistently identified as a "
            "structural component of {concept_a} in "
            "anatomical studies? Summarize the evidence."
        ),
        (
            "Does the evidence support {concept_b} as a "
            "functional part of {concept_a}? Explain."
        ),
    ],
}

_PUBMEDQA_ONE_HOP_DEFAULT: List[str] = [
    (
        "Is there evidence supporting a clinical relationship "
        "between {concept_a} and {concept_b}? Summarize "
        "the findings."
    ),
    (
        "Based on available research, are {concept_a} and "
        "{concept_b} clinically associated? Explain."
    ),
]

_PUBMEDQA_TWO_HOP: List[str] = [
    (
        "Does the evidence support the chain {concept_a} "
        "{relationship_1} {concept_b} {relationship_2} "
        "{concept_c}? Summarize the findings for each link."
    ),
    (
        "Is there clinical evidence that {concept_a} "
        "{relationship_1} {concept_b} and that {concept_b} "
        "{relationship_2} {concept_c}? Review the data."
    ),
    (
        "Based on current research, does the pathway from "
        "{concept_a} through {concept_b} to {concept_c} "
        "hold? Evaluate the evidence for {concept_a} "
        "{relationship_1} {concept_b} and {concept_b} "
        "{relationship_2} {concept_c}."
    ),
]

# ---------------------------------------------------------------------------
# Template registry — maps style → (one_hop_dict, one_hop_default, two_hop)
# ---------------------------------------------------------------------------

_TEMPLATE_REGISTRY: Dict[
    str,
    Tuple[Dict[str, List[str]], List[str], List[str]],
] = {
    "conversational": (_CONV_ONE_HOP, _CONV_ONE_HOP_DEFAULT, _CONV_TWO_HOP),
    "medqa": (_MEDQA_ONE_HOP, _MEDQA_ONE_HOP_DEFAULT, _MEDQA_TWO_HOP),
    "medmcqa": (
        _MEDMCQA_ONE_HOP,
        _MEDMCQA_ONE_HOP_DEFAULT,
        _MEDMCQA_TWO_HOP,
    ),
    "pubmedqa": (
        _PUBMEDQA_ONE_HOP,
        _PUBMEDQA_ONE_HOP_DEFAULT,
        _PUBMEDQA_TWO_HOP,
    ),
}

# Pre-built "mixed" list: all styles in round-robin order
_ALL_STYLES: List[str] = ["conversational", "medqa", "medmcqa", "pubmedqa"]

# ---------------------------------------------------------------------------
# Backward-compatible aliases for the original template names
# ---------------------------------------------------------------------------

ONE_HOP_QUESTION_TEMPLATES = _CONV_ONE_HOP
DEFAULT_ONE_HOP_TEMPLATES = _CONV_ONE_HOP_DEFAULT
TWO_HOP_QUESTION_TEMPLATES = _CONV_TWO_HOP

# ---------------------------------------------------------------------------
# Answer templates
# ---------------------------------------------------------------------------

ONE_HOP_ANSWER_TEMPLATE = (
    "{concept_a} {relationship} {concept_b}. "
    "{supporting_evidence}"
    "\n\nRelationship chain: {concept_a} {relationship} {concept_b}"
)

TWO_HOP_ANSWER_TEMPLATE = (
    "The clinical reasoning chain connects three concepts: "
    "{concept_a} {relationship_1} {concept_b}, and "
    "{concept_b} {relationship_2} {concept_c}. "
    "{supporting_evidence}"
    "\n\nRelationship chain: {concept_a} {relationship_1} {concept_b} "
    "{relationship_2} {concept_c}"
)

# ---------------------------------------------------------------------------
# Cypher queries
# ---------------------------------------------------------------------------

# Find 1-hop paths between UMLS concepts via specified relationship types.
# The actual schema uses UMLSConcept nodes connected by UMLS_REL edges
# with a rela_type property. Joins through HAS_SEMANTIC_TYPE to ensure
# concept diversity across medical domains (pharmacology, diseases,
# procedures, etc.) rather than clustering around high-connectivity
# hub concepts.
_ONE_HOP_PATHS_QUERY = """\
MATCH (ua:UMLSConcept)-[r:UMLS_REL]->(ub:UMLSConcept)
WHERE r.rela_type IN $relationship_types
  AND ua.preferred_name IS NOT NULL
  AND ub.preferred_name IS NOT NULL
  AND ua.cui <> ub.cui
WITH ua, ub, r
SKIP toInteger(rand() * 1000)
LIMIT $limit
WITH ua, ub, r
WHERE size(ua.preferred_name) > 3
  AND size(ub.preferred_name) > 3
RETURN DISTINCT ua.preferred_name AS concept_a_name,
       ua.cui AS concept_a_cui,
       ub.preferred_name AS concept_b_name,
       ub.cui AS concept_b_cui,
       r.rela_type AS relationship_type
"""

# Find 2-hop paths between UMLS concepts via specified relationship types.
# Uses DISTINCT on concept names to avoid duplicate paths through
# different intermediate nodes.
_TWO_HOP_PATHS_QUERY = """\
MATCH (ua:UMLSConcept)-[r1:UMLS_REL]->(ub:UMLSConcept)-[r2:UMLS_REL]->(uc:UMLSConcept)
WHERE r1.rela_type IN $relationship_types
  AND r2.rela_type IN $relationship_types
  AND ua.cui <> uc.cui
  AND ua.cui <> ub.cui
  AND ub.cui <> uc.cui
  AND ua.preferred_name IS NOT NULL
  AND ub.preferred_name IS NOT NULL
  AND uc.preferred_name IS NOT NULL
  AND size(ua.preferred_name) > 3
  AND size(ub.preferred_name) > 3
  AND size(uc.preferred_name) > 3
WITH ua, ub, uc, r1, r2
SKIP toInteger(rand() * 500)
LIMIT $limit
RETURN DISTINCT ua.preferred_name AS concept_a_name,
       ua.cui AS concept_a_cui,
       ub.preferred_name AS concept_b_name,
       ub.cui AS concept_b_cui,
       uc.preferred_name AS concept_c_name,
       uc.cui AS concept_c_cui,
       r1.rela_type AS relationship_type_1,
       r2.rela_type AS relationship_type_2
"""

# Find chunk IDs linked to a UMLS concept via Concept→SAME_AS→UMLSConcept
# and Concept→EXTRACTED_FROM→Chunk
_CONCEPT_CHUNKS_QUERY = """\
MATCH (c:Concept)-[:SAME_AS]->(u:UMLSConcept {cui: $cui})
MATCH (c)-[:EXTRACTED_FROM]->(ch:Chunk)
RETURN ch.chunk_id AS chunk_id
LIMIT $limit
"""


def _count_tokens(text: str) -> int:
    """Approximate token count by splitting on whitespace."""
    return len(text.split())


def _format_relationship(rel_type: str) -> str:
    """Format a relationship type for human-readable display.

    Converts e.g. ``TREATED_BY`` → ``treated by``.
    """
    return rel_type.lower().replace("_", " ")


def _get_one_hop_templates(
    style: str,
    relationship: str,
) -> List[str]:
    """Return 1-hop templates for a given style and relationship type.

    For ``"mixed"`` style, all styles' templates are concatenated so
    the caller can cycle through them.
    """
    if style == "mixed":
        combined: List[str] = []
        for s in _ALL_STYLES:
            one_hop_dict, one_hop_default, _ = _TEMPLATE_REGISTRY[s]
            combined.extend(
                one_hop_dict.get(relationship, one_hop_default)
            )
        return combined

    one_hop_dict, one_hop_default, _ = _TEMPLATE_REGISTRY.get(
        style, _TEMPLATE_REGISTRY["conversational"]
    )
    return one_hop_dict.get(relationship, one_hop_default)


def _get_two_hop_templates(style: str) -> List[str]:
    """Return 2-hop templates for a given style.

    For ``"mixed"`` style, all styles' templates are concatenated.
    """
    if style == "mixed":
        combined: List[str] = []
        for s in _ALL_STYLES:
            _, _, two_hop = _TEMPLATE_REGISTRY[s]
            combined.extend(two_hop)
        return combined

    _, _, two_hop = _TEMPLATE_REGISTRY.get(
        style, _TEMPLATE_REGISTRY["conversational"]
    )
    return two_hop


def _generate_one_hop_question(
    concept_a: str,
    concept_b: str,
    relationship: str,
    template_index: int = 0,
    question_style: str = "mixed",
) -> str:
    """Generate a question for a 1-hop relationship path.

    The question always contains both concept names so that
    Property 6 (all path concepts referenced) is satisfied.
    """
    templates = _get_one_hop_templates(question_style, relationship)
    template = templates[template_index % len(templates)]
    return template.format(
        concept_a=concept_a,
        concept_b=concept_b,
        relationship=_format_relationship(relationship),
    )


def _generate_two_hop_question(
    concept_a: str,
    concept_b: str,
    concept_c: str,
    relationship_1: str,
    relationship_2: str,
    template_index: int = 0,
    question_style: str = "mixed",
) -> str:
    """Generate a question for a 2-hop relationship path.

    The question always contains all three concept names so that
    Property 6 (all path concepts referenced) is satisfied.
    """
    templates = _get_two_hop_templates(question_style)
    template = templates[template_index % len(templates)]
    return template.format(
        concept_a=concept_a,
        concept_b=concept_b,
        concept_c=concept_c,
        relationship_1=_format_relationship(relationship_1),
        relationship_2=_format_relationship(relationship_2),
    )


def _generate_one_hop_answer(
    concept_a: str,
    concept_b: str,
    relationship: str,
    supporting_evidence: str,
) -> str:
    """Generate an answer for a 1-hop relationship path.

    The answer includes the relationship chain in the text so that
    Property 7 (context contains relationship chain) is satisfied.
    """
    return ONE_HOP_ANSWER_TEMPLATE.format(
        concept_a=concept_a,
        concept_b=concept_b,
        relationship=_format_relationship(relationship),
        supporting_evidence=supporting_evidence.strip(),
    )


def _generate_two_hop_answer(
    concept_a: str,
    concept_b: str,
    concept_c: str,
    relationship_1: str,
    relationship_2: str,
    supporting_evidence: str,
) -> str:
    """Generate an answer for a 2-hop relationship path.

    The answer includes the full relationship chain so that
    Property 7 (context contains relationship chain) is satisfied.
    """
    return TWO_HOP_ANSWER_TEMPLATE.format(
        concept_a=concept_a,
        concept_b=concept_b,
        concept_c=concept_c,
        relationship_1=_format_relationship(relationship_1),
        relationship_2=_format_relationship(relationship_2),
        supporting_evidence=supporting_evidence.strip(),
    )


def _build_relationship_chain(
    concepts: List[str],
    relationships: List[str],
) -> str:
    """Build a human-readable relationship chain string.

    For a 1-hop path: ``"Drug_A treats Disease_B"``
    For a 2-hop path: ``"Drug_A treats Disease_B presents with Symptom_C"``
    """
    if len(concepts) < 2 or len(relationships) < 1:
        return ""
    parts = [concepts[0]]
    for i, rel in enumerate(relationships):
        parts.append(_format_relationship(rel))
        if i + 1 < len(concepts):
            parts.append(concepts[i + 1])
    return " ".join(parts)


# ---------------------------------------------------------------------------
# UMLSReasoningStrategy
# ---------------------------------------------------------------------------


class UMLSReasoningStrategy:
    """Generate multi-hop reasoning Q&A from UMLS relationships.

    This strategy uses the RelationshipTraverser's Neo4j client to find
    1-hop and 2-hop paths between UMLS concepts via clinically relevant
    relationships (CAUSES, TREATS, TREATED_BY, PRESENTS_WITH, IS_A,
    PART_OF). For each path it generates a relationship-based question
    referencing all concepts and produces a reasoning answer with
    supporting chunk content from EXTRACTED_FROM edges.

    Paths with no supporting chunk content are skipped (Requirement 3.5).
    RelationshipTraverser timeouts are handled gracefully (skip and log).
    """

    def __init__(
        self,
        relationship_traverser: Any,
        umls_client: Any,
        vector_client: Any,
    ) -> None:
        """Initialise the strategy.

        Args:
            relationship_traverser: A ``RelationshipTraverser`` instance.
                Its ``_neo4j_client`` is used for executing Cypher
                queries to discover relationship paths.
            umls_client: A ``UMLSClient`` for UMLS concept lookups.
            vector_client: A vector-store client with an async
                ``get_chunk_by_id`` method (e.g. ``MilvusClient``).
        """
        self._traverser = relationship_traverser
        self._umls = umls_client
        self._vector = vector_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        target_count: int,
        max_hops: int = 2,
        relationship_types: Optional[List[str]] = None,
        question_style: str = "mixed",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[InstructionTuningPair]:
        """Generate UMLS reasoning Q&A instruction-tuning pairs.

        Args:
            target_count: Desired number of pairs to produce.
            max_hops: Maximum hop count for relationship paths (1 or 2).
                Default is 2, which enables both 1-hop and 2-hop paths.
            relationship_types: List of relationship type strings to
                traverse. Defaults to ``DEFAULT_RELATIONSHIP_TYPES``.
            question_style: Template style for generated questions.
                One of ``"mixed"`` (default — cycles through all
                styles), ``"conversational"``, ``"medqa"`` (USMLE
                vignette), ``"medmcqa"`` (direct factual recall),
                or ``"pubmedqa"`` (evidence-based).
            progress_callback: Optional ``(generated, target)`` callback
                invoked after each pair is produced.

        Returns:
            A list of ``InstructionTuningPair`` objects with
            ``metadata.strategy == "umls_reasoning"``.
        """
        if relationship_types is None:
            relationship_types = list(DEFAULT_RELATIONSHIP_TYPES)

        if question_style not in VALID_QUESTION_STYLES:
            logger.warning(
                "UMLS Reasoning: Unknown question_style '%s', "
                "falling back to 'mixed'",
                question_style,
            )
            question_style = "mixed"

        pairs: List[InstructionTuningPair] = []

        # Budget split: ~60% 1-hop, ~40% 2-hop when max_hops >= 2
        if max_hops >= 2:
            one_hop_target = int(target_count * 0.6)
        else:
            one_hop_target = target_count

        # Generate 1-hop pairs
        one_hop_pairs = await self._generate_one_hop_pairs(
            target_count=one_hop_target,
            relationship_types=relationship_types,
            question_style=question_style,
            progress_callback=progress_callback,
            current_total=0,
            overall_target=target_count,
        )
        pairs.extend(one_hop_pairs)

        # Generate 2-hop pairs if max_hops allows
        if max_hops >= 2 and len(pairs) < target_count:
            remaining = target_count - len(pairs)
            two_hop_pairs = await self._generate_two_hop_pairs(
                target_count=remaining,
                relationship_types=relationship_types,
                question_style=question_style,
                progress_callback=progress_callback,
                current_total=len(pairs),
                overall_target=target_count,
            )
            pairs.extend(two_hop_pairs)

        logger.info(
            "UMLS Reasoning: Generated %d pairs (%d one-hop, %d two-hop)",
            len(pairs),
            len(one_hop_pairs),
            len(pairs) - len(one_hop_pairs),
        )
        return pairs

    # ------------------------------------------------------------------
    # 1-hop pair generation
    # ------------------------------------------------------------------

    async def _generate_one_hop_pairs(
        self,
        target_count: int,
        relationship_types: List[str],
        question_style: str,
        progress_callback: Optional[Callable[[int, int], None]],
        current_total: int,
        overall_target: int,
    ) -> List[InstructionTuningPair]:
        """Generate pairs from 1-hop relationship paths."""
        # Fetch more paths than needed to account for filtering
        fetch_limit = target_count * 3

        paths = await self._fetch_one_hop_paths(
            relationship_types, fetch_limit
        )
        if not paths:
            logger.warning(
                "UMLS Reasoning: No 1-hop paths found in Neo4j"
            )
            return []

        logger.info(
            "UMLS Reasoning: Retrieved %d 1-hop paths, targeting %d pairs",
            len(paths),
            target_count,
        )

        pairs: List[InstructionTuningPair] = []
        template_counter = 0

        for path in paths:
            if len(pairs) >= target_count:
                break

            concept_a_name: str = path.get("concept_a_name", "")
            concept_a_cui: str = path.get("concept_a_cui", "")
            concept_b_name: str = path.get("concept_b_name", "")
            concept_b_cui: str = path.get("concept_b_cui", "")
            rela_type: str = path.get("relationship_type", "")

            # Map UMLS rela_type to template key
            relationship: str = _RELA_TO_TEMPLATE_KEY.get(
                rela_type, rela_type.upper()
            )

            if not concept_a_name or not concept_b_name or not rela_type:
                continue

            # Retrieve supporting chunk content (Requirement 3.4)
            supporting_content, chunk_ids = (
                await self._get_supporting_chunks(
                    [concept_a_cui, concept_b_cui]
                )
            )

            # Skip paths with no supporting chunk content (Requirement 3.5)
            if not supporting_content:
                logger.debug(
                    "UMLS Reasoning: Skipping 1-hop path %s %s %s — "
                    "no supporting chunk content",
                    concept_a_name,
                    relationship,
                    concept_b_name,
                )
                continue

            question = _generate_one_hop_question(
                concept_a=concept_a_name,
                concept_b=concept_b_name,
                relationship=relationship,
                template_index=template_counter,
                question_style=question_style,
            )
            template_counter += 1

            answer = _generate_one_hop_answer(
                concept_a=concept_a_name,
                concept_b=concept_b_name,
                relationship=relationship,
                supporting_evidence=supporting_content,
            )

            chain = _build_relationship_chain(
                concepts=[concept_a_name, concept_b_name],
                relationships=[relationship],
            )

            pair = InstructionTuningPair(
                instruction=question,
                context=chain,
                response=answer,
                metadata=PairMetadata(
                    strategy="umls_reasoning",
                    source_concepts=[
                        c for c in [concept_a_cui, concept_b_cui] if c
                    ],
                    confidence_score=self._compute_confidence(
                        supporting_content, hops=1
                    ),
                    chunk_ids=chunk_ids if chunk_ids else None,
                    relationship_chain=chain,
                ),
            )
            pairs.append(pair)

            if progress_callback is not None:
                progress_callback(
                    current_total + len(pairs), overall_target
                )

        return pairs

    # ------------------------------------------------------------------
    # 2-hop pair generation
    # ------------------------------------------------------------------

    async def _generate_two_hop_pairs(
        self,
        target_count: int,
        relationship_types: List[str],
        question_style: str,
        progress_callback: Optional[Callable[[int, int], None]],
        current_total: int,
        overall_target: int,
    ) -> List[InstructionTuningPair]:
        """Generate pairs from 2-hop relationship paths."""
        fetch_limit = target_count * 3

        paths = await self._fetch_two_hop_paths(
            relationship_types, fetch_limit
        )
        if not paths:
            logger.warning(
                "UMLS Reasoning: No 2-hop paths found in Neo4j"
            )
            return []

        logger.info(
            "UMLS Reasoning: Retrieved %d 2-hop paths, targeting %d pairs",
            len(paths),
            target_count,
        )

        pairs: List[InstructionTuningPair] = []
        template_counter = 0

        for path in paths:
            if len(pairs) >= target_count:
                break

            concept_a_name: str = path.get("concept_a_name", "")
            concept_a_cui: str = path.get("concept_a_cui", "")
            concept_b_name: str = path.get("concept_b_name", "")
            concept_b_cui: str = path.get("concept_b_cui", "")
            concept_c_name: str = path.get("concept_c_name", "")
            concept_c_cui: str = path.get("concept_c_cui", "")
            rela_type_1: str = path.get("relationship_type_1", "")
            rela_type_2: str = path.get("relationship_type_2", "")

            # Map UMLS rela_type to template keys
            relationship_1: str = _RELA_TO_TEMPLATE_KEY.get(
                rela_type_1, rela_type_1.upper()
            )
            relationship_2: str = _RELA_TO_TEMPLATE_KEY.get(
                rela_type_2, rela_type_2.upper()
            )

            if (
                not concept_a_name
                or not concept_b_name
                or not concept_c_name
                or not rela_type_1
                or not rela_type_2
            ):
                continue

            # Retrieve supporting chunk content (Requirement 3.4)
            supporting_content, chunk_ids = (
                await self._get_supporting_chunks(
                    [concept_a_cui, concept_b_cui, concept_c_cui]
                )
            )

            # Skip paths with no supporting chunk content (Requirement 3.5)
            if not supporting_content:
                logger.debug(
                    "UMLS Reasoning: Skipping 2-hop path "
                    "%s %s %s %s %s — no supporting chunk content",
                    concept_a_name,
                    relationship_1,
                    concept_b_name,
                    relationship_2,
                    concept_c_name,
                )
                continue

            question = _generate_two_hop_question(
                concept_a=concept_a_name,
                concept_b=concept_b_name,
                concept_c=concept_c_name,
                relationship_1=relationship_1,
                relationship_2=relationship_2,
                template_index=template_counter,
                question_style=question_style,
            )
            template_counter += 1

            answer = _generate_two_hop_answer(
                concept_a=concept_a_name,
                concept_b=concept_b_name,
                concept_c=concept_c_name,
                relationship_1=relationship_1,
                relationship_2=relationship_2,
                supporting_evidence=supporting_content,
            )

            chain = _build_relationship_chain(
                concepts=[concept_a_name, concept_b_name, concept_c_name],
                relationships=[relationship_1, relationship_2],
            )

            pair = InstructionTuningPair(
                instruction=question,
                context=chain,
                response=answer,
                metadata=PairMetadata(
                    strategy="umls_reasoning",
                    source_concepts=[
                        c
                        for c in [
                            concept_a_cui,
                            concept_b_cui,
                            concept_c_cui,
                        ]
                        if c
                    ],
                    confidence_score=self._compute_confidence(
                        supporting_content, hops=2
                    ),
                    chunk_ids=chunk_ids if chunk_ids else None,
                    relationship_chain=chain,
                ),
            )
            pairs.append(pair)

            if progress_callback is not None:
                progress_callback(
                    current_total + len(pairs), overall_target
                )

        return pairs

    # ------------------------------------------------------------------
    # Data fetching helpers
    # ------------------------------------------------------------------

    async def _fetch_one_hop_paths(
        self,
        relationship_types: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Query Neo4j for 1-hop relationship paths.

        Handles connection failures and timeouts gracefully by logging
        and returning an empty list.
        """
        neo4j_client = self._get_neo4j_client()
        if neo4j_client is None:
            logger.warning(
                "UMLS Reasoning: No Neo4j client available — "
                "skipping 1-hop path discovery"
            )
            return []

        try:
            results = await asyncio.wait_for(
                neo4j_client.execute_query(
                    _ONE_HOP_PATHS_QUERY,
                    {
                        "relationship_types": relationship_types,
                        "limit": limit,
                    },
                ),
                timeout=self._get_timeout(),
            )
            return results if results else []
        except asyncio.TimeoutError:
            logger.warning(
                "UMLS Reasoning: 1-hop path query timed out — skipping"
            )
            return []
        except Exception as exc:
            logger.error(
                "UMLS Reasoning: 1-hop path query failed — skipping: %s",
                exc,
            )
            return []

    async def _fetch_two_hop_paths(
        self,
        relationship_types: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Query Neo4j for 2-hop relationship paths.

        Handles connection failures and timeouts gracefully by logging
        and returning an empty list.
        """
        neo4j_client = self._get_neo4j_client()
        if neo4j_client is None:
            logger.warning(
                "UMLS Reasoning: No Neo4j client available — "
                "skipping 2-hop path discovery"
            )
            return []

        try:
            results = await asyncio.wait_for(
                neo4j_client.execute_query(
                    _TWO_HOP_PATHS_QUERY,
                    {
                        "relationship_types": relationship_types,
                        "limit": limit,
                    },
                ),
                timeout=self._get_timeout(),
            )
            return results if results else []
        except asyncio.TimeoutError:
            logger.warning(
                "UMLS Reasoning: 2-hop path query timed out — skipping"
            )
            return []
        except Exception as exc:
            logger.error(
                "UMLS Reasoning: 2-hop path query failed — skipping: %s",
                exc,
            )
            return []

    async def _get_supporting_chunks(
        self,
        cuis: List[str],
    ) -> Tuple[str, List[str]]:
        """Retrieve supporting chunk content for concepts along a path.

        Queries Neo4j for EXTRACTED_FROM edges from each concept, then
        retrieves chunk content from the vector store. Returns the
        concatenated content and list of chunk IDs.

        Args:
            cuis: List of CUIs for concepts along the path.

        Returns:
            Tuple of (concatenated_content, chunk_id_list). If no
            supporting content is found, returns ("", []).
        """
        neo4j_client = self._get_neo4j_client()
        if neo4j_client is None:
            return "", []

        all_chunk_ids: List[str] = []

        for cui in cuis:
            if not cui:
                continue
            try:
                results = await asyncio.wait_for(
                    neo4j_client.execute_query(
                        _CONCEPT_CHUNKS_QUERY,
                        {"cui": cui, "limit": 3},
                    ),
                    timeout=self._get_timeout(),
                )
                if results:
                    for record in results:
                        chunk_id = (
                            record.get("chunk_id")
                            if isinstance(record, dict)
                            else getattr(record, "chunk_id", None)
                        )
                        if chunk_id and chunk_id not in all_chunk_ids:
                            all_chunk_ids.append(chunk_id)
            except asyncio.TimeoutError:
                logger.warning(
                    "UMLS Reasoning: Chunk query timed out for CUI %s "
                    "— skipping",
                    cui,
                )
                continue
            except Exception as exc:
                logger.warning(
                    "UMLS Reasoning: Chunk query failed for CUI %s: %s",
                    cui,
                    exc,
                )
                continue

        if not all_chunk_ids:
            return "", []

        # Retrieve chunk content from vector store
        content_parts: List[str] = []
        valid_chunk_ids: List[str] = []

        for chunk_id in all_chunk_ids[:5]:  # Cap at 5 chunks
            try:
                chunk_data = await self._vector.get_chunk_by_id(chunk_id)
                if chunk_data is None:
                    continue
                content = self._extract_content(chunk_data)
                if content.strip():
                    content_parts.append(content.strip())
                    valid_chunk_ids.append(chunk_id)
            except Exception as exc:
                logger.warning(
                    "UMLS Reasoning: Failed to retrieve chunk %s: %s",
                    chunk_id,
                    exc,
                )
                continue

        return "\n\n".join(content_parts), valid_chunk_ids

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_neo4j_client(self) -> Any:
        """Get the Neo4j client from the RelationshipTraverser.

        The traverser stores its Neo4j client as ``_neo4j_client``.
        """
        client = getattr(self._traverser, "_neo4j_client", None)
        if client is None:
            # Fallback: try the traverser itself if it has execute_query
            if hasattr(self._traverser, "execute_query"):
                return self._traverser
        return client

    def _get_timeout(self) -> float:
        """Get the timeout from the RelationshipTraverser config.

        Uses a generous default of 30 seconds since UMLS_REL queries
        scan millions of edges. Falls back to 30.0 seconds if not
        available from the traverser.
        """
        traverser_timeout = getattr(
            self._traverser, "_timeout_seconds", None
        )
        # Use at least 30s for UMLS queries — the 3s traverser default
        # is too short for large-scale path discovery
        if traverser_timeout and traverser_timeout >= 30.0:
            return traverser_timeout
        return 30.0

    @staticmethod
    def _extract_content(chunk_data: Dict[str, Any]) -> str:
        """Extract text content from a chunk data dict.

        Supports both OpenSearch format (top-level ``content``) and
        Milvus format (``metadata.content``).
        """
        content = chunk_data.get("content", "")
        if not content:
            metadata = chunk_data.get("metadata", {})
            if isinstance(metadata, dict):
                content = metadata.get("content", "")
        return content or ""

    @staticmethod
    def _compute_confidence(
        supporting_content: str,
        hops: int,
    ) -> float:
        """Compute a confidence score for a reasoning pair.

        Longer supporting content and fewer hops yield higher
        confidence. The score is clamped to [0.0, 1.0].
        """
        token_count = _count_tokens(supporting_content)
        if token_count <= 0:
            return 0.0

        # Base confidence from content length
        # 50 tokens → 0.5, 200 tokens → 0.8, 500+ tokens → 1.0
        length_score = min(0.5 + (token_count - 50) * 0.002, 1.0)

        # Penalty for multi-hop (more hops = slightly less confident)
        hop_penalty = 0.05 * (hops - 1)

        score = max(length_score - hop_penalty, 0.0)
        return round(min(score, 1.0), 4)
