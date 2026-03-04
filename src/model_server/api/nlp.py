"""NLP API endpoints."""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models.nlp import get_nlp_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nlp", tags=["nlp"])


class NLPRequest(BaseModel):
    """Request model for NLP processing."""
    
    texts: List[str] = Field(
        ...,
        description="List of texts to process",
        min_length=1,
        max_length=100
    )
    tasks: Optional[List[str]] = Field(
        default=["tokenize", "ner", "pos"],
        description="NLP tasks to perform: tokenize, ner, pos, lemma, sentences"
    )


class NLPResult(BaseModel):
    """Result for a single text."""
    
    text: str
    tokens: Optional[List[str]] = None
    entities: Optional[List[Dict[str, Any]]] = None
    pos_tags: Optional[List[Dict[str, str]]] = None
    lemmas: Optional[List[str]] = None
    sentences: Optional[List[str]] = None


class NLPResponse(BaseModel):
    """Response model for NLP processing."""
    
    results: List[NLPResult] = Field(
        ...,
        description="Processing results for each text"
    )
    model: str = Field(
        ...,
        description="Model used for processing"
    )
    tasks: List[str] = Field(
        ...,
        description="Tasks performed"
    )
    count: int = Field(
        ...,
        description="Number of texts processed"
    )
    processing_time_ms: float = Field(
        ...,
        description="Processing time in milliseconds"
    )


@router.post("/process", response_model=NLPResponse)
async def process_texts(request: NLPRequest) -> NLPResponse:
    """
    Process texts with NLP tasks.
    
    Available tasks:
    - tokenize: Split text into tokens
    - ner: Named entity recognition
    - pos: Part-of-speech tagging
    - lemma: Lemmatization
    - sentences: Sentence segmentation
    """
    start_time = time.time()
    
    model = get_nlp_model()
    if model is None or not model.is_loaded:
        raise HTTPException(
            status_code=503,
            detail="NLP model not loaded"
        )
    
    # Validate tasks
    valid_tasks = {"tokenize", "ner", "pos", "lemma", "sentences"}
    tasks = request.tasks or ["tokenize", "ner", "pos"]
    invalid_tasks = set(tasks) - valid_tasks
    if invalid_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tasks: {invalid_tasks}. Valid tasks: {valid_tasks}"
        )
    
    try:
        results = model.process(
            texts=request.texts,
            tasks=tasks
        )
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            f"Processed {len(results)} texts with tasks {tasks} "
            f"in {processing_time_ms:.2f}ms"
        )
        
        return NLPResponse(
            results=[NLPResult(**r) for r in results],
            model=model.model_name,
            tasks=tasks,
            count=len(results),
            processing_time_ms=processing_time_ms
        )
        
    except Exception as e:
        logger.error(f"Error processing texts: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing texts: {str(e)}"
        )


@router.post("/tokenize")
async def tokenize_texts(texts: List[str]) -> Dict[str, Any]:
    """Tokenize texts (convenience endpoint)."""
    model = get_nlp_model()
    if model is None or not model.is_loaded:
        raise HTTPException(status_code=503, detail="NLP model not loaded")
    
    start_time = time.time()
    tokens = model.tokenize(texts)
    processing_time_ms = (time.time() - start_time) * 1000
    
    return {
        "tokens": tokens,
        "count": len(tokens),
        "processing_time_ms": processing_time_ms
    }


@router.post("/entities")
async def extract_entities(texts: List[str]) -> Dict[str, Any]:
    """Extract named entities (convenience endpoint)."""
    model = get_nlp_model()
    if model is None or not model.is_loaded:
        raise HTTPException(status_code=503, detail="NLP model not loaded")
    
    start_time = time.time()
    entities = model.get_entities(texts)
    processing_time_ms = (time.time() - start_time) * 1000
    
    return {
        "entities": entities,
        "count": len(entities),
        "processing_time_ms": processing_time_ms
    }


@router.get("/info")
async def get_nlp_info():
    """Get information about the NLP model."""
    model = get_nlp_model()
    if model is None:
        return {"status": "not_initialized"}
    
    return model.get_status()
