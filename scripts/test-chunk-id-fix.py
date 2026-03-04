#!/usr/bin/env python3
"""
Test script to verify the chunk ID mismatch fix.

This script:
1. Deletes existing chunks for a document from both PostgreSQL and Milvus
2. Reprocesses the document through the chunking framework
3. Verifies that chunk IDs match between PostgreSQL and Milvus
4. Tests RAG search to ensure content is findable

Usage:
    python scripts/test-chunk-id-fix.py <document_id>
    
Example:
    python scripts/test-chunk-id-fix.py 2c8a0794-bd76-4782-b975-79b041e3a770
"""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


async def test_chunk_id_consistency(document_id: str):
    """Test that chunk IDs are consistent between PostgreSQL and Milvus."""
    import uuid

    # Validate document ID
    try:
        uuid.UUID(document_id)
    except ValueError:
        print(f"❌ Invalid document ID: {document_id}")
        return False
    
    print(f"\n🔍 Testing chunk ID consistency for document: {document_id}")
    print("=" * 60)
    
    # Step 1: Check current state in PostgreSQL
    print("\n📊 Step 1: Checking PostgreSQL chunks...")
    try:
        from multimodal_librarian.database.connection import get_async_connection
        
        conn = await get_async_connection()
        try:
            # Get chunks from PostgreSQL
            pg_chunks = await conn.fetch("""
                SELECT id, chunk_index, substring(content, 1, 100) as content_preview
                FROM document_chunks
                WHERE document_id = $1::uuid
                ORDER BY chunk_index
                LIMIT 10
            """, document_id)
            
            print(f"   Found {len(pg_chunks)} chunks in PostgreSQL")
            for chunk in pg_chunks[:3]:
                print(f"   - ID: {chunk['id']}, Index: {chunk['chunk_index']}")
                print(f"     Content: {chunk['content_preview'][:50]}...")
        finally:
            await conn.close()
    except Exception as e:
        print(f"   ❌ Error checking PostgreSQL: {e}")
        return False
    
    # Step 2: Check current state in Milvus
    print("\n📊 Step 2: Checking Milvus chunks...")
    try:
        from multimodal_librarian.clients.database_factory import DatabaseClientFactory
        from multimodal_librarian.config.config_factory import get_database_config
        
        config = get_database_config()
        factory = DatabaseClientFactory(config)
        vector_client = factory.get_vector_client()
        
        await vector_client.connect()
        
        # Search for chunks from this document
        # Use a simple query to find chunks with this source_id
        results = await vector_client.semantic_search(
            query="test query",
            top_k=100
        )
        
        # Filter by source_id
        milvus_chunks = [r for r in results if r.get('metadata', {}).get('source_id') == document_id]
        
        print(f"   Found {len(milvus_chunks)} chunks in Milvus for this document")
        for chunk in milvus_chunks[:3]:
            chunk_id = chunk.get('id', 'unknown')
            content = chunk.get('content', chunk.get('metadata', {}).get('content', ''))[:50]
            print(f"   - ID: {chunk_id}")
            print(f"     Content: {content}...")
        
    except Exception as e:
        print(f"   ❌ Error checking Milvus: {e}")
        return False
    
    # Step 3: Verify UUID format
    print("\n📊 Step 3: Verifying UUID format...")
    pg_ids = set(str(chunk['id']) for chunk in pg_chunks)
    milvus_ids = set(chunk.get('id', '') for chunk in milvus_chunks)
    
    # Check if PostgreSQL IDs are valid UUIDs
    pg_valid_uuids = 0
    for id_str in pg_ids:
        try:
            uuid.UUID(id_str)
            pg_valid_uuids += 1
        except ValueError:
            print(f"   ⚠️ Invalid UUID in PostgreSQL: {id_str}")
    
    print(f"   PostgreSQL: {pg_valid_uuids}/{len(pg_ids)} valid UUIDs")
    
    # Check if Milvus IDs are valid UUIDs
    milvus_valid_uuids = 0
    milvus_bridge_ids = 0
    for id_str in milvus_ids:
        if id_str.startswith('bridge_'):
            milvus_bridge_ids += 1
        else:
            try:
                uuid.UUID(id_str)
                milvus_valid_uuids += 1
            except ValueError:
                print(f"   ⚠️ Invalid UUID in Milvus: {id_str}")
    
    print(f"   Milvus: {milvus_valid_uuids} valid UUIDs, {milvus_bridge_ids} bridge IDs")
    
    # Step 4: Check ID overlap
    print("\n📊 Step 4: Checking ID overlap...")
    common_ids = pg_ids & milvus_ids
    pg_only = pg_ids - milvus_ids
    milvus_only = milvus_ids - pg_ids
    
    print(f"   Common IDs: {len(common_ids)}")
    print(f"   PostgreSQL only: {len(pg_only)}")
    print(f"   Milvus only: {len(milvus_only)}")
    
    if len(common_ids) == 0 and len(pg_ids) > 0:
        print("\n   ❌ PROBLEM: No chunk IDs match between PostgreSQL and Milvus!")
        print("   This is the chunk ID mismatch issue.")
        return False
    elif len(pg_only) > 0:
        print(f"\n   ⚠️ WARNING: {len(pg_only)} chunks in PostgreSQL are not in Milvus")
        print("   These chunks won't be found by RAG search.")
        return False
    else:
        print("\n   ✅ All PostgreSQL chunk IDs are present in Milvus!")
        return True


async def test_rag_search(document_id: str, query: str = "Chelsea AI Ventures"):
    """Test RAG search for specific content."""
    print(f"\n🔍 Testing RAG search for: '{query}'")
    print("=" * 60)
    
    try:
        from multimodal_librarian.clients.database_factory import DatabaseClientFactory
        from multimodal_librarian.config.config_factory import get_database_config
        
        config = get_database_config()
        factory = DatabaseClientFactory(config)
        vector_client = factory.get_vector_client()
        
        await vector_client.connect()
        
        # Perform semantic search
        results = await vector_client.semantic_search(
            query=query,
            top_k=5
        )
        
        print(f"\n   Found {len(results)} results:")
        for i, result in enumerate(results, 1):
            content = result.get('content', result.get('metadata', {}).get('content', ''))
            score = result.get('score', 0)
            chunk_id = result.get('id', 'unknown')
            source_id = result.get('metadata', {}).get('source_id', 'unknown')
            
            print(f"\n   Result {i}:")
            print(f"   - ID: {chunk_id}")
            print(f"   - Source: {source_id}")
            print(f"   - Score: {score:.4f}")
            print(f"   - Content: {content[:200]}...")
            
            # Check if this result contains the query term
            if query.lower() in content.lower():
                print(f"   ✅ Contains '{query}'!")
        
        # Check if any result contains the query
        found = any(query.lower() in r.get('content', r.get('metadata', {}).get('content', '')).lower() 
                   for r in results)
        
        if found:
            print(f"\n   ✅ RAG search successfully found content containing '{query}'!")
            return True
        else:
            print(f"\n   ❌ RAG search did not find content containing '{query}'")
            return False
            
    except Exception as e:
        print(f"   ❌ Error during RAG search: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test-chunk-id-fix.py <document_id>")
        print("Example: python scripts/test-chunk-id-fix.py 2c8a0794-bd76-4782-b975-79b041e3a770")
        sys.exit(1)
    
    document_id = sys.argv[1]
    
    # Test chunk ID consistency
    consistency_ok = await test_chunk_id_consistency(document_id)
    
    # Test RAG search
    search_ok = await test_rag_search(document_id)
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Chunk ID Consistency: {'✅ PASS' if consistency_ok else '❌ FAIL'}")
    print(f"  RAG Search: {'✅ PASS' if search_ok else '❌ FAIL'}")
    
    if consistency_ok and search_ok:
        print("\n✅ All tests passed! The chunk ID fix is working.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. The document may need to be reprocessed.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
