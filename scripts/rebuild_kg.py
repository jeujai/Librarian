#!/usr/bin/env python3
"""Rebuild knowledge graph for a document from existing PostgreSQL chunks.

Usage (inside Docker):
    docker compose exec app python -m scripts.rebuild_kg <document_id>

Or from host:
    docker compose exec app python /app/scripts/rebuild_kg.py c9447e50-bdb5-45c0-b23c-3e218ef4d0e9
"""
import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def main(document_id: str):
    from sqlalchemy import text

    from multimodal_librarian.database.connection import db_manager

    db_manager.initialize()

    # Read chunks from PostgreSQL
    async with db_manager.AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT id, content, chunk_index, content_type, metadata
                FROM multimodal_librarian.knowledge_chunks
                WHERE source_id = :doc_id
                ORDER BY chunk_index
            """),
            {"doc_id": document_id}
        )
        rows = result.fetchall()

    print(f"Found {len(rows)} chunks for document {document_id}")

    chunks = []
    for row in rows:
        chunks.append({
            'id': str(row[0]),
            'content': row[1],
            'chunk_index': row[2],
            'chunk_type': row[3] or 'general',
            'metadata': row[4] if isinstance(row[4], dict) else {}
        })

    # Run KG update
    from multimodal_librarian.services.celery_service import _update_knowledge_graph
    await _update_knowledge_graph(document_id, chunks)
    print("Knowledge graph rebuild complete!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rebuild_kg.py <document_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
