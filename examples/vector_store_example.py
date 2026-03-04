#!/usr/bin/env python3
"""
Example usage of the Vector Store component.

This example demonstrates how to use the VectorStore and SemanticSearchService
for storing and searching knowledge chunks.
"""

import asyncio
import logging
from datetime import datetime

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.multimodal_librarian.components.vector_store import (
    VectorStore, 
    SemanticSearchService,
    VectorStoreError
)
from src.multimodal_librarian.models.core import (
    KnowledgeChunk, 
    SourceType, 
    ContentType,
    KnowledgeMetadata
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_sample_chunks() -> list[KnowledgeChunk]:
    """Create sample knowledge chunks for demonstration."""
    chunks = [
        KnowledgeChunk(
            id="chunk_1",
            content="Machine learning is a subset of artificial intelligence that enables computers to learn and improve from experience without being explicitly programmed.",
            source_type=SourceType.BOOK,
            source_id="ai_textbook",
            location_reference="page_15",
            section="chapter_2",
            content_type=ContentType.TECHNICAL,
            knowledge_metadata=KnowledgeMetadata(
                complexity_score=0.7,
                domain_tags=["machine_learning", "artificial_intelligence"],
                extraction_confidence=0.95
            )
        ),
        KnowledgeChunk(
            id="chunk_2", 
            content="Deep learning uses neural networks with multiple layers to model and understand complex patterns in data.",
            source_type=SourceType.BOOK,
            source_id="ai_textbook",
            location_reference="page_42",
            section="chapter_5",
            content_type=ContentType.TECHNICAL,
            knowledge_metadata=KnowledgeMetadata(
                complexity_score=0.8,
                domain_tags=["deep_learning", "neural_networks"],
                extraction_confidence=0.92
            )
        ),
        KnowledgeChunk(
            id="chunk_3",
            content="In our conversation yesterday, we discussed how transformers revolutionized natural language processing by introducing the attention mechanism.",
            source_type=SourceType.CONVERSATION,
            source_id="conv_123",
            location_reference="2024-01-15T14:30:00",
            section="discussion_nlp",
            content_type=ContentType.TECHNICAL,
            knowledge_metadata=KnowledgeMetadata(
                complexity_score=0.6,
                domain_tags=["transformers", "nlp", "attention"],
                extraction_confidence=0.88
            )
        ),
        KnowledgeChunk(
            id="bridge_1",
            content="The connection between machine learning and deep learning is that deep learning is a specialized approach within machine learning that uses neural networks with multiple layers.",
            source_type=SourceType.BOOK,
            source_id="ai_textbook", 
            location_reference="bridge_15_42",
            section="BRIDGE_chapter_2_5",
            content_type=ContentType.TECHNICAL,
            knowledge_metadata=KnowledgeMetadata(
                complexity_score=0.75,
                domain_tags=["machine_learning", "deep_learning", "bridge"],
                extraction_confidence=0.90
            )
        )
    ]
    
    return chunks


def demonstrate_vector_store():
    """Demonstrate vector store functionality."""
    print("🚀 Vector Store Integration Demo")
    print("=" * 50)
    
    # Note: This example shows the API usage but won't actually connect to Milvus
    # In a real environment, you would need a running Milvus instance
    
    try:
        # Initialize vector store
        print("\n1. Initializing Vector Store...")
        vector_store = VectorStore("demo_collection")
        print(f"   ✓ Vector store initialized with collection: {vector_store.collection_name}")
        
        # In a real scenario, you would connect to Milvus:
        # vector_store.connect()
        
        # Create sample data
        print("\n2. Creating sample knowledge chunks...")
        chunks = create_sample_chunks()
        print(f"   ✓ Created {len(chunks)} sample chunks")
        
        for chunk in chunks:
            print(f"     - {chunk.id}: {chunk.content[:50]}...")
        
        # Demonstrate search service
        print("\n3. Initializing Semantic Search Service...")
        search_service = SemanticSearchService(vector_store)
        print("   ✓ Search service initialized")
        
        # Show search query processing
        print("\n4. Demonstrating query processing...")
        from src.multimodal_librarian.components.vector_store.search_service import SearchQuery
        
        queries = [
            "What is machine learning?",
            "How do neural networks work?",
            "Tell me about our conversation on transformers"
        ]
        
        for query in queries:
            search_query = SearchQuery.from_text(query)
            print(f"\n   Query: '{query}'")
            print(f"   ├─ Processed: '{search_query.processed_query}'")
            print(f"   ├─ Type: {search_query.query_type}")
            print(f"   ├─ Key terms: {search_query.key_terms}")
            print(f"   └─ Context hints: {search_query.context_hints}")
        
        # Show different search types
        print("\n5. Search functionality overview:")
        print("   ├─ semantic_search(): General semantic search across all content")
        print("   ├─ search_books_only(): Search only in book content")
        print("   ├─ search_conversations_only(): Search only in conversations")
        print("   ├─ search_bridge_chunks(): Find contextual bridge chunks")
        print("   ├─ find_similar_chunks(): Find chunks similar to a reference")
        print("   └─ get_search_suggestions(): Get query suggestions")
        
        # Show ranking factors
        print("\n6. Search ranking factors:")
        print("   ├─ Similarity score (base score from embeddings)")
        print("   ├─ Content type relevance")
        print("   ├─ Query type matching")
        print("   ├─ Key term presence")
        print("   ├─ Recency boost (for conversations)")
        print("   └─ Bridge chunk integration")
        
        # Show metadata filtering
        print("\n7. Available filters:")
        print("   ├─ source_type: Filter by BOOK or CONVERSATION")
        print("   ├─ content_type: Filter by TECHNICAL, ACADEMIC, etc.")
        print("   ├─ source_id: Filter by specific book or conversation")
        print("   └─ include_bridges: Include/exclude bridge chunks")
        
        print("\n✅ Demo completed successfully!")
        print("\nTo use in production:")
        print("1. Start a Milvus instance (docker run -p 19530:19530 milvusdb/milvus)")
        print("2. Set MILVUS_HOST and MILVUS_PORT in your environment")
        print("3. Call vector_store.connect() to establish connection")
        print("4. Use vector_store.store_embeddings(chunks) to store data")
        print("5. Use search_service.search(query) to perform searches")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        logger.error(f"Demo error: {e}")


if __name__ == "__main__":
    demonstrate_vector_store()