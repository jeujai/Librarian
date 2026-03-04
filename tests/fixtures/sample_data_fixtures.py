"""
Sample data fixtures for local database testing.

This module provides pytest fixtures that generate realistic sample data
for testing database operations, including users, documents, conversations,
and knowledge graph data.
"""

import pytest
import uuid
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


# =============================================================================
# Data Classes for Sample Data
# =============================================================================

@dataclass
class SampleUser:
    """Sample user data for testing."""
    id: str
    username: str
    email: str
    role: str
    is_active: bool = True
    is_verified: bool = True
    created_at: Optional[datetime] = None
    password_hash: Optional[str] = None
    salt: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.password_hash is None:
            self.password_hash = f"hash_{self.username}"
        if self.salt is None:
            self.salt = f"salt_{self.username}"


@dataclass
class SampleDocument:
    """Sample document data for testing."""
    id: str
    user_id: str
    title: str
    filename: str
    file_size: int
    status: str = "completed"
    page_count: int = 10
    chunk_count: Optional[int] = None
    description: Optional[str] = None
    mime_type: str = "application/pdf"
    upload_timestamp: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.upload_timestamp is None:
            self.upload_timestamp = datetime.utcnow() - timedelta(days=random.randint(1, 30))
        if self.processing_completed_at is None and self.status == "completed":
            self.processing_completed_at = self.upload_timestamp + timedelta(minutes=random.randint(1, 60))
        if self.chunk_count is None and self.status == "completed":
            self.chunk_count = self.page_count * random.randint(2, 5)
        if self.metadata is None:
            self.metadata = {
                "content_type": "technical",
                "language": "en",
                "keywords": ["test", "sample", "document"]
            }


@dataclass
class SampleDocumentChunk:
    """Sample document chunk data for testing."""
    id: str
    document_id: str
    chunk_index: int
    content: str
    page_number: int
    chunk_type: str = "text"
    section_title: Optional[str] = None
    created_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.section_title is None:
            self.section_title = f"Section {(self.chunk_index // 5) + 1}"
        if self.metadata is None:
            self.metadata = {
                "word_count": len(self.content.split()),
                "character_count": len(self.content),
                "extraction_confidence": random.uniform(0.8, 1.0)
            }


@dataclass
class SampleConversation:
    """Sample conversation data for testing."""
    thread_id: str
    user_id: str
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0
    is_active: bool = True
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow() - timedelta(hours=random.randint(1, 72))
        if self.updated_at is None:
            self.updated_at = self.created_at + timedelta(minutes=random.randint(5, 120))


@dataclass
class SampleMessage:
    """Sample conversation message data for testing."""
    id: str
    thread_id: str
    content: str
    message_type: str  # "USER" or "SYSTEM"
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {
                "response_time": random.uniform(0.5, 3.0) if self.message_type == "SYSTEM" else None,
                "model_used": "gpt-4" if self.message_type == "SYSTEM" else None
            }


@dataclass
class SampleKnowledgeNode:
    """Sample knowledge graph node data for testing."""
    id: str
    label: str
    name: str
    node_type: str
    properties: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.properties is None:
            self.properties = {
                "created_at": datetime.utcnow().isoformat(),
                "source": "test_data"
            }


@dataclass
class SampleKnowledgeRelationship:
    """Sample knowledge graph relationship data for testing."""
    id: str
    from_node_id: str
    to_node_id: str
    relationship_type: str
    properties: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.properties is None:
            self.properties = {
                "created_at": datetime.utcnow().isoformat(),
                "confidence": random.uniform(0.7, 1.0)
            }


@dataclass
class SampleVector:
    """Sample vector data for testing."""
    id: str
    vector: List[float]
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {
                "source_type": "document_chunk",
                "created_at": datetime.utcnow().isoformat()
            }


# =============================================================================
# Sample Data Generation Fixtures
# =============================================================================

@pytest.fixture
def sample_users() -> List[SampleUser]:
    """Generate sample users for testing."""
    users = [
        SampleUser(
            id="test-user-admin",
            username="test_admin",
            email="admin@test.local",
            role="admin"
        ),
        SampleUser(
            id="test-user-researcher",
            username="test_researcher",
            email="researcher@test.local",
            role="ml_researcher"
        ),
        SampleUser(
            id="test-user-regular",
            username="test_user",
            email="user@test.local",
            role="user"
        ),
        SampleUser(
            id="test-user-readonly",
            username="test_readonly",
            email="readonly@test.local",
            role="read_only"
        ),
    ]
    
    # Add some additional random users
    for i in range(5, 10):
        users.append(SampleUser(
            id=f"test-user-{i:03d}",
            username=f"test_user_{i:03d}",
            email=f"user{i:03d}@test.local",
            role=random.choice(["user", "ml_researcher", "read_only"]),
            is_verified=random.choice([True, False])
        ))
    
    return users


@pytest.fixture
def sample_documents(sample_users) -> List[SampleDocument]:
    """Generate sample documents for testing."""
    document_templates = [
        {
            "title": "Machine Learning Fundamentals",
            "filename": "ml_fundamentals.pdf",
            "description": "Comprehensive guide to ML concepts",
            "page_count": 150,
            "file_size": 3145728,  # 3MB
        },
        {
            "title": "Deep Learning with PyTorch",
            "filename": "pytorch_guide.pdf", 
            "description": "Practical PyTorch implementation guide",
            "page_count": 200,
            "file_size": 4194304,  # 4MB
        },
        {
            "title": "Natural Language Processing",
            "filename": "nlp_handbook.pdf",
            "description": "NLP techniques and applications",
            "page_count": 180,
            "file_size": 3670016,  # 3.5MB
        },
        {
            "title": "Computer Vision Applications",
            "filename": "cv_applications.pdf",
            "description": "Modern computer vision approaches",
            "page_count": 120,
            "file_size": 2621440,  # 2.5MB
        },
        {
            "title": "Data Science Ethics",
            "filename": "ds_ethics.pdf",
            "description": "Ethical considerations in data science",
            "page_count": 80,
            "file_size": 1572864,  # 1.5MB
        }
    ]
    
    documents = []
    
    for i, template in enumerate(document_templates):
        # Assign to random user
        user = random.choice(sample_users)
        
        # Create document with some having different statuses
        status = "completed" if i < 4 else random.choice(["completed", "processing", "uploaded", "failed"])
        
        doc = SampleDocument(
            id=f"test-doc-{i+1:03d}",
            user_id=user.id,
            title=template["title"],
            filename=template["filename"],
            description=template["description"],
            page_count=template["page_count"],
            file_size=template["file_size"],
            status=status
        )
        documents.append(doc)
    
    return documents


@pytest.fixture
def sample_document_chunks(sample_documents) -> List[SampleDocumentChunk]:
    """Generate sample document chunks for testing."""
    chunks = []
    
    # Sample content templates
    content_templates = [
        "Machine learning is a subset of artificial intelligence that focuses on algorithms that can learn from data.",
        "Neural networks are computing systems inspired by biological neural networks that constitute animal brains.",
        "Deep learning uses multiple layers to progressively extract higher-level features from raw input.",
        "Natural language processing combines computational linguistics with statistical and machine learning methods.",
        "Computer vision is an interdisciplinary field that deals with how computers can gain understanding from images.",
        "Data preprocessing is a crucial step that involves cleaning and transforming raw data into a suitable format.",
        "Feature engineering is the process of selecting and transforming variables for machine learning models.",
        "Model evaluation involves assessing the performance of machine learning models using various metrics.",
        "Cross-validation is a technique used to assess how well a model will generalize to independent datasets.",
        "Overfitting occurs when a model learns the training data too well and fails to generalize to new data."
    ]
    
    for doc in sample_documents:
        if doc.status != "completed":
            continue  # Only create chunks for completed documents
        
        chunk_count = min(doc.chunk_count or 10, 20)  # Limit chunks for testing
        
        for i in range(chunk_count):
            content = random.choice(content_templates)
            content += f" This content is from {doc.title}, page {(i // 3) + 1}."
            
            chunk = SampleDocumentChunk(
                id=f"test-chunk-{doc.id}-{i+1:03d}",
                document_id=doc.id,
                chunk_index=i,
                content=content,
                page_number=(i // 3) + 1,  # Roughly 3 chunks per page
                chunk_type=random.choice(["text", "text", "text", "image", "table"])  # Mostly text
            )
            chunks.append(chunk)
    
    return chunks


@pytest.fixture
def sample_conversations(sample_users) -> List[SampleConversation]:
    """Generate sample conversations for testing."""
    conversations = []
    
    conversation_titles = [
        "Machine Learning Questions",
        "Deep Learning Discussion",
        "NLP Implementation Help",
        "Computer Vision Project",
        "Data Science Ethics Debate",
        "PyTorch Tutorial Questions",
        "Model Evaluation Strategies",
        "Feature Engineering Tips"
    ]
    
    for i, title in enumerate(conversation_titles):
        user = random.choice(sample_users)
        
        conv = SampleConversation(
            thread_id=f"test-thread-{i+1:03d}",
            user_id=user.id,
            title=title,
            message_count=random.randint(2, 10)
        )
        conversations.append(conv)
    
    return conversations


@pytest.fixture
def sample_messages(sample_conversations) -> List[SampleMessage]:
    """Generate sample conversation messages for testing."""
    messages = []
    
    # Sample user questions
    user_questions = [
        "What is the difference between supervised and unsupervised learning?",
        "How do I implement a neural network in PyTorch?",
        "What are the best practices for data preprocessing?",
        "Can you explain how convolutional neural networks work?",
        "What evaluation metrics should I use for classification?",
        "How do I handle overfitting in my model?",
        "What is the role of activation functions in neural networks?",
        "How do I choose the right algorithm for my problem?"
    ]
    
    # Sample system responses
    system_responses = [
        "Supervised learning uses labeled data to train models, while unsupervised learning finds patterns in unlabeled data.",
        "To implement a neural network in PyTorch, you'll need to define your model class, loss function, and optimizer.",
        "Data preprocessing best practices include handling missing values, scaling features, and encoding categorical variables.",
        "Convolutional neural networks use filters to detect local features in images through convolution operations.",
        "For classification, common metrics include accuracy, precision, recall, F1-score, and AUC-ROC.",
        "To handle overfitting, you can use techniques like regularization, dropout, early stopping, and data augmentation.",
        "Activation functions introduce non-linearity to neural networks, enabling them to learn complex patterns.",
        "Algorithm choice depends on your data size, problem type, interpretability needs, and performance requirements."
    ]
    
    for conv in sample_conversations:
        message_count = conv.message_count
        base_time = conv.created_at
        
        for i in range(message_count):
            # Alternate between user and system messages
            if i % 2 == 0:
                # User message
                message = SampleMessage(
                    id=f"test-msg-{conv.thread_id}-{i+1:03d}",
                    thread_id=conv.thread_id,
                    content=random.choice(user_questions),
                    message_type="USER",
                    timestamp=base_time + timedelta(minutes=i * 5)
                )
            else:
                # System message
                message = SampleMessage(
                    id=f"test-msg-{conv.thread_id}-{i+1:03d}",
                    thread_id=conv.thread_id,
                    content=random.choice(system_responses),
                    message_type="SYSTEM",
                    timestamp=base_time + timedelta(minutes=i * 5 + 2)
                )
            
            messages.append(message)
    
    return messages


@pytest.fixture
def sample_knowledge_nodes() -> List[SampleKnowledgeNode]:
    """Generate sample knowledge graph nodes for testing."""
    nodes = []
    
    # Document nodes
    document_nodes = [
        ("test-doc-node-1", "Document", "Machine Learning Fundamentals", "Document"),
        ("test-doc-node-2", "Document", "Deep Learning Guide", "Document"),
        ("test-doc-node-3", "Document", "NLP Handbook", "Document"),
    ]
    
    # Concept nodes
    concept_nodes = [
        ("test-concept-1", "Concept", "Machine Learning", "Concept"),
        ("test-concept-2", "Concept", "Neural Networks", "Concept"),
        ("test-concept-3", "Concept", "Deep Learning", "Concept"),
        ("test-concept-4", "Concept", "Natural Language Processing", "Concept"),
        ("test-concept-5", "Concept", "Computer Vision", "Concept"),
        ("test-concept-6", "Concept", "Supervised Learning", "Concept"),
        ("test-concept-7", "Concept", "Unsupervised Learning", "Concept"),
    ]
    
    # Author nodes
    author_nodes = [
        ("test-author-1", "Author", "Dr. Jane Smith", "Author"),
        ("test-author-2", "Author", "Prof. John Doe", "Author"),
        ("test-author-3", "Author", "Dr. Alice Johnson", "Author"),
    ]
    
    all_node_data = document_nodes + concept_nodes + author_nodes
    
    for node_id, label, name, node_type in all_node_data:
        node = SampleKnowledgeNode(
            id=node_id,
            label=label,
            name=name,
            node_type=node_type,
            properties={
                "created_at": datetime.utcnow().isoformat(),
                "source": "test_data",
                "description": f"Test {node_type.lower()}: {name}"
            }
        )
        nodes.append(node)
    
    return nodes


@pytest.fixture
def sample_knowledge_relationships(sample_knowledge_nodes) -> List[SampleKnowledgeRelationship]:
    """Generate sample knowledge graph relationships for testing."""
    relationships = []
    
    # Define relationships between nodes
    relationship_data = [
        # Document -> Concept relationships
        ("test-doc-node-1", "test-concept-1", "CONTAINS"),
        ("test-doc-node-1", "test-concept-6", "CONTAINS"),
        ("test-doc-node-2", "test-concept-2", "CONTAINS"),
        ("test-doc-node-2", "test-concept-3", "CONTAINS"),
        ("test-doc-node-3", "test-concept-4", "CONTAINS"),
        
        # Concept -> Concept relationships
        ("test-concept-3", "test-concept-1", "SUBSET_OF"),
        ("test-concept-6", "test-concept-1", "SUBSET_OF"),
        ("test-concept-7", "test-concept-1", "SUBSET_OF"),
        ("test-concept-2", "test-concept-3", "RELATED_TO"),
        ("test-concept-4", "test-concept-2", "USES"),
        
        # Document -> Author relationships
        ("test-doc-node-1", "test-author-1", "AUTHORED_BY"),
        ("test-doc-node-2", "test-author-2", "AUTHORED_BY"),
        ("test-doc-node-3", "test-author-3", "AUTHORED_BY"),
    ]
    
    for i, (from_id, to_id, rel_type) in enumerate(relationship_data):
        rel = SampleKnowledgeRelationship(
            id=f"test-rel-{i+1:03d}",
            from_node_id=from_id,
            to_node_id=to_id,
            relationship_type=rel_type,
            properties={
                "created_at": datetime.utcnow().isoformat(),
                "confidence": random.uniform(0.8, 1.0),
                "source": "test_data"
            }
        )
        relationships.append(rel)
    
    return relationships


@pytest.fixture
def sample_vectors() -> List[SampleVector]:
    """Generate sample vectors for testing."""
    vectors = []
    
    # Generate vectors with different dimensions for testing
    dimensions = [384, 768, 1536]  # Common embedding dimensions
    
    for i in range(20):  # Generate 20 sample vectors
        dim = random.choice(dimensions)
        
        # Generate normalized random vector
        vector = [random.gauss(0, 1) for _ in range(dim)]
        # Normalize the vector
        magnitude = sum(x**2 for x in vector) ** 0.5
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        
        vec = SampleVector(
            id=f"test-vector-{i+1:03d}",
            vector=vector,
            metadata={
                "source_type": random.choice(["document_chunk", "query", "concept"]),
                "dimension": dim,
                "created_at": datetime.utcnow().isoformat(),
                "source_id": f"test-source-{i+1:03d}"
            }
        )
        vectors.append(vec)
    
    return vectors


# =============================================================================
# Composite Sample Data Fixtures
# =============================================================================

@pytest.fixture
def complete_sample_dataset(
    sample_users,
    sample_documents,
    sample_document_chunks,
    sample_conversations,
    sample_messages,
    sample_knowledge_nodes,
    sample_knowledge_relationships,
    sample_vectors
):
    """
    Complete sample dataset for comprehensive testing.
    
    This fixture provides all types of sample data in a single dictionary
    for tests that need access to multiple data types.
    """
    return {
        "users": sample_users,
        "documents": sample_documents,
        "document_chunks": sample_document_chunks,
        "conversations": sample_conversations,
        "messages": sample_messages,
        "knowledge_nodes": sample_knowledge_nodes,
        "knowledge_relationships": sample_knowledge_relationships,
        "vectors": sample_vectors
    }


# =============================================================================
# Data Insertion Helper Fixtures
# =============================================================================

@pytest.fixture
async def insert_sample_users(postgres_client, sample_users):
    """
    Insert sample users into PostgreSQL for testing.
    
    This fixture inserts the sample users into the database and
    provides a cleanup function to remove them after the test.
    """
    inserted_users = []
    
    try:
        for user in sample_users:
            # Insert user into database
            insert_sql = """
                INSERT INTO users (
                    id, username, email, password_hash, salt, role,
                    is_active, is_verified, created_at
                ) VALUES (
                    :id, :username, :email, :password_hash, :salt, :role,
                    :is_active, :is_verified, :created_at
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
                "created_at": user.created_at
            })
            
            inserted_users.append(user.id)
        
        yield sample_users
        
    finally:
        # Cleanup: remove inserted users
        if inserted_users:
            cleanup_sql = "DELETE FROM users WHERE id = ANY(:user_ids)"
            await postgres_client.execute_command(cleanup_sql, {"user_ids": inserted_users})


@pytest.fixture
async def insert_sample_knowledge_graph(neo4j_client, sample_knowledge_nodes, sample_knowledge_relationships):
    """
    Insert sample knowledge graph data into Neo4j for testing.
    
    This fixture inserts the sample nodes and relationships into Neo4j
    and provides cleanup after the test.
    """
    inserted_node_ids = []
    inserted_rel_ids = []
    
    try:
        # Insert nodes
        for node in sample_knowledge_nodes:
            create_node_query = f"""
                CREATE (n:{node.label} {{
                    id: $id,
                    name: $name,
                    node_type: $node_type,
                    properties: $properties
                }})
                RETURN n.id as node_id
            """
            
            result = await neo4j_client.execute_query(create_node_query, {
                "id": node.id,
                "name": node.name,
                "node_type": node.node_type,
                "properties": json.dumps(node.properties)
            })
            
            if result:
                inserted_node_ids.append(node.id)
        
        # Insert relationships
        for rel in sample_knowledge_relationships:
            create_rel_query = f"""
                MATCH (from_node {{id: $from_id}})
                MATCH (to_node {{id: $to_id}})
                CREATE (from_node)-[r:{rel.relationship_type} {{
                    id: $rel_id,
                    properties: $properties
                }}]->(to_node)
                RETURN r.id as rel_id
            """
            
            result = await neo4j_client.execute_query(create_rel_query, {
                "from_id": rel.from_node_id,
                "to_id": rel.to_node_id,
                "rel_id": rel.id,
                "properties": json.dumps(rel.properties)
            })
            
            if result:
                inserted_rel_ids.append(rel.id)
        
        yield {
            "nodes": sample_knowledge_nodes,
            "relationships": sample_knowledge_relationships
        }
        
    finally:
        # Cleanup: remove inserted data
        if inserted_node_ids:
            cleanup_query = """
                MATCH (n) 
                WHERE n.id IN $node_ids 
                DETACH DELETE n
            """
            await neo4j_client.execute_query(cleanup_query, {"node_ids": inserted_node_ids})


@pytest.fixture
async def insert_sample_vectors(milvus_client, sample_vectors):
    """
    Insert sample vectors into Milvus for testing.
    
    This fixture creates a test collection and inserts sample vectors,
    providing cleanup after the test.
    """
    collection_name = "test_sample_vectors"
    inserted_vector_ids = []
    
    try:
        # Create test collection
        await milvus_client.create_collection(
            collection_name=collection_name,
            dimension=384,  # Use standard dimension
            description="Test collection for sample vectors"
        )
        
        # Filter vectors by dimension and insert
        vectors_384 = [v for v in sample_vectors if len(v.vector) == 384]
        
        if vectors_384:
            # Prepare data for insertion
            vector_data = []
            for vec in vectors_384:
                vector_data.append({
                    "id": vec.id,
                    "vector": vec.vector,
                    "metadata": json.dumps(vec.metadata)
                })
            
            # Insert vectors
            result = await milvus_client.insert_vectors(
                collection_name=collection_name,
                data=vector_data
            )
            
            if result and "ids" in result:
                inserted_vector_ids = result["ids"]
        
        yield {
            "collection_name": collection_name,
            "vectors": vectors_384,
            "inserted_ids": inserted_vector_ids
        }
        
    finally:
        # Cleanup: drop test collection
        try:
            await milvus_client.drop_collection(collection_name)
        except Exception:
            # Ignore errors during cleanup
            pass