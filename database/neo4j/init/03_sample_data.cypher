// Neo4j Initialization Script - Sample Data
// This script creates sample data for local development and testing

// Create sample users
CREATE (u1:User {
  id: 'user_dev_001',
  email: 'dev@multimodal-librarian.local',
  name: 'Developer User',
  created_at: datetime(),
  role: 'developer'
});

CREATE (u2:User {
  id: 'user_test_001',
  email: 'test@multimodal-librarian.local',
  name: 'Test User',
  created_at: datetime(),
  role: 'user'
});

// Create sample documents
CREATE (d1:Document {
  id: 'doc_sample_001',
  title: 'Introduction to Machine Learning',
  filename: 'ml_intro.pdf',
  content: 'This document provides an introduction to machine learning concepts and algorithms.',
  created_at: datetime(),
  file_size: 1024000,
  page_count: 25,
  status: 'processed'
});

CREATE (d2:Document {
  id: 'doc_sample_002',
  title: 'Neural Networks and Deep Learning',
  filename: 'neural_networks.pdf',
  content: 'A comprehensive guide to neural networks and deep learning architectures.',
  created_at: datetime(),
  file_size: 2048000,
  page_count: 45,
  status: 'processed'
});

// Create sample concepts
CREATE (c1:Concept {
  name: 'Machine Learning',
  type: 'topic',
  category: 'technology',
  confidence: 0.95,
  description: 'A subset of artificial intelligence that focuses on algorithms that can learn from data.'
});

CREATE (c2:Concept {
  name: 'Neural Networks',
  type: 'subtopic',
  category: 'technology',
  confidence: 0.92,
  description: 'Computing systems inspired by biological neural networks.'
});

CREATE (c3:Concept {
  name: 'Deep Learning',
  type: 'subtopic',
  category: 'technology',
  confidence: 0.90,
  description: 'Machine learning methods based on artificial neural networks with representation learning.'
});

CREATE (c4:Concept {
  name: 'Supervised Learning',
  type: 'method',
  category: 'algorithm',
  confidence: 0.88,
  description: 'Machine learning task of learning a function that maps input to output based on example pairs.'
});

// Create sample chunks
CREATE (ch1:Chunk {
  id: 'chunk_001',
  content: 'Machine learning is a method of data analysis that automates analytical model building.',
  position: 1,
  page_number: 1,
  embedding_id: 'emb_001'
});

CREATE (ch2:Chunk {
  id: 'chunk_002',
  content: 'Neural networks are computing systems vaguely inspired by the biological neural networks.',
  position: 2,
  page_number: 2,
  embedding_id: 'emb_002'
});

// Create sample conversations
CREATE (conv1:Conversation {
  id: 'conv_001',
  title: 'Learning about ML basics',
  created_at: datetime(),
  updated_at: datetime(),
  message_count: 3
});

// Create relationships between entities
CREATE (u1)-[:OWNS]->(d1);
CREATE (u1)-[:OWNS]->(d2);
CREATE (u2)-[:ACCESSED]->(d1);

CREATE (d1)-[:CONTAINS]->(c1);
CREATE (d1)-[:CONTAINS]->(c4);
CREATE (d2)-[:CONTAINS]->(c2);
CREATE (d2)-[:CONTAINS]->(c3);

CREATE (c1)-[:RELATED_TO {strength: 0.8}]->(c2);
CREATE (c2)-[:RELATED_TO {strength: 0.9}]->(c3);
CREATE (c1)-[:INCLUDES {strength: 0.7}]->(c4);

CREATE (d1)-[:HAS_CHUNK]->(ch1);
CREATE (d2)-[:HAS_CHUNK]->(ch2);

CREATE (ch1)-[:MENTIONS]->(c1);
CREATE (ch2)-[:MENTIONS]->(c2);

CREATE (u1)-[:PARTICIPATED_IN]->(conv1);
CREATE (conv1)-[:ABOUT]->(d1);

// Create some sample graph patterns for testing GDS algorithms
// Create a small knowledge network for testing graph algorithms
CREATE (topic1:Topic {name: 'Artificial Intelligence', level: 1});
CREATE (topic2:Topic {name: 'Machine Learning', level: 2});
CREATE (topic3:Topic {name: 'Deep Learning', level: 3});
CREATE (topic4:Topic {name: 'Computer Vision', level: 3});
CREATE (topic5:Topic {name: 'Natural Language Processing', level: 3});

CREATE (topic1)-[:CONTAINS]->(topic2);
CREATE (topic2)-[:CONTAINS]->(topic3);
CREATE (topic2)-[:CONTAINS]->(topic4);
CREATE (topic2)-[:CONTAINS]->(topic5);
CREATE (topic3)-[:APPLIES_TO]->(topic4);
CREATE (topic3)-[:APPLIES_TO]->(topic5);

// Add some metrics for testing
CREATE (metric1:Metric {
  name: 'document_processing_time',
  value: 45.2,
  unit: 'seconds',
  timestamp: datetime()
});

CREATE (metric2:Metric {
  name: 'query_response_time',
  value: 1.8,
  unit: 'seconds',
  timestamp: datetime()
});

CREATE (d1)-[:HAS_METRIC]->(metric1);
CREATE (conv1)-[:HAS_METRIC]->(metric2);