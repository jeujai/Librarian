#!/usr/bin/env python3
"""
Local Data Seeding Script

This script seeds the local development databases with sample data for testing.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.config_factory import get_database_config
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory


async def seed_postgres_data(client):
    """Seed PostgreSQL with sample users, documents, conversations."""
    print("🌱 Seeding PostgreSQL with sample data...")
    
    try:
        # Sample users
        await client.execute_command("""
            INSERT INTO users (id, email, name, created_at) VALUES 
            ('dev-user-1', 'developer@example.com', 'Developer User', NOW()),
            ('test-user-1', 'tester@example.com', 'Test User', NOW())
            ON CONFLICT (id) DO NOTHING;
        """)
        
        # Sample documents
        await client.execute_command("""
            INSERT INTO documents (id, title, filename, user_id, created_at) VALUES
            ('doc-1', 'Sample ML Paper', 'sample_ml_paper.pdf', 'dev-user-1', NOW()),
            ('doc-2', 'Test Research Document', 'test_research.pdf', 'test-user-1', NOW())
            ON CONFLICT (id) DO NOTHING;
        """)
        
        # Sample conversations
        await client.execute_command("""
            INSERT INTO conversations (id, user_id, title, created_at) VALUES
            ('conv-1', 'dev-user-1', 'Discussion about ML concepts', NOW()),
            ('conv-2', 'test-user-1', 'Questions about the research', NOW())
            ON CONFLICT (id) DO NOTHING;
        """)
        
        print("✅ PostgreSQL seeding completed")
        
    except Exception as e:
        print(f"❌ PostgreSQL seeding failed: {e}")


async def seed_neo4j_data(client):
    """Seed Neo4j with sample knowledge graph."""
    print("🌱 Seeding Neo4j with sample knowledge graph...")
    
    try:
        # Create sample concepts and relationships
        await client.execute_query("""
            MERGE (d1:Document {id: 'doc-1', title: 'Sample ML Paper'})
            MERGE (d2:Document {id: 'doc-2', title: 'Test Research Document'})
            
            MERGE (c1:Concept {name: 'Machine Learning', type: 'field'})
            MERGE (c2:Concept {name: 'Neural Networks', type: 'technique'})
            MERGE (c3:Concept {name: 'Deep Learning', type: 'subfield'})
            MERGE (c4:Concept {name: 'Natural Language Processing', type: 'application'})
            
            MERGE (d1)-[:CONTAINS]->(c1)
            MERGE (d1)-[:CONTAINS]->(c2)
            MERGE (d2)-[:CONTAINS]->(c3)
            MERGE (d2)-[:CONTAINS]->(c4)
            
            MERGE (c1)-[:RELATED_TO {strength: 0.8}]->(c2)
            MERGE (c2)-[:PART_OF {strength: 0.9}]->(c3)
            MERGE (c3)-[:APPLIED_IN {strength: 0.7}]->(c4)
        """)
        
        print("✅ Neo4j seeding completed")
        
    except Exception as e:
        print(f"❌ Neo4j seeding failed: {e}")


async def seed_milvus_data(client):
    """Seed Milvus with sample vectors."""
    print("🌱 Seeding Milvus with sample vectors...")
    
    try:
        # Sample vector data for document chunks
        chunks = [
            {
                "id": "doc-1-chunk-1", 
                "content": "Machine learning is a subset of artificial intelligence that focuses on algorithms that can learn from data.",
                "metadata": {
                    "source_id": "doc-1",
                    "chunk_index": 0,
                    "document_title": "Sample ML Paper"
                }
            },
            {
                "id": "doc-1-chunk-2", 
                "content": "Neural networks are computing systems inspired by biological neural networks that constitute animal brains.",
                "metadata": {
                    "source_id": "doc-1",
                    "chunk_index": 1,
                    "document_title": "Sample ML Paper"
                }
            },
            {
                "id": "doc-2-chunk-1", 
                "content": "Deep learning is a subset of machine learning that uses neural networks with multiple layers.",
                "metadata": {
                    "source_id": "doc-2",
                    "chunk_index": 0,
                    "document_title": "Test Research Document"
                }
            },
            {
                "id": "doc-2-chunk-2", 
                "content": "Natural language processing enables computers to understand and process human language.",
                "metadata": {
                    "source_id": "doc-2",
                    "chunk_index": 1,
                    "document_title": "Test Research Document"
                }
            }
        ]
        
        # Store embeddings using the high-level interface
        await client.store_embeddings(chunks)
        
        print("✅ Milvus seeding completed")
        print(f"   Stored {len(chunks)} document chunks with embeddings")
        
    except Exception as e:
        print(f"❌ Milvus seeding failed: {e}")
        print("   Note: This may be expected if Milvus client is not fully implemented")


async def main():
    """Main seeding function."""
    print("🚀 Starting local database seeding...")
    
    # Ensure we're in local environment
    os.environ["ML_ENVIRONMENT"] = "local"
    
    try:
        # Get configuration and create factory
        config = get_database_config()
        factory = DatabaseClientFactory(config)
        
        print(f"📋 Using configuration: {config.__class__.__name__}")
        
        # Create clients
        postgres_client = await factory.get_relational_client()
        neo4j_client = await factory.get_graph_client()
        milvus_client = await factory.get_vector_client()
        
        # Seed databases
        await seed_postgres_data(postgres_client)
        await seed_neo4j_data(neo4j_client)
        await seed_milvus_data(milvus_client)
        
        print("🎉 Local database seeding completed successfully!")
        print("")
        print("📊 Sample data created:")
        print("   • 2 users (developer@example.com, tester@example.com)")
        print("   • 2 documents (Sample ML Paper, Test Research Document)")
        print("   • 2 conversations")
        print("   • Knowledge graph with ML concepts and relationships")
        print("   • Vector embeddings (placeholder)")
        
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())