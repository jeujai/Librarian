"""
Machine Learning Training API endpoints.

This module provides streaming access to chunked knowledge data for ML training,
including reinforcement learning training data, chunk sequences, and reward signals.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

# Import dependency injection for VectorStore
from ...api.dependencies.database import get_search_service, get_vector_store
from ...components.conversation.conversation_manager import ConversationManager
from ...components.vector_store.search_service import SemanticSearchService
from ...config import get_settings
from ...models.core import (
    ContentType,
    InteractionType,
    KnowledgeChunk,
    SequenceType,
    SourceType,
)
from ...models.ml_training import (
    BatchMetadata,
    ChunkFilters,
    ChunkSequence,
    InteractionFeedback,
    TrainingBatch,
    TrainingChunk,
    TrainingCriteria,
)
from ..middleware import get_request_id, get_user_id
from ..models import (
    APIResponse,
    ChunkFiltersModel,
    ChunkSequenceRequest,
    ChunkSequenceResponse,
    ErrorResponse,
    InteractionFeedbackRequest,
    InteractionFeedbackResponse,
    StreamChunksRequest,
    TrainingBatchRequest,
    TrainingBatchResponse,
    TrainingCriteriaModel,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ml")
settings = get_settings()

# Initialize components - USING DEPENDENCY INJECTION
# Components are now initialized via FastAPI dependencies
search_service = None
conversation_manager = None
_components_initialized = False
_components_lock = None

async def _get_ml_components():
    """
    Lazy initialization of ML training components using dependency injection.
    
    This function now uses FastAPI dependency injection for VectorStore
    instead of direct instantiation.
    """
    global search_service, conversation_manager, _components_initialized, _components_lock
    
    if _components_initialized:
        return search_service, conversation_manager
    
    # Initialize async lock if needed (use asyncio.Lock to avoid blocking event loop)
    if _components_lock is None:
        import asyncio
        _components_lock = asyncio.Lock()
    
    async with _components_lock:
        # Double-check after acquiring lock
        if _components_initialized:
            return search_service, conversation_manager
        
        try:
            # Use dependency injection for VectorStore and SearchService
            search_service = await get_search_service()
            conversation_manager = ConversationManager()
            
            logger.info("ML training components initialized successfully (lazy with DI)")
            
        except Exception as e:
            logger.warning(f"Could not initialize ML training components: {e}")
            search_service = None
            conversation_manager = None
        
        _components_initialized = True
        return search_service, conversation_manager

# In-memory storage for interaction feedback (in production, use database)
interaction_feedback_store: Dict[str, List[InteractionFeedback]] = {}
training_batch_registry: Dict[str, TrainingBatch] = {}


@router.post("/stream/chunks", response_class=StreamingResponse)
async def stream_knowledge_chunks(
    request: StreamChunksRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Stream knowledge chunks for RL training.
    
    Provides real-time or batch access to chunked knowledge data with filtering
    capabilities for different ML training scenarios.
    """
    try:
        # Lazy load components
        search_service, _ = _get_ml_components()
        
        if not search_service:
            raise HTTPException(
                status_code=503,
                detail="ML training service not available"
            )
        
        # Convert request filters to internal format
        filters = None
        if request.filters:
            filters = ChunkFilters(
                content_types=request.filters.content_types,
                source_types=request.filters.source_types,
                complexity_range=request.filters.complexity_range,
                temporal_range=request.filters.temporal_range,
                reward_threshold=request.filters.reward_threshold,
                interaction_threshold=request.filters.interaction_threshold
            )
        
        # Create streaming response
        if request.stream_format == "jsonl":
            media_type = "application/x-ndjson"
        else:
            media_type = "application/json"
        
        return StreamingResponse(
            stream_chunks_generator(filters, request.batch_size, request.stream_format),
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Content-Type": "streaming"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting chunk stream: {e}")
        raise HTTPException(status_code=500, detail="Failed to start chunk stream")


@router.post("/batch/training", response_model=TrainingBatchResponse)
async def get_training_batch(
    request: TrainingBatchRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Get batch of chunks with reward signals for ML training.
    
    Generates structured training batches with embeddings, metadata,
    and reward signals based on user interactions and feedback.
    """
    try:
        # Lazy load components
        search_service, _ = _get_ml_components()
        
        if not search_service:
            raise HTTPException(
                status_code=503,
                detail="ML training service not available"
            )
        
        # Convert request to internal format
        criteria = TrainingCriteria(
            batch_size=request.criteria.batch_size,
            include_sequences=request.criteria.include_sequences,
            sequence_length=request.criteria.sequence_length,
            balance_content_types=request.criteria.balance_content_types,
            balance_source_types=request.criteria.balance_source_types,
            reward_weighting=request.criteria.reward_weighting,
            temporal_weighting=request.criteria.temporal_weighting
        )
        
        filters = None
        if request.filters:
            filters = ChunkFilters(
                content_types=request.filters.content_types,
                source_types=request.filters.source_types,
                complexity_range=request.filters.complexity_range,
                temporal_range=request.filters.temporal_range,
                reward_threshold=request.filters.reward_threshold,
                interaction_threshold=request.filters.interaction_threshold
            )
        
        # Generate training batch
        training_batch = await generate_training_batch(criteria, filters)
        
        # Store batch in registry
        training_batch_registry[training_batch.batch_id] = training_batch
        
        logger.info(f"Generated training batch {training_batch.batch_id} with {len(training_batch.chunks)} chunks")
        
        return TrainingBatchResponse(
            message="Training batch generated successfully",
            batch_id=training_batch.batch_id,
            total_chunks=training_batch.get_total_chunks(),
            total_sequences=training_batch.get_total_sequences(),
            batch_metadata=training_batch.batch_metadata.to_dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating training batch: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate training batch")


@router.get("/batch/{batch_id}", response_model=Dict[str, Any])
async def get_training_batch_data(
    batch_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Get the full data for a training batch.
    
    Returns the complete training batch with all chunks, sequences,
    and metadata for ML model training.
    """
    try:
        if batch_id not in training_batch_registry:
            raise HTTPException(status_code=404, detail="Training batch not found")
        
        training_batch = training_batch_registry[batch_id]
        
        return {
            "success": True,
            "message": "Training batch retrieved successfully",
            "batch": training_batch.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving training batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve training batch")


@router.post("/sequences", response_model=ChunkSequenceResponse)
async def get_chunk_sequences(
    request: ChunkSequenceRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Get ordered sequences of related chunks for sequential learning.
    
    Generates coherent sequences of knowledge chunks based on semantic,
    temporal, or causal relationships for sequential ML training.
    """
    try:
        # Lazy load components
        search_service, _ = _get_ml_components()
        
        if not search_service:
            raise HTTPException(
                status_code=503,
                detail="ML training service not available"
            )
        
        # Generate chunk sequences based on pattern
        sequences = await generate_chunk_sequences(
            pattern=request.pattern,
            sequence_length=request.sequence_length,
            sequence_type=request.sequence_type,
            max_sequences=request.max_sequences
        )
        
        # Convert to API format
        sequence_data = []
        for sequence in sequences:
            sequence_data.append({
                "sequence_id": sequence.sequence_id,
                "chunks": [chunk.to_dict() for chunk in sequence.chunks],
                "sequence_type": sequence.sequence_type.value,
                "coherence_score": sequence.coherence_score,
                "total_reward": sequence.total_reward
            })
        
        logger.info(f"Generated {len(sequences)} chunk sequences for pattern '{request.pattern}'")
        
        return ChunkSequenceResponse(
            message="Chunk sequences generated successfully",
            sequences=sequence_data,
            total_sequences=len(sequences)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating chunk sequences: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate chunk sequences")


@router.post("/feedback", response_model=InteractionFeedbackResponse)
async def record_interaction_feedback(
    request: InteractionFeedbackRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Record user interaction feedback for reward signal generation.
    
    Captures user interactions with knowledge chunks to generate
    reward signals for reinforcement learning training.
    """
    try:
        # Create interaction feedback
        feedback = InteractionFeedback(
            chunk_id=request.chunk_id,
            user_id=user_id or "anonymous",
            interaction_type=InteractionType(request.interaction_type),
            feedback_score=request.feedback_score,
            context_query=request.context_query or ""
        )
        
        # Validate feedback
        if not feedback.validate():
            raise HTTPException(
                status_code=400,
                detail="Invalid feedback data"
            )
        
        # Store feedback
        if request.chunk_id not in interaction_feedback_store:
            interaction_feedback_store[request.chunk_id] = []
        
        interaction_feedback_store[request.chunk_id].append(feedback)
        
        # Calculate updated reward signal
        updated_reward = calculate_chunk_reward_signal(request.chunk_id)
        
        feedback_id = str(uuid4())
        
        logger.info(f"Recorded interaction feedback for chunk {request.chunk_id}")
        
        return InteractionFeedbackResponse(
            message="Interaction feedback recorded successfully",
            feedback_id=feedback_id,
            updated_reward_signal=updated_reward
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording interaction feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")


@router.get("/feedback/{chunk_id}", response_model=Dict[str, Any])
async def get_chunk_feedback(
    chunk_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Get interaction feedback history for a specific chunk.
    
    Returns all recorded interactions and the current reward signal
    for a knowledge chunk.
    """
    try:
        feedback_list = interaction_feedback_store.get(chunk_id, [])
        
        # Convert to API format
        feedback_data = []
        for feedback in feedback_list:
            feedback_data.append({
                "user_id": feedback.user_id,
                "interaction_type": feedback.interaction_type.value,
                "feedback_score": feedback.feedback_score,
                "timestamp": feedback.timestamp.isoformat(),
                "context_query": feedback.context_query
            })
        
        # Calculate current reward signal
        current_reward = calculate_chunk_reward_signal(chunk_id)
        
        return {
            "success": True,
            "message": "Chunk feedback retrieved successfully",
            "chunk_id": chunk_id,
            "feedback_history": feedback_data,
            "current_reward_signal": current_reward,
            "total_interactions": len(feedback_list)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving chunk feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chunk feedback")


@router.get("/stats", response_model=Dict[str, Any])
async def get_ml_training_statistics():
    """
    Get statistics about ML training data availability and usage.
    
    Provides insights into the available training data, interaction patterns,
    and overall ML training data health.
    """
    try:
        # Lazy load components
        search_service, _ = _get_ml_components()
        
        stats = {
            "total_chunks_available": 0,
            "chunks_with_feedback": len(interaction_feedback_store),
            "total_interactions": sum(len(feedback_list) for feedback_list in interaction_feedback_store.values()),
            "active_training_batches": len(training_batch_registry),
            "source_distribution": {
                "books": 0,
                "conversations": 0
            },
            "content_type_distribution": {},
            "reward_signal_distribution": {
                "mean": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0
            },
            "interaction_type_distribution": {}
        }
        
        # Get chunk statistics from search service
        if search_service:
            try:
                collection_stats = search_service.get_collection_stats()
                stats["total_chunks_available"] = collection_stats.get("total_vectors", 0)
                
                source_breakdown = search_service.get_source_breakdown()
                stats["source_distribution"] = source_breakdown
                
                content_breakdown = search_service.get_content_type_breakdown()
                stats["content_type_distribution"] = content_breakdown
                
            except Exception as e:
                logger.warning(f"Could not get search service stats: {e}")
        
        # Calculate reward signal statistics
        if interaction_feedback_store:
            reward_signals = [calculate_chunk_reward_signal(chunk_id) 
                            for chunk_id in interaction_feedback_store.keys()]
            
            if reward_signals:
                import numpy as np
                stats["reward_signal_distribution"] = {
                    "mean": float(np.mean(reward_signals)),
                    "std": float(np.std(reward_signals)),
                    "min": float(np.min(reward_signals)),
                    "max": float(np.max(reward_signals))
                }
        
        # Calculate interaction type distribution
        interaction_counts = {}
        for feedback_list in interaction_feedback_store.values():
            for feedback in feedback_list:
                interaction_type = feedback.interaction_type.value
                interaction_counts[interaction_type] = interaction_counts.get(interaction_type, 0) + 1
        
        stats["interaction_type_distribution"] = interaction_counts
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting ML training statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ML training statistics")


@router.delete("/batch/{batch_id}", response_model=APIResponse)
async def delete_training_batch(
    batch_id: str,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Delete a training batch from the registry.
    
    Removes the training batch to free up memory and clean up resources.
    """
    try:
        if batch_id not in training_batch_registry:
            raise HTTPException(status_code=404, detail="Training batch not found")
        
        del training_batch_registry[batch_id]
        
        logger.info(f"Deleted training batch {batch_id}")
        
        return APIResponse(
            message="Training batch deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting training batch: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete training batch")


# Helper functions

async def stream_chunks_generator(
    filters: Optional[ChunkFilters],
    batch_size: int,
    stream_format: str
) -> AsyncIterator[str]:
    """Generate streaming chunks for ML training."""
    try:
        # Get chunks from search service
        chunks = await get_filtered_chunks(filters, batch_size * 10)  # Get more than needed
        
        # Convert to training chunks
        training_chunks = []
        for chunk in chunks:
            # Get reward signal
            reward_signal = calculate_chunk_reward_signal(chunk.id)
            
            # Get interaction count
            interaction_count = len(interaction_feedback_store.get(chunk.id, []))
            
            # Create training chunk
            training_chunk = TrainingChunk(
                knowledge_chunk=chunk,
                embedding_vector=chunk.embedding,
                reward_signal=reward_signal,
                interaction_count=interaction_count,
                complexity_score=chunk.knowledge_metadata.complexity_score if chunk.knowledge_metadata else 0.0,
                temporal_weight=1.0,  # Could be calculated based on recency
                related_chunk_ids=[]  # Could be populated from knowledge graph
            )
            
            # Apply filters
            if filters and not filters.matches_chunk(training_chunk):
                continue
            
            training_chunks.append(training_chunk)
            
            if len(training_chunks) >= batch_size:
                break
        
        # Stream chunks
        if stream_format == "jsonl":
            for chunk in training_chunks:
                yield json.dumps(chunk.to_dict()) + "\n"
        else:
            # Stream as JSON array
            yield "["
            for i, chunk in enumerate(training_chunks):
                if i > 0:
                    yield ","
                yield json.dumps(chunk.to_dict())
            yield "]"
        
    except Exception as e:
        logger.error(f"Error in chunk streaming: {e}")
        error_response = {"error": str(e)}
        yield json.dumps(error_response)


async def get_filtered_chunks(
    filters: Optional[ChunkFilters],
    limit: int
) -> List[KnowledgeChunk]:
    """Get filtered knowledge chunks from the search service."""
    try:
        # In a real implementation, this would query the vector store with filters
        # For now, return mock chunks
        chunks = []
        
        for i in range(min(limit, 100)):  # Limit to 100 for demo
            chunk = KnowledgeChunk(
                id=f"chunk_{i}",
                content=f"Sample knowledge chunk content {i}",
                source_type=SourceType.BOOK if i % 2 == 0 else SourceType.CONVERSATION,
                source_id=f"source_{i // 10}",
                location_reference=f"page_{i}",
                section=f"Section {i // 5}",
                content_type=ContentType.TECHNICAL if i % 3 == 0 else ContentType.GENERAL
            )
            chunks.append(chunk)
        
        return chunks
        
    except Exception as e:
        logger.error(f"Error getting filtered chunks: {e}")
        return []


async def generate_training_batch(
    criteria: TrainingCriteria,
    filters: Optional[ChunkFilters]
) -> TrainingBatch:
    """Generate a training batch based on criteria and filters."""
    try:
        # Get chunks
        chunks = await get_filtered_chunks(filters, criteria.batch_size * 2)
        
        # Convert to training chunks
        training_chunks = []
        for chunk in chunks[:criteria.batch_size]:
            reward_signal = calculate_chunk_reward_signal(chunk.id)
            interaction_count = len(interaction_feedback_store.get(chunk.id, []))
            
            training_chunk = TrainingChunk(
                knowledge_chunk=chunk,
                embedding_vector=chunk.embedding,
                reward_signal=reward_signal,
                interaction_count=interaction_count,
                complexity_score=chunk.knowledge_metadata.complexity_score if chunk.knowledge_metadata else 0.0,
                temporal_weight=1.0,
                related_chunk_ids=[]
            )
            training_chunks.append(training_chunk)
        
        # Generate sequences if requested
        sequences = []
        if criteria.include_sequences:
            sequences = await generate_sequences_from_chunks(
                training_chunks,
                criteria.sequence_length
            )
        
        # Create batch metadata
        batch_metadata = BatchMetadata(
            batch_id=str(uuid4()),
            total_chunks=len(training_chunks),
            total_sequences=len(sequences),
            content_types=[chunk.knowledge_chunk.content_type.value for chunk in training_chunks],
            source_types=[chunk.knowledge_chunk.source_type.value for chunk in training_chunks]
        )
        
        # Create training batch
        training_batch = TrainingBatch(
            batch_id=batch_metadata.batch_id,
            chunks=training_chunks,
            sequences=sequences,
            batch_metadata=batch_metadata
        )
        
        # Calculate reward distribution
        training_batch.calculate_reward_distribution()
        
        return training_batch
        
    except Exception as e:
        logger.error(f"Error generating training batch: {e}")
        raise


async def generate_chunk_sequences(
    pattern: str,
    sequence_length: int,
    sequence_type: str,
    max_sequences: int
) -> List[ChunkSequence]:
    """Generate chunk sequences based on pattern and type."""
    try:
        sequences = []
        
        # Get chunks matching pattern
        chunks = await get_filtered_chunks(None, max_sequences * sequence_length)
        
        # Group chunks into sequences
        for i in range(0, min(len(chunks), max_sequences * sequence_length), sequence_length):
            sequence_chunks = chunks[i:i + sequence_length]
            
            if len(sequence_chunks) < sequence_length:
                break
            
            # Convert to training chunks
            training_chunks = []
            for chunk in sequence_chunks:
                reward_signal = calculate_chunk_reward_signal(chunk.id)
                interaction_count = len(interaction_feedback_store.get(chunk.id, []))
                
                training_chunk = TrainingChunk(
                    knowledge_chunk=chunk,
                    embedding_vector=chunk.embedding,
                    reward_signal=reward_signal,
                    interaction_count=interaction_count,
                    complexity_score=0.5,
                    temporal_weight=1.0,
                    related_chunk_ids=[]
                )
                training_chunks.append(training_chunk)
            
            # Create sequence
            sequence = ChunkSequence(
                sequence_id=str(uuid4()),
                chunks=training_chunks,
                sequence_type=SequenceType(sequence_type),
                coherence_score=0.8,  # Would be calculated based on semantic similarity
                total_reward=0.0
            )
            
            # Calculate total reward
            sequence.calculate_total_reward()
            
            sequences.append(sequence)
            
            if len(sequences) >= max_sequences:
                break
        
        return sequences
        
    except Exception as e:
        logger.error(f"Error generating chunk sequences: {e}")
        return []


async def generate_sequences_from_chunks(
    training_chunks: List[TrainingChunk],
    sequence_length: int
) -> List[ChunkSequence]:
    """Generate sequences from a list of training chunks."""
    sequences = []
    
    for i in range(0, len(training_chunks), sequence_length):
        sequence_chunks = training_chunks[i:i + sequence_length]
        
        if len(sequence_chunks) < sequence_length:
            break
        
        sequence = ChunkSequence(
            sequence_id=str(uuid4()),
            chunks=sequence_chunks,
            sequence_type=SequenceType.SEMANTIC,
            coherence_score=0.7,
            total_reward=0.0
        )
        
        sequence.calculate_total_reward()
        sequences.append(sequence)
    
    return sequences


def calculate_chunk_reward_signal(chunk_id: str) -> float:
    """Calculate reward signal for a chunk based on interaction feedback."""
    feedback_list = interaction_feedback_store.get(chunk_id, [])
    
    if not feedback_list:
        return 0.0
    
    # Simple average of feedback scores with recency weighting
    total_weighted_score = 0.0
    total_weight = 0.0
    
    current_time = datetime.now()
    
    for feedback in feedback_list:
        # Calculate recency weight (more recent feedback has higher weight)
        time_diff = (current_time - feedback.timestamp).total_seconds()
        recency_weight = max(0.1, 1.0 - (time_diff / (30 * 24 * 3600)))  # 30 days decay
        
        # Weight by interaction type
        interaction_weight = {
            InteractionType.VIEW: 0.1,
            InteractionType.CITE: 0.5,
            InteractionType.EXPORT: 0.7,
            InteractionType.RATE: 1.0
        }.get(feedback.interaction_type, 0.5)
        
        final_weight = recency_weight * interaction_weight
        total_weighted_score += feedback.feedback_score * final_weight
        total_weight += final_weight
    
    return total_weighted_score / total_weight if total_weight > 0 else 0.0


@router.get("/health", response_model=Dict[str, Any])
async def ml_training_service_health():
    """Health check for ML training service."""
    # Lazy load components for health check
    search_service, conversation_manager = _get_ml_components()
    
    health_status = {
        "status": "healthy",
        "service": "ml_training",
        "components": {
            "search_service": "healthy" if search_service else "unavailable",
            "conversation_manager": "healthy" if conversation_manager else "unavailable"
        },
        "active_batches": len(training_batch_registry),
        "chunks_with_feedback": len(interaction_feedback_store),
        "total_interactions": sum(len(feedback_list) for feedback_list in interaction_feedback_store.values())
    }
    
    if not search_service or not conversation_manager:
        health_status["status"] = "degraded"
    
    return health_status