"""
Advanced Query Understanding for Multimodal Librarian.

This module implements sophisticated query analysis, intent detection,
entity extraction, and query optimization for improved search accuracy.

Uses model server for NLP processing (separate container).
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from ...clients.model_server_client import (
    ModelServerUnavailable,
    get_model_client,
    initialize_model_client,
)

# Import search types to avoid circular imports
from ...models.search_types import (
    QueryComplexity,
    QueryContext,
    QueryEntity,
    QueryIntent,
    QueryRelation,
    UnderstoodQuery,
)

logger = logging.getLogger(__name__)


class EntityExtractor:
    """Extracts and enriches entities from queries."""
    
    def __init__(self):
        self._model_server_client = None
        self.domain_entities = self._load_domain_entities()
        logger.info("EntityExtractor created (using model server for NLP)")
    
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
    
    def extract_entities(self, query: str, context: QueryContext) -> List[QueryEntity]:
        """
        Extract entities from query text using pattern-based extraction.
        
        For async NLP-based extraction, use extract_entities_async().
        
        Args:
            query: Query text
            context: Query context for domain-specific extraction
            
        Returns:
            List of extracted entities
        """
        entities = []
        
        # Add domain-specific entities
        domain_entities = self._extract_domain_entities(query, context.domain)
        entities.extend(domain_entities)
        
        # Add technical terms and concepts
        concept_entities = self._extract_concepts(query)
        entities.extend(concept_entities)
        
        # Deduplicate and enrich entities
        entities = self._deduplicate_entities(entities)
        entities = self._enrich_entities(entities, context)
        
        return entities
    
    async def extract_entities_async(self, query: str, context: QueryContext) -> List[QueryEntity]:
        """
        Extract entities from query text using model server NLP.
        
        Args:
            query: Query text
            context: Query context for domain-specific extraction
            
        Returns:
            List of extracted entities
        """
        entities = []
        
        # Try model server for NER
        try:
            client = await self._get_model_server_client()
            if client:
                results = await client.process_nlp([query], tasks=["ner"])
                if results and results[0].get("entities"):
                    for ent in results[0]["entities"]:
                        entity = QueryEntity(
                            text=ent.get("text", ""),
                            label=ent.get("label", ""),
                            start=ent.get("start", 0),
                            end=ent.get("end", 0),
                            confidence=0.8
                        )
                        entities.append(entity)
        except Exception as e:
            logger.warning(f"Model server NER failed: {e}")
        
        # Add domain-specific entities
        domain_entities = self._extract_domain_entities(query, context.domain)
        entities.extend(domain_entities)
        
        # Add technical terms and concepts
        concept_entities = self._extract_concepts(query)
        entities.extend(concept_entities)
        
        # Deduplicate and enrich entities
        entities = self._deduplicate_entities(entities)
        entities = self._enrich_entities(entities, context)
        return entities
    
    def _extract_domain_entities(self, query: str, domain: Optional[str]) -> List[QueryEntity]:
        """Extract domain-specific entities."""
        entities = []
        
        if not domain or domain not in self.domain_entities:
            return entities
        
        domain_terms = self.domain_entities[domain]
        query_lower = query.lower()
        
        for term, info in domain_terms.items():
            if term in query_lower:
                start = query_lower.find(term)
                entity = QueryEntity(
                    text=term,
                    label=info.get('type', 'CONCEPT'),
                    start=start,
                    end=start + len(term),
                    confidence=info.get('confidence', 0.9),
                    synonyms=info.get('synonyms', []),
                    related_terms=info.get('related', [])
                )
                entities.append(entity)
        
        return entities
    
    def _extract_concepts(self, query: str) -> List[QueryEntity]:
        """Extract technical concepts and terms."""
        # Pattern-based concept extraction
        concept_patterns = [
            r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',  # Title case terms
            r'\b[a-z]+(?:-[a-z]+)+\b',  # Hyphenated terms
            r'\b[A-Z]{2,}\b',  # Acronyms
        ]
        
        entities = []
        for pattern in concept_patterns:
            matches = re.finditer(pattern, query)
            for match in matches:
                entity = QueryEntity(
                    text=match.group(),
                    label='CONCEPT',
                    start=match.start(),
                    end=match.end(),
                    confidence=0.6
                )
                entities.append(entity)
        
        return entities
    
    def _deduplicate_entities(self, entities: List[QueryEntity]) -> List[QueryEntity]:
        """Remove duplicate entities, keeping the highest confidence."""
        entity_map = {}
        
        for entity in entities:
            key = (entity.text.lower(), entity.label)
            if key not in entity_map or entity.confidence > entity_map[key].confidence:
                entity_map[key] = entity
        
        return list(entity_map.values())
    
    def _enrich_entities(self, entities: List[QueryEntity], context: QueryContext) -> List[QueryEntity]:
        """Enrich entities with synonyms and related terms."""
        for entity in entities:
            # Add context-based enrichment
            if context.domain and entity.label == 'CONCEPT':
                # Look up domain-specific synonyms
                domain_terms = self.domain_entities.get(context.domain, {})
                if entity.text.lower() in domain_terms:
                    term_info = domain_terms[entity.text.lower()]
                    entity.synonyms.extend(term_info.get('synonyms', []))
                    entity.related_terms.extend(term_info.get('related', []))
        
        return entities
    
    def _load_domain_entities(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Load domain-specific entity dictionaries."""
        return {
            'technical': {
                'machine learning': {
                    'type': 'CONCEPT',
                    'confidence': 0.95,
                    'synonyms': ['ml', 'artificial intelligence', 'ai'],
                    'related': ['neural networks', 'deep learning', 'algorithms']
                },
                'neural network': {
                    'type': 'CONCEPT',
                    'confidence': 0.95,
                    'synonyms': ['nn', 'artificial neural network'],
                    'related': ['deep learning', 'backpropagation', 'layers']
                },
                'database': {
                    'type': 'CONCEPT',
                    'confidence': 0.9,
                    'synonyms': ['db', 'data store', 'repository'],
                    'related': ['sql', 'nosql', 'queries', 'indexing']
                }
            },
            'medical': {
                'cardiovascular': {
                    'type': 'MEDICAL_CONCEPT',
                    'confidence': 0.95,
                    'synonyms': ['cardiac', 'heart-related'],
                    'related': ['heart', 'blood vessels', 'circulation']
                }
            },
            'legal': {
                'contract': {
                    'type': 'LEGAL_CONCEPT',
                    'confidence': 0.95,
                    'synonyms': ['agreement', 'legal document'],
                    'related': ['terms', 'conditions', 'obligations']
                }
            }
        }


class IntentClassifier:
    """Classifies query intent using pattern matching and ML."""
    
    def __init__(self):
        self.intent_patterns = self._load_intent_patterns()
        self.ml_classifier = None
        self._ml_initialized = False
        # ML classifier loading is now lazy - happens on first use, not in __init__
        logger.info("IntentClassifier created (ML model will load on first use)")
    
    def _ensure_ml_loaded(self):
        """Lazily initialize ML-based intent classifier on first use.
        
        NOTE: ML classifier loading is DISABLED because:
        1. The _classify_by_ml() method is a placeholder that returns default values
        2. Loading transformers pipeline blocks the event loop for 30+ seconds
        3. This causes server freezes when health monitoring starts
        
        If ML-based intent classification is needed in the future, it should:
        - Use the model server for inference
        - Or run in a thread pool executor
        """
        if self._ml_initialized:
            return
        
        self._ml_initialized = True
        # DISABLED: ML classifier loading blocks the event loop
        # The _classify_by_ml() method is a placeholder anyway
        logger.info("ML intent classifier disabled (placeholder implementation)")
        self.ml_classifier = None
    
    def classify_intent(self, query: str, entities: List[QueryEntity]) -> Tuple[QueryIntent, float]:
        """
        Classify query intent.
        
        Args:
            query: Query text
            entities: Extracted entities
            
        Returns:
            Tuple of (intent, confidence)
        """
        # Pattern-based classification
        pattern_intent, pattern_confidence = self._classify_by_patterns(query)
        
        # ML-based classification (if available)
        ml_intent, ml_confidence = self._classify_by_ml(query)
        
        # Entity-based hints
        entity_intent, entity_confidence = self._classify_by_entities(entities)
        
        # Combine classifications
        final_intent, final_confidence = self._combine_classifications([
            (pattern_intent, pattern_confidence),
            (ml_intent, ml_confidence),
            (entity_intent, entity_confidence)
        ])
        
        return final_intent, final_confidence
    
    def _classify_by_patterns(self, query: str) -> Tuple[QueryIntent, float]:
        """Classify intent using pattern matching."""
        query_lower = query.lower()
        
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return QueryIntent(intent), 0.8
        
        # Default to factual if no pattern matches
        return QueryIntent.FACTUAL, 0.3
    
    def _classify_by_ml(self, query: str) -> Tuple[QueryIntent, float]:
        """Classify intent using ML model."""
        # Lazy load the ML classifier on first use
        self._ensure_ml_loaded()
        
        if not self.ml_classifier:
            return QueryIntent.FACTUAL, 0.0
        
        try:
            # This is a placeholder - in practice, you'd use a model trained on intent data
            # For now, return default
            return QueryIntent.FACTUAL, 0.5
        except Exception as e:
            logger.error(f"ML intent classification failed: {e}")
            return QueryIntent.FACTUAL, 0.0
    
    def _classify_by_entities(self, entities: List[QueryEntity]) -> Tuple[QueryIntent, float]:
        """Classify intent based on extracted entities."""
        # Simple heuristics based on entity types
        entity_types = [entity.label for entity in entities]
        
        if 'DATE' in entity_types or 'TIME' in entity_types:
            return QueryIntent.TEMPORAL, 0.6
        elif 'GPE' in entity_types or 'LOC' in entity_types:  # Geopolitical entity, Location
            return QueryIntent.LOCATIONAL, 0.6
        elif 'QUANTITY' in entity_types or 'PERCENT' in entity_types:
            return QueryIntent.QUANTITATIVE, 0.6
        elif len([e for e in entities if e.label == 'CONCEPT']) >= 2:
            return QueryIntent.COMPARATIVE, 0.5
        
        return QueryIntent.FACTUAL, 0.3
    
    def _combine_classifications(self, classifications: List[Tuple[QueryIntent, float]]) -> Tuple[QueryIntent, float]:
        """Combine multiple intent classifications."""
        # Weighted voting
        intent_scores = {}
        total_weight = 0
        
        for intent, confidence in classifications:
            if confidence > 0:
                intent_scores[intent] = intent_scores.get(intent, 0) + confidence
                total_weight += confidence
        
        if not intent_scores:
            return QueryIntent.FACTUAL, 0.3
        
        # Get highest scoring intent
        best_intent = max(intent_scores.items(), key=lambda x: x[1])
        final_confidence = best_intent[1] / total_weight if total_weight > 0 else 0.3
        
        return best_intent[0], final_confidence
    
    def _load_intent_patterns(self) -> Dict[str, List[str]]:
        """Load regex patterns for intent classification."""
        return {
            'factual': [
                r'\bwhat\s+is\b', r'\bdefine\b', r'\bexplain\b', r'\btell\s+me\s+about\b'
            ],
            'procedural': [
                r'\bhow\s+to\b', r'\bsteps\s+to\b', r'\bprocess\s+of\b', r'\bmethod\s+for\b'
            ],
            'comparative': [
                r'\bcompare\b', r'\bdifference\s+between\b', r'\bvs\b', r'\bversus\b',
                r'\bbetter\s+than\b', r'\bsimilar\s+to\b'
            ],
            'causal': [
                r'\bwhy\s+does\b', r'\bwhat\s+causes\b', r'\breason\s+for\b', r'\bbecause\s+of\b'
            ],
            'temporal': [
                r'\bwhen\s+did\b', r'\btimeline\s+of\b', r'\bhistory\s+of\b', r'\bchronology\b'
            ],
            'locational': [
                r'\bwhere\s+is\b', r'\blocation\s+of\b', r'\bfind\s+in\b', r'\bgeography\b'
            ],
            'quantitative': [
                r'\bhow\s+many\b', r'\bhow\s+much\b', r'\bpercentage\s+of\b', r'\bnumber\s+of\b'
            ],
            'analytical': [
                r'\banalyze\b', r'\bevaluate\b', r'\bassess\b', r'\bexamine\b'
            ]
        }


class ComplexityAnalyzer:
    """Analyzes query complexity for search strategy optimization."""
    
    def analyze_complexity(self, query: str, entities: List[QueryEntity], relations: List[QueryRelation]) -> Tuple[QueryComplexity, float]:
        """
        Analyze query complexity.
        
        Args:
            query: Query text
            entities: Extracted entities
            relations: Extracted relations
            
        Returns:
            Tuple of (complexity level, confidence)
        """
        complexity_score = 0
        
        # Length-based complexity
        word_count = len(query.split())
        if word_count > 20:
            complexity_score += 2
        elif word_count > 10:
            complexity_score += 1
        
        # Entity-based complexity
        entity_count = len(entities)
        if entity_count > 5:
            complexity_score += 2
        elif entity_count > 2:
            complexity_score += 1
        
        # Relation-based complexity
        relation_count = len(relations)
        complexity_score += min(relation_count, 3)
        
        # Pattern-based complexity indicators
        complex_patterns = [
            r'\band\b.*\band\b',  # Multiple AND conditions
            r'\bor\b.*\bor\b',    # Multiple OR conditions
            r'\bbut\b.*\bhowever\b',  # Contrasting ideas
            r'\bif\b.*\bthen\b',  # Conditional logic
            r'\bnot\s+only\b.*\bbut\s+also\b'  # Complex structures
        ]
        
        for pattern in complex_patterns:
            if re.search(pattern, query.lower()):
                complexity_score += 1
        
        # Multi-hop indicators
        multi_hop_patterns = [
            r'\brelationship\s+between\b',
            r'\bconnection\s+between\b',
            r'\bimpact\s+of\b.*\bon\b',
            r'\beffect\s+of\b.*\bon\b'
        ]
        
        for pattern in multi_hop_patterns:
            if re.search(pattern, query.lower()):
                complexity_score += 2
        
        # Determine complexity level
        if complexity_score >= 6:
            return QueryComplexity.MULTI_HOP, 0.9
        elif complexity_score >= 4:
            return QueryComplexity.COMPLEX, 0.8
        elif complexity_score >= 2:
            return QueryComplexity.MODERATE, 0.7
        else:
            return QueryComplexity.SIMPLE, 0.8


class QueryUnderstandingEngine:
    """
    Main engine for comprehensive query understanding.
    
    Combines entity extraction, intent classification, complexity analysis,
    and context processing to create a complete understanding of user queries.
    """
    
    def __init__(self):
        self.entity_extractor = EntityExtractor()
        self.intent_classifier = IntentClassifier()
        self.complexity_analyzer = ComplexityAnalyzer()
        
        logger.info("Query understanding engine initialized")
    
    async def understand_query(
        self,
        query: str,
        context: Optional[QueryContext] = None
    ) -> UnderstoodQuery:
        """
        Perform comprehensive query understanding.
        
        Args:
            query: User query text
            context: Optional context information
            
        Returns:
            Complete query understanding result
        """
        if context is None:
            context = QueryContext()
        
        # Normalize query
        normalized_query = self._normalize_query(query)
        
        # Extract entities
        entities = self.entity_extractor.extract_entities(normalized_query, context)
        
        # Extract relations (simplified for now)
        relations = self._extract_relations(normalized_query, entities)
        
        # Classify intent
        intent, intent_confidence = self.intent_classifier.classify_intent(normalized_query, entities)
        
        # Analyze complexity
        complexity, complexity_confidence = self.complexity_analyzer.analyze_complexity(
            normalized_query, entities, relations
        )
        
        # Extract key concepts
        key_concepts = self._extract_key_concepts(entities, relations)
        
        # Determine search strategy
        search_strategy = self._determine_search_strategy(intent, complexity, entities)
        
        # Generate query expansions
        suggested_expansions = self._generate_expansions(normalized_query, entities, context)
        
        # Calculate overall confidence
        overall_confidence = (intent_confidence + complexity_confidence) / 2
        
        # Create explanation
        explanation = self._generate_explanation(intent, complexity, entities, search_strategy)
        
        return UnderstoodQuery(
            original_query=query,
            normalized_query=normalized_query,
            intent=intent,
            complexity=complexity,
            entities=entities,
            relations=relations,
            key_concepts=key_concepts,
            context=context,
            confidence=overall_confidence,
            suggested_expansions=suggested_expansions,
            search_strategy=search_strategy,
            explanation=explanation
        )
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query text."""
        # Basic normalization
        normalized = query.strip()
        normalized = re.sub(r'\s+', ' ', normalized)  # Multiple spaces to single
        normalized = re.sub(r'[^\w\s\-\?\!]', '', normalized)  # Remove special chars except basic punctuation
        
        return normalized
    
    def _extract_relations(self, query: str, entities: List[QueryEntity]) -> List[QueryRelation]:
        """Extract relationships between entities (simplified)."""
        relations = []
        
        # Simple pattern-based relation extraction
        relation_patterns = [
            (r'(\w+)\s+is\s+a\s+(\w+)', 'is_a'),
            (r'(\w+)\s+causes\s+(\w+)', 'causes'),
            (r'(\w+)\s+affects\s+(\w+)', 'affects'),
            (r'(\w+)\s+includes\s+(\w+)', 'includes'),
            (r'(\w+)\s+requires\s+(\w+)', 'requires')
        ]
        
        for pattern, predicate in relation_patterns:
            matches = re.finditer(pattern, query.lower())
            for match in matches:
                relation = QueryRelation(
                    subject=match.group(1),
                    predicate=predicate,
                    object=match.group(2),
                    confidence=0.7
                )
                relations.append(relation)
        
        return relations
    
    def _extract_key_concepts(self, entities: List[QueryEntity], relations: List[QueryRelation]) -> List[str]:
        """Extract key concepts from entities and relations."""
        concepts = set()
        
        # Add entity texts as concepts
        for entity in entities:
            if entity.label in ['CONCEPT', 'ORG', 'PRODUCT']:
                concepts.add(entity.text.lower())
        
        # Add relation subjects and objects
        for relation in relations:
            concepts.add(relation.subject.lower())
            concepts.add(relation.object.lower())
        
        return list(concepts)
    
    def _determine_search_strategy(
        self,
        intent: QueryIntent,
        complexity: QueryComplexity,
        entities: List[QueryEntity]
    ) -> str:
        """Determine optimal search strategy based on query understanding."""
        
        # Multi-hop queries benefit from knowledge graph search
        if complexity == QueryComplexity.MULTI_HOP:
            return "knowledge_graph"
        
        # Factual queries with many entities work well with hybrid search
        if intent == QueryIntent.FACTUAL and len(entities) > 2:
            return "hybrid"
        
        # Procedural queries often need keyword matching
        if intent == QueryIntent.PROCEDURAL:
            return "keyword"
        
        # Complex comparative queries benefit from vector search
        if intent == QueryIntent.COMPARATIVE and complexity in [QueryComplexity.COMPLEX, QueryComplexity.MODERATE]:
            return "vector"
        
        # Default to hybrid search
        return "hybrid"
    
    def _generate_expansions(
        self,
        query: str,
        entities: List[QueryEntity],
        context: QueryContext
    ) -> List[str]:
        """Generate query expansion suggestions."""
        expansions = []
        
        # Add entity synonyms
        for entity in entities:
            for synonym in entity.synonyms[:2]:  # Top 2 synonyms
                expanded = query.replace(entity.text, synonym)
                if expanded != query:
                    expansions.append(expanded)
        
        # Add related terms
        for entity in entities:
            for related in entity.related_terms[:1]:  # Top related term
                expansions.append(f"{query} {related}")
        
        # Domain-specific expansions
        if context.domain:
            domain_expansion = f"{query} {context.domain}"
            expansions.append(domain_expansion)
        
        return expansions[:5]  # Limit to top 5 expansions
    
    def _generate_explanation(
        self,
        intent: QueryIntent,
        complexity: QueryComplexity,
        entities: List[QueryEntity],
        search_strategy: str
    ) -> str:
        """Generate human-readable explanation of query understanding."""
        
        explanation_parts = [
            f"Intent: {intent.value}",
            f"Complexity: {complexity.value}",
            f"Entities: {len(entities)}",
            f"Strategy: {search_strategy}"
        ]
        
        if entities:
            entity_types = list(set(e.label for e in entities))
            explanation_parts.append(f"Entity types: {', '.join(entity_types)}")
        
        return " | ".join(explanation_parts)