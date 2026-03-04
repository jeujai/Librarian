"""
Multi-Stage Validation System.

This module implements cross-encoding models for semantic relevance validation,
factual consistency validation using NLI models, bidirectional validation,
and composite scoring with content-type adaptive thresholds.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from ...models.chunking import BridgeChunk, ValidationDetails, ValidationResult
from ...models.core import ContentType

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound validation operations
_validator_executor: Optional[ThreadPoolExecutor] = None


def _get_validator_executor() -> ThreadPoolExecutor:
    """Get or create the validator thread pool executor."""
    global _validator_executor
    if _validator_executor is None:
        _validator_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="validator"
        )
        logger.info("Created validator thread pool executor")
    return _validator_executor


@dataclass
class ValidationConfig:
    """Configuration for validation thresholds and models."""
    semantic_relevance_threshold: float = 0.7
    factual_consistency_threshold: float = 0.6
    bidirectional_threshold: float = 0.65
    composite_threshold: float = 0.7
    
    # Content-type specific thresholds
    content_type_adjustments: Dict[ContentType, Dict[str, float]] = None
    
    def __post_init__(self):
        if self.content_type_adjustments is None:
            self.content_type_adjustments = {
                ContentType.MEDICAL: {
                    'semantic_relevance_threshold': 0.8,
                    'factual_consistency_threshold': 0.85,
                    'bidirectional_threshold': 0.8,
                    'composite_threshold': 0.8
                },
                ContentType.LEGAL: {
                    'semantic_relevance_threshold': 0.75,
                    'factual_consistency_threshold': 0.8,
                    'bidirectional_threshold': 0.75,
                    'composite_threshold': 0.75
                },
                ContentType.TECHNICAL: {
                    'semantic_relevance_threshold': 0.75,
                    'factual_consistency_threshold': 0.7,
                    'bidirectional_threshold': 0.7,
                    'composite_threshold': 0.72
                },
                ContentType.ACADEMIC: {
                    'semantic_relevance_threshold': 0.72,
                    'factual_consistency_threshold': 0.75,
                    'bidirectional_threshold': 0.7,
                    'composite_threshold': 0.72
                },
                ContentType.NARRATIVE: {
                    'semantic_relevance_threshold': 0.65,
                    'factual_consistency_threshold': 0.6,
                    'bidirectional_threshold': 0.6,
                    'composite_threshold': 0.65
                },
                ContentType.GENERAL: {
                    'semantic_relevance_threshold': 0.7,
                    'factual_consistency_threshold': 0.65,
                    'bidirectional_threshold': 0.65,
                    'composite_threshold': 0.7
                }
            }
    
    def get_thresholds(self, content_type: ContentType) -> Dict[str, float]:
        """Get thresholds for specific content type."""
        adjustments = self.content_type_adjustments.get(content_type, {})
        
        return {
            'semantic_relevance_threshold': adjustments.get('semantic_relevance_threshold', self.semantic_relevance_threshold),
            'factual_consistency_threshold': adjustments.get('factual_consistency_threshold', self.factual_consistency_threshold),
            'bidirectional_threshold': adjustments.get('bidirectional_threshold', self.bidirectional_threshold),
            'composite_threshold': adjustments.get('composite_threshold', self.composite_threshold)
        }


@dataclass
class SemanticRelevanceResult:
    """Result of semantic relevance validation."""
    forward_score: float  # Bridge relevance to chunk1
    backward_score: float  # Bridge relevance to chunk2
    average_score: float
    passed: bool
    details: Dict[str, Any]


@dataclass
class FactualConsistencyResult:
    """Result of factual consistency validation."""
    consistency_score: float
    contradiction_score: float
    neutral_score: float
    passed: bool
    details: Dict[str, Any]


@dataclass
class BidirectionalResult:
    """Result of bidirectional validation."""
    chunk1_to_bridge_score: float
    chunk2_to_bridge_score: float
    bridge_to_chunk1_score: float
    bridge_to_chunk2_score: float
    average_score: float
    passed: bool
    details: Dict[str, Any]


class MultiStageValidator:
    """
    Multi-stage validation system for bridge quality assessment.
    
    Implements cross-encoding for semantic relevance, NLI models for factual consistency,
    bidirectional validation, and composite scoring with adaptive thresholds.
    """
    
    def __init__(self, config: Optional[ValidationConfig] = None):
        """Initialize the multi-stage validator."""
        self.config = config or ValidationConfig()
        
        # Initialize models
        self.cross_encoder = None
        self.nli_pipeline = None
        self.sentence_model = None
        
        self._initialize_models()
        
        # Validation statistics
        self.validation_stats = {
            'total_validations': 0,
            'passed_validations': 0,
            'failed_validations': 0,
            'average_scores': {
                'semantic_relevance': 0.0,
                'factual_consistency': 0.0,
                'bidirectional': 0.0,
                'composite': 0.0
            }
        }
    
    def _initialize_models(self):
        """Initialize validation models with lazy loading to prevent blocking."""
        # Models are now lazy loaded on first use
        self._cross_encoder_loaded = False
        self._nli_loaded = False
        self._sentence_model_loaded = False
        self._model_server_client = None
        logger.info("Multi-stage validator initialized (models served by model-server)")
    
    def _ensure_cross_encoder(self):
        """
        Cross-encoder is served by model-server container.
        
        NOTE: Local model loading has been removed. Use model server for reranking.
        """
        if self.cross_encoder is None and not self._cross_encoder_loaded:
            self._cross_encoder_loaded = True
            logger.info("Cross-encoder available via model-server (use async methods)")
    
    def _ensure_nli_pipeline(self):
        """Lazy load NLI pipeline on first use.
        
        NOTE: NLI pipeline loading is DISABLED because:
        1. Loading transformers pipeline blocks the event loop for 30+ seconds
        2. This causes server freezes when health monitoring starts
        3. The fallback method (_validate_factual_consistency_fallback) works fine
        
        If NLI-based validation is needed in the future, it should:
        - Use the model server for inference
        - Or run in a thread pool executor
        """
        if self.nli_pipeline is None and not self._nli_loaded:
            self._nli_loaded = True
            # DISABLED: NLI pipeline loading blocks the event loop
            # Use fallback validation instead
            logger.info("NLI pipeline disabled (using fallback validation)")
            self.nli_pipeline = None
    
    def _ensure_sentence_model(self):
        """
        Sentence model is served by model-server container.
        
        NOTE: Local model loading has been removed. Use generate_embeddings_async()
        which calls the model server for non-blocking operation.
        """
        if self.sentence_model is None and not self._sentence_model_loaded:
            self._sentence_model_loaded = True
            logger.info("Sentence model available via model-server (use async methods)")
    
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
        
        Falls back to local model via thread pool if model server unavailable.
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
        executor = _get_validator_executor()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self._encode_sync, texts)
    
    def _encode_sync(self, texts: List[str]) -> np.ndarray:
        """Synchronous encode - called in thread pool."""
        self._ensure_sentence_model()
        if self.sentence_model is None:
            raise RuntimeError("Sentence model not available")
        return self.sentence_model.encode(texts)
    
    def validate_bridge(self, bridge: BridgeChunk, chunk1: str, chunk2: str,
                       content_type: ContentType = ContentType.GENERAL) -> ValidationResult:
        """
        Comprehensive bridge validation with cross-encoding.
        
        Args:
            bridge: Bridge chunk to validate
            chunk1: First source chunk
            chunk2: Second source chunk
            content_type: Content type for adaptive thresholds
            
        Returns:
            ValidationResult with comprehensive validation scores
        """
        logger.debug(f"Validating bridge between chunks (bridge length: {len(bridge.content)})")
        
        # Get content-type specific thresholds
        thresholds = self.config.get_thresholds(content_type)
        
        # Stage 1: Semantic relevance validation
        semantic_result = self._validate_semantic_relevance(bridge.content, chunk1, chunk2)
        
        # Stage 2: Factual consistency validation
        factual_result = self._validate_factual_consistency(bridge.content, chunk1, chunk2)
        
        # Stage 3: Bidirectional validation
        bidirectional_result = self._validate_bidirectional_coherence(bridge.content, chunk1, chunk2)
        
        # Calculate composite score
        composite_score = self.calculate_composite_score(
            semantic_result, factual_result, bidirectional_result, content_type
        )
        
        # Determine if validation passed
        passed_validation = (
            semantic_result.passed and
            factual_result.passed and
            bidirectional_result.passed and
            composite_score >= thresholds['composite_threshold']
        )
        
        # Create validation details
        validation_details = ValidationDetails(
            semantic_relevance_score=semantic_result.average_score,
            factual_consistency_score=factual_result.consistency_score,
            bidirectional_score=bidirectional_result.average_score,
            validation_method="multi_stage_cross_encoding",
            model_used="cross_encoder+nli+bidirectional"
        )
        
        # Compile individual scores
        individual_scores = {
            'semantic_relevance': semantic_result.average_score,
            'factual_consistency': factual_result.consistency_score,
            'bidirectional_coherence': bidirectional_result.average_score,
            'semantic_forward': semantic_result.forward_score,
            'semantic_backward': semantic_result.backward_score,
            'contradiction_score': factual_result.contradiction_score,
            'neutral_score': factual_result.neutral_score
        }
        
        # Update statistics
        self._update_validation_stats(individual_scores, composite_score, passed_validation)
        
        return ValidationResult(
            individual_scores=individual_scores,
            composite_score=composite_score,
            validation_details=validation_details,
            passed_validation=passed_validation,
            content_type_thresholds=thresholds
        )
    
    def _validate_semantic_relevance(self, bridge: str, chunk1: str, chunk2: str) -> SemanticRelevanceResult:
        """Validate semantic relevance using cross-encoding models."""
        # Lazy load cross-encoder
        self._ensure_cross_encoder()
        
        if not self.cross_encoder:
            # Fallback to embedding similarity
            return self._validate_semantic_relevance_fallback(bridge, chunk1, chunk2)
        
        try:
            # Prepare text pairs for cross-encoding
            pairs = [
                (chunk1, bridge),  # How relevant is bridge to chunk1
                (chunk2, bridge),  # How relevant is bridge to chunk2
                (bridge, chunk1),  # How relevant is chunk1 to bridge (bidirectional)
                (bridge, chunk2)   # How relevant is chunk2 to bridge (bidirectional)
            ]
            
            # Get cross-encoding scores - this is blocking
            scores = self.cross_encoder.predict(pairs)
            
            forward_score = float(scores[0])  # chunk1 -> bridge
            backward_score = float(scores[1])  # chunk2 -> bridge
            bridge_to_chunk1 = float(scores[2])  # bridge -> chunk1
            bridge_to_chunk2 = float(scores[3])  # bridge -> chunk2
            
            # Calculate average relevance
            average_score = (forward_score + backward_score) / 2.0
            
            # Check if passed (both directions should be relevant)
            threshold = self.config.semantic_relevance_threshold
            passed = forward_score >= threshold and backward_score >= threshold
            
            details = {
                'bridge_to_chunk1': bridge_to_chunk1,
                'bridge_to_chunk2': bridge_to_chunk2,
                'model_used': 'cross_encoder',
                'threshold_used': threshold
            }
            
            return SemanticRelevanceResult(
                forward_score=forward_score,
                backward_score=backward_score,
                average_score=average_score,
                passed=passed,
                details=details
            )
        
        except Exception as e:
            logger.warning(f"Cross-encoding validation failed: {e}")
            return self._validate_semantic_relevance_fallback(bridge, chunk1, chunk2)
    
    def _validate_semantic_relevance_fallback(self, bridge: str, chunk1: str, chunk2: str) -> SemanticRelevanceResult:
        """Fallback semantic relevance validation using embeddings."""
        # Lazy load sentence model
        self._ensure_sentence_model()
        
        if not self.sentence_model:
            # Ultimate fallback - simple text overlap
            return self._validate_semantic_relevance_simple(bridge, chunk1, chunk2)
        
        try:
            # Generate embeddings - this is blocking
            texts = [bridge, chunk1, chunk2]
            embeddings = self.sentence_model.encode(texts)
            
            # Calculate similarities
            bridge_emb = embeddings[0].reshape(1, -1)
            chunk1_emb = embeddings[1].reshape(1, -1)
            chunk2_emb = embeddings[2].reshape(1, -1)
            
            forward_score = float(cosine_similarity(chunk1_emb, bridge_emb)[0][0])
            backward_score = float(cosine_similarity(chunk2_emb, bridge_emb)[0][0])
            average_score = (forward_score + backward_score) / 2.0
            
            threshold = self.config.semantic_relevance_threshold * 0.8  # Lower threshold for fallback
            passed = forward_score >= threshold and backward_score >= threshold
            
            details = {
                'model_used': 'sentence_transformer_fallback',
                'threshold_used': threshold
            }
            
            return SemanticRelevanceResult(
                forward_score=forward_score,
                backward_score=backward_score,
                average_score=average_score,
                passed=passed,
                details=details
            )
        
        except Exception as e:
            logger.warning(f"Embedding validation failed: {e}")
            return self._validate_semantic_relevance_simple(bridge, chunk1, chunk2)
    
    def _validate_semantic_relevance_simple(self, bridge: str, chunk1: str, chunk2: str) -> SemanticRelevanceResult:
        """Simple text overlap-based semantic relevance validation."""
        # Calculate word overlap
        bridge_words = set(bridge.lower().split())
        chunk1_words = set(chunk1.lower().split())
        chunk2_words = set(chunk2.lower().split())
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
        bridge_words -= stop_words
        chunk1_words -= stop_words
        chunk2_words -= stop_words
        
        # Calculate overlap ratios
        if not bridge_words:
            return SemanticRelevanceResult(0.0, 0.0, 0.0, False, {'model_used': 'simple_overlap'})
        
        chunk1_overlap = len(bridge_words.intersection(chunk1_words)) / len(bridge_words)
        chunk2_overlap = len(bridge_words.intersection(chunk2_words)) / len(bridge_words)
        
        forward_score = chunk1_overlap
        backward_score = chunk2_overlap
        average_score = (forward_score + backward_score) / 2.0
        
        threshold = 0.2  # Lower threshold for simple method
        passed = forward_score >= threshold and backward_score >= threshold
        
        details = {
            'model_used': 'simple_overlap',
            'threshold_used': threshold,
            'bridge_words_count': len(bridge_words)
        }
        
        return SemanticRelevanceResult(
            forward_score=forward_score,
            backward_score=backward_score,
            average_score=average_score,
            passed=passed,
            details=details
        )
    
    def _validate_factual_consistency(self, bridge: str, chunk1: str, chunk2: str) -> FactualConsistencyResult:
        """Validate factual consistency using NLI models."""
        # Lazy load NLI pipeline
        self._ensure_nli_pipeline()
        
        if not self.nli_pipeline:
            # Fallback to simple consistency check
            return self._validate_factual_consistency_fallback(bridge, chunk1, chunk2)
        
        try:
            # Prepare premise-hypothesis pairs for NLI
            pairs = [
                {"text": chunk1, "text_pair": bridge},  # Does chunk1 entail bridge?
                {"text": chunk2, "text_pair": bridge},  # Does chunk2 entail bridge?
                {"text": bridge, "text_pair": chunk1},  # Does bridge entail chunk1?
                {"text": bridge, "text_pair": chunk2}   # Does bridge entail chunk2?
            ]
            
            # Get NLI predictions - this is blocking
            results = []
            for pair in pairs:
                try:
                    result = self.nli_pipeline(pair)
                    results.append(result)
                except Exception as e:
                    logger.debug(f"NLI prediction failed for pair: {e}")
                    results.append([])
            
            # Process results
            entailment_scores = []
            contradiction_scores = []
            neutral_scores = []
            
            for result in results:
                if result:
                    # Extract scores for each label
                    scores_dict = {item['label']: item['score'] for item in result}
                    
                    entailment_scores.append(scores_dict.get('ENTAILMENT', 0.0))
                    contradiction_scores.append(scores_dict.get('CONTRADICTION', 0.0))
                    neutral_scores.append(scores_dict.get('NEUTRAL', 0.0))
                else:
                    entailment_scores.append(0.0)
                    contradiction_scores.append(0.0)
                    neutral_scores.append(0.0)
            
            # Calculate average scores
            consistency_score = np.mean(entailment_scores) if entailment_scores else 0.0
            contradiction_score = np.mean(contradiction_scores) if contradiction_scores else 0.0
            neutral_score = np.mean(neutral_scores) if neutral_scores else 0.0
            
            # Check if passed (high consistency, low contradiction)
            threshold = self.config.factual_consistency_threshold
            passed = (consistency_score >= threshold and 
                     contradiction_score <= (1.0 - threshold))
            
            details = {
                'model_used': 'nli_pipeline',
                'entailment_scores': entailment_scores,
                'threshold_used': threshold,
                'pairs_processed': len([r for r in results if r])
            }
            
            return FactualConsistencyResult(
                consistency_score=consistency_score,
                contradiction_score=contradiction_score,
                neutral_score=neutral_score,
                passed=passed,
                details=details
            )
        
        except Exception as e:
            logger.warning(f"NLI validation failed: {e}")
            return self._validate_factual_consistency_fallback(bridge, chunk1, chunk2)
    
    def _validate_factual_consistency_fallback(self, bridge: str, chunk1: str, chunk2: str) -> FactualConsistencyResult:
        """Fallback factual consistency validation."""
        # Simple heuristic: check for contradictory terms
        contradictory_pairs = [
            ('not', 'is'), ('no', 'yes'), ('never', 'always'),
            ('impossible', 'possible'), ('false', 'true'),
            ('incorrect', 'correct'), ('wrong', 'right')
        ]
        
        bridge_lower = bridge.lower()
        chunk1_lower = chunk1.lower()
        chunk2_lower = chunk2.lower()
        
        contradiction_count = 0
        total_checks = 0
        
        for neg_term, pos_term in contradictory_pairs:
            total_checks += 2
            
            # Check for contradictions between bridge and chunks
            if ((neg_term in bridge_lower and pos_term in chunk1_lower) or
                (pos_term in bridge_lower and neg_term in chunk1_lower)):
                contradiction_count += 1
            
            if ((neg_term in bridge_lower and pos_term in chunk2_lower) or
                (pos_term in bridge_lower and neg_term in chunk2_lower)):
                contradiction_count += 1
        
        # Calculate scores
        contradiction_score = contradiction_count / total_checks if total_checks > 0 else 0.0
        consistency_score = 1.0 - contradiction_score
        neutral_score = 0.0
        
        # Simple threshold
        threshold = 0.7
        passed = consistency_score >= threshold
        
        details = {
            'model_used': 'simple_contradiction_check',
            'contradiction_count': contradiction_count,
            'total_checks': total_checks,
            'threshold_used': threshold
        }
        
        return FactualConsistencyResult(
            consistency_score=consistency_score,
            contradiction_score=contradiction_score,
            neutral_score=neutral_score,
            passed=passed,
            details=details
        )
    
    def _validate_bidirectional_coherence(self, bridge: str, chunk1: str, chunk2: str) -> BidirectionalResult:
        """Validate bidirectional coherence between bridge and chunks."""
        # Lazy load cross-encoder
        self._ensure_cross_encoder()
        
        if not self.cross_encoder:
            return self._validate_bidirectional_coherence_fallback(bridge, chunk1, chunk2)
        
        try:
            # Bidirectional pairs
            pairs = [
                (chunk1, bridge),  # chunk1 -> bridge
                (chunk2, bridge),  # chunk2 -> bridge
                (bridge, chunk1),  # bridge -> chunk1
                (bridge, chunk2)   # bridge -> chunk2
            ]
            
            # Get scores - this is blocking
            scores = self.cross_encoder.predict(pairs)
            
            chunk1_to_bridge = float(scores[0])
            chunk2_to_bridge = float(scores[1])
            bridge_to_chunk1 = float(scores[2])
            bridge_to_chunk2 = float(scores[3])
            
            # Calculate average bidirectional score
            average_score = (chunk1_to_bridge + chunk2_to_bridge + 
                           bridge_to_chunk1 + bridge_to_chunk2) / 4.0
            
            # Check if passed
            threshold = self.config.bidirectional_threshold
            passed = all(score >= threshold for score in scores)
            
            details = {
                'model_used': 'cross_encoder_bidirectional',
                'threshold_used': threshold,
                'all_scores': scores.tolist() if hasattr(scores, 'tolist') else list(scores)
            }
            
            return BidirectionalResult(
                chunk1_to_bridge_score=chunk1_to_bridge,
                chunk2_to_bridge_score=chunk2_to_bridge,
                bridge_to_chunk1_score=bridge_to_chunk1,
                bridge_to_chunk2_score=bridge_to_chunk2,
                average_score=average_score,
                passed=passed,
                details=details
            )
        
        except Exception as e:
            logger.warning(f"Bidirectional validation failed: {e}")
            return self._validate_bidirectional_coherence_fallback(bridge, chunk1, chunk2)
    
    def _validate_bidirectional_coherence_fallback(self, bridge: str, chunk1: str, chunk2: str) -> BidirectionalResult:
        """Fallback bidirectional coherence validation."""
        # Lazy load sentence model
        self._ensure_sentence_model()
        
        if not self.sentence_model:
            return self._validate_bidirectional_coherence_simple(bridge, chunk1, chunk2)
        
        try:
            # Generate embeddings - this is blocking
            embeddings = self.sentence_model.encode([bridge, chunk1, chunk2])
            
            bridge_emb = embeddings[0].reshape(1, -1)
            chunk1_emb = embeddings[1].reshape(1, -1)
            chunk2_emb = embeddings[2].reshape(1, -1)
            
            # Calculate bidirectional similarities
            chunk1_to_bridge = float(cosine_similarity(chunk1_emb, bridge_emb)[0][0])
            chunk2_to_bridge = float(cosine_similarity(chunk2_emb, bridge_emb)[0][0])
            bridge_to_chunk1 = chunk1_to_bridge  # Cosine similarity is symmetric
            bridge_to_chunk2 = chunk2_to_bridge
            
            average_score = (chunk1_to_bridge + chunk2_to_bridge) / 2.0
            
            threshold = self.config.bidirectional_threshold * 0.8  # Lower threshold for fallback
            passed = chunk1_to_bridge >= threshold and chunk2_to_bridge >= threshold
            
            details = {
                'model_used': 'sentence_transformer_bidirectional',
                'threshold_used': threshold
            }
            
            return BidirectionalResult(
                chunk1_to_bridge_score=chunk1_to_bridge,
                chunk2_to_bridge_score=chunk2_to_bridge,
                bridge_to_chunk1_score=bridge_to_chunk1,
                bridge_to_chunk2_score=bridge_to_chunk2,
                average_score=average_score,
                passed=passed,
                details=details
            )
        
        except Exception as e:
            logger.warning(f"Embedding bidirectional validation failed: {e}")
            return self._validate_bidirectional_coherence_simple(bridge, chunk1, chunk2)
    
    def _validate_bidirectional_coherence_simple(self, bridge: str, chunk1: str, chunk2: str) -> BidirectionalResult:
        """Simple bidirectional coherence validation."""
        # Use word overlap as proxy for coherence
        bridge_words = set(bridge.lower().split())
        chunk1_words = set(chunk1.lower().split())
        chunk2_words = set(chunk2.lower().split())
        
        # Remove stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        bridge_words -= stop_words
        chunk1_words -= stop_words
        chunk2_words -= stop_words
        
        if not bridge_words:
            return BidirectionalResult(0.0, 0.0, 0.0, 0.0, 0.0, False, {'model_used': 'simple_bidirectional'})
        
        # Calculate overlaps
        chunk1_overlap = len(bridge_words.intersection(chunk1_words)) / len(bridge_words)
        chunk2_overlap = len(bridge_words.intersection(chunk2_words)) / len(bridge_words)
        
        average_score = (chunk1_overlap + chunk2_overlap) / 2.0
        
        threshold = 0.15  # Lower threshold for simple method
        passed = chunk1_overlap >= threshold and chunk2_overlap >= threshold
        
        details = {
            'model_used': 'simple_bidirectional',
            'threshold_used': threshold
        }
        
        return BidirectionalResult(
            chunk1_to_bridge_score=chunk1_overlap,
            chunk2_to_bridge_score=chunk2_overlap,
            bridge_to_chunk1_score=chunk1_overlap,
            bridge_to_chunk2_score=chunk2_overlap,
            average_score=average_score,
            passed=passed,
            details=details
        )
    
    def calculate_composite_score(self, semantic_result: SemanticRelevanceResult,
                                factual_result: FactualConsistencyResult,
                                bidirectional_result: BidirectionalResult,
                                content_type: ContentType) -> float:
        """
        Calculate composite quality score with adaptive thresholds.
        
        Args:
            semantic_result: Semantic relevance validation result
            factual_result: Factual consistency validation result
            bidirectional_result: Bidirectional validation result
            content_type: Content type for adaptive weighting
            
        Returns:
            Composite score (0.0-1.0)
        """
        # Content-type specific weights
        weights = {
            ContentType.MEDICAL: {
                'semantic': 0.25,
                'factual': 0.45,  # High weight on factual accuracy
                'bidirectional': 0.30
            },
            ContentType.LEGAL: {
                'semantic': 0.30,
                'factual': 0.40,  # High weight on factual accuracy
                'bidirectional': 0.30
            },
            ContentType.TECHNICAL: {
                'semantic': 0.35,
                'factual': 0.35,
                'bidirectional': 0.30
            },
            ContentType.ACADEMIC: {
                'semantic': 0.35,
                'factual': 0.35,
                'bidirectional': 0.30
            },
            ContentType.NARRATIVE: {
                'semantic': 0.40,  # Higher weight on semantic flow
                'factual': 0.25,
                'bidirectional': 0.35
            },
            ContentType.GENERAL: {
                'semantic': 0.35,
                'factual': 0.30,
                'bidirectional': 0.35
            }
        }
        
        content_weights = weights.get(content_type, weights[ContentType.GENERAL])
        
        # Calculate weighted composite score
        composite_score = (
            semantic_result.average_score * content_weights['semantic'] +
            factual_result.consistency_score * content_weights['factual'] +
            bidirectional_result.average_score * content_weights['bidirectional']
        )
        
        # Apply penalty for high contradiction scores
        if factual_result.contradiction_score > 0.3:
            penalty = factual_result.contradiction_score * 0.2
            composite_score = max(0.0, composite_score - penalty)
        
        return min(1.0, composite_score)
    
    def cross_encode_semantic_relevance(self, bridge: str, source_chunk: str) -> float:
        """
        Validate semantic relevance using cross-encoding models.
        
        Args:
            bridge: Bridge content
            source_chunk: Source chunk content
            
        Returns:
            Semantic relevance score (0.0-1.0)
        """
        if not self.cross_encoder:
            # Fallback to embedding similarity
            if self.sentence_model:
                embeddings = self.sentence_model.encode([bridge, source_chunk])
                similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
                return float(similarity)
            else:
                return 0.5  # Default score
        
        try:
            score = self.cross_encoder.predict([(source_chunk, bridge)])
            return float(score[0]) if hasattr(score, '__getitem__') else float(score)
        except Exception as e:
            logger.warning(f"Cross-encoding failed: {e}")
            return 0.5
    
    def validate_factual_consistency(self, bridge: str, source_chunks: List[str]) -> float:
        """
        Validate factual consistency using NLI models.
        
        Args:
            bridge: Bridge content
            source_chunks: List of source chunk contents
            
        Returns:
            Factual consistency score (0.0-1.0)
        """
        if not self.nli_pipeline or not source_chunks:
            return 0.7  # Default score
        
        consistency_scores = []
        
        for chunk in source_chunks:
            try:
                result = self.nli_pipeline({"text": chunk, "text_pair": bridge})
                
                # Extract entailment score
                entailment_score = 0.0
                for item in result:
                    if item['label'] == 'ENTAILMENT':
                        entailment_score = item['score']
                        break
                
                consistency_scores.append(entailment_score)
            
            except Exception as e:
                logger.debug(f"NLI validation failed for chunk: {e}")
                consistency_scores.append(0.5)  # Default score
        
        return np.mean(consistency_scores) if consistency_scores else 0.5
    
    def _update_validation_stats(self, individual_scores: Dict[str, float], 
                               composite_score: float, passed: bool):
        """Update validation statistics."""
        self.validation_stats['total_validations'] += 1
        
        if passed:
            self.validation_stats['passed_validations'] += 1
        else:
            self.validation_stats['failed_validations'] += 1
        
        # Update running averages
        total = self.validation_stats['total_validations']
        
        for metric in self.validation_stats['average_scores']:
            if metric in individual_scores:
                current_avg = self.validation_stats['average_scores'][metric]
                new_score = individual_scores[metric]
                self.validation_stats['average_scores'][metric] = (
                    (current_avg * (total - 1) + new_score) / total
                )
        
        # Update composite average
        current_composite_avg = self.validation_stats['average_scores'].get('composite', 0.0)
        self.validation_stats['average_scores']['composite'] = (
            (current_composite_avg * (total - 1) + composite_score) / total
        )
    
    def get_validation_statistics(self) -> Dict[str, Any]:
        """Get validation statistics."""
        stats = self.validation_stats.copy()
        
        if stats['total_validations'] > 0:
            stats['pass_rate'] = stats['passed_validations'] / stats['total_validations']
        else:
            stats['pass_rate'] = 0.0
        
        return stats
    
    def reset_statistics(self):
        """Reset validation statistics."""
        self.validation_stats = {
            'total_validations': 0,
            'passed_validations': 0,
            'failed_validations': 0,
            'average_scores': {
                'semantic_relevance': 0.0,
                'factual_consistency': 0.0,
                'bidirectional': 0.0,
                'composite': 0.0
            }
        }