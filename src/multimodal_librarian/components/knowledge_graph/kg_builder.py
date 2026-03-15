"""
Knowledge Graph Builder Component.

This component extracts concepts and relationships from all content types,
builds incremental knowledge graphs, and manages knowledge graph construction.
"""

import asyncio
import logging
import math
import re
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ...config import get_settings
from ...models.core import KnowledgeChunk, RelationshipType
from ...models.knowledge_graph import (
    ConceptExtraction,
    ConceptNode,
    KnowledgeGraphStats,
    RelationshipEdge,
    Triple,
)
from .relation_type_mapper import RelationTypeMapper

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound embedding operations
_kg_executor: Optional[ThreadPoolExecutor] = None


def _get_kg_executor() -> ThreadPoolExecutor:
    """Get or create the KG thread pool executor for CPU-bound operations."""
    global _kg_executor
    if _kg_executor is None:
        _kg_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="kg_embedding"
        )
        logger.info("Created KG embedding thread pool executor")
    return _kg_executor


class ConceptExtractor:
    """Extracts concepts from text using multiple methods."""
    
    def __init__(self):
        self.settings = get_settings()
        self._embedding_model = None  # Lazy loaded (local fallback only)
        self._model_server_client = None  # Model server client (preferred)
        self._model_lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
        
        # Curated concept patterns (regex-only extraction)
        # ENTITY, PROCESS, PROPERTY patterns removed — replaced by spaCy NER
        self.concept_patterns = {
            'CODE_TERM': [
                r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b',                    # snake_case: allow_dangerous_code, max_retries
                r'\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b',               # camelCase: getData, processDocument
                r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',                       # PascalCase: ConnectionManager, DataProcessor
                r'\b[a-zA-Z_][a-zA-Z0-9_]*=[A-Za-z0-9_]+\b',             # param assignment: allowed_dangerous_code=True
                r'\b[a-zA-Z_][a-zA-Z0-9_]*\(\)',                           # function calls: process_document(), getData()
                r'\b[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*){1,4}\b',         # dotted: os.path.join, config.settings
            ],
            'MULTI_WORD': [
                r'\b(?:knowledge graph|vector database|natural language processing|'
                r'machine learning|deep learning|neural network|'
                r'information retrieval|semantic search|named entity recognition|'
                r'text embedding|content analysis|concept extraction|'
                r'graph database|search engine|data model|'
                r'chunk(?:ing)?\s+(?:strategy|framework|pipeline|size)|'
                r'retrieval\s+(?:quality|pipeline|service|augmented)|'
                r'embedding\s+(?:model|dimension|space|vector))\b',
            ],
            'ACRONYM': [
                r'\b[A-Z]{2,6}\b',
            ],
        }
        
        # Acronym stopword filter — common short English words that match the ACRONYM pattern
        self._acronym_stopwords = {
            "IT", "IS", "OR", "AN", "AT", "IF", "IN", "ON", "TO", "UP",
            "DO", "GO", "NO", "SO", "BY", "HE", "ME", "WE", "US", "AM",
            "BE", "OF", "AS",
        }
        
        # Corpus-level collocation frequency cache.
        # Keyed by normalized bigram string (e.g. "knowledge_graph"), storing:
        #   frequency: cumulative count across all documents
        #   doc_count: number of documents the bigram appeared in
        self._collocation_cache: Dict[str, Dict[str, int]] = {}
    
    @property
    def embedding_model(self):
        """
        Embedding model property - models are served by model-server container.
        
        NOTE: Local model loading has been removed. Use generate_embeddings_async()
        which calls the model server for non-blocking operation.
        """
        logger.warning("Local embedding model not available - use generate_embeddings_async() instead")
        return None
    
    async def _get_model_server_client(self):
        """Get or initialize the model server client."""
        if self._model_server_client is None:
            try:
                from ...clients.model_server_client import (
                    get_model_client,
                    initialize_model_client,
                )
                
                client = get_model_client()
                if client is None:
                    await initialize_model_client()
                    client = get_model_client()
                
                if client and client.enabled:
                    self._model_server_client = client
            except Exception as e:
                logger.warning(f"Model server not available: {e}")
        return self._model_server_client
    
    async def generate_embeddings_async(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings asynchronously using model server (non-blocking).
        
        Model server is required - no local fallback.
        """
        # Try model server first
        client = await self._get_model_server_client()
        if client is not None:
            try:
                embeddings = await client.generate_embeddings(texts)
                if embeddings:
                    return np.array(embeddings)
            except Exception as e:
                logger.warning(f"Model server embedding failed: {e}")
        
        # Fallback to local model via thread pool
        executor = _get_kg_executor()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self._encode_sync, texts)
    
    def _encode_sync(self, texts: List[str]) -> np.ndarray:
        """Synchronous encode - called in thread pool."""
        return self.embedding_model.encode(texts)
    
    def extract_concepts_regex(self, text: str) -> List[ConceptNode]:
        """Extract concepts using curated regex patterns only (MULTI_WORD, CODE_TERM, ACRONYM + PMI).

        Assigns pattern-specific confidence scores from settings:
        - MULTI_WORD (seed list): ``multi_word_seed_confidence`` (default 0.85)
        - ACRONYM: ``acronym_confidence`` (default 0.6)
        - All other types: 0.7

        Applies a frequency boost of ``frequency_boost_increment`` per
        additional occurrence, capped at ``frequency_boost_cap`` above the
        base confidence.

        After the pattern loop the method:
        1. Updates the corpus-level collocation cache.
        2. Merges PMI-discovered collocations (deduplicating by normalised name,
           keeping the higher-confidence seed match when both exist).
        3. Runs acronym-expansion alias linking.
        """
        # Read confidence settings with safe defaults
        multi_word_seed_conf = getattr(self.settings, 'multi_word_seed_confidence', 0.85)
        acronym_conf = getattr(self.settings, 'acronym_confidence', 0.6)
        freq_increment = getattr(self.settings, 'frequency_boost_increment', 0.02)
        freq_cap = getattr(self.settings, 'frequency_boost_cap', 0.1)

        concepts = []
        concept_id_map = {}
        # Track cumulative frequency boost per concept_id
        freq_boost_map: Dict[str, float] = {}

        for concept_type, patterns in self.concept_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    concept_name = match.group().strip()
                    if len(concept_name) < 3:  # Skip very short concepts
                        continue

                    # Filter ACRONYM matches against stopword set
                    if concept_type == 'ACRONYM' and concept_name.upper() in self._acronym_stopwords:
                        continue

                    # Normalize concept name
                    normalized_name = self._normalize_concept_name(concept_name)
                    concept_id = f"{concept_type.lower()}_{normalized_name}"

                    if concept_id not in concept_id_map:
                        # Determine base confidence by pattern type
                        if concept_type == 'MULTI_WORD':
                            base_confidence = multi_word_seed_conf
                        elif concept_type == 'ACRONYM':
                            base_confidence = acronym_conf
                        else:
                            base_confidence = 0.7  # NER confidence for other types

                        concept = ConceptNode(
                            concept_id=concept_id,
                            concept_name=concept_name,
                            concept_type=concept_type,
                            confidence=base_confidence,
                        )
                        concepts.append(concept)
                        concept_id_map[concept_id] = concept
                        freq_boost_map[concept_id] = 0.0
                    else:
                        # Repeated occurrence — apply frequency boost
                        existing_concept = concept_id_map[concept_id]
                        current_boost = freq_boost_map[concept_id]
                        if current_boost < freq_cap:
                            added = min(freq_increment, freq_cap - current_boost)
                            existing_concept.confidence += added
                            freq_boost_map[concept_id] = current_boost + added

                        # Add as alias if different surface form
                        if concept_name not in existing_concept.aliases and concept_name != existing_concept.concept_name:
                            existing_concept.add_alias(concept_name)

        # Update corpus-level collocation cache
        self._update_collocation_cache(text)

        # Merge PMI-discovered collocations, deduplicating by normalised name
        pmi_concepts = self._extract_collocations_pmi(text)
        for pmi_concept in pmi_concepts:
            normalized_name = self._normalize_concept_name(pmi_concept.concept_name)
            pmi_id = f"multi_word_{normalized_name}"
            if pmi_id not in concept_id_map:
                concepts.append(pmi_concept)
                concept_id_map[pmi_id] = pmi_concept

        # Link acronym expansions (stub-safe — method may not exist yet)
        if hasattr(self, '_link_acronym_expansions'):
            self._link_acronym_expansions(text, concepts, concept_id_map)

        return concepts
    
    async def extract_concepts_with_ner(self, text: str) -> List[ConceptNode]:
        """Extract concepts using spaCy NER via model server.

        Calls ``ModelServerClient.get_entities()`` and converts each spaCy
        entity dict into a :class:`ConceptNode` with ``concept_type`` set to
        the spaCy label and ``confidence`` of 0.85.

        Returns an empty list and logs a warning when the model server is
        unavailable.
        """
        client = await self._get_model_server_client()
        if client is None:
            logger.warning(
                "Model server unavailable, skipping NER extraction"
            )
            return []

        try:
            entity_lists = await client.get_entities([text])
        except Exception as e:
            logger.warning(f"NER extraction failed: {e}")
            return []

        concepts: List[ConceptNode] = []
        seen: set = set()
        for entity in entity_lists[0] if entity_lists else []:
            name = entity.get("text", "").strip()
            label = entity.get("label", "ENTITY")
            if not name or len(name) < 2:
                continue
            normalized = self._normalize_concept_name(name)
            concept_id = f"{label.lower()}_{normalized}"
            if concept_id in seen:
                continue
            seen.add(concept_id)
            concepts.append(
                ConceptNode(
                    concept_id=concept_id,
                    concept_name=name,
                    concept_type=label,
                    confidence=0.85,
                )
            )
        return concepts

    async def extract_all_concepts_async(self, text: str) -> List[ConceptNode]:
        """Combine NER + regex extraction and deduplicate.

        Merges results from :meth:`extract_concepts_with_ner` (spaCy NER via
        model server) and :meth:`extract_concepts_regex` (MULTI_WORD,
        CODE_TERM, ACRONYM + PMI).  Deduplicates by normalized concept name,
        keeping the higher-confidence entry.

        If the model server is unavailable the result is regex-only (a warning
        is already logged by :meth:`extract_concepts_with_ner`).
        """
        ner_concepts = await self.extract_concepts_with_ner(text)
        regex_concepts = self.extract_concepts_regex(text)

        # Merge: index by normalized name, keep higher confidence
        merged: Dict[str, ConceptNode] = {}
        for concept in ner_concepts + regex_concepts:
            key = self._normalize_concept_name(concept.concept_name)
            existing = merged.get(key)
            if existing is None or concept.confidence > existing.confidence:
                merged[key] = concept
        return list(merged.values())

    def extract_concepts_llm(self, text: str, chunk_id: str) -> List[ConceptNode]:
        """Extract concepts using LLM-based analysis."""
        # This would integrate with an LLM API like OpenAI GPT-4
        # For now, implementing a simplified version
        concepts = []
        
        # Extract key terms and phrases
        sentences = text.split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            
            # Look for definition patterns
            definition_patterns = [
                r'(.+?)\s+is\s+(?:a|an)\s+(.+)',
                r'(.+?)\s+refers\s+to\s+(.+)',
                r'(.+?)\s+means\s+(.+)',
                r'(.+?):\s+(.+)'
            ]
            
            for pattern in definition_patterns:
                match = re.search(pattern, sentence, re.IGNORECASE)
                if match:
                    concept_name = match.group(1).strip()
                    definition = match.group(2).strip()
                    
                    if len(concept_name) > 2 and len(definition) > 5:
                        concept_id = f"entity_{self._normalize_concept_name(concept_name)}"
                        concept = ConceptNode(
                            concept_id=concept_id,
                            concept_name=concept_name,
                            concept_type="ENTITY",
                            confidence=0.8,  # LLM confidence
                            source_chunks=[chunk_id]
                        )
                        concepts.append(concept)
        
        return concepts
    
    def extract_concepts_embedding(self, text: str, chunk_id: str, 
                                 existing_concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Extract concepts using embedding-based similarity (sync version - use async when possible)."""
        if not existing_concepts:
            return []
        
        # Skip if no local embedding model (model-server-separation architecture)
        # Use extract_concepts_embedding_async for embedding-based extraction
        if self.embedding_model is None:
            logger.debug("Skipping embedding-based concept extraction - no local model (use async version)")
            return []
        
        # Generate embedding for the text - this is blocking, prefer async version
        text_embedding = self._encode_sync([text])[0]
        
        # Find similar concepts based on embeddings
        similar_concepts = []
        for concept in existing_concepts:
            # Generate embedding for concept name
            concept_embedding = self._encode_sync([concept.concept_name])[0]
            
            # Calculate similarity
            similarity = np.dot(text_embedding, concept_embedding) / (
                np.linalg.norm(text_embedding) * np.linalg.norm(concept_embedding)
            )
            
            if similarity > 0.7:  # High similarity threshold
                # Create a reference to existing concept
                referenced_concept = ConceptNode(
                    concept_id=concept.concept_id,
                    concept_name=concept.concept_name,
                    concept_type=concept.concept_type,
                    confidence=similarity,
                    source_chunks=[chunk_id]
                )
                similar_concepts.append(referenced_concept)
        
        return similar_concepts
    
    async def extract_concepts_embedding_async(self, text: str, chunk_id: str, 
                                              existing_concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Extract concepts using embedding-based similarity (async, non-blocking via model server)."""
        if not existing_concepts:
            return []
        
        try:
            # Get model server client
            model_server_client = await self._get_model_server_client()
            if model_server_client is None:
                logger.debug("Model server not available for embedding-based concept extraction")
                return []
            
            # Generate embedding for the text via model server
            text_embeddings = await model_server_client.generate_embeddings([text])
            if not text_embeddings:
                logger.warning("Failed to generate text embedding via model server")
                return []
            text_embedding = np.array(text_embeddings[0])
            
            # Find similar concepts based on embeddings
            similar_concepts = []
            concept_names = [concept.concept_name for concept in existing_concepts]
            
            # Batch encode all concept names via model server
            concept_embeddings = await model_server_client.generate_embeddings(concept_names)
            if not concept_embeddings:
                logger.warning("Failed to generate concept embeddings via model server")
                return []
            
            for concept, concept_embedding in zip(existing_concepts, concept_embeddings):
                concept_embedding = np.array(concept_embedding)
                # Calculate similarity
                similarity = np.dot(text_embedding, concept_embedding) / (
                    np.linalg.norm(text_embedding) * np.linalg.norm(concept_embedding)
                )
                
                if similarity > 0.7:  # High similarity threshold
                    # Create a reference to existing concept
                    referenced_concept = ConceptNode(
                        concept_id=concept.concept_id,
                        concept_name=concept.concept_name,
                        concept_type=concept.concept_type,
                        confidence=float(similarity),
                        source_chunks=[chunk_id]
                    )
                    similar_concepts.append(referenced_concept)
            
            return similar_concepts
            
        except Exception as e:
            logger.warning(f"Error in embedding-based concept extraction: {e}")
            return []
    
    def _normalize_concept_name(self, name: str) -> str:
        """Normalize concept name for ID generation."""
        # Remove articles and common words
        stop_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with'}
        words = name.lower().split()
        filtered_words = [word for word in words if word not in stop_words]
        return '_'.join(filtered_words)

    def _update_collocation_cache(self, text: str) -> None:
        """
        Update the corpus-level collocation frequency cache with bigrams from *text*.

        Each call represents one document.  For every unique bigram in the text
        we increment ``doc_count`` by 1 and add the bigram's occurrence count to
        ``frequency``.

        Args:
            text: The full document (or chunk) text to analyse.
        """
        words = text.lower().split()
        if len(words) < 2:
            return

        bigram_freq = Counter(zip(words, words[1:]))
        seen_bigrams: Set[str] = set()

        for (w1, w2), count in bigram_freq.items():
            key = f"{w1}_{w2}"
            if key not in self._collocation_cache:
                self._collocation_cache[key] = {"frequency": 0, "doc_count": 0}
            self._collocation_cache[key]["frequency"] += count
            if key not in seen_bigrams:
                self._collocation_cache[key]["doc_count"] += 1
                seen_bigrams.add(key)

    # Stopwords for PMI collocation filtering
    _pmi_stopwords = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "and", "or", "but", "if",
        "then", "than", "that", "this", "these", "those", "for", "from",
        "with", "into", "of", "to", "in", "on", "at", "by", "as", "not", "no",
    })

    def _extract_collocations_pmi(self, text: str) -> List[ConceptNode]:
        """
        Extract multi-word concepts via Pointwise Mutual Information.

        PMI(x,y) = log2(P(x,y) / (P(x) * P(y)))

        A PMI threshold of 5.0 means the bigram co-occurs ~32x more often
        than expected by chance. This is a conservative threshold that
        filters most noise while catching genuine collocations.

        When the corpus-level collocation cache has entries, PMI is computed
        using corpus-level frequencies for improved accuracy.  For the first
        document (empty cache) the method falls back to document-level PMI.

        Args:
            text: The chunk text to analyze.

        Returns:
            List of ConceptNode objects for bigrams exceeding the PMI threshold.
        """
        words = text.lower().split()
        if len(words) < 10:
            return []  # too short for meaningful statistics

        pmi_threshold = getattr(self.settings, 'pmi_threshold', 5.0)
        base_confidence = getattr(self.settings, 'multi_word_pmi_confidence', 0.65)

        use_corpus = bool(self._collocation_cache)

        if use_corpus:
            # Corpus-level PMI: aggregate frequencies from the cache
            corpus_total = sum(
                entry["frequency"] for entry in self._collocation_cache.values()
            )
            # Build corpus-level unigram frequencies from cached bigrams
            corpus_word_freq: Counter = Counter()
            for key, entry in self._collocation_cache.items():
                w1, w2 = key.split("_", 1)
                corpus_word_freq[w1] += entry["frequency"]
                corpus_word_freq[w2] += entry["frequency"]
        else:
            corpus_total = 0
            corpus_word_freq = Counter()

        # Document-level frequencies (always needed for occurrence count check)
        word_freq = Counter(words)
        bigrams = list(zip(words, words[1:]))
        bigram_freq = Counter(bigrams)
        total = len(words)

        concepts = []
        for (w1, w2), count in bigram_freq.items():
            if count < 2:
                continue  # require at least 2 occurrences
            if w1 in self._pmi_stopwords or w2 in self._pmi_stopwords:
                continue  # skip stopword bigrams

            if use_corpus:
                cache_key = f"{w1}_{w2}"
                cached = self._collocation_cache.get(cache_key)
                if cached and corpus_total > 0:
                    p_xy = cached["frequency"] / corpus_total
                    p_x = corpus_word_freq.get(w1, 1) / (2 * corpus_total)
                    p_y = corpus_word_freq.get(w2, 1) / (2 * corpus_total)
                else:
                    # Bigram not in cache yet — fall back to document-level
                    p_xy = count / total
                    p_x = word_freq[w1] / total
                    p_y = word_freq[w2] / total
            else:
                # No cache — pure document-level PMI
                p_xy = count / total
                p_x = word_freq[w1] / total
                p_y = word_freq[w2] / total

            if p_x * p_y == 0:
                continue  # avoid division by zero

            pmi = math.log2(p_xy / (p_x * p_y))

            if pmi >= pmi_threshold:
                phrase = f"{w1} {w2}"
                confidence = base_confidence + min(0.1, (count - 2) * 0.02)
                normalized = self._normalize_concept_name(phrase)
                concept_id = f"multi_word_{normalized}"

                concepts.append(ConceptNode(
                    concept_id=concept_id,
                    concept_name=phrase,
                    concept_type="MULTI_WORD",
                    confidence=confidence,
                    source_chunks=[],
                ))

        return concepts

    def _link_acronym_expansions(
        self,
        text: str,
        concepts: List[ConceptNode],
        concept_id_map: Dict[str, ConceptNode],
    ) -> None:
        """Link acronyms to their expanded forms as aliases.

        Detects patterns like ``"Expanded Form (ACRONYM)"`` and
        ``"ACRONYM (Expanded Form)"`` and links matching concepts
        via ``add_alias``.
        """
        # Pattern 1: "Expanded Form (ACRONYM)" — e.g. "Natural Language Processing (NLP)"
        expansion_first = re.finditer(
            r'([A-Z][a-z]+(?:\s+[A-Za-z]+)*)\s*\(([A-Z]{2,6})\)',
            text,
        )
        # Pattern 2: "ACRONYM (Expanded Form)" — e.g. "NLP (Natural Language Processing)"
        acronym_first = re.finditer(
            r'([A-Z]{2,6})\s*\(([A-Z][a-z]+(?:\s+[A-Za-z]+)*)\)',
            text,
        )

        pairs: List[tuple] = []  # (acronym_text, expansion_text)
        for m in expansion_first:
            pairs.append((m.group(2), m.group(1)))
        for m in acronym_first:
            pairs.append((m.group(1), m.group(2)))

        for acronym_text, expansion_text in pairs:
            # Skip stopword acronyms
            if acronym_text.upper() in self._acronym_stopwords:
                continue

            acronym_norm = self._normalize_concept_name(acronym_text)
            expansion_norm = self._normalize_concept_name(expansion_text)

            # Look up both forms across all concept type prefixes in the map
            acronym_concept = concept_id_map.get(f"acronym_{acronym_norm}")
            expansion_concept = (
                concept_id_map.get(f"entity_{expansion_norm}")
                or concept_id_map.get(f"multi_word_{expansion_norm}")
            )

            if acronym_concept is not None:
                acronym_concept.add_alias(expansion_text)
            if expansion_concept is not None:
                expansion_concept.add_alias(acronym_text)

    def _extract_cross_references(
        self, text: str, chunk_id: str
    ) -> list:
        """Extract explicit cross-reference patterns from chunk text.

        Returns list of CrossReference instances.

        Requirements: 5.1
        """
        from multimodal_librarian.models.kg_retrieval import CrossReference

        ref_patterns = [
            (
                r'(?:see|refer\s+to)\s+'
                r'(section|chapter|page|figure|table)'
                r'\s+(\d+(?:\.\d+)*)',
                'explicit',
            ),
            (
                r'as\s+(?:mentioned|discussed|shown|described)'
                r'\s+in\s+(section|chapter|page|figure|table)'
                r'\s+(\d+(?:\.\d+)*)',
                'backward',
            ),
            (
                r'(section|chapter|page|figure|table)'
                r'\s+(\d+(?:\.\d+)*)'
                r'\s+(?:above|below|earlier|later)',
                'positional',
            ),
        ]

        references: list = []
        for pattern, ref_type in ref_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                references.append(CrossReference(
                    source_chunk_id=chunk_id,
                    reference_type=ref_type,
                    target_type=match.group(1).lower(),
                    target_label=match.group(2),
                    raw_text=match.group(0),
                ))
        return references





class RelationshipExtractor:
    """Extracts relationships between concepts."""
    
    def __init__(self):
        self.settings = get_settings()
        
        # Common relationship patterns
        self.relationship_patterns = {
            'IS_A': [
                r'(.+?)\s+is\s+(?:a|an)\s+(.+)',
                r'(.+?)\s+are\s+(.+)'
            ],
            'PART_OF': [
                r'(.+?)\s+(?:is\s+)?part\s+of\s+(.+)',
                r'(.+?)\s+belongs\s+to\s+(.+)',
                r'(.+?)\s+contains\s+(.+)'
            ],
            'CAUSES': [
                r'(.+?)\s+causes\s+(.+)',
                r'(.+?)\s+leads\s+to\s+(.+)',
                r'(.+?)\s+results\s+in\s+(.+)'
            ],
            'RELATED_TO': [
                r'(.+?)\s+(?:is\s+)?related\s+to\s+(.+)',
                r'(.+?)\s+(?:is\s+)?associated\s+with\s+(.+)',
                r'(.+?)\s+(?:is\s+)?connected\s+to\s+(.+)'
            ]
        }
    
    def extract_relationships_pattern(self, text: str, concepts: List[ConceptNode]) -> List[RelationshipEdge]:
        """Extract relationships using pattern matching."""
        relationships = []
        concept_names = {concept.concept_name.lower(): concept for concept in concepts}
        
        for predicate, patterns in self.relationship_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    subject = match.group(1).strip().lower()
                    object_text = match.group(2).strip().lower()
                    
                    # Find matching concepts
                    subject_concept = None
                    object_concept = None
                    
                    for concept_name, concept in concept_names.items():
                        if concept_name in subject:
                            subject_concept = concept
                        if concept_name in object_text:
                            object_concept = concept
                    
                    if subject_concept and object_concept and subject_concept != object_concept:
                        relationship = RelationshipEdge(
                            subject_concept=subject_concept.concept_id,
                            predicate=predicate,
                            object_concept=object_concept.concept_id,
                            confidence=0.7,
                            relationship_type=self._get_relationship_type(predicate)
                        )
                        relationships.append(relationship)
        
        return relationships
    
    def extract_relationships_llm(self, text: str, concepts: List[ConceptNode], 
                                chunk_id: str) -> List[RelationshipEdge]:
        """Extract relationships using LLM-based analysis.

        Note: The previous co-occurrence RELATED_TO logic has been removed.
        Real semantic relationships are now sourced from ConceptNet via the
        validation gate, and pattern-based relationships (IS_A, PART_OF,
        CAUSES) are handled by extract_relationships_pattern().
        """
        # Co-occurrence relationship creation removed — replaced by
        # ConceptNet relationships from the validation gate.
        return []
    
    def extract_relationships_embedding(self, concepts: List[ConceptNode], 
                                      embedding_model) -> List[RelationshipEdge]:
        """Extract relationships using embedding-based similarity (sync version)."""
        relationships = []
        
        if len(concepts) < 2:
            return relationships
        
        # Skip if no embedding model available (model-server-separation architecture)
        if embedding_model is None:
            logger.debug("Skipping embedding-based relationship extraction - no local model available")
            return relationships
        
        # Generate embeddings for all concepts
        concept_texts = [concept.concept_name for concept in concepts]
        embeddings = embedding_model.encode(concept_texts)
        
        # Find similar concepts
        for i, concept1 in enumerate(concepts):
            for j, concept2 in enumerate(concepts[i+1:], i+1):
                similarity = np.dot(embeddings[i], embeddings[j]) / (
                    np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
                )
                
                if similarity > 0.8:  # Similarity threshold (raised from 0.6 to reduce relationship explosion)
                    relationship = RelationshipEdge(
                        subject_concept=concept1.concept_id,
                        predicate="SIMILAR_TO",
                        object_concept=concept2.concept_id,
                        confidence=similarity,
                        relationship_type=RelationshipType.ASSOCIATIVE
                    )
                    relationships.append(relationship)
        
        return relationships
    
    async def extract_relationships_embedding_async(self, concepts: List[ConceptNode], 
                                                   model_server_client) -> List[RelationshipEdge]:
        """Extract relationships using embedding-based similarity via model server (async, non-blocking)."""
        relationships = []
        
        if len(concepts) < 2:
            return relationships
        
        if model_server_client is None:
            logger.debug("Skipping embedding-based relationship extraction - no model server available")
            return relationships
        
        try:
            # Generate embeddings for all concepts via model server
            concept_texts = [concept.concept_name for concept in concepts]
            embeddings_list = await model_server_client.generate_embeddings(concept_texts)
            
            if not embeddings_list:
                logger.warning("Model server returned empty embeddings for relationship extraction")
                return relationships
            
            embeddings = np.array(embeddings_list)
            
            # Find similar concepts
            for i, concept1 in enumerate(concepts):
                for j, concept2 in enumerate(concepts[i+1:], i+1):
                    similarity = np.dot(embeddings[i], embeddings[j]) / (
                        np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
                    )
                    
                    if similarity > 0.8:  # Similarity threshold (raised from 0.6 to reduce relationship explosion)
                        relationship = RelationshipEdge(
                            subject_concept=concept1.concept_id,
                            predicate="SIMILAR_TO",
                            object_concept=concept2.concept_id,
                            confidence=float(similarity),
                            relationship_type=RelationshipType.ASSOCIATIVE
                        )
                        relationships.append(relationship)
            
            logger.debug(f"Extracted {len(relationships)} embedding-based relationships")
            return relationships
            
        except Exception as e:
            logger.warning(f"Error in embedding-based relationship extraction: {e}")
            return relationships
        
        return relationships
    
    def _get_relationship_type(self, predicate: str) -> RelationshipType:
        """Map predicate to relationship type."""
        return RelationTypeMapper.classify(predicate)


class KnowledgeGraphBuilder:
    """Main knowledge graph builder component."""
    
    def __init__(self, neo4j_client=None):
        self.settings = get_settings()
        self.concept_extractor = ConceptExtractor()
        self.relationship_extractor = RelationshipExtractor()
        self._embedding_model = None  # Lazy loaded (local fallback only)
        self._model_server_client = None  # Model server client (preferred)
        self._neo4j_client = neo4j_client  # For ConceptNet validation (optional)
        self._conceptnet_validator = None  # Lazy-initialized

        # In-memory storage for development (would use database in production)
        self.concepts: Dict[str, ConceptNode] = {}
        self.relationships: Dict[str, RelationshipEdge] = {}
        self.extractions: Dict[str, ConceptExtraction] = {}

        logger.info("Knowledge Graph Builder initialized (models will load on first use)")
    
    @property
    def embedding_model(self):
        """
        Lazy load embedding model on first access.
        
        NOTE: This is the LOCAL fallback model. Prefer using model server via
        generate_embeddings_async() for non-blocking operation.
        """
        logger.warning("Local embedding model not available - use generate_embeddings_async() instead")
        return None
    
    async def _get_model_server_client(self):
        """Get or initialize the model server client."""
        if self._model_server_client is None:
            try:
                from ...clients.model_server_client import (
                    get_model_client,
                    initialize_model_client,
                )
                
                client = get_model_client()
                if client is None:
                    await initialize_model_client()
                    client = get_model_client()
                
                if client and client.enabled:
                    self._model_server_client = client
            except Exception as e:
                logger.warning(f"Model server not available: {e}")
        return self._model_server_client

    def _get_conceptnet_validator(self):
        """Get or create the ConceptNet validator (requires neo4j_client)."""
        if self._conceptnet_validator is None and self._neo4j_client is not None:
            try:
                from .conceptnet_validator import ConceptNetValidator
                self._conceptnet_validator = ConceptNetValidator(self._neo4j_client)
            except Exception as e:
                logger.warning(f"Failed to initialize ConceptNet validator: {e}")
        return self._conceptnet_validator
    
    async def generate_embeddings_async(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings asynchronously using model server (non-blocking).
        
        Model server is required - no local fallback.
        """
        # Try model server first
        client = await self._get_model_server_client()
        if client is not None:
            try:
                embeddings = await client.generate_embeddings(texts)
                if embeddings:
                    return np.array(embeddings)
            except Exception as e:
                logger.warning(f"Model server embedding failed: {e}")
        
        # Fallback to local model via thread pool
        executor = _get_kg_executor()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            executor, 
            lambda: self.embedding_model.encode(texts)
        )
        return self._embedding_model
    
    def extract_knowledge_triples(self, content: str, source_id: str) -> List[Triple]:
        """Extract (subject, predicate, object) relationships from content."""
        try:
            # Extract concepts first
            concepts = self.extract_concepts_from_content(content, source_id)
            
            # Extract relationships
            relationships = self.extract_relationships_from_content(content, concepts, source_id)
            
            # Convert to triples
            triples = []
            for relationship in relationships:
                triple = Triple(
                    subject=relationship.subject_concept,
                    predicate=relationship.predicate,
                    object=relationship.object_concept,
                    confidence=relationship.confidence,
                    source_id=source_id,
                    extraction_method="HYBRID"
                )
                triples.append(triple)
            
            logger.info(f"Extracted {len(triples)} triples from content {source_id}")
            return triples
            
        except Exception as e:
            logger.error(f"Error extracting knowledge triples: {e}")
            return []
    
    def extract_concepts_from_content(self, content: str, chunk_id: str) -> List[ConceptNode]:
        """Extract concepts from content using multiple methods."""
        all_concepts = []
        
        try:
            # Method 1: Regex pattern extraction (MULTI_WORD, CODE_TERM, ACRONYM + PMI)
            regex_concepts = self.concept_extractor.extract_concepts_regex(content)
            all_concepts.extend(regex_concepts)
            
            # Method 2: LLM-based extraction
            llm_concepts = self.concept_extractor.extract_concepts_llm(content, chunk_id)
            all_concepts.extend(llm_concepts)
            
            # Method 3: Embedding-based similarity to existing concepts
            existing_concepts = list(self.concepts.values())
            embedding_concepts = self.concept_extractor.extract_concepts_embedding(
                content, chunk_id, existing_concepts
            )
            all_concepts.extend(embedding_concepts)
            
            # Deduplicate and merge concepts
            merged_concepts = self._merge_similar_concepts(all_concepts)
            
            # Add source chunk reference
            for concept in merged_concepts:
                concept.add_source_chunk(chunk_id)
            
            logger.info(f"Extracted {len(merged_concepts)} concepts from chunk {chunk_id}")
            return merged_concepts
            
        except Exception as e:
            logger.error(f"Error extracting concepts: {e}")
            return []
    
    async def extract_concepts_from_content_async(self, content: str, chunk_id: str) -> List[ConceptNode]:
        """Extract concepts from content using multiple methods (async, non-blocking)."""
        all_concepts = []
        
        try:
            # Method 1: Regex pattern extraction (sync - fast)
            regex_concepts = self.concept_extractor.extract_concepts_regex(content)
            all_concepts.extend(regex_concepts)
            
            # Method 2: LLM-based extraction (sync - pattern matching)
            llm_concepts = self.concept_extractor.extract_concepts_llm(content, chunk_id)
            all_concepts.extend(llm_concepts)
            
            # Method 3: Embedding-based similarity to existing concepts (async - uses model server)
            existing_concepts = list(self.concepts.values())
            if existing_concepts:
                embedding_concepts = await self.concept_extractor.extract_concepts_embedding_async(
                    content, chunk_id, existing_concepts
                )
                all_concepts.extend(embedding_concepts)
            
            # Deduplicate and merge concepts
            merged_concepts = self._merge_similar_concepts(all_concepts)
            
            # Add source chunk reference
            for concept in merged_concepts:
                concept.add_source_chunk(chunk_id)
            
            logger.info(f"Extracted {len(merged_concepts)} concepts (async) from chunk {chunk_id}")
            return merged_concepts
            
        except Exception as e:
            logger.error(f"Error extracting concepts (async): {e}")
            return []
    
    def extract_relationships_from_content(self, content: str, concepts: List[ConceptNode], 
                                         chunk_id: str) -> List[RelationshipEdge]:
        """Extract relationships from content using multiple methods (sync - pattern and LLM only)."""
        all_relationships = []
        
        try:
            # Method 1: Pattern-based extraction
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                content, concepts
            )
            all_relationships.extend(pattern_relationships)
            
            # Method 2: LLM-based extraction
            llm_relationships = self.relationship_extractor.extract_relationships_llm(
                content, concepts, chunk_id
            )
            all_relationships.extend(llm_relationships)
            
            # Method 3: Embedding-based similarity (skipped in sync - use async version)
            # Note: self.embedding_model is None in model-server-separation architecture
            # Use extract_relationships_from_content_async for embedding-based extraction
            embedding_relationships = self.relationship_extractor.extract_relationships_embedding(
                concepts, self.embedding_model
            )
            all_relationships.extend(embedding_relationships)
            
            # Add evidence chunk reference
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk_id)
            
            # Deduplicate relationships
            unique_relationships = self._deduplicate_relationships(all_relationships)
            
            logger.info(f"Extracted {len(unique_relationships)} relationships from chunk {chunk_id}")
            return unique_relationships
            
        except Exception as e:
            logger.error(f"Error extracting relationships: {e}")
            return []
    
    async def extract_relationships_from_content_async(self, content: str, concepts: List[ConceptNode], 
                                                       chunk_id: str) -> List[RelationshipEdge]:
        """Extract relationships from content using all methods including model server embeddings (async)."""
        all_relationships = []
        
        try:
            # Method 1: Pattern-based extraction
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                content, concepts
            )
            all_relationships.extend(pattern_relationships)
            
            # Method 2: LLM-based extraction
            llm_relationships = self.relationship_extractor.extract_relationships_llm(
                content, concepts, chunk_id
            )
            all_relationships.extend(llm_relationships)
            
            # Method 3: Embedding-based similarity via model server
            model_server_client = await self._get_model_server_client()
            embedding_relationships = await self.relationship_extractor.extract_relationships_embedding_async(
                concepts, model_server_client
            )
            all_relationships.extend(embedding_relationships)
            
            # Add evidence chunk reference
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk_id)
            
            # Deduplicate relationships
            unique_relationships = self._deduplicate_relationships(all_relationships)
            
            logger.info(f"Extracted {len(unique_relationships)} relationships (async) from chunk {chunk_id}")
            return unique_relationships
            
        except Exception as e:
            logger.error(f"Error extracting relationships (async): {e}")
            return []
    
    def build_confidence_scores(self, extractions: List[ConceptExtraction]) -> Dict[str, float]:
        """Build confidence scores for extracted relationships."""
        confidence_scores = {}
        
        try:
            for extraction in extractions:
                # Calculate concept confidence
                for concept in extraction.extracted_concepts:
                    if concept.concept_id not in confidence_scores:
                        confidence_scores[concept.concept_id] = []
                    confidence_scores[concept.concept_id].append(concept.confidence)
                
                # Calculate relationship confidence
                for relationship in extraction.extracted_relationships:
                    rel_key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
                    if rel_key not in confidence_scores:
                        confidence_scores[rel_key] = []
                    confidence_scores[rel_key].append(relationship.confidence)
            
            # Average confidence scores
            averaged_scores = {}
            for key, scores in confidence_scores.items():
                averaged_scores[key] = sum(scores) / len(scores)
            
            return averaged_scores
            
        except Exception as e:
            logger.error(f"Error building confidence scores: {e}")
            return {}
    
    def process_knowledge_chunk(self, chunk: KnowledgeChunk) -> ConceptExtraction:
        """Process a knowledge chunk and extract concepts and relationships (sync version)."""
        try:
            extraction_id = str(uuid.uuid4())
            
            # Extract concepts and relationships
            concepts = self.extract_concepts_from_content(chunk.content, chunk.id)
            relationships = self.extract_relationships_from_content(chunk.content, concepts, chunk.id)
            
            # Calculate overall confidence
            all_confidences = [c.confidence for c in concepts] + [r.confidence for r in relationships]
            overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
            
            # Create extraction record
            extraction = ConceptExtraction(
                extraction_id=extraction_id,
                chunk_id=chunk.id,
                extracted_concepts=concepts,
                extracted_relationships=relationships,
                extraction_method="HYBRID",
                confidence_score=overall_confidence
            )
            
            # Store extraction
            self.extractions[extraction_id] = extraction
            
            # Update knowledge graph
            self._update_knowledge_graph(concepts, relationships)
            
            logger.info(f"Processed knowledge chunk {chunk.id} with {len(concepts)} concepts and {len(relationships)} relationships")
            return extraction
            
        except Exception as e:
            logger.error(f"Error processing knowledge chunk: {e}")
            return ConceptExtraction(
                extraction_id=str(uuid.uuid4()),
                chunk_id=chunk.id,
                extracted_concepts=[],
                extracted_relationships=[],
                confidence_score=0.0
            )
    
    async def process_knowledge_chunk_async(self, chunk: KnowledgeChunk) -> ConceptExtraction:
        """Process a knowledge chunk with async NER + regex extraction and ConceptNet validation."""
        try:
            extraction_id = str(uuid.uuid4())

            # Step 1: Extract concepts using combined NER + regex pipeline
            concepts = await self.concept_extractor.extract_all_concepts_async(chunk.content)

            # Add source chunk reference
            for concept in concepts:
                concept.add_source_chunk(chunk.id)

            # Step 2: Validate concepts through ConceptNet gate (if available)
            conceptnet_relationships: List[RelationshipEdge] = []
            validator = self._get_conceptnet_validator()
            if validator is not None:
                try:
                    validation_result = await validator.validate_concepts(concepts)
                    concepts = validation_result.validated_concepts
                    conceptnet_relationships = validation_result.conceptnet_relationships
                    logger.info(
                        f"ConceptNet validation: kept {len(concepts)} concepts "
                        f"(conceptnet={validation_result.kept_by_conceptnet}, "
                        f"ner={validation_result.kept_by_ner}, "
                        f"pattern={validation_result.kept_by_pattern}, "
                        f"discarded={validation_result.discarded_count})"
                    )
                except Exception as e:
                    logger.warning(
                        f"ConceptNet validation failed, using raw extraction: {e}"
                    )
            else:
                logger.debug(
                    "ConceptNet validator not available, skipping validation gate"
                )

            # Step 3: Extract pattern-based relationships (IS_A, PART_OF, CAUSES)
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                chunk.content, concepts
            )

            # Step 4: Extract embedding-based relationships
            model_server_client = await self._get_model_server_client()
            embedding_relationships = await self.relationship_extractor.extract_relationships_embedding_async(
                concepts, model_server_client
            )

            # Combine: ConceptNet relationships + pattern relationships + embedding relationships
            # ConceptNet relationships replace co-occurrence RELATED_TO
            all_relationships = conceptnet_relationships + pattern_relationships + embedding_relationships

            # Add evidence chunk reference
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk.id)

            # Deduplicate relationships
            relationships = self._deduplicate_relationships(all_relationships)

            # Calculate overall confidence
            all_confidences = [c.confidence for c in concepts] + [r.confidence for r in relationships]
            overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

            # Create extraction record
            extraction = ConceptExtraction(
                extraction_id=extraction_id,
                chunk_id=chunk.id,
                extracted_concepts=concepts,
                extracted_relationships=relationships,
                extraction_method="HYBRID_ASYNC",
                confidence_score=overall_confidence
            )

            # Store extraction
            self.extractions[extraction_id] = extraction

            # Update knowledge graph
            self._update_knowledge_graph(concepts, relationships)

            logger.info(f"Processed knowledge chunk (async) {chunk.id} with {len(concepts)} concepts and {len(relationships)} relationships")
            return extraction

        except Exception as e:
            logger.error(f"Error processing knowledge chunk (async): {e}")
            return ConceptExtraction(
                extraction_id=str(uuid.uuid4()),
                chunk_id=chunk.id,
                extracted_concepts=[],
                extracted_relationships=[],
                confidence_score=0.0
            )

    async def process_knowledge_chunk_extract_only(self, chunk: KnowledgeChunk) -> ConceptExtraction:
        """Extract concepts and relationships from a chunk WITHOUT ConceptNet validation.

        Identical to process_knowledge_chunk_async but skips the per-chunk
        ConceptNet validation gate (Step 2). Validation is deferred to
        batch level via validate_batch_concepts().
        """
        try:
            extraction_id = str(uuid.uuid4())

            # Step 1: Extract concepts using combined NER + regex pipeline
            concepts = await self.concept_extractor.extract_all_concepts_async(chunk.content)
            for concept in concepts:
                concept.add_source_chunk(chunk.id)

            # Step 2: SKIPPED — no per-chunk ConceptNet validation

            # Step 3: Extract pattern-based relationships
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                chunk.content, concepts
            )

            # Step 4: Extract embedding-based relationships
            model_server_client = await self._get_model_server_client()
            embedding_relationships = await self.relationship_extractor.extract_relationships_embedding_async(
                concepts, model_server_client
            )

            all_relationships = pattern_relationships + embedding_relationships
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk.id)

            relationships = self._deduplicate_relationships(all_relationships)

            all_confidences = [c.confidence for c in concepts] + [r.confidence for r in relationships]
            overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

            extraction = ConceptExtraction(
                extraction_id=extraction_id,
                chunk_id=chunk.id,
                extracted_concepts=concepts,
                extracted_relationships=relationships,
                extraction_method="HYBRID_ASYNC_EXTRACT_ONLY",
                confidence_score=overall_confidence
            )

            self.extractions[extraction_id] = extraction
            self._update_knowledge_graph(concepts, relationships)

            logger.info(
                f"Extracted (no validation) chunk {chunk.id}: "
                f"{len(concepts)} concepts, {len(relationships)} relationships"
            )
            return extraction

        except Exception as e:
            logger.error(f"Error in extract-only processing: {e}")
            return ConceptExtraction(
                extraction_id=str(uuid.uuid4()),
                chunk_id=chunk.id,
                extracted_concepts=[],
                extracted_relationships=[],
                confidence_score=0.0
            )

    async def validate_batch_concepts(
        self, concepts: List[ConceptNode]
    ) -> tuple:
        """Validate a batch of concepts through ConceptNet in one pass.

        Deduplicates concepts by normalized name, runs a single
        validate_concepts() call, then returns the filtered list.

        Returns:
            (validated_concepts, conceptnet_relationships, stats_dict)
        """
        validator = self._get_conceptnet_validator()
        if validator is None:
            logger.debug("No ConceptNet validator; returning all concepts unfiltered")
            return concepts, [], {"kept": len(concepts), "discarded": 0}

        # Deduplicate by lowered name, merging source_chunks from all occurrences
        seen: dict = {}
        for c in concepts:
            key = c.concept_name.lower().strip()
            if key not in seen:
                seen[key] = c
            else:
                existing = seen[key]
                if c.confidence > existing.confidence:
                    # Keep higher-confidence version but merge source_chunks
                    for chunk_id in existing.source_chunks:
                        c.add_source_chunk(chunk_id)
                    seen[key] = c
                else:
                    # Merge source_chunks into existing
                    for chunk_id in c.source_chunks:
                        existing.add_source_chunk(chunk_id)
        unique_concepts = list(seen.values())

        try:
            result = await validator.validate_concepts(unique_concepts)
            stats = {
                "kept": len(result.validated_concepts),
                "discarded": result.discarded_count,
                "conceptnet": result.kept_by_conceptnet,
                "ner": result.kept_by_ner,
                "pattern": result.kept_by_pattern,
            }
            logger.info(
                f"Batch ConceptNet validation: {len(unique_concepts)} unique → "
                f"{len(result.validated_concepts)} kept "
                f"(conceptnet={result.kept_by_conceptnet}, "
                f"ner={result.kept_by_ner}, "
                f"pattern={result.kept_by_pattern}, "
                f"discarded={result.discarded_count})"
            )
            return result.validated_concepts, result.conceptnet_relationships, stats
        except Exception as e:
            logger.warning(f"Batch ConceptNet validation failed: {e}")
            return concepts, [], {"kept": len(concepts), "discarded": 0, "error": str(e)}


    
    def _merge_similar_concepts(self, concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Merge similar concepts to avoid duplicates."""
        merged = {}
        
        for concept in concepts:
            # Use normalized name as key
            key = concept.concept_name.lower().strip()
            
            if key in merged:
                # Merge with existing concept
                existing = merged[key]
                existing.confidence = max(existing.confidence, concept.confidence)
                for alias in concept.aliases:
                    existing.add_alias(alias)
                for chunk_id in concept.source_chunks:
                    existing.add_source_chunk(chunk_id)
            else:
                merged[key] = concept
        
        return list(merged.values())
    
    def _deduplicate_relationships(self, relationships: List[RelationshipEdge]) -> List[RelationshipEdge]:
        """Remove duplicate relationships."""
        unique = {}
        
        for relationship in relationships:
            key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
            
            if key in unique:
                # Merge evidence
                existing = unique[key]
                existing.confidence = max(existing.confidence, relationship.confidence)
                for chunk_id in relationship.evidence_chunks:
                    existing.add_evidence_chunk(chunk_id)
            else:
                unique[key] = relationship
        
        return list(unique.values())
    
    def _update_knowledge_graph(self, concepts: List[ConceptNode], 
                              relationships: List[RelationshipEdge]) -> None:
        """Update the in-memory knowledge graph."""
        # Add concepts
        for concept in concepts:
            if concept.concept_id in self.concepts:
                # Merge with existing
                existing = self.concepts[concept.concept_id]
                existing.confidence = max(existing.confidence, concept.confidence)
                for alias in concept.aliases:
                    existing.add_alias(alias)
                for chunk_id in concept.source_chunks:
                    existing.add_source_chunk(chunk_id)
            else:
                self.concepts[concept.concept_id] = concept
        
        # Add relationships
        for relationship in relationships:
            key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
            if key in self.relationships:
                # Merge with existing
                existing = self.relationships[key]
                existing.confidence = max(existing.confidence, relationship.confidence)
                for chunk_id in relationship.evidence_chunks:
                    existing.add_evidence_chunk(chunk_id)
            else:
                self.relationships[key] = relationship
    
    def get_knowledge_graph_stats(self) -> KnowledgeGraphStats:
        """Get statistics about the current knowledge graph."""
        stats = KnowledgeGraphStats()
        concepts = list(self.concepts.values())
        relationships = list(self.relationships.values())
        stats.update_stats(concepts, relationships)
        return stats
    
    def get_concepts_by_type(self, concept_type: str) -> List[ConceptNode]:
        """Get all concepts of a specific type."""
        return [concept for concept in self.concepts.values() 
                if concept.concept_type == concept_type]
    
    def get_relationships_by_predicate(self, predicate: str) -> List[RelationshipEdge]:
        """Get all relationships with a specific predicate."""
        return [relationship for relationship in self.relationships.values() 
                if relationship.predicate == predicate]
    
    def find_concept_by_name(self, name: str) -> Optional[ConceptNode]:
        """Find a concept by name or alias."""
        name_lower = name.lower()
        
        for concept in self.concepts.values():
            if concept.concept_name.lower() == name_lower:
                return concept
            if name_lower in [alias.lower() for alias in concept.aliases]:
                return concept
        
        return None

    def _reconcile_cross_references(
        self,
        cross_references: List,
        chunk_metadata: Dict[str, Dict[str, Any]],
    ) -> list:
        """Resolve cross-reference targets to chunk IDs using section/chapter metadata.

        Args:
            cross_references: List of CrossReference objects from _extract_cross_references
            chunk_metadata: Mapping of chunk_id -> metadata dict. Each metadata dict
                should contain keys like 'section', 'chapter', 'page', 'figure', 'table'
                with their corresponding label values (e.g., {'section': '3.1', 'chapter': '4'}).

        Returns:
            The same list of CrossReference objects with resolved_chunk_ids populated
            where possible. Unresolved references have resolved_chunk_ids = None.

        Requirements: 5.2, 5.3
        """

        # Build reverse index: (target_type, target_label) -> [chunk_ids]
        target_index: Dict[tuple, List[str]] = {}
        for chunk_id, meta in chunk_metadata.items():
            for key in ('section', 'chapter', 'page', 'figure', 'table'):
                label = meta.get(key)
                if label is not None:
                    idx_key = (key, str(label))
                    target_index.setdefault(idx_key, []).append(chunk_id)

        # Resolve each cross-reference
        resolved_count = 0
        for ref in cross_references:
            lookup_key = (ref.target_type, ref.target_label)
            matched_chunks = target_index.get(lookup_key)
            if matched_chunks:
                ref.resolved_chunk_ids = matched_chunks
                resolved_count += 1
                # Create REFERENCES edges in the in-memory KG
                for target_chunk_id in matched_chunks:
                    edge_key = f"{ref.source_chunk_id}_REFERENCES_{target_chunk_id}"
                    if edge_key not in self.relationships:
                        edge = RelationshipEdge(
                            subject_concept=ref.source_chunk_id,
                            predicate="REFERENCES",
                            object_concept=target_chunk_id,
                            confidence=0.8,
                            evidence_chunks=[ref.source_chunk_id],
                        )
                        self.relationships[edge_key] = edge
            else:
                logger.warning(
                    f"Unresolved cross-reference: {ref.raw_text} "
                    f"(target: {ref.target_type} {ref.target_label})"
                )

        logger.info(f"Reconciled {resolved_count}/{len(cross_references)} cross-references")
        return cross_references

