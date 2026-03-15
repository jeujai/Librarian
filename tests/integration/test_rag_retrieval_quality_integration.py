"""
Integration tests for RAG retrieval quality improvement.

Tests the 768-dimension embedding schema for Milvus collections
and Neo4j vector indexes end-to-end against real local services.

Validates: Requirements 4.1, 4.2, 5.1, 5.2
"""

import socket
import uuid

import numpy as np
import pytest
import pytest_asyncio

TEST_COLLECTION = f"test_rag_768_{uuid.uuid4().hex[:8]}"


def _service_available(host: str, port: int) -> bool:
    """Check if a service is reachable."""
    try:
        with socket.create_connection(
            (host, port), timeout=1.0
        ):
            return True
    except (socket.error, socket.timeout):
        return False


# ============================================================
# Fixtures
# ============================================================


@pytest_asyncio.fixture
async def milvus_client():
    """Connect to local Milvus for integration testing."""
    if not _service_available("localhost", 19530):
        pytest.skip("Milvus not available on localhost:19530")

    from multimodal_librarian.clients.milvus_client import MilvusClient

    client = MilvusClient(host="localhost", port=19530)
    await client.connect()
    yield client
    await client.disconnect()


@pytest_asyncio.fixture
async def neo4j_client():
    """Connect to local Neo4j for integration testing."""
    if not _service_available("localhost", 7687):
        pytest.skip("Neo4j not available on localhost:7687")

    from multimodal_librarian.clients.neo4j_client import Neo4jClient

    client = Neo4jClient(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="ml_password",
    )
    try:
        await client.connect()
    except Exception as exc:
        pytest.skip(f"Neo4j connection failed: {exc}")
    yield client
    await client.disconnect()


# ============================================================
# Milvus Integration Tests (Requirements 4.1, 4.2)
# ============================================================


@pytest.mark.asyncio
async def test_milvus_collection_768_schema(milvus_client):
    """
    Create a Milvus collection with dim=768, insert 768-dim
    vectors, search, and verify results are returned correctly.

    Validates: Requirements 4.1, 4.2
    """
    # Ensure clean state
    await milvus_client.delete_collection(TEST_COLLECTION)

    try:
        # Create collection with 768 dimensions
        created = await milvus_client.create_collection(
            collection_name=TEST_COLLECTION,
            dimension=768,
            metric_type="L2",
        )
        assert created is True

        # Generate deterministic 768-dim vectors
        rng = np.random.default_rng(42)
        vectors = []
        for i in range(5):
            vec = rng.standard_normal(768).tolist()
            vectors.append({
                "id": f"chunk_{i}",
                "vector": vec,
                "metadata": {
                    "content": f"test content {i}",
                    "source_id": "doc_1",
                },
            })

        # Insert vectors
        inserted = await milvus_client.insert_vectors(
            TEST_COLLECTION, vectors
        )
        assert inserted is True

        # Create index (required before search in Milvus)
        await milvus_client.create_index(
            collection_name=TEST_COLLECTION,
            field_name="vector",
            index_params={
                "index_type": "FLAT",
                "metric_type": "L2",
                "params": {},
            },
        )

        # Search using the first vector as query
        results = await milvus_client.search_vectors(
            collection_name=TEST_COLLECTION,
            query_vector=vectors[0]["vector"],
            k=3,
        )

        # Verify search returns results
        assert len(results) > 0
        # Most similar to vectors[0] should be itself
        assert results[0]["id"] == "chunk_0"

    finally:
        await milvus_client.delete_collection(TEST_COLLECTION)


# ============================================================
# Neo4j Integration Tests (Requirements 5.1, 5.2)
# ============================================================


@pytest.mark.asyncio
async def test_neo4j_vector_index_768(neo4j_client):
    """
    Create the concept_embedding_index at 768 dims, insert a
    Concept node with a 768-dim embedding, query the index,
    and verify results.

    Validates: Requirements 5.1, 5.2
    """
    try:
        # Drop any pre-existing vector index
        try:
            await neo4j_client.execute_write_query(
                "DROP INDEX concept_embedding_index "
                "IF EXISTS"
            )
        except Exception:
            pass

        # Create indexes (includes 768-dim vector index)
        await neo4j_client.ensure_indexes()

        # Insert a Concept node with 768-dim embedding
        rng = np.random.default_rng(99)
        embedding = rng.standard_normal(768).tolist()

        await neo4j_client.execute_write_query(
            "CREATE (c:Concept {"
            "concept_id: $cid, "
            "name: $name, "
            "embedding: $emb"
            "})",
            {
                "cid": "test_concept_768",
                "name": "test embedding concept",
                "emb": embedding,
            },
        )

        # Query the vector index
        results = await neo4j_client.execute_query(
            "CALL db.index.vector.queryNodes("
            "'concept_embedding_index', 1, $qvec"
            ") YIELD node, score "
            "RETURN node.concept_id AS concept_id, "
            "score",
            {"qvec": embedding},
        )

        assert len(results) > 0
        assert results[0]["concept_id"] == "test_concept_768"

    finally:
        # Cleanup test data
        try:
            await neo4j_client.execute_write_query(
                "MATCH (c:Concept {concept_id: $cid}) "
                "DETACH DELETE c",
                {"cid": "test_concept_768"},
            )
        except Exception:
            pass
        try:
            await neo4j_client.execute_write_query(
                "DROP INDEX concept_embedding_index "
                "IF EXISTS"
            )
        except Exception:
            pass
