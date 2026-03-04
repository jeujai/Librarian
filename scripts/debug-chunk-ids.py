#!/usr/bin/env python3
"""Debug script to trace chunk IDs through the processing pipeline."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def main():
    import uuid

    from multimodal_librarian.components.knowledge_graph.kg_builder import (
        KnowledgeGraphBuilder,
    )
    from multimodal_librarian.models.core import ContentType, KnowledgeChunk, SourceType

    # Create a test chunk with a known UUID
    test_uuid = str(uuid.uuid4())
    print(f"Test UUID: {test_uuid}")
    
    knowledge_chunk = KnowledgeChunk(
        id=test_uuid,
        content="Machine learning is a subset of artificial intelligence. Deep learning uses neural networks.",
        source_type=SourceType.BOOK,
        source_id="test-doc-123",
        location_reference="0",
        section="Test Section",
        content_type=ContentType.GENERAL
    )
    
    print(f"KnowledgeChunk.id: {knowledge_chunk.id}")
    
    # Process through knowledge graph builder
    kg_builder = KnowledgeGraphBuilder()
    extraction = await kg_builder.process_knowledge_chunk_async(knowledge_chunk)
    
    print(f"\nExtracted {len(extraction.extracted_concepts)} concepts:")
    for concept in extraction.extracted_concepts[:5]:
        print(f"  - {concept.concept_name}")
        print(f"    source_chunks: {concept.source_chunks}")
    
    print(f"\nExtraction chunk_id: {extraction.chunk_id}")

if __name__ == "__main__":
    asyncio.run(main())
