"""
UMLS Linker for linking document-extracted concepts to UMLS concepts.

Links ConceptNode instances to UMLS CUIs during knowledge graph extraction
by performing batch lookups against the UMLS data in Neo4j. Updates
external_ids with matched CUIs and refines concept_type using UMLS
semantic types when the current type is the default "ENTITY".

Degrades gracefully when the UMLS client is None or unavailable —
returns input concepts unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

import structlog

from multimodal_librarian.models.knowledge_graph import ConceptNode

if TYPE_CHECKING:
    from multimodal_librarian.components import knowledge_graph as _kg
    UMLSClient = _kg.umls_client.UMLSClient

logger = structlog.get_logger(__name__)


class UMLSLinker:
    """Links document-extracted concepts to UMLS CUIs.

    Uses the UMLSClient to batch-search concept names against UMLS data
    in Neo4j. For matched concepts, sets ``external_ids["umls_cui"]`` and
    optionally updates ``concept_type`` from the default ``"ENTITY"`` to
    the UMLS semantic type name.

    When ``umls_client`` is ``None`` or unavailable, all methods return
    the input concepts unchanged (passthrough).
    """

    def __init__(self, umls_client: Optional[UMLSClient] = None) -> None:
        self._client = umls_client

    async def link_concepts(
        self,
        concepts: List[ConceptNode],
        document_context: Optional[str] = None,
    ) -> List[ConceptNode]:
        """Link a list of extracted concepts to UMLS CUIs.

        Parameters
        ----------
        concepts:
            Concept nodes extracted from a document chunk.
        document_context:
            Optional text describing the document domain, used for
            disambiguation when multiple UMLS matches exist.

        Returns
        -------
        The same list of concepts, potentially enriched with UMLS CUIs
        and refined concept types. Returned unchanged when the UMLS
        client is unavailable.
        """
        if not concepts:
            return concepts

        # Graceful degradation: no client → passthrough
        if self._client is None:
            logger.debug("umls_linker_skip", reason="no_client")
            return concepts

        if not await self._client.is_available():
            logger.debug("umls_linker_skip", reason="client_unavailable")
            return concepts

        # Step 1: Collect concept names for batch lookup
        names = [c.concept_name for c in concepts]

        # Step 2: Batch search all names in a single query
        name_to_cui = await self._client.batch_search_by_names(names)
        if name_to_cui is None:
            logger.debug(
                "umls_linker_skip",
                reason="batch_search_returned_none",
            )
            return concepts

        matched = 0
        for concept in concepts:
            cui = name_to_cui.get(concept.concept_name)
            if cui is None:
                continue

            # Step 3a: Store the CUI
            concept.external_ids["umls_cui"] = cui
            matched += 1

            # Step 3b: Update concept_type for default-typed concepts
            if concept.concept_type == "ENTITY":
                sem_types = await self._client.get_semantic_types(cui)
                if sem_types:
                    concept.concept_type = sem_types[0]

        logger.info(
            "umls_linker_complete",
            total=len(concepts),
            matched=matched,
        )
        return concepts
