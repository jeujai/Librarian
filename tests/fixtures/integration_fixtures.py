"""
Integration test fixtures for local database testing.

This module provides pytest fixtures for comprehensive integration testing
that combines multiple database services and realistic data scenarios.
"""

import pytest
import asyncio
import logging
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from .database_fixtures import (
    postgres_client, neo4j_client, milvus_client, database_factory,
    clean_postgres_test_data, clean_neo4j_test_data, clean_milvus_test_data,
    require_all_services
)
from .sample_data_fixtures import (
    sample_users, sample_documents, sample_document_chunks,
    sample_conversations, sample_messages, sample_knowledge_nodes,
    sample_knowledge_relationships, sample_vectors,
    insert_sample_users, insert_sample_knowledge_graph, insert_sample_vectors
)

logger = logging.getLogger(__name__)


# =============================================================================
# Multi-Database Integration Fixtures
# =============================================================================

@pytest.fixture
async def integrated_database_clients(
    postgres_client,
    neo4j_client, 
    milvus_client,
    clean_postgres_test_data,
    clean_neo4j_test_data,
    clean_milvus_test_data
):
    """
    Integrated database clients for multi-database testing.
    
    This fixture provides all three database clients with clean test data,
    ready for comprehensive integration testing.
    """
    clients = {
        "postgres": postgres_client,
        "neo4j": neo4j_client,
        "milvus": milvus_client
    }
    
    # Verify all clients are connected
    for name, client in clients.items():
        health = await client.health_check()
        if health.get("status") != "healthy":
            pytest.skip(f"{name} client is not healthy: {health}")
    
    yield clients


@pytest.fixture
async def populated_test_database(
    integrated_database_clients,
    insert_sample_users,
    insert_sample_knowledge_graph,
    insert_sample_vectors
):
    """
    Fully populated test database with sample data across all services.
    
    This fixture provides a complete test environment with realistic data
    in PostgreSQL, Neo4j, and Milvus for end-to-end testing.
    """
    clients = integrated_database_clients
    
    # Insert additional relational data (documents, conversations)
    await _insert_sample_documents(clients["postgres"], insert_sample_users)
    await _insert_sample_conversations(clients["postgres"], insert_sample_users)
    
    yield {
        "clients": clients,
        "users": insert_sample_users,
        "knowledge_graph": insert_sample_knowledge_graph,
        "vectors": insert_sample_vectors
    }


# =============================================================================
# Scenario-Based Integration Fixtures
# =============================================================================

@pytest.fixture
async def document_processing_scenario(integrated_database_clients, sample_users, sample_documents):
    """
    Document processing integration scenario.
    
    This fixture sets up a realistic document processing scenario with:
    - Users uploading documents
    - Documents being processed and chunked
    - Knowledge graph extraction
    - Vector embeddings generation
    """
    clients = integrated_database_clients
    
    # Insert users
    user_data = []
    for user in sample_users[:3]:  # Use first 3 users
        await _insert_user(clients["postgres"], user)
        user_data.append(user)
    
    # Insert documents with processing pipeline simulation
    doc_data = []
    for i, doc in enumerate(sample_documents[:2]):  # Use first 2 documents
        doc.user_id = user_data[i % len(user_data)].id
        await _insert_document(clients["postgres"], doc)
        
        # Simulate knowledge extraction to Neo4j
        await _create_document_knowledge_graph(clients["neo4j"], doc)
        
        # Simulate vector embeddings to Milvus
        await _create_document_vectors(clients["milvus"], doc)
        
        doc_data.append(doc)
    
    yield {
        "clients": clients,
        "users": user_data,
        "documents": doc_data,
        "scenario": "document_processing"
    }


@pytest.fixture
async def conversation_scenario(integrated_database_clients, sample_users, sample_conversations, sample_messages):
    """
    Conversation integration scenario.
    
    This fixture sets up a realistic conversation scenario with:
    - Users having conversations
    - Messages with context retrieval
    - Knowledge graph queries
    - Vector similarity searches
    """
    clients = integrated_database_clients
    
    # Insert users
    user_data = []
    for user in sample_users[:2]:  # Use first 2 users
        await _insert_user(clients["postgres"], user)
        user_data.append(user)
    
    # Insert conversations and messages
    conv_data = []
    msg_data = []
    
    for conv in sample_conversations[:2]:  # Use first 2 conversations
        conv.user_id = user_data[0].id  # Assign to first user
        await _insert_conversation(clients["postgres"], conv)
        conv_data.append(conv)
        
        # Insert messages for this conversation
        conv_messages = [msg for msg in sample_messages if msg.thread_id == conv.thread_id]
        for msg in conv_messages[:4]:  # Limit messages for testing
            await _insert_message(clients["postgres"], msg)
            msg_data.append(msg)
    
    yield {
        "clients": clients,
        "users": user_data,
        "conversations": conv_data,
        "messages": msg_data,
        "scenario": "conversation"
    }


@pytest.fixture
async def search_scenario(integrated_database_clients, sample_vectors, sample_knowledge_nodes):
    """
    Search integration scenario.
    
    This fixture sets up a realistic search scenario with:
    - Vector similarity search in Milvus
    - Knowledge graph traversal in Neo4j
    - Metadata queries in PostgreSQL
    """
    clients = integrated_database_clients
    
    # Create test collection in Milvus
    collection_name = "test_search_vectors"
    await clients["milvus"].create_collection(
        collection_name=collection_name,
        dimension=384,
        description="Test collection for search scenario"
    )
    
    # Insert vectors (filter by dimension)
    vectors_384 = [v for v in sample_vectors if len(v.vector) == 384][:10]
    if vectors_384:
        vector_data = []
        for vec in vectors_384:
            vector_data.append({
                "id": vec.id,
                "vector": vec.vector,
                "metadata": vec.metadata
            })
        
        await clients["milvus"].insert_vectors(
            collection_name=collection_name,
            data=vector_data
        )
    
    # Insert knowledge nodes
    node_data = []
    for node in sample_knowledge_nodes[:10]:  # Use first 10 nodes
        await _insert_knowledge_node(clients["neo4j"], node)
        node_data.append(node)
    
    yield {
        "clients": clients,
        "collection_name": collection_name,
        "vectors": vectors_384,
        "knowledge_nodes": node_data,
        "scenario": "search"
    }
    
    # Cleanup
    try:
        await clients["milvus"].drop_collection(collection_name)
    except Exception:
        pass


# =============================================================================
# Performance Testing Fixtures
# =============================================================================

@pytest.fixture
async def performance_test_data(integrated_database_clients):
    """
    Performance test data for load testing scenarios.
    
    This fixture creates larger datasets for performance testing
    across all database services.
    """
    clients = integrated_database_clients
    
    # Create performance test data
    perf_data = {
        "users_created": 0,
        "documents_created": 0,
        "vectors_created": 0,
        "nodes_created": 0
    }
    
    # Create batch of users
    user_batch_size = 50
    for i in range(user_batch_size):
        user_id = f"test-perf-user-{i:04d}"
        await _insert_user(clients["postgres"], type('User', (), {
            'id': user_id,
            'username': f'perf_user_{i:04d}',
            'email': f'perf{i:04d}@test.local',
            'role': 'user',
            'is_active': True,
            'is_verified': True,
            'password_hash': f'hash_{i}',
            'salt': f'salt_{i}'
        })())
        perf_data["users_created"] += 1
    
    # Create batch of vectors
    collection_name = "test_performance_vectors"
    await clients["milvus"].create_collection(
        collection_name=collection_name,
        dimension=384,
        description="Performance test collection"
    )
    
    vector_batch_size = 1000
    batch_data = []
    for i in range(vector_batch_size):
        # Generate random normalized vector
        import random
        vector = [random.gauss(0, 1) for _ in range(384)]
        magnitude = sum(x**2 for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        
        batch_data.append({
            "id": f"test-perf-vector-{i:04d}",
            "vector": vector,
            "metadata": {"batch_id": "performance_test", "index": i}
        })
        
        # Insert in batches of 100
        if len(batch_data) >= 100:
            await clients["milvus"].insert_vectors(
                collection_name=collection_name,
                data=batch_data
            )
            perf_data["vectors_created"] += len(batch_data)
            batch_data = []
    
    # Insert remaining vectors
    if batch_data:
        await clients["milvus"].insert_vectors(
            collection_name=collection_name,
            data=batch_data
        )
        perf_data["vectors_created"] += len(batch_data)
    
    # Create batch of knowledge nodes
    node_batch_size = 200
    for i in range(node_batch_size):
        node_id = f"test-perf-node-{i:04d}"
        create_query = """
            CREATE (n:PerfTestNode {
                id: $id,
                name: $name,
                batch_id: $batch_id,
                index: $index
            })
        """
        
        await clients["neo4j"].execute_query(create_query, {
            "id": node_id,
            "name": f"Performance Test Node {i:04d}",
            "batch_id": "performance_test",
            "index": i
        })
        perf_data["nodes_created"] += 1
    
    yield {
        "clients": clients,
        "collection_name": collection_name,
        "performance_data": perf_data,
        "scenario": "performance"
    }
    
    # Cleanup performance data
    try:
        # Clean Milvus
        await clients["milvus"].drop_collection(collection_name)
        
        # Clean Neo4j
        await clients["neo4j"].execute_query(
            "MATCH (n:PerfTestNode {batch_id: 'performance_test'}) DELETE n"
        )
        
        # Clean PostgreSQL
        await clients["postgres"].execute_command(
            "DELETE FROM users WHERE username LIKE 'perf_user_%'"
        )
    except Exception as e:
        logger.warning(f"Cleanup error in performance test data: {e}")


# =============================================================================
# Error Scenario Fixtures
# =============================================================================

@pytest.fixture
async def error_handling_scenario(integrated_database_clients):
    """
    Error handling scenario for testing resilience.
    
    This fixture sets up scenarios to test error handling and recovery
    across database services.
    """
    clients = integrated_database_clients
    
    # Create test data that might cause errors
    error_scenarios = {
        "invalid_data": [],
        "constraint_violations": [],
        "connection_issues": []
    }
    
    # Test invalid data scenarios
    try:
        # Try to insert user with invalid email
        await _insert_user(clients["postgres"], type('User', (), {
            'id': 'test-invalid-user',
            'username': 'invalid_user',
            'email': 'not-an-email',  # Invalid email format
            'role': 'user',
            'is_active': True,
            'is_verified': True,
            'password_hash': 'hash',
            'salt': 'salt'
        })())
    except Exception as e:
        error_scenarios["invalid_data"].append(("postgres", "invalid_email", str(e)))
    
    # Test constraint violations
    try:
        # Try to insert duplicate user
        user_data = type('User', (), {
            'id': 'test-duplicate-user',
            'username': 'duplicate_user',
            'email': 'duplicate@test.local',
            'role': 'user',
            'is_active': True,
            'is_verified': True,
            'password_hash': 'hash',
            'salt': 'salt'
        })()
        
        await _insert_user(clients["postgres"], user_data)
        await _insert_user(clients["postgres"], user_data)  # Should fail
    except Exception as e:
        error_scenarios["constraint_violations"].append(("postgres", "duplicate_user", str(e)))
    
    yield {
        "clients": clients,
        "error_scenarios": error_scenarios,
        "scenario": "error_handling"
    }


# =============================================================================
# Helper Functions
# =============================================================================

async def _insert_user(postgres_client, user):
    """Insert a user into PostgreSQL."""
    insert_sql = """
        INSERT INTO users (
            id, username, email, password_hash, salt, role,
            is_active, is_verified, created_at
        ) VALUES (
            :id, :username, :email, :password_hash, :salt, :role,
            :is_active, :is_verified, COALESCE(:created_at, NOW())
        )
    """
    
    await postgres_client.execute_command(insert_sql, {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "password_hash": user.password_hash,
        "salt": user.salt,
        "role": user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": getattr(user, 'created_at', None)
    })


async def _insert_document(postgres_client, document):
    """Insert a document into PostgreSQL."""
    insert_sql = """
        INSERT INTO documents (
            id, user_id, title, filename, file_size, status,
            page_count, chunk_count, description, mime_type,
            upload_timestamp, processing_completed_at
        ) VALUES (
            :id, :user_id, :title, :filename, :file_size, :status,
            :page_count, :chunk_count, :description, :mime_type,
            :upload_timestamp, :processing_completed_at
        )
    """
    
    await postgres_client.execute_command(insert_sql, {
        "id": document.id,
        "user_id": document.user_id,
        "title": document.title,
        "filename": document.filename,
        "file_size": document.file_size,
        "status": document.status,
        "page_count": document.page_count,
        "chunk_count": document.chunk_count,
        "description": document.description,
        "mime_type": document.mime_type,
        "upload_timestamp": document.upload_timestamp,
        "processing_completed_at": document.processing_completed_at
    })


async def _insert_conversation(postgres_client, conversation):
    """Insert a conversation into PostgreSQL."""
    insert_sql = """
        INSERT INTO conversation_threads (
            id, user_id, title, created_at, updated_at, is_active
        ) VALUES (
            :id, :user_id, :title, :created_at, :updated_at, :is_active
        )
    """
    
    await postgres_client.execute_command(insert_sql, {
        "id": conversation.thread_id,
        "user_id": conversation.user_id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "is_active": conversation.is_active
    })


async def _insert_message(postgres_client, message):
    """Insert a message into PostgreSQL."""
    insert_sql = """
        INSERT INTO conversation_messages (
            id, thread_id, content, message_type, timestamp
        ) VALUES (
            :id, :thread_id, :content, :message_type, :timestamp
        )
    """
    
    await postgres_client.execute_command(insert_sql, {
        "id": message.id,
        "thread_id": message.thread_id,
        "content": message.content,
        "message_type": message.message_type,
        "timestamp": message.timestamp
    })


async def _insert_knowledge_node(neo4j_client, node):
    """Insert a knowledge node into Neo4j."""
    create_query = f"""
        CREATE (n:{node.label} {{
            id: $id,
            name: $name,
            node_type: $node_type
        }})
    """
    
    await neo4j_client.execute_query(create_query, {
        "id": node.id,
        "name": node.name,
        "node_type": node.node_type
    })


async def _create_document_knowledge_graph(neo4j_client, document):
    """Create knowledge graph representation of a document."""
    # Create document node
    create_doc_query = """
        CREATE (d:Document {
            id: $doc_id,
            title: $title,
            filename: $filename,
            status: $status
        })
    """
    
    await neo4j_client.execute_query(create_doc_query, {
        "doc_id": document.id,
        "title": document.title,
        "filename": document.filename,
        "status": document.status
    })
    
    # Create some concept nodes and relationships
    concepts = ["Machine Learning", "Data Science", "AI"]
    for i, concept in enumerate(concepts):
        concept_id = f"{document.id}-concept-{i}"
        
        # Create concept node
        create_concept_query = """
            CREATE (c:Concept {
                id: $concept_id,
                name: $concept_name
            })
        """
        
        await neo4j_client.execute_query(create_concept_query, {
            "concept_id": concept_id,
            "concept_name": concept
        })
        
        # Create relationship
        create_rel_query = """
            MATCH (d:Document {id: $doc_id})
            MATCH (c:Concept {id: $concept_id})
            CREATE (d)-[:CONTAINS]->(c)
        """
        
        await neo4j_client.execute_query(create_rel_query, {
            "doc_id": document.id,
            "concept_id": concept_id
        })


async def _create_document_vectors(milvus_client, document):
    """Create vector embeddings for a document."""
    collection_name = "test_document_vectors"
    
    # Create collection if it doesn't exist
    try:
        await milvus_client.create_collection(
            collection_name=collection_name,
            dimension=384,
            description="Test document vectors"
        )
    except Exception:
        # Collection might already exist
        pass
    
    # Generate some sample vectors for the document
    import random
    
    for i in range(3):  # Create 3 vectors per document
        vector = [random.gauss(0, 1) for _ in range(384)]
        magnitude = sum(x**2 for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        
        vector_data = [{
            "id": f"{document.id}-vector-{i}",
            "vector": vector,
            "metadata": {
                "document_id": document.id,
                "chunk_index": i,
                "document_title": document.title
            }
        }]
        
        await milvus_client.insert_vectors(
            collection_name=collection_name,
            data=vector_data
        )


async def _insert_sample_documents(postgres_client, users):
    """Insert sample documents for the given users."""
    from .sample_data_fixtures import SampleDocument
    
    documents = [
        SampleDocument(
            id="test-integration-doc-1",
            user_id=users[0].id,
            title="Integration Test Document 1",
            filename="integration_test_1.pdf",
            file_size=1048576,
            status="completed"
        ),
        SampleDocument(
            id="test-integration-doc-2", 
            user_id=users[1].id if len(users) > 1 else users[0].id,
            title="Integration Test Document 2",
            filename="integration_test_2.pdf",
            file_size=2097152,
            status="completed"
        )
    ]
    
    for doc in documents:
        await _insert_document(postgres_client, doc)


async def _insert_sample_conversations(postgres_client, users):
    """Insert sample conversations for the given users."""
    from .sample_data_fixtures import SampleConversation, SampleMessage
    
    conversations = [
        SampleConversation(
            thread_id="test-integration-thread-1",
            user_id=users[0].id,
            title="Integration Test Conversation 1"
        )
    ]
    
    messages = [
        SampleMessage(
            id="test-integration-msg-1",
            thread_id="test-integration-thread-1",
            content="What is machine learning?",
            message_type="USER"
        ),
        SampleMessage(
            id="test-integration-msg-2",
            thread_id="test-integration-thread-1", 
            content="Machine learning is a subset of AI that focuses on algorithms that learn from data.",
            message_type="SYSTEM"
        )
    ]
    
    for conv in conversations:
        await _insert_conversation(postgres_client, conv)
    
    for msg in messages:
        await _insert_message(postgres_client, msg)