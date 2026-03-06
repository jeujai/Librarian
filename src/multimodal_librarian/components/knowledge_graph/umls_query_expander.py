"""
UMLS Query Expander Component.

Expands RAG queries using UMLS synonyms and related concepts
to improve retrieval of biomedical content when users use
different terminology than the source documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

import structlog

if TYPE_CHECKING:
    from multimodal_librarian.components import knowledge_graph as _kg

    UMLSClient = _kg.umls_client.UMLSClient

logger = structlog.get_logger(__name__)


@dataclass
class ExpandedTerm:
    """A query expansion term derived from UMLS data."""

    term: str
    weight: float  # 0.3 to 0.8
    source: str  # "synonym" or "related"
    cui: Optional[str] = None


class UMLSQueryExpander:
    """Expands RAG queries using UMLS synonyms and related concepts.

    For each query term that matches a UMLS concept, retrieves synonyms
    and directly related concepts (1-hop) to broaden the search. Assigns
    weights in the [0.3, 0.8] range based on relationship type:
    - Synonyms: 0.7 (high relevance, same concept different name)
    - Related concepts: 0.4 (moderate relevance, connected concept)

    When ``umls_client`` is ``None`` or unavailable, returns an empty
    list (no expansion).
    """

    SYNONYM_WEIGHT = 0.7
    RELATED_WEIGHT = 0.4

    def __init__(self, umls_client: Optional[UMLSClient] = None) -> None:
        self._client = umls_client

    async def expand_query(
        self,
        query_terms: List[str],
        max_synonyms: int = 5,
    ) -> List[ExpandedTerm]:
        """Expand query terms using UMLS synonyms and related concepts.

        Parameters
        ----------
        query_terms:
            List of terms extracted from the user query.
        max_synonyms:
            Maximum number of synonyms to include per term (default 5).

        Returns
        -------
        List of ``ExpandedTerm`` entries with weights in [0.3, 0.8].
        Returns an empty list when the UMLS client is unavailable.
        """
        if not query_terms:
            return []

        if self._client is None:
            logger.debug("umls_query_expander_skip", reason="no_client")
            return []

        if not await self._client.is_available():
            logger.debug(
                "umls_query_expander_skip", reason="client_unavailable",
            )
            return []

        expanded: List[ExpandedTerm] = []

        for term in query_terms:
            term_expansions = await self._expand_single_term(
                term, max_synonyms,
            )
            expanded.extend(term_expansions)

        logger.info(
            "umls_query_expansion_complete",
            input_terms=len(query_terms),
            expanded_terms=len(expanded),
        )
        return expanded

    async def _expand_single_term(
        self,
        term: str,
        max_synonyms: int,
    ) -> List[ExpandedTerm]:
        """Expand a single query term via UMLS lookup.

        Steps:
        1. Search UMLS by name to find a matching concept
        2. If found, retrieve synonyms (up to max_synonyms)
        3. Retrieve directly related concepts (1-hop)
        4. Return ExpandedTerm entries with appropriate weights
        """
        assert self._client is not None  # guaranteed by caller

        # Step 1: Search for the term in UMLS
        matches = await self._client.search_by_name(term)
        if not matches:
            logger.debug(
                "umls_query_expander_no_match", term=term,
            )
            return []

        # Use the first match (best match by CUI sort order)
        cui = matches[0].get("cui")
        if not cui:
            return []

        results: List[ExpandedTerm] = []

        # Step 2: Get synonyms for the matched concept
        synonyms = await self._client.get_synonyms(cui)
        if synonyms:
            # Take up to max_synonyms, excluding the original term
            added = 0
            for synonym in synonyms:
                if added >= max_synonyms:
                    break
                if synonym.lower() == term.lower():
                    continue
                results.append(
                    ExpandedTerm(
                        term=synonym,
                        weight=self.SYNONYM_WEIGHT,
                        source="synonym",
                        cui=cui,
                    ),
                )
                added += 1

        # Step 3: Get directly related concepts (1-hop)
        related = await self._client.get_related_concepts(cui, limit=5)
        if related:
            for rel in related:
                rel_name = rel.get("preferred_name")
                rel_cui = rel.get("cui")
                if not rel_name:
                    continue
                # Skip if it duplicates the original term
                if rel_name.lower() == term.lower():
                    continue
                results.append(
                    ExpandedTerm(
                        term=rel_name,
                        weight=self.RELATED_WEIGHT,
                        source="related",
                        cui=rel_cui,
                    ),
                )

        logger.debug(
            "umls_query_expander_term",
            term=term,
            cui=cui,
            synonyms_added=sum(
                1 for r in results if r.source == "synonym"
            ),
            related_added=sum(
                1 for r in results if r.source == "related"
            ),
        )
        return results
