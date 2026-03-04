#!/usr/bin/env python3
"""
Milvus Collection Schema Definitions

This module defines the collection schemas used by the Multimodal Librarian
application for vector storage and semantic search operations.

Each schema includes:
- Field definitions with appropriate data types
- Index configurations for optimal search performance
- Collection metadata and descriptions
- Validation rules and constraints

Usage:
    from database.milvus.schemas import COLLECTION_SCHEMAS, create_collection_with_schema
    
    # Get schema for a collection
    schema = COLLECTION_SCHEMAS["knowledge_chunks"]
    
    # Create collection with predefined schema
    await create_collection_with_schema(client, "knowledge_chunks")
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

try:
    from pymilvus import FieldSchema, CollectionSchema, DataType
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False
    # Define mock classes for type hints when pymilvus is not available
    class FieldSchema:
        pass
    class CollectionSchema:
        pass
    class DataType:
        VARCHAR = "VARCHAR"
        FLOAT_VECTOR = "FLOAT_VECTOR"
        INT64 = "INT64"
        JSON = "JSON"
        BOOL = "BOOL"


class IndexType(Enum):
    """Supported index types for vector fields"""
    IVF_FLAT = "IVF_FLAT"
    IVF_SQ8 = "IVF_SQ8"
    HNSW = "HNSW"
    ANNOY = "ANNOY"
    AUTOINDEX = "AUTOINDEX"


class MetricType(Enum):
    """Supported distance metrics for vector similarity"""
    L2 = "L2"          # Euclidean distance
    IP = "IP"          # Inner product
    COSINE = "COSINE"  # Cosine similarity


@dataclass
class IndexConfig:
    """Configuration for vector field indexes"""
    index_type: IndexType
    metric_type: MetricType
    params: Dict[str, Any]


@dataclass
class CollectionConfig:
    """Complete configuration for a Milvus collection"""
    name: str
    description: str
    fields: List[FieldSchema]
    index_config: IndexConfig
    shard_num: int = 1
    consistency_level: str = "Strong"


# =============================================================================
# COLLECTION SCHEMA DEFINITIONS
# =============================================================================

def create_knowledge_chunks_schema() -> CollectionConfig:
    """
    Schema for document knowledge chunks with embeddings.
    
    This collection stores text chunks from processed documents along with
    their vector embeddings for semantic search. Each chunk includes:
    - Unique identifier
    - Vector embedding (384-dimensional for sentence-transformers)
    - Original text content
    - Source document metadata
    - Processing metadata
    
    Optimized for:
    - Fast semantic similarity search
    - Filtering by document source
    - Retrieval of original text content
    - Metadata-based queries
    """
    if not PYMILVUS_AVAILABLE:
        raise ImportError("pymilvus is required for schema creation")
    
    fields = [
        # Primary key field
        FieldSchema(
            name="id",
            dtype=DataType.VARCHAR,
            max_length=512,
            is_primary=True,
            description="Unique identifier for the chunk (format: {source_id}_chunk_{index}_{hash})"
        ),
        
        # Vector embedding field
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=384,  # Default for all-MiniLM-L6-v2 model
            description="Vector embedding of the text chunk (384-dimensional)"
        ),
        
        # Content fields
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=65535,  # 64KB max content
            description="Original text content of the chunk"
        ),
        
        # Source metadata
        FieldSchema(
            name="source_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="ID of the source document"
        ),
        
        FieldSchema(
            name="chunk_index",
            dtype=DataType.INT64,
            description="Position of this chunk within the source document"
        ),
        
        # Processing metadata
        FieldSchema(
            name="content_type",
            dtype=DataType.VARCHAR,
            max_length=50,
            description="Type of content (text, table, image_caption, etc.)"
        ),
        
        FieldSchema(
            name="processing_metadata",
            dtype=DataType.JSON,
            description="Additional processing metadata as JSON"
        ),
        
        # Timestamps
        FieldSchema(
            name="created_at",
            dtype=DataType.INT64,
            description="Unix timestamp when chunk was created"
        ),
        
        FieldSchema(
            name="updated_at",
            dtype=DataType.INT64,
            description="Unix timestamp when chunk was last updated"
        )
    ]
    
    # Index configuration optimized for development and moderate scale
    index_config = IndexConfig(
        index_type=IndexType.IVF_FLAT,
        metric_type=MetricType.L2,
        params={
            "nlist": 1024,  # Number of cluster units
            "nprobe": 10    # Number of units to query
        }
    )
    
    return CollectionConfig(
        name="knowledge_chunks",
        description="Document knowledge chunks with vector embeddings for semantic search",
        fields=fields,
        index_config=index_config,
        shard_num=1,
        consistency_level="Strong"
    )


def create_document_embeddings_schema() -> CollectionConfig:
    """
    Schema for document-level embeddings.
    
    This collection stores embeddings for entire documents, useful for:
    - Document similarity search
    - Document clustering and categorization
    - High-level document retrieval
    - Document recommendation systems
    
    Optimized for:
    - Fast document-level similarity search
    - Document metadata filtering
    - Large-scale document collections
    """
    if not PYMILVUS_AVAILABLE:
        raise ImportError("pymilvus is required for schema creation")
    
    fields = [
        # Primary key
        FieldSchema(
            name="document_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            is_primary=True,
            description="Unique identifier for the document"
        ),
        
        # Document embedding
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=384,
            description="Vector embedding representing the entire document"
        ),
        
        # Document metadata
        FieldSchema(
            name="title",
            dtype=DataType.VARCHAR,
            max_length=1000,
            description="Document title"
        ),
        
        FieldSchema(
            name="author",
            dtype=DataType.VARCHAR,
            max_length=500,
            description="Document author(s)"
        ),
        
        FieldSchema(
            name="document_type",
            dtype=DataType.VARCHAR,
            max_length=50,
            description="Type of document (pdf, docx, txt, etc.)"
        ),
        
        FieldSchema(
            name="language",
            dtype=DataType.VARCHAR,
            max_length=10,
            description="Document language code (en, es, fr, etc.)"
        ),
        
        FieldSchema(
            name="page_count",
            dtype=DataType.INT64,
            description="Number of pages in the document"
        ),
        
        FieldSchema(
            name="word_count",
            dtype=DataType.INT64,
            description="Approximate word count"
        ),
        
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
            description="Additional document metadata as JSON"
        ),
        
        # Timestamps
        FieldSchema(
            name="uploaded_at",
            dtype=DataType.INT64,
            description="Unix timestamp when document was uploaded"
        ),
        
        FieldSchema(
            name="processed_at",
            dtype=DataType.INT64,
            description="Unix timestamp when document was processed"
        )
    ]
    
    # Index configuration for document-level search
    index_config = IndexConfig(
        index_type=IndexType.IVF_FLAT,
        metric_type=MetricType.COSINE,  # Cosine similarity for document comparison
        params={
            "nlist": 512,
            "nprobe": 8
        }
    )
    
    return CollectionConfig(
        name="document_embeddings",
        description="Document-level embeddings for similarity search and categorization",
        fields=fields,
        index_config=index_config,
        shard_num=1,
        consistency_level="Strong"
    )


def create_conversation_embeddings_schema() -> CollectionConfig:
    """
    Schema for conversation message embeddings.
    
    This collection stores embeddings for chat messages and conversation turns,
    enabling:
    - Conversation similarity search
    - Context-aware response generation
    - Conversation clustering and analysis
    - Historical conversation retrieval
    
    Optimized for:
    - Fast message similarity search
    - Conversation context retrieval
    - User-specific conversation filtering
    """
    if not PYMILVUS_AVAILABLE:
        raise ImportError("pymilvus is required for schema creation")
    
    fields = [
        # Primary key
        FieldSchema(
            name="message_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            is_primary=True,
            description="Unique identifier for the message"
        ),
        
        # Message embedding
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=384,
            description="Vector embedding of the message content"
        ),
        
        # Message content
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=32768,  # 32KB for longer messages
            description="Original message content"
        ),
        
        # Conversation context
        FieldSchema(
            name="conversation_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="ID of the conversation this message belongs to"
        ),
        
        FieldSchema(
            name="user_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="ID of the user who sent the message"
        ),
        
        FieldSchema(
            name="message_type",
            dtype=DataType.VARCHAR,
            max_length=20,
            description="Type of message (user, assistant, system)"
        ),
        
        FieldSchema(
            name="turn_index",
            dtype=DataType.INT64,
            description="Position of this message in the conversation"
        ),
        
        # Message metadata
        FieldSchema(
            name="intent",
            dtype=DataType.VARCHAR,
            max_length=100,
            description="Detected intent of the message (optional)"
        ),
        
        FieldSchema(
            name="sentiment",
            dtype=DataType.VARCHAR,
            max_length=20,
            description="Sentiment analysis result (positive, negative, neutral)"
        ),
        
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
            description="Additional message metadata as JSON"
        ),
        
        # Timestamps
        FieldSchema(
            name="created_at",
            dtype=DataType.INT64,
            description="Unix timestamp when message was created"
        )
    ]
    
    # Index configuration for conversation search
    index_config = IndexConfig(
        index_type=IndexType.IVF_FLAT,
        metric_type=MetricType.L2,
        params={
            "nlist": 256,
            "nprobe": 6
        }
    )
    
    return CollectionConfig(
        name="conversation_embeddings",
        description="Conversation message embeddings for context-aware chat",
        fields=fields,
        index_config=index_config,
        shard_num=1,
        consistency_level="Strong"
    )


def create_multimedia_embeddings_schema() -> CollectionConfig:
    """
    Schema for multimedia content embeddings.
    
    This collection stores embeddings for images, charts, diagrams, and other
    multimedia content extracted from documents, enabling:
    - Multimodal similarity search
    - Image-text cross-modal retrieval
    - Visual content categorization
    - Multimedia content recommendation
    
    Optimized for:
    - Cross-modal search (text-to-image, image-to-text)
    - Visual content similarity
    - Multimedia content filtering
    """
    if not PYMILVUS_AVAILABLE:
        raise ImportError("pymilvus is required for schema creation")
    
    fields = [
        # Primary key
        FieldSchema(
            name="media_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            is_primary=True,
            description="Unique identifier for the multimedia content"
        ),
        
        # Multimedia embedding (using CLIP or similar multimodal model)
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=512,  # Common dimension for CLIP embeddings
            description="Multimodal vector embedding of the content"
        ),
        
        # Content metadata
        FieldSchema(
            name="media_type",
            dtype=DataType.VARCHAR,
            max_length=50,
            description="Type of multimedia content (image, chart, diagram, table)"
        ),
        
        FieldSchema(
            name="caption",
            dtype=DataType.VARCHAR,
            max_length=2000,
            description="Generated or extracted caption/description"
        ),
        
        FieldSchema(
            name="alt_text",
            dtype=DataType.VARCHAR,
            max_length=1000,
            description="Alternative text description for accessibility"
        ),
        
        # Source information
        FieldSchema(
            name="source_document_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="ID of the source document containing this media"
        ),
        
        FieldSchema(
            name="page_number",
            dtype=DataType.INT64,
            description="Page number where the media appears"
        ),
        
        FieldSchema(
            name="position_index",
            dtype=DataType.INT64,
            description="Position index within the page"
        ),
        
        # Technical metadata
        FieldSchema(
            name="file_path",
            dtype=DataType.VARCHAR,
            max_length=1000,
            description="Path to the extracted media file"
        ),
        
        FieldSchema(
            name="file_format",
            dtype=DataType.VARCHAR,
            max_length=20,
            description="File format (png, jpg, svg, etc.)"
        ),
        
        FieldSchema(
            name="width",
            dtype=DataType.INT64,
            description="Image width in pixels"
        ),
        
        FieldSchema(
            name="height",
            dtype=DataType.INT64,
            description="Image height in pixels"
        ),
        
        FieldSchema(
            name="file_size",
            dtype=DataType.INT64,
            description="File size in bytes"
        ),
        
        # Processing metadata
        FieldSchema(
            name="extraction_method",
            dtype=DataType.VARCHAR,
            max_length=100,
            description="Method used to extract the media (ocr, pdf_extract, etc.)"
        ),
        
        FieldSchema(
            name="processing_metadata",
            dtype=DataType.JSON,
            description="Additional processing metadata as JSON"
        ),
        
        # Timestamps
        FieldSchema(
            name="extracted_at",
            dtype=DataType.INT64,
            description="Unix timestamp when media was extracted"
        ),
        
        FieldSchema(
            name="processed_at",
            dtype=DataType.INT64,
            description="Unix timestamp when embedding was generated"
        )
    ]
    
    # Index configuration for multimodal search
    index_config = IndexConfig(
        index_type=IndexType.HNSW,  # HNSW is good for higher-dimensional embeddings
        metric_type=MetricType.COSINE,
        params={
            "M": 16,        # Number of bi-directional links for each node
            "efConstruction": 200,  # Size of dynamic candidate list
            "ef": 64        # Search parameter
        }
    )
    
    return CollectionConfig(
        name="multimedia_embeddings",
        description="Multimodal embeddings for images, charts, and visual content",
        fields=fields,
        index_config=index_config,
        shard_num=1,
        consistency_level="Strong"
    )


# =============================================================================
# COLLECTION REGISTRY
# =============================================================================

# Registry of all available collection schemas
COLLECTION_SCHEMAS: Dict[str, CollectionConfig] = {
    "knowledge_chunks": create_knowledge_chunks_schema(),
    "document_embeddings": create_document_embeddings_schema(),
    "conversation_embeddings": create_conversation_embeddings_schema(),
    "multimedia_embeddings": create_multimedia_embeddings_schema(),
}


# Default collections to create during initialization
DEFAULT_COLLECTIONS = [
    "knowledge_chunks",      # Primary collection for document chunks
    "document_embeddings",   # Document-level embeddings
    "conversation_embeddings"  # Chat message embeddings
]


# Optional collections (created on demand)
OPTIONAL_COLLECTIONS = [
    "multimedia_embeddings"  # Multimodal content (requires CLIP model)
]


def get_collection_schema(collection_name: str) -> CollectionConfig:
    """
    Get the schema configuration for a collection.
    
    Args:
        collection_name: Name of the collection
        
    Returns:
        CollectionConfig object with schema definition
        
    Raises:
        KeyError: If collection schema is not defined
    """
    if collection_name not in COLLECTION_SCHEMAS:
        available = list(COLLECTION_SCHEMAS.keys())
        raise KeyError(
            f"Collection schema '{collection_name}' not found. "
            f"Available schemas: {available}"
        )
    
    return COLLECTION_SCHEMAS[collection_name]


def list_available_schemas() -> List[str]:
    """
    List all available collection schemas.
    
    Returns:
        List of collection names with defined schemas
    """
    return list(COLLECTION_SCHEMAS.keys())


def validate_schema_compatibility(collection_name: str, existing_fields: List[Dict]) -> bool:
    """
    Validate that an existing collection is compatible with the defined schema.
    
    Args:
        collection_name: Name of the collection to validate
        existing_fields: List of existing field definitions from Milvus
        
    Returns:
        True if compatible, False otherwise
    """
    try:
        schema_config = get_collection_schema(collection_name)
        expected_fields = {field.name: field for field in schema_config.fields}
        
        # Check that all expected fields exist with correct types
        for existing_field in existing_fields:
            field_name = existing_field.get("name")
            field_type = existing_field.get("type")
            
            if field_name in expected_fields:
                expected_field = expected_fields[field_name]
                expected_type = str(expected_field.dtype)
                
                if field_type != expected_type:
                    return False
        
        # Check that all required fields are present
        existing_field_names = {f.get("name") for f in existing_fields}
        expected_field_names = set(expected_fields.keys())
        
        missing_fields = expected_field_names - existing_field_names
        if missing_fields:
            return False
        
        return True
        
    except KeyError:
        return False


def get_embedding_dimension(collection_name: str) -> int:
    """
    Get the embedding dimension for a collection.
    
    Args:
        collection_name: Name of the collection
        
    Returns:
        Embedding dimension (number of vector components)
        
    Raises:
        KeyError: If collection schema is not defined
        ValueError: If collection has no vector field
    """
    schema_config = get_collection_schema(collection_name)
    
    for field in schema_config.fields:
        if hasattr(field, 'dtype') and field.dtype == DataType.FLOAT_VECTOR:
            return field.params.get('dim', 0)
    
    raise ValueError(f"Collection '{collection_name}' has no vector field defined")


def get_index_parameters(collection_name: str) -> Dict[str, Any]:
    """
    Get the recommended index parameters for a collection.
    
    Args:
        collection_name: Name of the collection
        
    Returns:
        Dictionary with index parameters for pymilvus
    """
    schema_config = get_collection_schema(collection_name)
    index_config = schema_config.index_config
    
    return {
        "index_type": index_config.index_type.value,
        "metric_type": index_config.metric_type.value,
        "params": index_config.params
    }