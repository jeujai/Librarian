"""
Conceptual Gap Analyzer.

This module implements semantic distance calculation, concept overlap analysis,
cross-reference detection, and bridge necessity determination logic.

Uses model server for embeddings and NLP processing (separate container).
"""

import asyncio
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ...clients.model_server_client import (
    ModelServerUnavailable,
    get_model_client,
    initialize_model_client,
)
from ...models.chunking import DomainConfig, GapAnalysis
from ...models.core import BridgeStrategy, ContentType, GapType

logger = logging.getLogger(__name__)


@dataclass
class ChunkBoundary:
    """Represents a boundary between two chunks for gap analysis."""
    chunk1_content: str
    chunk2_content: str
    chunk1_id: str
    chunk2_id: str
    boundary_context: str = ""  # Text around the boundary
    
    def get_boundary_text(self, context_size: int = 100) -> str:
        """Get text around the boundary for analysis."""
        chunk1_end = self.chunk1_content[-context_size:] if len(self.chunk1_content) > context_size else self.chunk1_content
        chunk2_start = self.chunk2_content[:context_size] if len(self.chunk2_content) > context_size else self.chunk2_content
        return f"{chunk1_end} [BOUNDARY] {chunk2_start}"


@dataclass
class ConceptExtraction:
    """Represents extracted concepts from text."""
    concepts: List[str]
    entities: List[str]
    key_terms: List[str]
    topics: List[str]
    
    def get_all_concepts(self) -> Set[str]:
        """Get all unique concepts."""
        return set(self.concepts + self.entities + self.key_terms + self.topics)


@dataclass
class CrossReferenceAnalysis:
    """Analysis of cross-references between chunks."""
    forward_references: List[str]  # References from chunk1 to chunk2
    backward_references: List[str]  # References from chunk2 to chunk1
    shared_references: List[str]  # Common references
    reference_density: float
    reference_types: Dict[str, int]
    
    def get_total_references(self) -> int:
        """Get total number of references."""
        return len(self.forward_references) + len(self.backward_references) + len(self.shared_references)


class ConceptualGapAnalyzer:
    """
    Conceptual gap analyzer for determining bridge necessity.
    
    Implements semantic distance calculation, concept overlap analysis,
    cross-reference detection, and composite gap scoring with domain-specific weighting.
    """
    
    def __init__(self):
        """Initialize the conceptual gap analyzer."""
        self.sentence_model = None
        self.nlp = None
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words='english',
            ngram_range=(1, 2)
        )
        
        self._initialize_models()
        
        # Gap type thresholds
        self.gap_thresholds = {
            GapType.CONCEPTUAL: {
                'semantic_distance': 0.7,
                'concept_overlap': 0.3,
                'necessity_threshold': 0.6
            },
            GapType.PROCEDURAL: {
                'semantic_distance': 0.6,
                'concept_overlap': 0.4,
                'necessity_threshold': 0.7
            },
            GapType.CROSS_REFERENCE: {
                'semantic_distance': 0.5,
                'concept_overlap': 0.2,
                'necessity_threshold': 0.8
            }
        }
        
        # Domain-specific weights
        self.domain_weights = {
            ContentType.TECHNICAL: {
                'semantic_distance': 0.3,
                'concept_overlap': 0.25,
                'cross_reference_density': 0.2,
                'structural_continuity': 0.25
            },
            ContentType.MEDICAL: {
                'semantic_distance': 0.35,
                'concept_overlap': 0.3,
                'cross_reference_density': 0.15,
                'structural_continuity': 0.2
            },
            ContentType.LEGAL: {
                'semantic_distance': 0.25,
                'concept_overlap': 0.2,
                'cross_reference_density': 0.35,
                'structural_continuity': 0.2
            },
            ContentType.ACADEMIC: {
                'semantic_distance': 0.3,
                'concept_overlap': 0.25,
                'cross_reference_density': 0.25,
                'structural_continuity': 0.2
            },
            ContentType.NARRATIVE: {
                'semantic_distance': 0.4,
                'concept_overlap': 0.2,
                'cross_reference_density': 0.1,
                'structural_continuity': 0.3
            },
            ContentType.GENERAL: {
                'semantic_distance': 0.3,
                'concept_overlap': 0.25,
                'cross_reference_density': 0.2,
                'structural_continuity': 0.25
            }
        }
    
    def _initialize_models(self):
        """Initialize NLP models with lazy loading to prevent blocking."""
        # Models are now loaded via model server
        self._model_server_client = None
        logger.info("Gap analyzer initialized (using model server for embeddings and NLP)")
    
    def _ensure_sentence_model(self):
        """
        Ensure sentence model is available for embedding generation.
        
        Since we now use the model server, this method sets sentence_model to None
        to trigger the TF-IDF fallback in sync methods. For async methods,
        use the model server client directly.
        """
        # In the model server architecture, we don't load sentence-transformers locally
        # The sync methods will fall back to TF-IDF similarity
        # For proper embeddings, use the async methods with model server
        if self.sentence_model is None:
            logger.debug("Sentence model not loaded locally - using TF-IDF fallback for sync operations")
    
    def _ensure_nlp_model(self):
        """
        Ensure NLP model (spaCy) is available for concept extraction.
        
        Since we now use the model server, this method sets nlp to None
        to trigger the pattern-based fallback in _extract_concepts.
        For proper NLP processing, use the model server client directly.
        """
        # In the model server architecture, we don't load spaCy locally
        # The _extract_concepts method will fall back to pattern-based extraction
        if self.nlp is None:
            logger.debug("NLP model not loaded locally - using pattern-based fallback for concept extraction")
    
    async def _get_model_server_client(self):
        """Get or initialize the model server client."""
        if self._model_server_client is None:
            try:
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
        
        Raises:
            ModelServerUnavailable: If model server is not available
        """
        client = await self._get_model_server_client()
        if client is None:
            raise ModelServerUnavailable("Model server not available")
        
        embeddings = await client.generate_embeddings(texts)
        if embeddings:
            return np.array(embeddings)
        
        raise ModelServerUnavailable("Failed to generate embeddings from model server")
    
    async def _get_model_server_client_dup(self):
        """Duplicate method - remove this."""
        pass
    
    async def generate_embeddings_async_dup(self, texts: List[str]) -> np.ndarray:
        """Duplicate method - remove this."""
        pass
    
    def analyze_boundary_gap(self, chunk1: str, chunk2: str, 
                           content_type: ContentType = ContentType.GENERAL,
                           domain_config: Optional[DomainConfig] = None) -> GapAnalysis:
        """
        Determine bridge necessity using multi-factor analysis.
        
        Args:
            chunk1: Content of first chunk
            chunk2: Content of second chunk
            content_type: Type of content for domain-specific analysis
            domain_config: Domain configuration for thresholds
            
        Returns:
            GapAnalysis with bridge necessity determination
        """
        logger.debug(f"Analyzing gap between chunks (lengths: {len(chunk1)}, {len(chunk2)})")
        
        # Create boundary for analysis
        boundary = ChunkBoundary(
            chunk1_content=chunk1,
            chunk2_content=chunk2,
            chunk1_id="chunk1",
            chunk2_id="chunk2"
        )
        
        # Calculate semantic distance
        semantic_distance = self.calculate_semantic_distance(chunk1, chunk2)
        
        # Analyze concept overlap
        concept_overlap = self._calculate_concept_overlap(chunk1, chunk2)
        
        # Detect cross-references
        cross_ref_analysis = self.detect_cross_references(chunk1, chunk2)
        cross_ref_density = cross_ref_analysis.reference_density
        
        # Calculate structural continuity
        structural_continuity = self._calculate_structural_continuity(chunk1, chunk2, content_type)
        
        # Determine gap type and strategy
        gap_type, bridge_strategy = self._determine_gap_type_and_strategy(
            semantic_distance, concept_overlap, cross_ref_density, 
            structural_continuity, content_type
        )
        
        # Calculate domain-specific gaps
        domain_specific_gaps = self._calculate_domain_specific_gaps(
            chunk1, chunk2, content_type, domain_config
        )
        
        # Calculate necessity score using domain weights
        necessity_score = self._calculate_necessity_score(
            semantic_distance, concept_overlap, cross_ref_density,
            structural_continuity, content_type, domain_specific_gaps
        )
        
        return GapAnalysis(
            necessity_score=necessity_score,
            gap_type=gap_type,
            bridge_strategy=bridge_strategy,
            semantic_distance=semantic_distance,
            concept_overlap=concept_overlap,
            cross_reference_density=cross_ref_density,
            structural_continuity=structural_continuity,
            domain_specific_gaps=domain_specific_gaps
        )
    
    def calculate_semantic_distance(self, chunk1: str, chunk2: str) -> float:
        """
        Calculate semantic distance using embedding similarity (sync version).
        
        Note: This is blocking. Use calculate_semantic_distance_async when possible.
        
        Args:
            chunk1: First chunk content
            chunk2: Second chunk content
            
        Returns:
            Semantic distance (0.0 = identical, 1.0 = completely different)
        """
        self._ensure_sentence_model()
        if not self.sentence_model:
            # Fallback to TF-IDF similarity
            return self._calculate_tfidf_distance(chunk1, chunk2)
        
        try:
            # Generate embeddings - this is blocking
            embeddings = self.sentence_model.encode([chunk1, chunk2])
            
            # Calculate cosine similarity
            similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
            
            # Convert similarity to distance (0 = identical, 1 = completely different)
            distance = 1.0 - similarity
            
            return max(0.0, min(1.0, distance))
        
        except Exception as e:
            logger.warning(f"Failed to calculate semantic distance with embeddings: {e}")
            return self._calculate_tfidf_distance(chunk1, chunk2)
    
    async def calculate_semantic_distance_async(self, chunk1: str, chunk2: str) -> float:
        """
        Calculate semantic distance using embedding similarity (async, non-blocking).
        
        Args:
            chunk1: First chunk content
            chunk2: Second chunk content
            
        Returns:
            Semantic distance (0.0 = identical, 1.0 = completely different)
        """
        self._ensure_sentence_model()
        if not self.sentence_model:
            # Fallback to TF-IDF similarity
            return self._calculate_tfidf_distance(chunk1, chunk2)
        
        try:
            loop = asyncio.get_event_loop()
            executor = _get_gap_analyzer_executor()
            
            # Generate embeddings in thread pool
            embeddings = await loop.run_in_executor(
                executor,
                self._encode_sync,
                [chunk1, chunk2]
            )
            
            # Calculate cosine similarity
            similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
            
            # Convert similarity to distance (0 = identical, 1 = completely different)
            distance = 1.0 - similarity
            
            return max(0.0, min(1.0, distance))
        
        except Exception as e:
            logger.warning(f"Failed to calculate semantic distance with embeddings: {e}")
            return self._calculate_tfidf_distance(chunk1, chunk2)
    
    def _calculate_tfidf_distance(self, chunk1: str, chunk2: str) -> float:
        """Fallback TF-IDF based distance calculation."""
        try:
            # Fit TF-IDF on both chunks
            tfidf_matrix = self.tfidf_vectorizer.fit_transform([chunk1, chunk2])
            
            # Calculate cosine similarity
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            
            # Convert to distance
            distance = 1.0 - similarity
            
            return max(0.0, min(1.0, distance))
        
        except Exception as e:
            logger.warning(f"Failed to calculate TF-IDF distance: {e}")
            return 0.5  # Default moderate distance
    
    def _calculate_concept_overlap(self, chunk1: str, chunk2: str) -> float:
        """Calculate concept overlap between chunks."""
        # Extract concepts from both chunks
        concepts1 = self._extract_concepts(chunk1)
        concepts2 = self._extract_concepts(chunk2)
        
        # Get all unique concepts
        all_concepts1 = concepts1.get_all_concepts()
        all_concepts2 = concepts2.get_all_concepts()
        
        # Calculate overlap
        if not all_concepts1 or not all_concepts2:
            return 0.0
        
        intersection = all_concepts1.intersection(all_concepts2)
        union = all_concepts1.union(all_concepts2)
        
        overlap = len(intersection) / len(union) if union else 0.0
        
        return overlap
    
    def _extract_concepts(self, text: str) -> ConceptExtraction:
        """Extract concepts, entities, and key terms from text."""
        concepts = []
        entities = []
        key_terms = []
        topics = []
        
        # Lazy load spaCy model
        self._ensure_nlp_model()
        
        if self.nlp:
            # Use spaCy for entity extraction
            doc = self.nlp(text)
            
            # Extract named entities
            for ent in doc.ents:
                if ent.label_ in ['PERSON', 'ORG', 'GPE', 'PRODUCT', 'EVENT']:
                    entities.append(ent.text.lower())
            
            # Extract noun phrases as concepts
            for chunk in doc.noun_chunks:
                if len(chunk.text.split()) <= 3:  # Limit to reasonable length
                    concepts.append(chunk.text.lower())
            
            # Extract key terms (nouns and adjectives)
            for token in doc:
                if token.pos_ in ['NOUN', 'ADJ'] and len(token.text) > 3:
                    key_terms.append(token.lemma_.lower())
        
        else:
            # Fallback pattern-based extraction
            # Extract capitalized words as potential entities
            entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
            entities = [ent.lower() for ent in entities]
            
            # Extract potential key terms (longer words)
            key_terms = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        
        # Extract topic indicators
        topic_patterns = [
            r'\b(?:about|regarding|concerning|related to|focuses on)\s+([^.!?]+)',
            r'\b(?:topic|subject|theme|area|field)\s+(?:of|is)\s+([^.!?]+)',
        ]
        
        for pattern in topic_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            topics.extend([match.strip().lower() for match in matches])
        
        return ConceptExtraction(
            concepts=list(set(concepts)),
            entities=list(set(entities)),
            key_terms=list(set(key_terms)),
            topics=list(set(topics))
        )
    
    def detect_cross_references(self, chunk1: str, chunk2: str) -> CrossReferenceAnalysis:
        """
        Detect and analyze cross-reference patterns.
        
        Args:
            chunk1: First chunk content
            chunk2: Second chunk content
            
        Returns:
            CrossReferenceAnalysis with reference patterns
        """
        # Reference patterns
        reference_patterns = {
            'section_ref': r'(?:section|chapter|part)\s+\d+',
            'figure_ref': r'(?:figure|fig|diagram)\s+\d+',
            'table_ref': r'table\s+\d+',
            'page_ref': r'page\s+\d+',
            'above_below': r'\b(?:above|below|previously|later|aforementioned)\b',
            'see_ref': r'see\s+(?:[^.!?]+)',
            'as_mentioned': r'as\s+(?:mentioned|discussed|shown|described)',
            'citation': r'\([^)]*\d{4}[^)]*\)',
        }
        
        forward_references = []
        backward_references = []
        shared_references = []
        reference_types = defaultdict(int)
        
        # Find references in both chunks
        chunk1_refs = self._find_references(chunk1, reference_patterns)
        chunk2_refs = self._find_references(chunk2, reference_patterns)
        
        # Analyze reference relationships
        for ref_type, refs1 in chunk1_refs.items():
            refs2 = chunk2_refs.get(ref_type, [])
            reference_types[ref_type] += len(refs1) + len(refs2)
            
            # Check for shared references
            shared = set(refs1).intersection(set(refs2))
            shared_references.extend(list(shared))
            
            # Directional references (simplified heuristic)
            forward_references.extend(refs1)
            backward_references.extend(refs2)
        
        # Calculate reference density
        total_words = len(chunk1.split()) + len(chunk2.split())
        total_refs = len(forward_references) + len(backward_references)
        reference_density = total_refs / max(total_words, 1) * 100  # References per 100 words
        
        return CrossReferenceAnalysis(
            forward_references=forward_references,
            backward_references=backward_references,
            shared_references=shared_references,
            reference_density=min(reference_density, 1.0),  # Normalize to 0-1
            reference_types=dict(reference_types)
        )
    
    def _find_references(self, text: str, patterns: Dict[str, str]) -> Dict[str, List[str]]:
        """Find references in text using patterns."""
        references = defaultdict(list)
        
        for ref_type, pattern in patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            references[ref_type] = matches
        
        return references
    
    def _calculate_structural_continuity(self, chunk1: str, chunk2: str, 
                                       content_type: ContentType) -> float:
        """Calculate structural continuity between chunks."""
        continuity_factors = []
        
        # Sentence boundary continuity
        chunk1_ends_complete = chunk1.rstrip().endswith(('.', '!', '?', ':', ';'))
        chunk2_starts_complete = chunk2.lstrip()[0].isupper() if chunk2.lstrip() else False
        
        sentence_continuity = 1.0 if chunk1_ends_complete and chunk2_starts_complete else 0.3
        continuity_factors.append(sentence_continuity)
        
        # Paragraph continuity
        chunk1_ends_paragraph = chunk1.rstrip().endswith('\n\n') or chunk1.rstrip().endswith('\n')
        paragraph_continuity = 0.8 if chunk1_ends_paragraph else 0.4
        continuity_factors.append(paragraph_continuity)
        
        # Content-type specific continuity
        if content_type == ContentType.TECHNICAL:
            # Check for code block continuity
            code_continuity = self._check_code_continuity(chunk1, chunk2)
            continuity_factors.append(code_continuity)
        
        elif content_type == ContentType.LEGAL:
            # Check for legal section continuity
            legal_continuity = self._check_legal_continuity(chunk1, chunk2)
            continuity_factors.append(legal_continuity)
        
        elif content_type == ContentType.ACADEMIC:
            # Check for academic section continuity
            academic_continuity = self._check_academic_continuity(chunk1, chunk2)
            continuity_factors.append(academic_continuity)
        
        elif content_type == ContentType.NARRATIVE:
            # Check for narrative flow continuity
            narrative_continuity = self._check_narrative_continuity(chunk1, chunk2)
            continuity_factors.append(narrative_continuity)
        
        # Calculate weighted average
        return sum(continuity_factors) / len(continuity_factors)
    
    def _check_code_continuity(self, chunk1: str, chunk2: str) -> float:
        """Check continuity for technical/code content."""
        # Check if chunks are part of the same code block
        chunk1_in_code = '```' in chunk1 and chunk1.count('```') % 2 == 1
        chunk2_in_code = '```' in chunk2 and chunk2.count('```') % 2 == 1
        
        if chunk1_in_code and chunk2_in_code:
            return 0.9  # High continuity within code block
        
        # Check for function/class continuity
        chunk1_has_def = bool(re.search(r'\b(?:def|class|function)\s+\w+', chunk1))
        chunk2_continues_def = bool(re.search(r'^\s+', chunk2))  # Indented continuation
        
        if chunk1_has_def and chunk2_continues_def:
            return 0.8
        
        return 0.5  # Default technical continuity
    
    def _check_legal_continuity(self, chunk1: str, chunk2: str) -> float:
        """Check continuity for legal content."""
        # Check for section/subsection continuity
        chunk1_section = re.search(r'(?:Section|Article)\s+(\d+)', chunk1)
        chunk2_section = re.search(r'(?:Section|Article)\s+(\d+)', chunk2)
        
        if chunk1_section and chunk2_section:
            num1 = int(chunk1_section.group(1))
            num2 = int(chunk2_section.group(1))
            if num2 == num1 + 1:
                return 0.9  # Sequential sections
        
        # Check for subsection continuity
        chunk1_subsection = re.search(r'\(([a-z])\)', chunk1)
        chunk2_subsection = re.search(r'\(([a-z])\)', chunk2)
        
        if chunk1_subsection and chunk2_subsection:
            if ord(chunk2_subsection.group(1)) == ord(chunk1_subsection.group(1)) + 1:
                return 0.8  # Sequential subsections
        
        return 0.6  # Default legal continuity
    
    def _check_academic_continuity(self, chunk1: str, chunk2: str) -> float:
        """Check continuity for academic content."""
        # Check for section headers
        academic_sections = ['abstract', 'introduction', 'methodology', 'results', 
                           'discussion', 'conclusion', 'references']
        
        chunk1_section = None
        chunk2_section = None
        
        for i, section in enumerate(academic_sections):
            if section.lower() in chunk1.lower():
                chunk1_section = i
            if section.lower() in chunk2.lower():
                chunk2_section = i
        
        if chunk1_section is not None and chunk2_section is not None:
            if chunk2_section == chunk1_section + 1:
                return 0.9  # Sequential academic sections
        
        # Check for numbered subsections
        chunk1_num = re.search(r'(\d+)\.(\d+)', chunk1)
        chunk2_num = re.search(r'(\d+)\.(\d+)', chunk2)
        
        if chunk1_num and chunk2_num:
            # Sequential numbering indicates high continuity
            return 0.8
        
        return 0.6  # Default academic continuity
    
    def _check_narrative_continuity(self, chunk1: str, chunk2: str) -> float:
        """Check continuity for narrative content."""
        # Check for dialogue continuity
        chunk1_ends_dialogue = chunk1.rstrip().endswith('"')
        chunk2_starts_dialogue = chunk2.lstrip().startswith('"')
        
        if chunk1_ends_dialogue and chunk2_starts_dialogue:
            return 0.7  # Dialogue continuation
        
        # Check for scene breaks
        scene_break_patterns = [r'\*\s*\*\s*\*', r'---', r'###']
        
        for pattern in scene_break_patterns:
            if re.search(pattern, chunk1) or re.search(pattern, chunk2):
                return 0.3  # Scene break indicates low continuity
        
        # Check for temporal continuity indicators
        temporal_indicators = ['then', 'next', 'after', 'meanwhile', 'suddenly', 'later']
        
        chunk2_start = chunk2[:100].lower()
        if any(indicator in chunk2_start for indicator in temporal_indicators):
            return 0.8  # Temporal continuity
        
        return 0.6  # Default narrative continuity
    
    def _determine_gap_type_and_strategy(self, semantic_distance: float, 
                                       concept_overlap: float,
                                       cross_ref_density: float,
                                       structural_continuity: float,
                                       content_type: ContentType) -> Tuple[GapType, BridgeStrategy]:
        """Determine gap type and appropriate bridge strategy."""
        
        # Determine gap type based on primary factors
        if cross_ref_density > 0.3:
            gap_type = GapType.CROSS_REFERENCE
        elif structural_continuity < 0.4:
            gap_type = GapType.PROCEDURAL
        else:
            gap_type = GapType.CONCEPTUAL
        
        # Determine bridge strategy based on gap characteristics
        if semantic_distance > 0.8 or concept_overlap < 0.2:
            # Large semantic gap requires LLM bridge
            bridge_strategy = BridgeStrategy.GEMINI_FLASH
        elif cross_ref_density > 0.5 or structural_continuity < 0.3:
            # High reference density or low continuity needs LLM bridge
            bridge_strategy = BridgeStrategy.GEMINI_FLASH
        elif semantic_distance > 0.6:
            # Moderate gap can use semantic overlap
            bridge_strategy = BridgeStrategy.SEMANTIC_OVERLAP
        else:
            # Small gap can use mechanical fallback
            bridge_strategy = BridgeStrategy.MECHANICAL_FALLBACK
        
        # Content-type specific adjustments
        if content_type in [ContentType.MEDICAL, ContentType.LEGAL]:
            # High-precision domains prefer LLM bridges
            if semantic_distance > 0.5:
                bridge_strategy = BridgeStrategy.GEMINI_FLASH
        
        elif content_type == ContentType.NARRATIVE:
            # Narrative content can often use mechanical fallback
            if semantic_distance < 0.7:
                bridge_strategy = BridgeStrategy.MECHANICAL_FALLBACK
        
        return gap_type, bridge_strategy
    
    def _calculate_domain_specific_gaps(self, chunk1: str, chunk2: str,
                                      content_type: ContentType,
                                      domain_config: Optional[DomainConfig]) -> Dict[str, float]:
        """Calculate domain-specific gap metrics."""
        domain_gaps = {}
        
        if content_type == ContentType.TECHNICAL:
            # Technical-specific gaps
            domain_gaps['api_continuity'] = self._calculate_api_continuity_gap(chunk1, chunk2)
            domain_gaps['code_context'] = self._calculate_code_context_gap(chunk1, chunk2)
            domain_gaps['technical_terminology'] = self._calculate_terminology_gap(chunk1, chunk2, 'technical')
        
        elif content_type == ContentType.MEDICAL:
            # Medical-specific gaps
            domain_gaps['clinical_continuity'] = self._calculate_clinical_continuity_gap(chunk1, chunk2)
            domain_gaps['safety_information'] = self._calculate_safety_information_gap(chunk1, chunk2)
            domain_gaps['medical_terminology'] = self._calculate_terminology_gap(chunk1, chunk2, 'medical')
        
        elif content_type == ContentType.LEGAL:
            # Legal-specific gaps
            domain_gaps['legal_continuity'] = self._calculate_legal_continuity_gap(chunk1, chunk2)
            domain_gaps['statutory_flow'] = self._calculate_statutory_flow_gap(chunk1, chunk2)
            domain_gaps['precedent_connection'] = self._calculate_precedent_connection_gap(chunk1, chunk2)
        
        elif content_type == ContentType.ACADEMIC:
            # Academic-specific gaps
            domain_gaps['research_continuity'] = self._calculate_research_continuity_gap(chunk1, chunk2)
            domain_gaps['methodological_flow'] = self._calculate_methodological_flow_gap(chunk1, chunk2)
            domain_gaps['citation_context'] = self._calculate_citation_context_gap(chunk1, chunk2)
        
        elif content_type == ContentType.NARRATIVE:
            # Narrative-specific gaps
            domain_gaps['narrative_flow'] = self._calculate_narrative_flow_gap(chunk1, chunk2)
            domain_gaps['character_continuity'] = self._calculate_character_continuity_gap(chunk1, chunk2)
            domain_gaps['scene_transition'] = self._calculate_scene_transition_gap(chunk1, chunk2)
        
        return domain_gaps
    
    def _calculate_api_continuity_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate API continuity gap for technical content."""
        # Look for API-related patterns
        api_patterns = [r'\b\w+\(\)', r'\b\w+\.\w+', r'class\s+\w+', r'def\s+\w+']
        
        chunk1_apis = set()
        chunk2_apis = set()
        
        for pattern in api_patterns:
            chunk1_apis.update(re.findall(pattern, chunk1))
            chunk2_apis.update(re.findall(pattern, chunk2))
        
        if not chunk1_apis or not chunk2_apis:
            return 0.5  # Moderate gap when no APIs detected
        
        overlap = len(chunk1_apis.intersection(chunk2_apis))
        total = len(chunk1_apis.union(chunk2_apis))
        
        return 1.0 - (overlap / total) if total > 0 else 0.5
    
    def _calculate_code_context_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate code context gap."""
        # Check for code block boundaries
        chunk1_has_code = bool(re.search(r'```|^\s{4,}', chunk1, re.MULTILINE))
        chunk2_has_code = bool(re.search(r'```|^\s{4,}', chunk2, re.MULTILINE))
        
        if chunk1_has_code and chunk2_has_code:
            # Both have code - check for context continuity
            return 0.3  # Lower gap for code-to-code
        elif chunk1_has_code or chunk2_has_code:
            # Mixed code and text
            return 0.7  # Higher gap for mixed content
        else:
            # No code detected
            return 0.5  # Moderate gap
    
    def _calculate_terminology_gap(self, chunk1: str, chunk2: str, domain: str) -> float:
        """Calculate terminology gap for specific domains."""
        domain_terms = {
            'technical': ['algorithm', 'function', 'variable', 'class', 'method', 'API', 'framework'],
            'medical': ['patient', 'diagnosis', 'treatment', 'symptom', 'medication', 'clinical', 'therapeutic'],
            'legal': ['statute', 'regulation', 'court', 'jurisdiction', 'precedent', 'contract', 'liability']
        }
        
        terms = domain_terms.get(domain, [])
        if not terms:
            return 0.5
        
        chunk1_terms = set(term for term in terms if term.lower() in chunk1.lower())
        chunk2_terms = set(term for term in terms if term.lower() in chunk2.lower())
        
        if not chunk1_terms and not chunk2_terms:
            return 0.5  # No domain terms found
        
        overlap = len(chunk1_terms.intersection(chunk2_terms))
        total = len(chunk1_terms.union(chunk2_terms))
        
        return 1.0 - (overlap / total) if total > 0 else 0.5
    
    def _calculate_clinical_continuity_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate clinical continuity gap for medical content."""
        clinical_sections = ['symptoms', 'diagnosis', 'treatment', 'prognosis', 'contraindications']
        
        chunk1_sections = [s for s in clinical_sections if s in chunk1.lower()]
        chunk2_sections = [s for s in clinical_sections if s in chunk2.lower()]
        
        if chunk1_sections and chunk2_sections:
            # Check for logical flow
            section_order = {s: i for i, s in enumerate(clinical_sections)}
            chunk1_max = max(section_order[s] for s in chunk1_sections)
            chunk2_min = min(section_order[s] for s in chunk2_sections)
            
            if chunk2_min > chunk1_max:
                return 0.2  # Good clinical flow
            else:
                return 0.6  # Mixed or reverse flow
        
        return 0.5  # Default gap
    
    def _calculate_safety_information_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate safety information gap for medical content."""
        safety_keywords = ['contraindication', 'side effect', 'adverse', 'warning', 'caution', 'risk']
        
        chunk1_safety = any(keyword in chunk1.lower() for keyword in safety_keywords)
        chunk2_safety = any(keyword in chunk2.lower() for keyword in safety_keywords)
        
        if chunk1_safety and not chunk2_safety:
            return 0.8  # High gap when safety info is separated
        elif chunk1_safety and chunk2_safety:
            return 0.3  # Low gap when both contain safety info
        else:
            return 0.5  # Default gap
    
    def _calculate_legal_continuity_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate legal continuity gap."""
        # Check for legal section numbering
        chunk1_sections = re.findall(r'(?:Section|Article)\s+(\d+)', chunk1)
        chunk2_sections = re.findall(r'(?:Section|Article)\s+(\d+)', chunk2)
        
        if chunk1_sections and chunk2_sections:
            chunk1_max = max(int(s) for s in chunk1_sections)
            chunk2_min = min(int(s) for s in chunk2_sections)
            
            if chunk2_min == chunk1_max + 1:
                return 0.2  # Sequential sections
            elif chunk2_min > chunk1_max:
                return 0.4  # Non-sequential but ordered
            else:
                return 0.7  # Disordered sections
        
        return 0.5  # Default gap
    
    def _calculate_statutory_flow_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate statutory flow gap for legal content."""
        # Look for legal flow indicators
        flow_indicators = ['pursuant to', 'in accordance with', 'subject to', 'provided that']
        
        chunk2_start = chunk2[:200].lower()
        has_flow_indicator = any(indicator in chunk2_start for indicator in flow_indicators)
        
        return 0.3 if has_flow_indicator else 0.6
    
    def _calculate_precedent_connection_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate precedent connection gap for legal content."""
        # Look for case citations and precedent references
        citation_pattern = r'\b\w+\s+v\.\s+\w+\b'
        
        chunk1_citations = re.findall(citation_pattern, chunk1)
        chunk2_citations = re.findall(citation_pattern, chunk2)
        
        shared_citations = set(chunk1_citations).intersection(set(chunk2_citations))
        
        if shared_citations:
            return 0.2  # Strong precedent connection
        elif chunk1_citations and chunk2_citations:
            return 0.5  # Different precedents
        else:
            return 0.7  # No precedent connection
    
    def _calculate_research_continuity_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate research continuity gap for academic content."""
        research_sections = ['hypothesis', 'methodology', 'results', 'analysis', 'discussion']
        
        chunk1_sections = [s for s in research_sections if s in chunk1.lower()]
        chunk2_sections = [s for s in research_sections if s in chunk2.lower()]
        
        if chunk1_sections and chunk2_sections:
            return 0.3  # Research continuity present
        else:
            return 0.6  # No clear research flow
    
    def _calculate_methodological_flow_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate methodological flow gap for academic content."""
        method_keywords = ['method', 'procedure', 'protocol', 'approach', 'technique']
        
        chunk1_methods = any(keyword in chunk1.lower() for keyword in method_keywords)
        chunk2_methods = any(keyword in chunk2.lower() for keyword in method_keywords)
        
        if chunk1_methods and chunk2_methods:
            return 0.3  # Methodological continuity
        else:
            return 0.6  # No methodological flow
    
    def _calculate_citation_context_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate citation context gap for academic content."""
        # Look for citation patterns
        citation_patterns = [r'\([^)]*\d{4}[^)]*\)', r'\[\d+\]', r'\w+\s+et\s+al\.']
        
        chunk1_citations = []
        chunk2_citations = []
        
        for pattern in citation_patterns:
            chunk1_citations.extend(re.findall(pattern, chunk1))
            chunk2_citations.extend(re.findall(pattern, chunk2))
        
        if chunk1_citations and chunk2_citations:
            return 0.4  # Both have citations
        elif chunk1_citations or chunk2_citations:
            return 0.6  # Only one has citations
        else:
            return 0.5  # No citations
    
    def _calculate_narrative_flow_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate narrative flow gap."""
        # Look for narrative flow indicators
        flow_indicators = ['then', 'next', 'after', 'meanwhile', 'suddenly', 'later', 'finally']
        
        chunk2_start = chunk2[:100].lower()
        has_flow = any(indicator in chunk2_start for indicator in flow_indicators)
        
        return 0.3 if has_flow else 0.6
    
    def _calculate_character_continuity_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate character continuity gap for narrative content."""
        # Extract potential character names (capitalized words)
        chunk1_names = set(re.findall(r'\b[A-Z][a-z]+\b', chunk1))
        chunk2_names = set(re.findall(r'\b[A-Z][a-z]+\b', chunk2))
        
        # Filter out common non-name words
        common_words = {'The', 'This', 'That', 'When', 'Where', 'How', 'Why', 'What'}
        chunk1_names -= common_words
        chunk2_names -= common_words
        
        if not chunk1_names or not chunk2_names:
            return 0.5
        
        overlap = len(chunk1_names.intersection(chunk2_names))
        total = len(chunk1_names.union(chunk2_names))
        
        return 1.0 - (overlap / total) if total > 0 else 0.5
    
    def _calculate_scene_transition_gap(self, chunk1: str, chunk2: str) -> float:
        """Calculate scene transition gap for narrative content."""
        # Look for scene break indicators
        scene_breaks = [r'\*\s*\*\s*\*', r'---+', r'###', r'Chapter\s+\d+']
        
        has_scene_break = any(re.search(pattern, chunk1 + chunk2) for pattern in scene_breaks)
        
        return 0.8 if has_scene_break else 0.4
    
    def _calculate_necessity_score(self, semantic_distance: float, concept_overlap: float,
                                 cross_ref_density: float, structural_continuity: float,
                                 content_type: ContentType, 
                                 domain_specific_gaps: Dict[str, float]) -> float:
        """Calculate necessity score using domain weights."""
        
        # Get domain-specific weights
        weights = self.domain_weights.get(content_type, self.domain_weights[ContentType.GENERAL])
        
        # Calculate base necessity score
        base_score = (
            semantic_distance * weights['semantic_distance'] +
            (1.0 - concept_overlap) * weights['concept_overlap'] +  # Invert overlap (high overlap = low necessity)
            cross_ref_density * weights['cross_reference_density'] +
            (1.0 - structural_continuity) * weights['structural_continuity']  # Invert continuity
        )
        
        # Add domain-specific adjustments
        domain_adjustment = 0.0
        if domain_specific_gaps:
            domain_scores = list(domain_specific_gaps.values())
            domain_adjustment = sum(domain_scores) / len(domain_scores) * 0.2  # 20% weight for domain factors
        
        necessity_score = base_score + domain_adjustment
        
        # Ensure score is in valid range
        return max(0.0, min(1.0, necessity_score))        
        # Ensure score is in valid range
        return max(0.0, min(1.0, necessity_score))