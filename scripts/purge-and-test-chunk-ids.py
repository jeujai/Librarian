#!/usr/bin/env python3
"""
Purge all databases and re-upload Langchain document to test chunk ID consistency.

This script:
1. Purges PostgreSQL (documents, document_chunks, processing_jobs)
2. Purges Milvus (all collections)
3. Purges Neo4j (all nodes and relationships)
4. Re-uploads the Langchain document
5. Analyzes the resulting chunk IDs across all three databases
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def purge_postgresql():
    """Purge all document-related data from PostgreSQL."""
    logger.info("=" * 60)
    logger.info("PURGING POSTGRESQL")
    logger.info("=" * 60)
    
    try:
        import psycopg2
        
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="multimodal_librarian",
            user="postgres",
            password="postgres"
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Delete in order to respect foreign keys
        tables = [
            'processing_jobs',
            'document_chunks', 
            'documents',
            'enrichment_cache'
        ]
        
        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table}")
                logger.info(f"  Deleted from {table}")
            except Exception as e:
                logger.warning(f"  Could not delete from {table}: {e}")
        
        cursor.close()
        conn.close()
        
        logger.info("✅ PostgreSQL purged successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to purge PostgreSQL: {e}")
        return False


async def purge_milvus():
    """Purge all data from Milvus."""
    logger.info("=" * 60)
    logger.info("PURGING MILVUS")
    logger.info("=" * 60)
    
    try:
        from pymilvus import Collection, connections, utility

        # Connect to Milvus
        connections.connect(
            alias="default",
            host="localhost",
            port="19530"
        )
        
        # List and drop all collections
        collections = utility.list_collections()
        logger.info(f"  Found {len(collections)} collections: {collections}")
        
        for coll_name in collections:
            try:
                collection = Collection(coll_name)
                collection.drop()
                logger.info(f"  Dropped collection: {coll_name}")
            except Exception as e:
                logger.warning(f"  Could not drop {coll_name}: {e}")
        
        connections.disconnect("default")
        logger.info("✅ Milvus purged successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to purge Milvus: {e}")
        return False


async def purge_neo4j():
    """Purge all data from Neo4j."""
    logger.info("=" * 60)
    logger.info("PURGING NEO4J")
    logger.info("=" * 60)
    
    try:
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "password")
        )
        
        with driver.session() as session:
            # Delete in batches to avoid memory issues
            batch_size = 1000
            total_rels = 0
            total_nodes = 0
            
            # Delete relationships in batches
            while True:
                result = session.run(
                    "MATCH ()-[r]->() WITH r LIMIT $batch DELETE r RETURN count(r) as count",
                    batch=batch_size
                )
                count = result.single()["count"]
                total_rels += count
                if count == 0:
                    break
                logger.info(f"  Deleted {count} relationships (total: {total_rels})")
            
            # Delete nodes in batches
            while True:
                result = session.run(
                    "MATCH (n) WITH n LIMIT $batch DELETE n RETURN count(n) as count",
                    batch=batch_size
                )
                count = result.single()["count"]
                total_nodes += count
                if count == 0:
                    break
                logger.info(f"  Deleted {count} nodes (total: {total_nodes})")
            
            logger.info(f"  Total deleted: {total_rels} relationships, {total_nodes} nodes")
        
        driver.close()
        logger.info("✅ Neo4j purged successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to purge Neo4j: {e}")
        return False


async def find_langchain_pdf():
    """Find the Langchain PDF file."""
    # Common locations to check
    locations = [
        Path("uploads"),
        Path("test_uploads"),
        Path("data"),
        Path.home() / "Downloads",
    ]
    
    for loc in locations:
        if loc.exists():
            for pdf in loc.glob("*langchain*.pdf"):
                logger.info(f"Found Langchain PDF: {pdf}")
                return pdf
            for pdf in loc.glob("*LangChain*.pdf"):
                logger.info(f"Found Langchain PDF: {pdf}")
                return pdf
    
    # Check if there's any PDF in uploads
    uploads = Path("uploads")
    if uploads.exists():
        pdfs = list(uploads.glob("*.pdf"))
        if pdfs:
            logger.info(f"Available PDFs in uploads: {[p.name for p in pdfs]}")
    
    return None


async def upload_document(pdf_path: Path):
    """Upload a document via the API."""
    logger.info("=" * 60)
    logger.info(f"UPLOADING DOCUMENT: {pdf_path.name}")
    logger.info("=" * 60)
    
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            with open(pdf_path, 'rb') as f:
                files = {'file': (pdf_path.name, f, 'application/pdf')}
                response = await client.post(
                    'http://localhost:8000/api/documents/upload',
                    files=files
                )
            
            if response.status_code == 200:
                data = response.json()
                document_id = data.get('document_id') or data.get('id')
                logger.info(f"✅ Document uploaded successfully")
                logger.info(f"   Document ID: {document_id}")
                return document_id
            else:
                logger.error(f"❌ Upload failed: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Upload error: {e}")
        return None


async def wait_for_processing(document_id: str, timeout: int = 600):
    """Wait for document processing to complete."""
    logger.info("=" * 60)
    logger.info("WAITING FOR PROCESSING")
    logger.info("=" * 60)
    
    import time

    import httpx
    
    start_time = time.time()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        while time.time() - start_time < timeout:
            try:
                response = await client.get(
                    f'http://localhost:8000/api/documents/{document_id}/status'
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', 'unknown')
                    progress = data.get('progress_percentage', 0)
                    step = data.get('current_step', 'unknown')
                    
                    logger.info(f"  Status: {status} ({progress}%) - {step}")
                    
                    if status == 'completed':
                        logger.info("✅ Processing completed!")
                        return True
                    elif status == 'failed':
                        logger.error(f"❌ Processing failed: {data.get('error_message')}")
                        return False
                
            except Exception as e:
                logger.warning(f"  Status check error: {e}")
            
            await asyncio.sleep(5)
    
    logger.error("❌ Processing timed out")
    return False


async def analyze_chunk_ids(document_id: str):
    """Analyze chunk IDs across all three databases."""
    logger.info("=" * 60)
    logger.info("ANALYZING CHUNK IDS")
    logger.info("=" * 60)
    
    results = {
        'postgresql': {'chunk_ids': [], 'sample': []},
        'milvus': {'chunk_ids': [], 'sample': []},
        'neo4j': {'source_chunks': [], 'sample': []}
    }
    
    # 1. PostgreSQL chunk IDs
    logger.info("\n--- PostgreSQL ---")
    try:
        import psycopg2
        
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="multimodal_librarian",
            user="postgres",
            password="postgres"
        )
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, chunk_index FROM document_chunks "
            "WHERE document_id = %s ORDER BY chunk_index LIMIT 10",
            (document_id,)
        )
        rows = cursor.fetchall()
        
        for row in rows:
            chunk_id = str(row[0])
            chunk_index = row[1]
            results['postgresql']['chunk_ids'].append(chunk_id)
            results['postgresql']['sample'].append({
                'chunk_id': chunk_id,
                'chunk_index': chunk_index
            })
            logger.info(f"  chunk_index={chunk_index}: id={chunk_id}")
        
        # Get total count
        cursor.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE document_id = %s",
            (document_id,)
        )
        total = cursor.fetchone()[0]
        logger.info(f"  Total chunks in PostgreSQL: {total}")
        
        cursor.close()
        conn.close()
            
    except Exception as e:
        logger.error(f"  PostgreSQL error: {e}")
    
    # 2. Milvus chunk IDs
    logger.info("\n--- Milvus ---")
    try:
        from pymilvus import Collection, connections
        
        connections.connect(alias="default", host="localhost", port="19530")
        
        collection = Collection("knowledge_chunks")
        collection.load()
        
        # Query for chunks from this document
        results_milvus = collection.query(
            expr=f'source_id == "{document_id}"',
            output_fields=["chunk_id", "source_id"],
            limit=10
        )
        
        for item in results_milvus:
            chunk_id = item.get('chunk_id', 'N/A')
            results['milvus']['chunk_ids'].append(chunk_id)
            results['milvus']['sample'].append({'chunk_id': chunk_id})
            logger.info(f"  chunk_id={chunk_id}")
        
        # Get total count
        total_results = collection.query(
            expr=f'source_id == "{document_id}"',
            output_fields=["chunk_id"],
            limit=10000
        )
        logger.info(f"  Total chunks in Milvus: {len(total_results)}")
        
        connections.disconnect("default")
        
    except Exception as e:
        logger.error(f"  Milvus error: {e}")
    
    # 3. Neo4j source_chunks
    logger.info("\n--- Neo4j ---")
    try:
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "password")
        )
        
        with driver.session() as session:
            # Get concepts with source_chunks for this document
            result = session.run("""
                MATCH (c:Concept)
                WHERE c.source_document = $doc_id
                RETURN c.name as name, c.source_chunks as source_chunks
                LIMIT 10
            """, doc_id=document_id)
            
            for record in result:
                name = record["name"]
                source_chunks = record["source_chunks"]
                if source_chunks:
                    chunks_list = source_chunks.split(',') if isinstance(source_chunks, str) else source_chunks
                    for chunk_id in chunks_list[:3]:  # Show first 3
                        chunk_id = chunk_id.strip()
                        results['neo4j']['source_chunks'].append(chunk_id)
                        logger.info(f"  Concept '{name}': source_chunk={chunk_id}")
            
            # Get total concept count
            count_result = session.run("""
                MATCH (c:Concept)
                WHERE c.source_document = $doc_id
                RETURN count(c) as count
            """, doc_id=document_id)
            total = count_result.single()["count"]
            logger.info(f"  Total concepts in Neo4j: {total}")
            
            # Check for chunk_N format
            chunk_n_result = session.run("""
                MATCH (c:Concept)
                WHERE c.source_document = $doc_id AND c.source_chunks =~ '.*chunk_[0-9]+.*'
                RETURN count(c) as count
            """, doc_id=document_id)
            chunk_n_count = chunk_n_result.single()["count"]
            
            uuid_result = session.run("""
                MATCH (c:Concept)
                WHERE c.source_document = $doc_id AND c.source_chunks =~ '.*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}.*'
                RETURN count(c) as count
            """, doc_id=document_id)
            uuid_count = uuid_result.single()["count"]
            
            logger.info(f"  Concepts with chunk_N format: {chunk_n_count}")
            logger.info(f"  Concepts with UUID format: {uuid_count}")
        
        driver.close()
        
    except Exception as e:
        logger.error(f"  Neo4j error: {e}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    
    pg_sample = results['postgresql']['sample'][0]['chunk_id'] if results['postgresql']['sample'] else 'N/A'
    milvus_sample = results['milvus']['sample'][0]['chunk_id'] if results['milvus']['sample'] else 'N/A'
    neo4j_sample = results['neo4j']['source_chunks'][0] if results['neo4j']['source_chunks'] else 'N/A'
    
    logger.info(f"PostgreSQL chunk ID sample: {pg_sample}")
    logger.info(f"Milvus chunk ID sample:     {milvus_sample}")
    logger.info(f"Neo4j source_chunk sample:  {neo4j_sample}")
    
    # Check consistency
    if pg_sample != 'N/A' and milvus_sample != 'N/A':
        if pg_sample == milvus_sample:
            logger.info("✅ PostgreSQL and Milvus chunk IDs MATCH")
        else:
            logger.error("❌ PostgreSQL and Milvus chunk IDs DO NOT MATCH")
    
    if pg_sample != 'N/A' and neo4j_sample != 'N/A':
        if pg_sample == neo4j_sample:
            logger.info("✅ PostgreSQL and Neo4j chunk IDs MATCH")
        else:
            logger.error("❌ PostgreSQL and Neo4j chunk IDs DO NOT MATCH")
            logger.error(f"   PostgreSQL format: {pg_sample[:50]}...")
            logger.error(f"   Neo4j format:      {neo4j_sample[:50]}...")
    
    return results


async def main():
    """Main function."""
    logger.info("=" * 60)
    logger.info("CHUNK ID CONSISTENCY TEST")
    logger.info("=" * 60)
    
    # Step 1: Purge all databases
    pg_ok = await purge_postgresql()
    milvus_ok = await purge_milvus()
    neo4j_ok = await purge_neo4j()
    
    if not (pg_ok and milvus_ok and neo4j_ok):
        logger.error("Failed to purge one or more databases. Aborting.")
        return 1
    
    # Step 2: Find Langchain PDF
    pdf_path = await find_langchain_pdf()
    if not pdf_path:
        logger.error("Could not find Langchain PDF. Please provide the path.")
        logger.info("Looking for PDFs in uploads directory...")
        uploads = Path("uploads")
        if uploads.exists():
            pdfs = list(uploads.glob("*.pdf"))
            if pdfs:
                logger.info(f"Found PDFs: {[p.name for p in pdfs]}")
                pdf_path = pdfs[0]
                logger.info(f"Using: {pdf_path}")
            else:
                logger.error("No PDFs found in uploads/")
                return 1
        else:
            logger.error("uploads/ directory does not exist")
            return 1
    
    # Step 3: Upload document
    document_id = await upload_document(pdf_path)
    if not document_id:
        logger.error("Failed to upload document")
        return 1
    
    # Step 4: Wait for processing
    success = await wait_for_processing(document_id)
    if not success:
        logger.warning("Processing may not have completed successfully")
    
    # Step 5: Analyze chunk IDs
    await analyze_chunk_ids(document_id)
    
    logger.info("\n" + "=" * 60)
    logger.info("TEST COMPLETE")
    logger.info("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
