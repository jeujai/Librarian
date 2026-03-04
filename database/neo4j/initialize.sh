#!/bin/bash
# Initialize Neo4j with constraints and sample data

set -e

NEO4J_HOST=${NEO4J_HOST:-localhost}
NEO4J_PORT=${NEO4J_PORT:-7687}
NEO4J_USER=${NEO4J_USER:-neo4j}
NEO4J_PASSWORD=${NEO4J_PASSWORD:-ml_password}

echo "Initializing Neo4j with constraints and sample data..."

# Create constraints
echo "Creating constraints..."
docker compose -f docker-compose.local.yml exec neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;
"

# Create sample data
echo "Creating sample data..."
docker compose -f docker-compose.local.yml exec neo4j cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "
CREATE (u1:User {
  id: 'user_dev_001',
  email: 'dev@multimodal-librarian.local',
  name: 'Developer User',
  created_at: datetime()
});

CREATE (d1:Document {
  id: 'doc_sample_001',
  title: 'Introduction to Machine Learning',
  filename: 'ml_intro.pdf',
  created_at: datetime()
});

CREATE (c1:Concept {
  name: 'Machine Learning',
  type: 'topic',
  confidence: 0.95
});

CREATE (u1)-[:OWNS]->(d1);
CREATE (d1)-[:CONTAINS]->(c1);
"

echo "Neo4j initialization completed successfully!"