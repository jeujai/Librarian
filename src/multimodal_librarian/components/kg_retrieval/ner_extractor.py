"""
NER Extractor — Three-Layer Concurrent Scientific/Medical NER.

Layer 1 (Base): en_core_web_sm — general proper nouns
Layer 2 (Scientific): en_core_sci_sm — scientific/medical entities
Layer 3 (Medical Precision): UMLS n-gram lookup via UMLSClient

All three layers run concurrently via asyncio.gather.
Merge hierarchy (override priority): UMLS > sci > web.
Each layer degrades independently.

Requirements: 2.1–2.4, 3.1–3.4, 4.1–4.6, 5.1–5.5, 6.1–6.6, 10.1–10.4
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class NERResult:
    """Structured result from three-layer concurrent NER extraction."""

    web_entities: List[str] = field(default_factory=list)   # Layer 1: en_core_web_sm
    sci_entities: List[str] = field(default_factory=list)   # Layer 2: en_core_sci_sm
    umls_entities: List[str] = field(default_factory=list)  # Layer 3: UMLS lookup
    key_terms: Set[str] = field(default_factory=set)        # Merged result

    def to_dict(self) -> dict:
        """Serialize to dict with deterministic ordering."""
        return {
            "web_entities": sorted(self.web_entities),
            "sci_entities": sorted(self.sci_entities),
            "umls_entities": sorted(self.umls_entities),
            "key_terms": sorted(self.key_terms),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NERResult":
        """Deserialize from dict."""
        return cls(
            web_entities=data.get("web_entities", []),
            sci_entities=data.get("sci_entities", []),
            umls_entities=data.get("umls_entities", []),
            key_terms=set(data.get("key_terms", [])),
        )


class NER_Extractor:
    """Three-layer concurrent NER extraction for scientific/medical queries.

    Layer 1 (Base): en_core_web_sm — general proper nouns
    Layer 2 (Scientific): en_core_sci_sm — scientific/medical entities
    Layer 3 (Medical Precision): UMLS n-gram lookup via UMLSClient

    All three layers run concurrently via asyncio.gather.
    Merge hierarchy (override priority): UMLS > sci > web.
    Each layer degrades independently.

    Parameters:
        spacy_web_nlp: Pre-loaded en_core_web_sm model (or None).
        spacy_sci_nlp: Pre-loaded en_core_sci_sm model (or None).
        umls_client: Optional UMLSClient for Layer 3 refinement.
        umls_timeout_ms: Timeout for UMLS lookup in milliseconds.
        max_ngram_size: Maximum n-gram token count for UMLS candidates.
    """

    # Labels to filter out from spaCy entities
    FILTERED_LABELS: frozenset = frozenset({
        "CARDINAL", "ORDINAL", "QUANTITY",
        "DATE", "TIME", "PERCENT", "MONEY",
    })

    _AGE_PATTERN = re.compile(r"^\d+-year-old$", re.IGNORECASE)
    _NUMERIC_PATTERN = re.compile(r"^\d+[\d\s.,%/:-]*$")

    def __init__(
        self,
        spacy_web_nlp: Optional[Any] = None,
        spacy_sci_nlp: Optional[Any] = None,
        umls_client: Optional[Any] = None,
        umls_timeout_ms: int = 200,
        max_ngram_size: int = 5,
    ) -> None:
        self.spacy_web_nlp = spacy_web_nlp
        self.spacy_sci_nlp = spacy_sci_nlp
        self.umls_client = umls_client
        self.umls_timeout_ms = umls_timeout_ms
        self.max_ngram_size = max_ngram_size

        logger.info(
            "NER_Extractor initialized — web_model=%s, sci_model=%s, "
            "umls=%s, timeout=%dms, max_ngram=%d",
            type(spacy_web_nlp).__name__ if spacy_web_nlp else "None",
            type(spacy_sci_nlp).__name__ if spacy_sci_nlp else "None",
            "available" if umls_client else "None",
            umls_timeout_ms,
            max_ngram_size,
        )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    async def extract_key_terms(self, query: str) -> NERResult:
        """Extract named entities and key terms from a query.

        Runs all three layers concurrently via asyncio.gather,
        then merges results with priority hierarchy:
        UMLS > en_core_sci_sm > en_core_web_sm.
        """
        if not query or not query.strip():
            return NERResult()

        # Run all three layers concurrently
        web_entities, sci_entities, umls_entities = await asyncio.gather(
            self._extract_layer1_web(query),
            self._extract_layer2_sci(query),
            self._extract_layer3_umls(query),
        )

        # Three-way merge with priority hierarchy
        key_terms = self._merge_entities(
            web_entities, sci_entities, umls_entities
        )

        return NERResult(
            web_entities=web_entities,
            sci_entities=sci_entities,
            umls_entities=umls_entities,
            key_terms=key_terms,
        )

    # -----------------------------------------------------------------
    # Layer 1 — Base (en_core_web_sm)
    # -----------------------------------------------------------------

    async def _extract_layer1_web(self, query: str) -> List[str]:
        """Layer 1 (Base): Extract entities using en_core_web_sm."""
        if self.spacy_web_nlp is None:
            return []
        try:
            return self._run_spacy_extraction(self.spacy_web_nlp, query)
        except Exception as e:
            logger.warning(
                "Layer 1 (en_core_web_sm) failed: %s, "
                "continuing with Layer 2+3",
                e,
            )
            return []

    # -----------------------------------------------------------------
    # Layer 2 — Scientific (en_core_sci_sm)
    # -----------------------------------------------------------------

    async def _extract_layer2_sci(self, query: str) -> List[str]:
        """Layer 2 (Scientific): Extract entities using en_core_sci_sm."""
        if self.spacy_sci_nlp is None:
            return []
        try:
            return self._run_spacy_extraction(self.spacy_sci_nlp, query)
        except Exception as e:
            logger.warning(
                "Layer 2 (en_core_sci_sm) failed: %s, "
                "continuing with Layer 1+3",
                e,
            )
            return []

    # -----------------------------------------------------------------
    # Shared spaCy extraction logic
    # -----------------------------------------------------------------

    def _run_spacy_extraction(self, nlp: Any, query: str) -> List[str]:
        """Shared spaCy extraction logic for Layer 1 and Layer 2.

        1. Run nlp(query) and extract named entities, filtering out
           FILTERED_LABELS, age descriptors, and numeric-only entities.
        2. Extract PROPN tokens (length > 2) and capitalized NOUN tokens
           (length > 2) from noun chunks.
        3. Return sorted list of unique terms.
        """
        doc = nlp(query)
        terms: set = set()

        # Named entities (filtered)
        for ent in doc.ents:
            text = ent.text.strip()
            if (
                not self._AGE_PATTERN.match(text)
                and not self._NUMERIC_PATTERN.match(text)
                and ent.label_ not in self.FILTERED_LABELS
            ):
                terms.add(ent.text)

        # PROPN tokens and capitalized NOUNs from noun chunks
        for nc in doc.noun_chunks:
            for tok in nc:
                if tok.pos_ == "PROPN" and len(tok.text) > 2:
                    terms.add(tok.text)
                elif (
                    tok.pos_ == "NOUN"
                    and tok.text[0:1].isupper()
                    and len(tok.text) > 2
                ):
                    terms.add(tok.text)

        return sorted(terms)

    # -----------------------------------------------------------------
    # Layer 3 — Medical Precision (UMLS n-gram lookup)
    # -----------------------------------------------------------------

    async def _extract_layer3_umls(self, query: str) -> List[str]:
        """Layer 3 (Medical Precision): UMLS n-gram lookup with timeout."""
        if self.umls_client is None:
            return []

        # Generate candidate n-grams
        candidates = self._generate_ngrams(query)
        if not candidates:
            return []

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.umls_client.batch_search_by_names(candidates),
                timeout=self.umls_timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(
                "Layer 3 UMLS lookup timed out after %.1fms "
                "(limit=%dms), continuing with Layer 1+2 only",
                elapsed,
                self.umls_timeout_ms,
            )
            return []
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.warning(
                "Layer 3 UMLS lookup failed after %.1fms: %s, "
                "continuing with Layer 1+2 only",
                elapsed,
                e,
            )
            return []

        if not result:
            return []

        # Return matched UMLS terms (original casing from candidates)
        matched = [name for name in candidates if name in result]
        elapsed = (time.monotonic() - start) * 1000
        logger.debug(
            "Layer 3 UMLS: %d candidates → %d matches in %.1fms",
            len(candidates),
            len(matched),
            elapsed,
        )
        return matched

    # -----------------------------------------------------------------
    # N-gram generation
    # -----------------------------------------------------------------

    def _generate_ngrams(self, query: str) -> List[str]:
        """Generate candidate n-grams (2 to max_ngram_size tokens).

        Splits query into words, generates all contiguous subsequences
        of 2 to max_ngram_size tokens, and strips trailing punctuation
        from each n-gram.
        """
        words = query.split()
        candidates: list = []
        for n in range(2, min(self.max_ngram_size + 1, len(words) + 1)):
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i : i + n])
                # Strip trailing punctuation from the n-gram
                gram = gram.strip("?.,!\"';:()[]{}").strip()
                if gram:
                    candidates.append(gram)
        return candidates

    # -----------------------------------------------------------------
    # Three-way entity merge
    # -----------------------------------------------------------------

    def _merge_entities(
        self,
        web_entities: List[str],
        sci_entities: List[str],
        umls_overrides: List[str],
    ) -> Set[str]:
        """Three-way merge with priority hierarchy.

        Override priority: UMLS > sci > web.
        - UMLS terms override shorter sci terms when they fully contain them.
        - Remaining sci terms override shorter web terms when they fully
          contain them.
        - UMLS terms also directly subsume web entities.
        - Non-overlapping terms from all three layers are preserved.
        - Longest match wins when multiple terms overlap.
        """
        merged: set = set()
        subsumed_sci: set = set()
        subsumed_web: set = set()

        # Step 1: UMLS overrides subsume shorter sci entities
        sorted_umls = sorted(umls_overrides, key=len, reverse=True)
        for umls_term in sorted_umls:
            umls_lower = umls_term.lower()
            for sci_ent in sci_entities:
                if (
                    sci_ent.lower() in umls_lower
                    and len(umls_term) > len(sci_ent)
                ):
                    subsumed_sci.add(sci_ent)
            merged.add(umls_term)

        # Step 2: Remaining sci entities subsume shorter web entities
        remaining_sci = [e for e in sci_entities if e not in subsumed_sci]
        sorted_sci = sorted(remaining_sci, key=len, reverse=True)
        for sci_term in sorted_sci:
            sci_lower = sci_term.lower()
            for web_ent in web_entities:
                if (
                    web_ent.lower() in sci_lower
                    and len(sci_term) > len(web_ent)
                ):
                    subsumed_web.add(web_ent)
            merged.add(sci_term)

        # Step 3: UMLS terms also directly subsume web entities
        for umls_term in sorted_umls:
            umls_lower = umls_term.lower()
            for web_ent in web_entities:
                if (
                    web_ent.lower() in umls_lower
                    and len(umls_term) > len(web_ent)
                ):
                    subsumed_web.add(web_ent)

        # Step 4: Add non-subsumed web entities
        for web_ent in web_entities:
            if web_ent not in subsumed_web:
                merged.add(web_ent)

        return merged
