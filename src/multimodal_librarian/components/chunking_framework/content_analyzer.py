"""
Automated Content Analyzer with Knowledge Graph Integration.

This module implements automated content profiling using YAGO entity extraction,
ConceptNet relationship analysis, and comprehensive content complexity scoring.

Uses model server for embeddings and NLP processing (separate container).
"""

import asyncio
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

import numpy as np
import requests

from ...clients.model_server_client import (
    ModelServerUnavailable,
    get_model_client,
    initialize_model_client,
)
from ...config import get_settings
from ...models.chunking import ChunkingRequirements, ContentProfile, DomainPatterns
from ...models.core import ContentType, DocumentContent, DocumentStructure

logger = logging.getLogger(__name__)


@dataclass
class EntityExtraction:
    """Represents an extracted entity with YAGO information."""
    text: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    confidence: float = 0.0
    categories: List[str] = None
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = []


@dataclass
class ConceptNetRelation:
    """Represents a ConceptNet relationship."""
    subject: str
    relation: str
    object: str
    weight: float = 0.0
    source: str = "conceptnet"


class AutomatedContentAnalyzer:
    """
    Automated content analyzer with knowledge graph integration.
    
    Implements YAGO entity extraction, ConceptNet relationship analysis,
    content complexity scoring, and comprehensive content profile generation.
    """
    
    def __init__(self):
        """Initialize the content analyzer with required models and APIs."""
        self.nlp = None
        self.sentence_model = None
        self._initialize_models()
        
        # YAGO SPARQL endpoint
        self.yago_endpoint = "https://yago-knowledge.org/sparql/query"
        
        # ConceptNet API endpoint
        self.conceptnet_endpoint = "http://api.conceptnet.io"
        
        # Cache for API responses
        self._entity_cache = {}
        self._relation_cache = {}
        
        # Domain classification patterns
        self.domain_patterns = {
            ContentType.TECHNICAL: [
                r'\b(?:algorithm|software|hardware|programming|computer|system|network|database|API|protocol)\b',
                r'\b(?:implementation|architecture|framework|library|module|function|class|method)\b',
                r'\b(?:performance|optimization|scalability|efficiency|throughput|latency)\b'
            ],
            ContentType.MEDICAL: [
                r'\b(?:patient|diagnosis|treatment|therapy|medication|disease|symptom|clinical|medical)\b',
                r'\b(?:anatomy|physiology|pathology|pharmacology|surgery|hospital|doctor|nurse)\b',
                r'\b(?:health|healthcare|medicine|pharmaceutical|therapeutic|diagnostic)\b',
                r'\b(?:orthopaedic|orthopedic|cardiology|oncology|neurology|radiology|pediatric)\b',
                r'\b(?:epidemiology|prognosis|comorbidity|etiology|chronic|acute|benign|malignant)\b',
                # Pharmacopoeia and pharmaceutical standards terminology
                r'\b(?:pharmacopoeia|pharmacopeia|monograph|excipient|formulation|dosage|potency|purity)\b',
                r'\b(?:assay|titration|chromatography|spectrophotometry|dissolution|bioavailability)\b',
                r'\b(?:drug|substance|compound|active\s+ingredient|API|impurity|degradation)\b',
                # Herbal and botanical medicine terminology
                r'\b(?:herbal|botanical|extract|tincture|decoction|infusion|herb|plant\s+medicine)\b',
                r'\b(?:contraindication|interaction|adverse|toxicity|efficacy|indication)\b',
            ],
            ContentType.LEGAL: [
                r'\b(?:law|legal|court|judge|attorney|lawyer|contract|agreement|statute|regulation)\b',
                r'\b(?:plaintiff|defendant|litigation|jurisdiction|precedent|ruling|verdict)\b',
                r'\b(?:constitutional|criminal|civil|administrative|commercial|intellectual property)\b'
            ],
            ContentType.ACADEMIC: [
                r'\b(?:research|study|analysis|methodology|hypothesis|theory|experiment|data)\b',
                r'\b(?:literature|review|citation|reference|bibliography|journal|publication)\b',
                r'\b(?:academic|scholarly|peer-reviewed|empirical|statistical|quantitative|qualitative)\b'
            ],
            ContentType.NARRATIVE: [
                r'\b(?:story|character|plot|narrative|fiction|novel|chapter|scene|dialogue)\b',
                r'\b(?:protagonist|antagonist|setting|theme|metaphor|symbolism|literary)\b',
                r'\b(?:biography|autobiography|memoir|historical|personal|experience)\b'
            ]
        }
    
    def _initialize_models(self):
        """Initialize NLP models with error handling."""
        # NLP processing is done via model server
        self.nlp = None
        self._model_server_client = None
        logger.info("Content analyzer initialized (using model server for NLP and embeddings)")
    
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
    
    def analyze_document(self, document: DocumentContent) -> ContentProfile:
        """
        Generate comprehensive content profile using multiple knowledge sources.
        
        Args:
            document: Document content to analyze
            
        Returns:
            ContentProfile with automated analysis results
        """
        logger.info("Starting automated content analysis")
        
        # Extract entities and classify content type
        entities = self._extract_entities(document.text)
        content_type = self._classify_content_type(document.text, entities)
        
        # Get domain categories from YAGO
        domain_categories = self._get_yago_categories(entities)
        
        # Analyze domain patterns using ConceptNet
        domain_patterns = self._analyze_domain_patterns(entities, content_type)
        
        # Calculate complexity and density scores
        complexity_score = self._calculate_complexity_score(document)
        cross_ref_density = self._calculate_cross_reference_density(document.text)
        conceptual_density = self._calculate_conceptual_density(document.text, entities)
        
        # Generate chunking requirements
        chunking_requirements = self._generate_chunking_requirements(
            content_type, complexity_score, conceptual_density
        )
        
        # Create content profile
        profile = ContentProfile(
            content_type=content_type,
            domain_categories=domain_categories,
            complexity_score=complexity_score,
            structure_hierarchy=self._analyze_structure_hierarchy(document),
            domain_patterns=domain_patterns,
            cross_reference_density=cross_ref_density,
            conceptual_density=conceptual_density,
            chunking_requirements=chunking_requirements
        )
        
        logger.info(f"Content analysis complete. Type: {content_type.value}, "
                   f"Complexity: {complexity_score:.2f}, "
                   f"Categories: {len(domain_categories)}")
        
        return profile
    
    def _extract_entities(self, text: str) -> List[EntityExtraction]:
        """Extract entities using pattern-based extraction and model server NLP."""
        # Use pattern-based extraction (model server NLP can be used async separately)
        return self._extract_entities_pattern_based(text)
    
    async def _extract_entities_async(self, text: str) -> List[EntityExtraction]:
        """Extract entities using model server NLP asynchronously."""
        entities = []
        
        try:
            client = await self._get_model_server_client()
            if client:
                # Use model server for NER
                results = await client.process_nlp([text], tasks=["ner"])
                if results and results[0].get("entities"):
                    for ent in results[0]["entities"]:
                        if ent.get("label") in ['PERSON', 'ORG', 'GPE', 'PRODUCT', 'EVENT', 'WORK_OF_ART']:
                            entity = EntityExtraction(
                                text=ent.get("text", ""),
                                entity_type=ent.get("label"),
                                confidence=0.8
                            )
                            self._enrich_entity_with_yago(entity)
                            entities.append(entity)
                    return entities
        except Exception as e:
            logger.warning(f"Model server NER failed: {e}")
        
        # Fallback to pattern-based extraction
        return self._extract_entities_pattern_based(text)
    
    def _extract_entities_pattern_based(self, text: str) -> List[EntityExtraction]:
        """Fallback entity extraction using patterns."""
        entities = []
        
        # Simple pattern-based extraction for key terms
        patterns = [
            (r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', 'PERSON'),  # Proper names
            (r'\b[A-Z]{2,}\b', 'ORG'),  # Acronyms
            (r'\b\d{4}\b', 'DATE'),  # Years
        ]
        
        for pattern, entity_type in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                entity = EntityExtraction(
                    text=match.group(),
                    entity_type=entity_type,
                    confidence=0.6  # Lower confidence for pattern-based
                )
                entities.append(entity)
        
        return entities
    
    def _enrich_entity_with_yago(self, entity: EntityExtraction):
        """Enrich entity with YAGO information."""
        if entity.text in self._entity_cache:
            cached_data = self._entity_cache[entity.text]
            entity.entity_id = cached_data.get('entity_id')
            entity.categories = cached_data.get('categories', [])
            return
        
        try:
            # Search for entity in YAGO
            search_url = f"{self.yago_endpoint}"
            query = f"""
            SELECT ?item ?itemLabel ?instanceOf ?instanceOfLabel WHERE {{
              ?item rdfs:label "{entity.text}"@en .
              OPTIONAL {{ ?item wdt:P31 ?instanceOf . }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
            }}
            LIMIT 5
            """
            
            response = requests.get(search_url, params={'query': query, 'format': 'json'}, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('results', {}).get('bindings'):
                    result = data['results']['bindings'][0]
                    entity.entity_id = result.get('item', {}).get('value', '').split('/')[-1]
                    
                    # Extract categories from instanceOf
                    categories = []
                    for binding in data['results']['bindings']:
                        if 'instanceOfLabel' in binding:
                            categories.append(binding['instanceOfLabel']['value'])
                    
                    entity.categories = categories[:5]  # Limit to top 5 categories
                    
                    # Cache the result
                    self._entity_cache[entity.text] = {
                        'entity_id': entity.entity_id,
                        'categories': entity.categories
                    }
        
        except Exception as e:
            logger.debug(f"Failed to enrich entity {entity.text} with YAGO: {e}")
    
    def _classify_content_type(self, text: str, entities: List[EntityExtraction]) -> ContentType:
        """Classify content type using domain patterns and entity analysis."""
        text_lower = text.lower()
        
        # Score each content type based on pattern matches
        type_scores = {}
        
        for content_type, patterns in self.domain_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
                score += matches
            
            # Normalize by text length
            type_scores[content_type] = score / max(len(text.split()), 1)
        
        # Add entity-based scoring
        entity_categories = []
        for entity in entities:
            entity_categories.extend(entity.categories)
        
        category_counter = Counter(entity_categories)
        
        # Boost scores based on entity categories
        for category, count in category_counter.items():
            category_lower = category.lower()
            if any(term in category_lower for term in ['software', 'computer', 'technology']):
                type_scores[ContentType.TECHNICAL] += count * 0.1
            elif any(term in category_lower for term in ['medical', 'health', 'disease']):
                type_scores[ContentType.MEDICAL] += count * 0.1
            elif any(term in category_lower for term in ['law', 'legal', 'court']):
                type_scores[ContentType.LEGAL] += count * 0.1
            elif any(term in category_lower for term in ['academic', 'research', 'university']):
                type_scores[ContentType.ACADEMIC] += count * 0.1
            elif any(term in category_lower for term in ['book', 'novel', 'story']):
                type_scores[ContentType.NARRATIVE] += count * 0.1
        
        # Return the highest scoring type, default to GENERAL
        if type_scores:
            best_type = max(type_scores, key=type_scores.get)
            if type_scores[best_type] > 0.01:  # Minimum threshold
                return best_type
        
        return ContentType.GENERAL
    
    def _get_yago_categories(self, entities: List[EntityExtraction]) -> List[str]:
        """Get domain categories from YAGO entity analysis."""
        categories = set()
        
        for entity in entities:
            categories.update(entity.categories)
        
        # Filter and prioritize relevant categories
        relevant_categories = []
        for category in categories:
            if len(category.split()) <= 3:  # Avoid overly specific categories
                relevant_categories.append(category)
        
        return sorted(relevant_categories)[:10]  # Return top 10 categories
    
    def _analyze_domain_patterns(self, entities: List[EntityExtraction], 
                                content_type: ContentType) -> DomainPatterns:
        """Analyze domain patterns using ConceptNet relationship analysis."""
        
        # Extract key concepts from entities
        concepts = [entity.text.lower().replace(' ', '_') for entity in entities[:10]]
        
        # Get ConceptNet relationships
        relationships = self._get_conceptnet_relationships(concepts)
        
        # Analyze patterns from relationships
        relationship_patterns = self._extract_relationship_patterns(relationships)
        structural_patterns = self._extract_structural_patterns(content_type)
        semantic_patterns = self._extract_semantic_patterns(relationships)
        delimiter_patterns = self._extract_delimiter_patterns(content_type)
        
        return DomainPatterns(
            relationship_patterns=relationship_patterns,
            structural_patterns=structural_patterns,
            semantic_patterns=semantic_patterns,
            delimiter_patterns=delimiter_patterns
        )
    
    def _get_conceptnet_relationships(self, concepts: List[str]) -> List[ConceptNetRelation]:
        """Get relationships from ConceptNet for given concepts."""
        relationships = []
        
        for concept in concepts[:5]:  # Limit API calls
            if concept in self._relation_cache:
                relationships.extend(self._relation_cache[concept])
                continue
            
            try:
                url = f"{self.conceptnet_endpoint}/c/en/{quote(concept)}"
                response = requests.get(url, params={'limit': 10}, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    concept_relations = []
                    
                    for edge in data.get('edges', []):
                        relation = ConceptNetRelation(
                            subject=edge.get('start', {}).get('label', ''),
                            relation=edge.get('rel', {}).get('label', ''),
                            object=edge.get('end', {}).get('label', ''),
                            weight=edge.get('weight', 0.0)
                        )
                        concept_relations.append(relation)
                        relationships.append(relation)
                    
                    self._relation_cache[concept] = concept_relations
            
            except Exception as e:
                logger.debug(f"Failed to get ConceptNet relationships for {concept}: {e}")
        
        return relationships
    
    def _extract_relationship_patterns(self, relationships: List[ConceptNetRelation]) -> List[str]:
        """Extract relationship patterns from ConceptNet data."""
        patterns = []
        
        # Count relationship types
        relation_counter = Counter(rel.relation for rel in relationships)
        
        # Extract common relationship patterns
        for relation, count in relation_counter.most_common(5):
            if count >= 2:  # Only include patterns that appear multiple times
                patterns.append(f"common_relation:{relation}")
        
        return patterns
    
    def _extract_structural_patterns(self, content_type: ContentType) -> List[str]:
        """Extract structural patterns based on content type."""
        patterns = []
        
        if content_type == ContentType.TECHNICAL:
            patterns.extend([
                "section_headers", "code_blocks", "numbered_lists",
                "bullet_points", "diagrams", "tables"
            ])
        elif content_type == ContentType.ACADEMIC:
            patterns.extend([
                "abstract", "introduction", "methodology", "results",
                "discussion", "conclusion", "references"
            ])
        elif content_type == ContentType.LEGAL:
            patterns.extend([
                "numbered_sections", "subsections", "definitions",
                "clauses", "articles", "amendments"
            ])
        elif content_type == ContentType.MEDICAL:
            patterns.extend([
                "symptoms", "diagnosis", "treatment", "dosage",
                "contraindications", "side_effects"
            ])
        elif content_type == ContentType.NARRATIVE:
            patterns.extend([
                "chapters", "scenes", "dialogue", "descriptions",
                "character_development", "plot_progression"
            ])
        else:
            patterns.extend([
                "paragraphs", "sections", "headings", "lists"
            ])
        
        return patterns
    
    def _extract_semantic_patterns(self, relationships: List[ConceptNetRelation]) -> List[str]:
        """Extract semantic patterns from relationship analysis."""
        patterns = []
        
        # Analyze semantic relationship types
        semantic_types = defaultdict(int)
        
        for rel in relationships:
            if rel.relation in ['IsA', 'PartOf', 'UsedFor', 'CapableOf']:
                semantic_types[rel.relation] += 1
        
        # Convert to patterns
        for rel_type, count in semantic_types.items():
            if count >= 2:
                patterns.append(f"semantic:{rel_type.lower()}")
        
        return patterns
    
    def _extract_delimiter_patterns(self, content_type: ContentType) -> List[str]:
        """Extract delimiter patterns based on content type."""
        patterns = []
        
        if content_type == ContentType.TECHNICAL:
            patterns.extend([
                r'\n\s*\d+\.\s+',  # Numbered sections
                r'\n\s*[A-Z][a-z]+:',  # Section headers
                r'\n\s*```',  # Code blocks
                r'\n\s*-\s+',  # Bullet points
            ])
        elif content_type == ContentType.ACADEMIC:
            patterns.extend([
                r'\n\s*\d+\.\d+\s+',  # Subsections
                r'\n\s*[A-Z][A-Z\s]+\n',  # All caps headers
                r'\n\s*Abstract\s*\n',  # Abstract section
                r'\n\s*References\s*\n',  # References section
            ])
        elif content_type == ContentType.LEGAL:
            patterns.extend([
                r'\n\s*\([a-z]\)\s+',  # Lettered subsections
                r'\n\s*Section\s+\d+',  # Section markers
                r'\n\s*Article\s+[IVX]+',  # Article markers
            ])
        else:
            patterns.extend([
                r'\n\s*Chapter\s+\d+',  # Chapters
                r'\n\s*\d+\.\s+',  # Numbered sections
                r'\n\n',  # Paragraph breaks
            ])
        
        return patterns
    
    def _calculate_complexity_score(self, document: DocumentContent) -> float:
        """Calculate content complexity score (0.0-1.0)."""
        text = document.text
        
        # Handle empty documents
        if not text or not text.strip():
            return 0.0
        
        # Factors for complexity calculation
        factors = {}
        
        # Sentence length complexity
        sentences = re.split(r'[.!?]+', text)
        sentence_lengths = [len(s.split()) for s in sentences if s.strip()]
        if sentence_lengths:
            avg_sentence_length = np.mean(sentence_lengths)
            factors['sentence_length'] = min(avg_sentence_length / 30.0, 1.0)  # Normalize to 30 words
        else:
            factors['sentence_length'] = 0.0
        
        # Vocabulary complexity (unique words ratio)
        words = text.lower().split()
        if words:
            unique_ratio = len(set(words)) / len(words)
            factors['vocabulary'] = unique_ratio
        else:
            factors['vocabulary'] = 0.0
        
        # Technical term density
        technical_patterns = [
            r'\b\w+tion\b', r'\b\w+ment\b', r'\b\w+ness\b',  # Abstract nouns
            r'\b\w{10,}\b',  # Long words
            r'\b[A-Z]{2,}\b',  # Acronyms
        ]
        
        technical_count = 0
        for pattern in technical_patterns:
            technical_count += len(re.findall(pattern, text))
        
        if words:
            factors['technical_density'] = min(technical_count / len(words), 1.0)
        else:
            factors['technical_density'] = 0.0
        
        # Structural complexity (nested elements)
        lines = text.split('\n')
        if lines:
            structural_elements = len(re.findall(r'\n\s+', text))  # Indented lines
            factors['structure'] = min(structural_elements / len(lines), 1.0)
        else:
            factors['structure'] = 0.0
        
        # Multimedia complexity
        media_count = len(document.get_all_media())
        factors['multimedia'] = min(media_count / 10.0, 1.0)  # Normalize to 10 media elements
        
        # Weighted average
        weights = {
            'sentence_length': 0.25,
            'vocabulary': 0.25,
            'technical_density': 0.25,
            'structure': 0.15,
            'multimedia': 0.10
        }
        
        complexity_score = sum(factors[key] * weights[key] for key in factors)
        return min(complexity_score, 1.0)
    
    def _calculate_cross_reference_density(self, text: str) -> float:
        """Calculate cross-reference density in the text."""
        # Patterns for cross-references
        ref_patterns = [
            r'see\s+(?:section|chapter|page|figure|table)\s+\d+',
            r'(?:section|chapter|page|figure|table)\s+\d+',
            r'above|below|previously|later|aforementioned',
            r'\(see\s+[^)]+\)',
            r'as\s+(?:mentioned|discussed|shown|described)\s+(?:above|below|earlier|later)',
        ]
        
        total_refs = 0
        for pattern in ref_patterns:
            total_refs += len(re.findall(pattern, text, re.IGNORECASE))
        
        # Normalize by text length (references per 1000 words)
        word_count = len(text.split())
        density = (total_refs / max(word_count, 1)) * 1000
        
        return min(density / 50.0, 1.0)  # Normalize to max 50 refs per 1000 words
    
    def _calculate_conceptual_density(self, text: str, entities: List[EntityExtraction]) -> float:
        """Calculate conceptual density based on entity distribution."""
        if not entities:
            return 0.0
        
        # Calculate entity density (entities per 100 words)
        word_count = len(text.split())
        entity_density = (len(entities) / max(word_count, 1)) * 100
        
        # Calculate entity diversity (unique entity types)
        entity_types = set(entity.entity_type for entity in entities if entity.entity_type)
        type_diversity = len(entity_types) / max(len(entities), 1)
        
        # Calculate category richness
        all_categories = []
        for entity in entities:
            all_categories.extend(entity.categories)
        
        category_diversity = len(set(all_categories)) / max(len(all_categories), 1) if all_categories else 0
        
        # Combine factors
        conceptual_density = (entity_density * 0.4 + type_diversity * 0.3 + category_diversity * 0.3)
        
        return min(conceptual_density / 10.0, 1.0)  # Normalize
    
    def _generate_chunking_requirements(self, content_type: ContentType, 
                                      complexity_score: float, 
                                      conceptual_density: float) -> ChunkingRequirements:
        """Generate chunking requirements based on content analysis."""
        
        # Read embedding-aware chunk size bounds from settings
        settings = get_settings()
        target_tokens = getattr(settings, 'target_embedding_tokens', 256)
        max_tokens = getattr(settings, 'max_embedding_tokens', 512)
        min_tokens = getattr(settings, 'min_embedding_tokens', 64)
        
        base_overlap = 0.1
        base_threshold = 0.7
        
        # Adjust based on content type
        type_adjustments = {
            ContentType.TECHNICAL: {'size_mult': 1.2, 'overlap_mult': 1.3, 'threshold_mult': 0.9},
            ContentType.LEGAL: {'size_mult': 1.5, 'overlap_mult': 1.4, 'threshold_mult': 0.8},
            ContentType.MEDICAL: {'size_mult': 1.3, 'overlap_mult': 1.2, 'threshold_mult': 0.85},
            ContentType.ACADEMIC: {'size_mult': 1.4, 'overlap_mult': 1.1, 'threshold_mult': 0.9},
            ContentType.NARRATIVE: {'size_mult': 0.8, 'overlap_mult': 0.8, 'threshold_mult': 1.1},
            ContentType.GENERAL: {'size_mult': 1.0, 'overlap_mult': 1.0, 'threshold_mult': 1.0}
        }
        
        adjustments = type_adjustments.get(content_type, type_adjustments[ContentType.GENERAL])
        
        # Adjust based on complexity
        complexity_factor = 1.0 + (complexity_score - 0.5) * 0.4  # Range: 0.8 to 1.2
        
        # Adjust based on conceptual density
        density_factor = 1.0 + (conceptual_density - 0.5) * 0.3  # Range: 0.85 to 1.15
        
        # Calculate final values using target_embedding_tokens as base
        preferred_size = int(target_tokens * adjustments['size_mult'] * complexity_factor)
        overlap_percentage = base_overlap * adjustments['overlap_mult'] * density_factor
        bridge_threshold = base_threshold * adjustments['threshold_mult']
        
        # Clamp to embedding model bounds
        preferred_size = max(min_tokens, min(preferred_size, max_tokens))
        overlap_percentage = max(0.05, min(overlap_percentage, 0.3))
        bridge_threshold = max(0.5, min(bridge_threshold, 0.9))
        
        return ChunkingRequirements(
            preferred_chunk_size=preferred_size,
            min_chunk_size=max(min_tokens, preferred_size // 3),
            max_chunk_size=min(max_tokens, int(preferred_size * 1.5)),
            overlap_percentage=overlap_percentage,
            preserve_sentences=True,
            preserve_paragraphs=content_type in [ContentType.NARRATIVE, ContentType.ACADEMIC],
            bridge_threshold=bridge_threshold
        )
    
    def _analyze_structure_hierarchy(self, document: DocumentContent) -> Dict[str, Any]:
        """Analyze document structure hierarchy."""
        if document.structure:
            return document.structure.to_dict()
        
        # Basic structure analysis from text
        text = document.text
        structure = {
            'has_chapters': bool(re.search(r'chapter\s+\d+', text, re.IGNORECASE)),
            'has_sections': bool(re.search(r'section\s+\d+', text, re.IGNORECASE)),
            'has_numbered_lists': bool(re.search(r'\n\s*\d+\.\s+', text)),
            'has_bullet_points': bool(re.search(r'\n\s*[-*•]\s+', text)),
            'paragraph_count': len(re.split(r'\n\s*\n', text)),
            'estimated_reading_time': len(text.split()) / 200  # Assuming 200 WPM
        }
        
        return structure

    def classify_content_type(self, document: DocumentContent) -> ContentType:
        """
        Classify content using YAGO entity classification.
        
        Args:
            document: Document to classify
            
        Returns:
            ContentType classification
        """
        entities = self._extract_entities(document.text)
        return self._classify_content_type(document.text, entities)
    
    def extract_domain_patterns(self, document: DocumentContent) -> DomainPatterns:
        """
        Extract domain-specific patterns using ConceptNet analysis.
        
        Args:
            document: Document to analyze
            
        Returns:
            DomainPatterns extracted from the document
        """
        entities = self._extract_entities(document.text)
        content_type = self._classify_content_type(document.text, entities)
        return self._analyze_domain_patterns(entities, content_type)
    def _split_into_sections(self, text: str) -> List[str]:
        """Split text at structural boundaries (headings, chapter markers, topic shifts).

        Requirements: 6.2
        """
        pattern = r'(?=\n#{1,3}\s)|(?=\nChapter\s+\d)|(?=\nSection\s+\d)|(?=\n[A-Z][A-Z\s]{10,}\n)'
        sections = re.split(pattern, text)
        result = [s.strip() for s in sections if s.strip()]
        # If no structural markers found, return entire text as single section
        if not result:
            return [text.strip()] if text.strip() else []
        return result

    def classify_sections(self, document: DocumentContent) -> List[Tuple[str, ContentType, ChunkingRequirements]]:
        """Split document into sections and classify each independently.

        Sections shorter than 100 tokens inherit the previous section's classification.

        Requirements: 6.1, 6.3, 6.5
        """
        sections = self._split_into_sections(document.text)
        results = []
        last_classification = ContentType.GENERAL

        for section_text in sections:
            if len(section_text.split()) < 100:
                classification = last_classification  # inherit
            else:
                entities = self._extract_entities(section_text)
                classification = self._classify_content_type(section_text, entities)
                last_classification = classification

            complexity = self._calculate_complexity_score(
                DocumentContent(
                    text=section_text, images=[], tables=[],
                    metadata={}, structure=None
                )
            )
            entities = self._extract_entities(section_text)
            density = self._calculate_conceptual_density(section_text, entities)
            reqs = self._generate_chunking_requirements(classification, complexity, density)
            results.append((section_text, classification, reqs))

        return results




