"""Emergent-bootstrap: conversation-time scaffolding for unresolved idioms (§5.5).

When a query surfaces a phrase that no document and no ontology (UMLS/ConceptNet)
can supply, this component turns the silent semantic fallback into a transparent,
human-anchored interaction:

1. Offer a ranked candidate list — the closest existing Librarian concepts by
   embedding first; only when the phrase has *no* close embedding (a true
   orphan), generate head+modifier composites and keep only those viable under a
   faithful ConceptNet edge (§4.5).
2. On selection, mint a durable ``Concept`` (``provenance='llm-bootstrap'``) and
   wire it to the choice — ``SIMILAR_TO`` for an existing concept, ``SAME_AS`` to
   a ``:Anchor {kind:"composite"}`` for a subgraph equivalent.

The minted node hardcodes ``scope='public'`` / ``owner_id=NULL`` through Phase 5
(§7).  The Phase 0 orphan-cleanup predicate already preserves ``llm-bootstrap``
nodes, so the write is safe across document deletions.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from ...models.kg_retrieval import (
    ClarificationRequest,
    CompositeCandidate,
    ConceptCandidate,
    UnresolvedPhrase,
)

logger = logging.getLogger(__name__)

# Mint a bare bootstrap Concept and link it to an existing Librarian concept via
# SIMILAR_TO (confidence = the candidate's similarity).  MERGE keeps it idempotent
# and honours earliest-wins provenance: an existing node is never re-provenanced.
_MINT_CONCEPT = """
MERGE (c:Concept {name_lower: toLower($name), scope: 'public'})
ON CREATE SET c.name = $name,
              c.name_lower = toLower($name),
              c.scope = 'public',
              c.bridge_status = 'emergent',
              c.provenance = 'llm-bootstrap',
              c.owner_id = NULL,
              c.concept_id = 'public:' + toLower($name),
              c.embedding = $embedding,
              c.created_at = $ts,
              c.updated_at = $ts
WITH c
MATCH (t:Concept {concept_id: $chosen_id})
MERGE (c)-[r:SIMILAR_TO]->(t)
ON CREATE SET r.confidence = $similarity, r.created_at = $ts
RETURN c.concept_id AS concept_id
"""

# Mint a bootstrap Concept and anchor it to a ConceptNet subgraph equivalent via a
# reified :Anchor {kind:"composite"} (mirrors enrichment_service's materializer).
_MINT_COMPOSITE = """
MERGE (c:Concept {name_lower: toLower($name), scope: 'public'})
ON CREATE SET c.name = $name,
              c.name_lower = toLower($name),
              c.scope = 'public',
              c.bridge_status = 'emergent',
              c.provenance = 'llm-bootstrap',
              c.owner_id = NULL,
              c.concept_id = 'public:' + toLower($name),
              c.embedding = $embedding,
              c.created_at = $ts,
              c.updated_at = $ts
WITH c
MATCH (h:ConceptNetConcept {name: $head})
MATCH (m:ConceptNetConcept {name: $modifier})
MERGE (a:Anchor {kind: 'composite', relationship_type: $rel_type,
                 name_lower: toLower($name), scope: 'public'})
ON CREATE SET a.owner_id = NULL, a.created_at = $ts
MERGE (a)-[:HAS_PART]->(h)
MERGE (a)-[:HAS_PART]->(m)
MERGE (c)-[:SAME_AS]->(a)
RETURN c.concept_id AS concept_id
"""


class EmergentBootstrap:
    """Build candidate lists and mint llm-bootstrap nodes at conversation time."""

    def __init__(
        self,
        neo4j_client: Any,
        model_server_client: Any,
        conceptnet_validator: Any,
        ai_service: Any = None,
    ) -> None:
        self._neo4j = neo4j_client
        self._model = model_server_client
        self._conceptnet = conceptnet_validator
        self._ai = ai_service

    async def build_clarification(
        self,
        query: str,
        unresolved_phrases: List[UnresolvedPhrase],
    ) -> ClarificationRequest:
        """Attach composite candidates (lazily) and wrap into a ClarificationRequest."""
        for phrase in unresolved_phrases:
            if not phrase.nearest_concepts:
                phrase.composite_candidates = await self._build_composites(
                    phrase.phrase
                )
        return ClarificationRequest(
            request_id=uuid4().hex,
            original_query=query,
            unresolved_phrases=unresolved_phrases,
        )

    async def _build_composites(
        self, phrase: str, limit: int = 5
    ) -> List[CompositeCandidate]:
        """Decompose the phrase into head+modifier and pre-screen through ConceptNet."""
        if not self._ai or not self._conceptnet:
            return []

        pairs = await self._decompose_head_modifier(phrase)
        composites: List[CompositeCandidate] = []
        for head, modifier in pairs:
            viable = await self._is_viable(head, modifier)
            if not viable:
                continue
            composites.append(
                CompositeCandidate(
                    head=head,
                    modifier=modifier,
                    relationship_type=viable,
                    display=f"{modifier} {head}",
                )
            )
            if len(composites) >= limit:
                break
        return composites

    async def _decompose_head_modifier(self, phrase: str) -> List[tuple]:
        """Ask the LLM for head|modifier decompositions of a phrase."""
        prompt = [
            {
                "role": "user",
                "content": (
                    f'Decompose the phrase "{phrase}" into its head noun and '
                    'modifier. Return one decomposition per line in the format '
                    '"head|modifier" (head first). If the phrase is a non-'
                    'compositional idiom (e.g. "cold feet"), return nothing.'
                ),
            }
        ]
        try:
            response = await self._ai.generate_response(
                messages=prompt,
                temperature=0.0,
                max_tokens=150,
            )
            text = getattr(response, "content", "") or ""
        except Exception as e:
            logger.warning(f"Composite decomposition failed: {e}")
            return []

        pairs: List[tuple] = []
        for line in text.splitlines():
            line = line.strip().strip("- ").strip()
            if not line or "|" not in line:
                continue
            head, _, modifier = line.partition("|")
            head, modifier = head.strip().lower(), modifier.strip().lower()
            if head and modifier and head != modifier:
                pairs.append((head, modifier))
        return pairs

    async def _is_viable(self, head: str, modifier: str) -> Optional[str]:
        """Return the faithful ConceptNet edge type, or None if not viable (§4.5)."""
        try:
            found = await self._conceptnet.batch_lookup_concepts([head, modifier])
            if head not in found or modifier not in found:
                return None
            edges = await self._conceptnet.get_relationships_for_concepts(
                [head, modifier]
            )
            if not edges:
                return None
            return edges[0].predicate or edges[0].raw_relation_type
        except Exception as e:
            logger.warning(f"ConceptNet viability check failed: {e}")
            return None

    async def mint(self, phrase: str, choice: Any) -> None:
        """Fire-and-forget write: mint the bootstrap Concept and wire it to the choice."""
        try:
            embeddings = await self._model.generate_embeddings([phrase])
            embedding = embeddings[0] if embeddings else None
        except Exception as e:
            logger.warning(f"Embedding for bootstrap mint failed: {e}")
            embedding = None

        ts = datetime.now(timezone.utc).isoformat()

        if isinstance(choice, CompositeCandidate):
            query = _MINT_COMPOSITE
            params = {
                "name": phrase,
                "embedding": embedding,
                "head": choice.head,
                "modifier": choice.modifier,
                "rel_type": choice.relationship_type,
                "ts": ts,
            }
        elif isinstance(choice, ConceptCandidate):
            query = _MINT_CONCEPT
            params = {
                "name": phrase,
                "embedding": embedding,
                "chosen_id": choice.concept_id,
                "similarity": choice.similarity_score,
                "ts": ts,
            }
        else:
            logger.warning(f"Unknown candidate choice: {choice!r}")
            return

        try:
            await self._neo4j.execute_write_query(query, params)
            logger.info(f"Minted llm-bootstrap concept for {phrase!r}")
        except Exception as e:
            logger.warning(f"llm-bootstrap mint failed for {phrase!r}: {e}")

    @staticmethod
    def substitute(query: str, phrase: str, replacement: str) -> str:
        """Replace the first (case-insensitive) occurrence of phrase in query."""
        return re.compile(re.escape(phrase), re.IGNORECASE).sub(
            replacement, query, count=1
        )
