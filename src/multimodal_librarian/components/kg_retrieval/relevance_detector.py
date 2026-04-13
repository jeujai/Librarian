"""
Relevance Detector for Knowledge Graph-Guided Retrieval.

Identifies "no relevant results" scenarios using three signals:
1. Score Distribution Analysis — detects uniform/clustered
   final_score values
2. Concept Specificity Analysis — detects generic vs
   domain-specific concept matches
3. Query Term Coverage — detects whether the query's proper
   nouns (via spaCy NER) appear in matched concept names

When 2+ signals fire the verdict is "irrelevant".  When exactly
one fires a partial penalty is applied.  Pure in-memory
computation (spaCy model pre-loaded at startup).

Requirements: 1.1–1.5, 2.1–2.6, 3.1–3.5
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from multimodal_librarian.models.kg_retrieval import QueryDecomposition, RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class ScoreDistributionResult:
    """Result of score distribution analysis."""

    variance: float
    spread: float
    is_semantic_floor: bool
    chunk_count: int
    is_indeterminate: bool = False


@dataclass
class ConceptSpecificityResult:
    """Result of concept specificity analysis."""

    per_concept_scores: Dict[str, float]
    average_specificity: float
    is_low_specificity: bool
    high_specificity_count: int
    low_specificity_count: int


@dataclass
class QueryTermCoverageResult:
    """Result of query term coverage analysis."""

    proper_nouns: List[str] = field(default_factory=list)
    covered_nouns: List[str] = field(default_factory=list)
    uncovered_nouns: List[str] = field(default_factory=list)
    coverage_ratio: float = 1.0
    has_proper_noun_gap: bool = False
    # Co-occurrence: are the query's key PROPN tokens found
    # together in at least one chunk?  False when no chunk
    # contains all key terms, indicating scattered matches.
    has_cooccurrence_gap: bool = False
    key_nouns: List[str] = field(default_factory=list)
    adaptive_threshold: float = 1.0
    detected_domain: Optional[str] = None


@dataclass
class RelevanceVerdict:
    """Combined relevance detection verdict."""

    is_relevant: bool
    confidence_adjustment_factor: float
    score_distribution: ScoreDistributionResult
    concept_specificity: ConceptSpecificityResult
    query_term_coverage: QueryTermCoverageResult
    reasoning: str


def analyze_score_distribution(
    chunks: List[RetrievedChunk],
    spread_threshold: float,
    variance_threshold: float,
) -> ScoreDistributionResult:
    """Analyze the distribution of final_score values across chunks.

    Computes spread (max - min) and population variance of final_score
    values. When either metric falls below its threshold, the result set
    is classified as exhibiting a semantic floor pattern.

    Args:
        chunks: List of RetrievedChunk with final_score set.
        spread_threshold: Threshold below which spread
            indicates semantic floor.
        variance_threshold: Threshold below which variance
            indicates semantic floor.

    Returns:
        ScoreDistributionResult with computed statistics and classification.

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
    """
    if len(chunks) < 3:
        return ScoreDistributionResult(
            variance=0.0,
            spread=0.0,
            is_semantic_floor=False,
            chunk_count=len(chunks),
            is_indeterminate=True,
        )

    # Defensively clamp scores to [0, 1]
    scores = [max(0.0, min(1.0, c.final_score)) for c in chunks]

    spread = max(scores) - min(scores)
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)

    is_semantic_floor = (
        spread < spread_threshold or variance < variance_threshold
    )

    return ScoreDistributionResult(
        variance=variance,
        spread=spread,
        is_semantic_floor=is_semantic_floor,
        chunk_count=len(scores),
    )


# Common English words that match generic KG concepts but carry
# no domain-specific signal.  Kept as a module-level frozenset to
# avoid per-call allocation.  ~60 entries drawn from the design doc.
GENERIC_WORDS: frozenset = frozenset({
    "about", "been", "come", "day", "each", "find", "from", "get",
    "give", "go", "going", "good", "has", "have", "her", "him",
    "how", "its", "just", "like", "long", "look", "make", "man",
    "many", "may", "new", "now", "old", "said", "see", "some",
    "take", "tell", "than", "that", "them", "then", "this", "time",
    "use", "very", "want", "way", "what", "when", "will", "with",
    "work", "world", "your", "today", "big", "run", "set", "put",
    "got", "let", "say", "try", "ask", "own", "too", "any", "end",
    "did", "bit", "lot", "top", "yet", "ago", "far", "few",
})


def analyze_concept_specificity(
    concept_matches: List[Dict[str, Any]],
    specificity_threshold: float,
) -> ConceptSpecificityResult:
    """Analyze the specificity of matched KG concepts.

    Scores each concept using lexical heuristics (proper-noun flag,
    multi-word structure, length, generic-word membership, word
    coverage) and classifies the overall set as low-specificity when
    *all* individual scores fall below ``specificity_threshold``.

    Args:
        concept_matches: Concept match dicts from QueryDecomposition.
            Expected keys: ``name``, ``is_proper_noun_match``,
            ``word_coverage``.  Missing keys are handled via ``.get()``
            with safe defaults.
        specificity_threshold: Score below which a concept is
            considered low-specificity.

    Returns:
        ConceptSpecificityResult with per-concept scores, average,
        and high/low counts.

    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
    """
    if not concept_matches:
        return ConceptSpecificityResult(
            per_concept_scores={},
            average_specificity=0.0,
            is_low_specificity=True,
            high_specificity_count=0,
            low_specificity_count=0,
        )

    per_concept_scores: Dict[str, float] = {}
    high_count = 0
    low_count = 0

    for match in concept_matches:
        name: str = match.get("name", "")
        is_proper_noun: bool = match.get("is_proper_noun_match", False)
        word_coverage: float = match.get("word_coverage", 1.0)

        score = 0.5

        # +0.3 for proper nouns
        if is_proper_noun:
            score += 0.3

        # +0.2 for multi-word, hyphenated, or underscored names
        if (
            len(name.split()) > 1
            or "-" in name
            or "_" in name
        ):
            score += 0.2

        # +0.1 for names with 5+ characters
        if len(name) >= 5:
            score += 0.1

        # -0.3 for short generic words
        name_lower = name.lower().strip()
        if (
            len(name_lower) < 5
            and name_lower in GENERIC_WORDS
            and len(name_lower.split()) == 1
        ):
            score -= 0.3

        # -0.1 for weak word coverage
        if word_coverage < 0.5:
            score -= 0.1

        # Clamp to [0.0, 1.0]
        score = max(0.0, min(1.0, score))

        per_concept_scores[name] = score
        if score >= specificity_threshold:
            high_count += 1
        else:
            low_count += 1

    total = high_count + low_count
    average = (
        sum(per_concept_scores.values()) / total if total else 0.0
    )
    is_low = all(
        s < specificity_threshold
        for s in per_concept_scores.values()
    )

    return ConceptSpecificityResult(
        per_concept_scores=per_concept_scores,
        average_specificity=average,
        is_low_specificity=is_low,
        high_specificity_count=high_count,
        low_specificity_count=low_count,
    )


def compute_adaptive_threshold(
    proper_noun_count: int,
    domain: Optional[str] = None,
    base_threshold_floor: float = 0.70,
    medical_threshold: float = 0.95,
    legal_threshold: float = 0.90,
    small_query_noun_limit: int = 2,
) -> float:
    """Compute the adaptive coverage threshold.

    For queries with few proper nouns (≤ ``small_query_noun_limit``),
    100 % coverage is required.  As the noun count grows the
    threshold decreases linearly, flooring at
    ``base_threshold_floor``.  Domain elevation raises the
    floor for medical and legal queries.

    Returns a float clamped to ``[0.0, 1.0]``.
    """
    if proper_noun_count <= small_query_noun_limit:
        threshold = 1.0
    else:
        threshold = max(
            base_threshold_floor,
            1.0 - (proper_noun_count - small_query_noun_limit) * 0.05,
        )

    # Domain elevation
    if domain == "medical":
        threshold = max(threshold, medical_threshold)
    elif domain == "legal":
        threshold = max(threshold, legal_threshold)

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, threshold))


def compute_chunk_noun_score(
    chunk_content: str,
    key_nouns: List[str],
) -> float:
    """Fraction of *key_nouns* found in *chunk_content*.

    Uses case-insensitive substring matching.  Returns ``1.0``
    when *key_nouns* is empty.
    """
    if not key_nouns:
        return 1.0
    content_lower = chunk_content.lower()
    found = sum(
        1 for noun in key_nouns if noun.lower() in content_lower
    )
    return found / len(key_nouns)


def analyze_query_term_coverage(
    query: str,
    concept_matches: List[Dict[str, Any]],
    spacy_nlp: Optional[Any] = None,
    chunks: Optional[List[RetrievedChunk]] = None,
    domain: Optional[str] = None,
    base_threshold_floor: float = 0.70,
    medical_threshold: float = 0.95,
    legal_threshold: float = 0.90,
    small_query_noun_limit: int = 2,
) -> QueryTermCoverageResult:
    """Check if the query's proper nouns are covered in results.

    Uses spaCy NER to extract named entities (proper nouns) from
    the query, then applies a two-level coverage check:

    1. **Concept-level**: Does the proper noun appear as a
       substring in any matched concept name?
    2. **Chunk-level**: Does the proper noun appear in the
       *content* of any returned chunk?

    A proper noun is only considered "covered" if it passes
    BOTH checks.  This prevents false negatives where a
    concept exists in the KG (e.g. ``gpe_venezuela`` from a
    conversation) but none of the returned chunks actually
    contain that proper noun — meaning the concept's chunks
    were outranked by unrelated chunks during reranking.

    Additionally performs a **co-occurrence check** using spaCy
    POS tagging.  When the query contains 2+ PROPN tokens
    (e.g. "President" and "Venezuela"), the function checks
    whether any single chunk achieves a noun score meeting or
    exceeding the adaptive threshold.  If no chunk does, the
    results are likely incidental matches rather than genuinely
    relevant content.

    If spaCy is unavailable or the query contains no named
    entities, the signal is indeterminate (no gap detected).

    Args:
        query: Original user query text.
        concept_matches: Concept match dicts with ``name`` key.
        spacy_nlp: Pre-loaded spaCy Language model, or None.
        chunks: Returned chunks to verify content-level coverage.
            When None, only concept-level check is performed.
        domain: Detected domain string (e.g. ``"medical"``,
            ``"legal"``) or None for general queries.
        base_threshold_floor: Minimum adaptive threshold.
        medical_threshold: Minimum threshold for medical domain.
        legal_threshold: Minimum threshold for legal domain.
        small_query_noun_limit: Noun count at or below which
            100 % coverage is required.

    Returns:
        QueryTermCoverageResult with proper nouns found,
        which are covered/uncovered, and whether a gap exists.
    """
    if spacy_nlp is None or not query:
        return QueryTermCoverageResult()

    doc = spacy_nlp(query)
    # Extract unique entity texts from spaCy NER
    proper_nouns = list({
        ent.text for ent in doc.ents
    })

    if not proper_nouns:
        return QueryTermCoverageResult()

    # Compute adaptive threshold based on noun count and domain
    adaptive_thresh = compute_adaptive_threshold(
        proper_noun_count=len(proper_nouns),
        domain=domain,
        base_threshold_floor=base_threshold_floor,
        medical_threshold=medical_threshold,
        legal_threshold=legal_threshold,
        small_query_noun_limit=small_query_noun_limit,
    )

    # Build a lowercase list of all concept names
    # for substring matching
    concept_names_lower = [
        m.get("name", "").lower()
        for m in concept_matches
    ]

    # Build a lowercase set of chunk content for
    # content-level verification
    chunk_contents_lower: Optional[List[str]] = None
    if chunks:
        chunk_contents_lower = [
            (c.content or "").lower() for c in chunks
        ]

    covered: List[str] = []
    uncovered: List[str] = []
    for noun in proper_nouns:
        noun_lower = noun.lower()

        # Level 1: concept-level check
        in_concepts = any(
            noun_lower in cn for cn in concept_names_lower
        )

        if not in_concepts:
            # Not even a concept match — definitely uncovered
            uncovered.append(noun)
            continue

        # Level 2: chunk-content check (when chunks available)
        # If the proper noun matched a concept but none of the
        # returned chunks contain it, the concept's chunks were
        # outranked — treat as uncovered.
        if chunk_contents_lower is not None:
            in_chunks = any(
                noun_lower in cc for cc in chunk_contents_lower
            )
            if not in_chunks:
                uncovered.append(noun)
                continue

        covered.append(noun)

    total = len(proper_nouns)
    ratio = len(covered) / total if total else 1.0
    # Gap exists when coverage ratio falls below adaptive threshold
    has_gap = ratio < adaptive_thresh

    # --- Co-occurrence check using PROPN POS tags + noun chunk
    # PROPN tokens ---
    # NER misses terms like "President" (common noun in NER
    # but PROPN in POS or a capitalized NOUN in a noun chunk).
    # Combine PROPN tokens with capitalized NOUN tokens from
    # noun chunks to build a comprehensive set of key nouns.
    # Only include tokens that are PROPN or capitalized NOUNs
    # (title-like words such as "President", "Minister") —
    # skip generic lowercase nouns like "developments".
    key_nouns: List[str] = []
    has_cooccurrence_gap = False

    propn_tokens = {
        t.text for t in doc if t.pos_ == "PROPN"
    }
    # Add capitalized NOUN tokens from noun chunks that
    # look like proper-noun-like terms (e.g. "President")
    for nc in doc.noun_chunks:
        for tok in nc:
            if (
                tok.pos_ == "NOUN"
                and tok.text[0].isupper()
                and len(tok.text) > 2
            ):
                propn_tokens.add(tok.text)

    if len(propn_tokens) >= 2 and chunk_contents_lower:
        key_nouns = sorted(propn_tokens)

        # Adaptive co-occurrence: gap iff no chunk achieves
        # a noun score >= adaptive threshold
        best_score = max(
            compute_chunk_noun_score(cc, key_nouns)
            for cc in chunk_contents_lower
        )
        if best_score < adaptive_thresh:
            has_cooccurrence_gap = True
            logger.info(
                "Co-occurrence gap: no chunk meets adaptive "
                "threshold %.2f for key nouns %s "
                "(best score=%.2f)",
                adaptive_thresh,
                key_nouns,
                best_score,
            )

    logger.info(
        "Adaptive coverage: proper_noun_count=%d "
        "adaptive_threshold=%.2f coverage_ratio=%.2f "
        "detected_domain=%s has_proper_noun_gap=%s "
        "has_cooccurrence_gap=%s",
        len(proper_nouns),
        adaptive_thresh,
        ratio,
        domain,
        has_gap,
        has_cooccurrence_gap,
    )

    return QueryTermCoverageResult(
        proper_nouns=proper_nouns,
        covered_nouns=covered,
        uncovered_nouns=uncovered,
        coverage_ratio=ratio,
        has_proper_noun_gap=has_gap,
        has_cooccurrence_gap=has_cooccurrence_gap,
        key_nouns=key_nouns,
        adaptive_threshold=adaptive_thresh,
        detected_domain=domain,
    )


class RelevanceDetector:
    """Evaluates retrieval result quality using score distribution,
    concept specificity, and query term coverage signals.

    Requires a pre-loaded spaCy Language model for NER-based
    proper-noun extraction.  The model should be injected via
    the DI layer at startup — no model loading happens here.

    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.8
    """

    # Domain keyword patterns for extracting domain from query text.
    # Mirrors the patterns in QueryProcessor._extract_context_keywords().
    _DOMAIN_PATTERNS: Dict[str, List[str]] = {
        "medical": [
            "patient", "treatment", "diagnosis", "medical",
            "health", "disease", "symptom",
        ],
        "legal": [
            "law", "legal", "court", "statute", "regulation",
            "attorney", "plaintiff", "defendant",
        ],
        "technical": [
            "algorithm", "code", "programming", "software",
            "system", "api", "database",
        ],
        "academic": [
            "research", "study", "theory", "hypothesis",
            "methodology",
        ],
        "business": [
            "market", "revenue", "strategy", "investment",
            "profit",
        ],
    }

    def __init__(
        self,
        spread_threshold: float = 0.05,
        variance_threshold: float = 0.001,
        specificity_threshold: float = 0.3,
        spacy_nlp: Optional[Any] = None,
        base_threshold_floor: float = 0.70,
        medical_threshold: float = 0.95,
        legal_threshold: float = 0.90,
        small_query_noun_limit: int = 2,
    ) -> None:
        self.spread_threshold = spread_threshold
        self.variance_threshold = variance_threshold
        self.specificity_threshold = specificity_threshold
        self.spacy_nlp = spacy_nlp
        self.base_threshold_floor = base_threshold_floor
        self.medical_threshold = medical_threshold
        self.legal_threshold = legal_threshold
        self.small_query_noun_limit = small_query_noun_limit

        logger.info(
            "RelevanceDetector initialised — "
            "spread=%.4f, variance=%.5f, "
            "specificity=%.2f, spacy=%s, "
            "adaptive_floor=%.2f, medical=%.2f, "
            "legal=%.2f, small_noun_limit=%d",
            spread_threshold,
            variance_threshold,
            specificity_threshold,
            "loaded" if spacy_nlp else "None",
            base_threshold_floor,
            medical_threshold,
            legal_threshold,
            small_query_noun_limit,
        )

    def _detect_domain(self, query: str) -> Optional[str]:
        """Extract domain from query text using keyword patterns.

        Mirrors the domain detection logic in
        ``QueryProcessor._extract_context_keywords()`` so that
        the relevance detector can determine domain independently
        without requiring the query processor's output.

        Returns:
            Domain string (e.g. ``"medical"``, ``"legal"``)
            or ``None`` when no domain is detected.
        """
        query_lower = query.lower()
        for domain, terms in self._DOMAIN_PATTERNS.items():
            if any(term in query_lower for term in terms):
                return domain
        return None

    def evaluate(
        self,
        chunks: List[RetrievedChunk],
        query_decomposition: QueryDecomposition,
    ) -> RelevanceVerdict:
        """Produce a relevance verdict from chunks and
        query decomposition.

        Uses three signals:
        1. Score distribution (semantic floor)
        2. Concept specificity (generic matches)
        3. Query term coverage (proper-noun gap)

        Decision matrix:
        - 2+ signals fire → irrelevant (factor 0.3)
        - 1 signal fires  → partial penalty (factor 0.8)
        - 0 signals       → relevant (factor 1.0)
        """
        for chunk in chunks:
            chunk.final_score = max(
                0.0, min(1.0, chunk.final_score)
            )

        score_dist = analyze_score_distribution(
            chunks,
            self.spread_threshold,
            self.variance_threshold,
        )
        concept_spec = analyze_concept_specificity(
            query_decomposition.concept_matches,
            self.specificity_threshold,
        )
        term_cov = analyze_query_term_coverage(
            query_decomposition.original_query,
            query_decomposition.concept_matches,
            self.spacy_nlp,
            chunks,
            domain=self._detect_domain(
                query_decomposition.original_query,
            ),
            base_threshold_floor=self.base_threshold_floor,
            medical_threshold=self.medical_threshold,
            legal_threshold=self.legal_threshold,
            small_query_noun_limit=self.small_query_noun_limit,
        )

        # Count how many signals fired
        semantic_floor = score_dist.is_semantic_floor
        low_specificity = concept_spec.is_low_specificity
        proper_noun_gap = term_cov.has_proper_noun_gap
        cooccurrence_gap = term_cov.has_cooccurrence_gap

        signals = [
            semantic_floor,
            low_specificity,
            proper_noun_gap,
            cooccurrence_gap,
        ]
        fired = sum(signals)

        # Proper-noun gap is a strong standalone signal:
        # if the KG has no concept matching a named entity
        # from the query, the results are almost certainly
        # irrelevant regardless of score distribution or
        # concept specificity.  Treat it as 2 signals.
        if proper_noun_gap:
            fired += 1  # double-weight

        # Co-occurrence gap is also a strong signal:
        # the query has 2+ proper nouns (e.g. "President"
        # and "Venezuela") but no single chunk contains all
        # of them — the matches are scattered across
        # unrelated books.  Treat as 2 signals.
        if cooccurrence_gap:
            fired += 1  # double-weight

        if fired >= 2:
            is_relevant = False
            factor = 0.3
            parts = []
            if semantic_floor:
                parts.append(
                    "semantic floor (spread=%.4f)"
                    % score_dist.spread
                )
            if low_specificity:
                parts.append(
                    "low specificity (avg=%.2f)"
                    % concept_spec.average_specificity
                )
            if proper_noun_gap:
                parts.append(
                    "proper-noun gap (%s)"
                    % ", ".join(term_cov.uncovered_nouns)
                )
            if cooccurrence_gap:
                parts.append(
                    "co-occurrence gap (%s)"
                    % ", ".join(term_cov.key_nouns)
                )
            reasoning = (
                "%d signals fired: %s. "
                "Results are likely irrelevant."
                % (fired, "; ".join(parts))
            )
        elif fired == 1:
            is_relevant = True
            factor = 0.8
            if semantic_floor:
                reasoning = (
                    "1/3 signals: semantic floor "
                    "(spread=%.4f). Partial penalty."
                    % score_dist.spread
                )
            elif low_specificity:
                reasoning = (
                    "1/3 signals: low specificity "
                    "(avg=%.2f). Partial penalty."
                    % concept_spec.average_specificity
                )
            else:
                reasoning = (
                    "1/3 signals: proper-noun gap "
                    "(%s). Partial penalty."
                    % ", ".join(term_cov.uncovered_nouns)
                )
        else:
            is_relevant = True
            factor = 1.0
            reasoning = (
                "0/3 signals fired. "
                "No adjustment needed."
            )

        return RelevanceVerdict(
            is_relevant=is_relevant,
            confidence_adjustment_factor=factor,
            score_distribution=score_dist,
            concept_specificity=concept_spec,
            query_term_coverage=term_cov,
            reasoning=reasoning,
        )

    def filter_chunks_by_proper_nouns(
        self,
        chunks: List[RetrievedChunk],
        query: str,
        adaptive_threshold: float = 1.0,
    ) -> Optional[List[RetrievedChunk]]:
        """Pre-reranking filter: keep only chunks whose content
        contains the query's proper nouns, using a three-tier
        strategy.

        Uses spaCy NER to extract named entities from *query*,
        then does a case-insensitive substring match against
        each chunk's ``content``.

        Three-tier filter:
        1. Prefer chunks containing ALL key terms.
        2. Fall back to chunks where the fraction of matched
           key terms >= ``adaptive_threshold``.
        3. Fall back to chunks containing ANY key term.

        Returns
        -------
        Optional[List[RetrievedChunk]]
            Filtered list when proper nouns were found and the
            filtered set is non-empty.  ``None`` when:
            - spaCy model is unavailable
            - query has no proper nouns
            - filtered set is empty (fall back to unfiltered)

        Requirements: 5.1, 5.2, 5.3, 7.1, 7.3, 7.4, 7.6, 7.7, 7.9
        """
        if self.spacy_nlp is None or not query:
            return None

        doc = self.spacy_nlp(query)

        # Collect key terms from both NER entities and noun chunks.
        # doc.ents gives named entities ("Venezuela").
        # doc.noun_chunks gives noun phrases ("the President"),
        # from which we extract only PROPN tokens and
        # capitalized NOUN tokens (title-like words such as
        # "President", "Minister") — NOT generic lowercase
        # nouns like "developments" or "current".
        key_terms: set = set()
        for ent in doc.ents:
            key_terms.add(ent.text)

        for nc in doc.noun_chunks:
            for tok in nc:
                if tok.pos_ == "PROPN" and len(tok.text) > 2:
                    key_terms.add(tok.text)
                elif (
                    tok.pos_ == "NOUN"
                    and tok.text[0].isupper()
                    and len(tok.text) > 2
                ):
                    key_terms.add(tok.text)

        if not key_terms:
            return None

        key_terms_lower = [kt.lower() for kt in key_terms]
        total_key_terms = len(key_terms_lower)
        before_count = len(chunks)

        # Three-tier filter:
        # 1. Prefer chunks containing ALL key terms
        # 2. Fall back to chunks meeting adaptive threshold fraction
        # 3. Fall back to chunks containing ANY key term
        filtered_all = [
            c for c in chunks
            if all(
                kt in (c.content or "").lower()
                for kt in key_terms_lower
            )
        ]

        if filtered_all:
            filtered = filtered_all
            match_mode = "all"
        else:
            # Tier 2: chunks where matched fraction >= adaptive_threshold
            filtered_threshold = [
                c for c in chunks
                if (
                    sum(
                        1 for kt in key_terms_lower
                        if kt in (c.content or "").lower()
                    )
                    / total_key_terms
                )
                >= adaptive_threshold
            ]

            if filtered_threshold:
                filtered = filtered_threshold
                match_mode = "threshold"
            else:
                # Tier 3: any key term present
                filtered = [
                    c for c in chunks
                    if any(
                        kt in (c.content or "").lower()
                        for kt in key_terms_lower
                    )
                ]
                match_mode = "any"

        after_count = len(filtered)
        retained_ids = [c.chunk_id for c in filtered]

        logger.info(
            "Proper-noun chunk filter: %d → %d chunks "
            "(key_terms=%s, match_mode=%s, adaptive_threshold=%.2f, "
            "retained_ids=%s)",
            before_count,
            after_count,
            sorted(key_terms),
            match_mode,
            adaptive_threshold,
            retained_ids,
        )

        if not filtered:
            return None

        return filtered
