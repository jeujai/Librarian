#!/usr/bin/env python3
"""
Document-Concept Associations Generator

This script creates associations between existing documents and concepts in the knowledge graph.
It analyzes document content and creates realistic CONTAINS relationships between documents
and relevant concepts based on content similarity and domain matching.

Usage:
    python scripts/seed-document-concept-associations.py [--max-associations N] [--reset]
    
    --max-associations N: Maximum associations per document (default: 8)
    --reset: Reset existing document-concept associations
"""

import asyncio
import argparse
import logging
import uuid
import json
import random
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
import sys
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.local_config import LocalDatabaseConfig
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DocumentConceptAssociationGenerator:
    """Generator for document-concept associations in the knowledge graph."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize the generator with database configuration."""
        self.config = config
        self.factory = DatabaseClientFactory(config)
        
        # Keywords for matching documents to concepts
        self.concept_keywords = {
            # Machine Learning concepts
            "machine_learning": [
                "machine learning", "ml", "artificial intelligence", "ai", "algorithm", "model",
                "training", "prediction", "classification", "regression", "supervised", "unsupervised"
            ],
            "neural_networks": [
                "neural network", "neural net", "nn", "deep learning", "neuron", "layer",
                "activation", "weight", "bias", "backpropagation"
            ],
            "deep_learning": [
                "deep learning", "deep neural", "cnn", "rnn", "lstm", "transformer",
                "convolutional", "recurrent", "attention"
            ],
            "supervised_learning": [
                "supervised learning", "labeled data", "training data", "classification",
                "regression", "target variable", "ground truth"
            ],
            "unsupervised_learning": [
                "unsupervised learning", "clustering", "dimensionality reduction", "pca",
                "k-means", "unlabeled data", "pattern discovery"
            ],
            "reinforcement_learning": [
                "reinforcement learning", "rl", "agent", "environment", "reward", "policy",
                "q-learning", "markov decision"
            ],
            
            # Natural Language Processing concepts
            "natural_language_processing": [
                "natural language processing", "nlp", "text processing", "language model",
                "text analysis", "computational linguistics"
            ],
            "tokenization": [
                "tokenization", "tokenize", "token", "word segmentation", "text preprocessing",
                "splitting text", "parsing"
            ],
            "named_entity_recognition": [
                "named entity recognition", "ner", "entity extraction", "entity identification",
                "person names", "organization", "location"
            ],
            "sentiment_analysis": [
                "sentiment analysis", "opinion mining", "emotion detection", "polarity",
                "positive sentiment", "negative sentiment"
            ],
            "machine_translation": [
                "machine translation", "translation", "multilingual", "language pairs",
                "source language", "target language"
            ],
            "language_model": [
                "language model", "lm", "bert", "gpt", "transformer", "pre-trained",
                "fine-tuning", "embeddings"
            ],
            
            # Computer Vision concepts
            "computer_vision": [
                "computer vision", "cv", "image processing", "visual recognition",
                "image analysis", "visual perception"
            ],
            "image_classification": [
                "image classification", "image recognition", "visual classification",
                "object recognition", "category prediction"
            ],
            "object_detection": [
                "object detection", "bounding box", "localization", "yolo", "rcnn",
                "detection algorithm"
            ],
            "convolutional_neural_network": [
                "convolutional neural network", "cnn", "convolution", "pooling", "filter",
                "feature map", "kernel"
            ],
            "face_recognition": [
                "face recognition", "facial recognition", "face detection", "biometric",
                "identity verification"
            ],
            
            # Data Science concepts
            "data_science": [
                "data science", "data analysis", "analytics", "big data", "data mining",
                "statistical analysis", "data-driven"
            ],
            "data_visualization": [
                "data visualization", "visualization", "chart", "graph", "plot",
                "dashboard", "infographic"
            ],
            "statistical_analysis": [
                "statistical analysis", "statistics", "hypothesis testing", "p-value",
                "correlation", "regression analysis"
            ],
            "exploratory_data_analysis": [
                "exploratory data analysis", "eda", "data exploration", "descriptive statistics",
                "data profiling", "summary statistics"
            ],
            "feature_engineering": [
                "feature engineering", "feature selection", "feature extraction",
                "data preprocessing", "variable transformation"
            ],
            "cross_validation": [
                "cross validation", "k-fold", "validation", "model evaluation",
                "train test split", "holdout"
            ]
        }
        
        # Document subject to concept domain mapping
        self.subject_to_domain = {
            "Machine Learning": "machine_learning",
            "Deep Learning": "machine_learning", 
            "Natural Language Processing": "natural_language_processing",
            "Computer Vision": "computer_vision",
            "Data Science": "data_science",
            "Artificial Intelligence": "machine_learning",
            "Neural Networks": "machine_learning",
            "Statistics": "data_science",
            "Analytics": "data_science",
            "Algorithms": "machine_learning"
        }
        
        # Extraction methods for different association types
        self.extraction_methods = [
            "keyword_matching",
            "content_analysis", 
            "title_analysis",
            "subject_mapping",
            "semantic_similarity",
            "domain_classification"
        ]
    
    async def generate_document_concept_associations(
        self,
        max_associations_per_document: int = 8,
        reset: bool = False
    ) -> Dict[str, Any]:
        """
        Generate associations between documents and concepts.
        
        Args:
            max_associations_per_document: Maximum number of concept associations per document
            reset: Whether to reset existing associations first
            
        Returns:
            Dictionary with created associations data
        """
        logger.info(f"Generating document-concept associations (max_per_doc={max_associations_per_document}, reset={reset})")
        
        try:
            # Get database clients
            postgres_client = await self.factory.get_relational_client()
            neo4j_client = await self.factory.get_graph_client()
            await neo4j_client.connect()
            
            # Reset associations if requested
            if reset:
                await self._reset_document_concept_associations(neo4j_client)
            
            # Get existing documents and concepts
            documents = await self._get_documents(postgres_client)
            concepts = await self._get_concepts(neo4j_client)
            
            if not documents:
                logger.warning("No documents found. Run seed-sample-documents.py first.")
                return {"associations": [], "documents_processed": 0, "concepts_available": len(concepts)}
            
            if not concepts:
                logger.warning("No concepts found. Run seed-sample-knowledge-graph.py first.")
                return {"associations": [], "documents_processed": len(documents), "concepts_available": 0}
            
            # Create document nodes in Neo4j if they don't exist
            document_nodes = await self._create_document_nodes(neo4j_client, documents)
            
            # Generate associations
            created_associations = await self._create_document_concept_associations(
                neo4j_client, document_nodes, concepts, max_associations_per_document
            )
            
            # Create chunk-concept associations
            chunk_associations = await self._create_chunk_concept_associations(
                postgres_client, neo4j_client, documents, concepts
            )
            
            logger.info(f"Successfully created {len(created_associations)} document-concept associations")
            logger.info(f"Successfully created {len(chunk_associations)} chunk-concept associations")
            
            return {
                "document_associations": created_associations,
                "chunk_associations": chunk_associations,
                "documents_processed": len(documents),
                "concepts_available": len(concepts),
                "document_nodes_created": len(document_nodes)
            }
            
        except Exception as e:
            logger.error(f"Failed to generate document-concept associations: {e}")
            raise
        finally:
            if 'neo4j_client' in locals():
                await neo4j_client.disconnect()
    
    async def _reset_document_concept_associations(self, neo4j_client) -> None:
        """Reset existing document-concept associations."""
        logger.info("Resetting existing document-concept associations")
        
        try:
            # Delete CONTAINS relationships between documents and concepts
            await neo4j_client.execute_write_query(
                "MATCH (d:Document)-[r:CONTAINS]->(c:Concept) DELETE r"
            )
            
            # Delete MENTIONS relationships between chunks and concepts
            await neo4j_client.execute_write_query(
                "MATCH (ch:Chunk)-[r:MENTIONS]->(c:Concept) DELETE r"
            )
            
            # Delete HAS_CHUNK relationships between documents and chunks
            await neo4j_client.execute_write_query(
                "MATCH (d:Document)-[r:HAS_CHUNK]->(ch:Chunk) DELETE r"
            )
            
            # Delete chunk nodes
            await neo4j_client.execute_write_query("MATCH (ch:Chunk) DELETE ch")
            
            # Delete document nodes (they will be recreated)
            await neo4j_client.execute_write_query("MATCH (d:Document) DELETE d")
            
            logger.info("Successfully reset document-concept associations")
            
        except Exception as e:
            logger.error(f"Failed to reset associations: {e}")
            raise
    
    async def _get_documents(self, postgres_client) -> List[Dict[str, Any]]:
        """Get existing documents from PostgreSQL."""
        try:
            async with postgres_client.get_async_session() as session:
                result = await session.execute("""
                    SELECT id, title, description, filename, doc_metadata, 
                           page_count, status, created_at
                    FROM documents 
                    WHERE status = 'completed'
                    ORDER BY created_at DESC
                    LIMIT 100
                """)
                
                documents = []
                for row in result.fetchall():
                    # Parse metadata JSON
                    metadata = {}
                    if row[4]:  # doc_metadata
                        try:
                            metadata = json.loads(row[4])
                        except json.JSONDecodeError:
                            metadata = {}
                    
                    documents.append({
                        "id": row[0],
                        "title": row[1],
                        "description": row[2] or "",
                        "filename": row[3],
                        "metadata": metadata,
                        "page_count": row[5] or 0,
                        "status": row[6],
                        "created_at": row[7]
                    })
                
                logger.info(f"Retrieved {len(documents)} completed documents")
                return documents
                
        except Exception as e:
            logger.error(f"Failed to get documents: {e}")
            return []
    
    async def _get_concepts(self, neo4j_client) -> List[Dict[str, Any]]:
        """Get existing concepts from Neo4j."""
        try:
            query = """
            MATCH (c:Concept)
            RETURN id(c) as id, c.name as name, c.type as type, 
                   c.category as category, c.domain as domain,
                   c.description as description, c.aliases as aliases
            ORDER BY c.name
            """
            
            result = await neo4j_client.execute_query(query)
            
            concepts = []
            for record in result:
                concepts.append({
                    "id": str(record["id"]),
                    "name": record["name"],
                    "type": record["type"],
                    "category": record["category"],
                    "domain": record["domain"],
                    "description": record["description"] or "",
                    "aliases": record["aliases"] or []
                })
            
            logger.info(f"Retrieved {len(concepts)} concepts")
            return concepts
            
        except Exception as e:
            logger.error(f"Failed to get concepts: {e}")
            return []
    
    async def _create_document_nodes(self, neo4j_client, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create document nodes in Neo4j."""
        logger.info(f"Creating {len(documents)} document nodes in Neo4j")
        
        document_nodes = []
        
        for doc in documents:
            try:
                # Create document properties
                doc_props = {
                    "document_id": doc["id"],
                    "title": doc["title"],
                    "description": doc["description"],
                    "filename": doc["filename"],
                    "page_count": doc["page_count"],
                    "status": doc["status"],
                    "created_at": doc["created_at"].isoformat() if doc["created_at"] else datetime.utcnow().isoformat(),
                    "content_type": doc["metadata"].get("content_type", "general"),
                    "subject": doc["metadata"].get("subject", ""),
                    "keywords": doc["metadata"].get("keywords", []),
                    "language": doc["metadata"].get("language", "en")
                }
                
                # Create document node
                node_id = await neo4j_client.create_node(["Document"], doc_props)
                
                document_node = {
                    "neo4j_id": node_id,
                    "document_id": doc["id"],
                    "title": doc["title"],
                    "description": doc["description"],
                    "subject": doc_props["subject"],
                    "keywords": doc_props["keywords"],
                    "content_type": doc_props["content_type"]
                }
                
                document_nodes.append(document_node)
                logger.debug(f"Created document node: {doc['title']}")
                
            except Exception as e:
                logger.warning(f"Failed to create document node for {doc['title']}: {e}")
        
        return document_nodes
    
    async def _create_document_concept_associations(
        self, 
        neo4j_client, 
        document_nodes: List[Dict[str, Any]], 
        concepts: List[Dict[str, Any]],
        max_associations: int
    ) -> List[Dict[str, Any]]:
        """Create CONTAINS relationships between documents and concepts."""
        logger.info("Creating document-concept associations")
        
        created_associations = []
        
        for doc_node in document_nodes:
            try:
                # Find relevant concepts for this document
                relevant_concepts = self._find_relevant_concepts(doc_node, concepts)
                
                # Limit to max associations
                if len(relevant_concepts) > max_associations:
                    # Sort by relevance score and take top N
                    relevant_concepts.sort(key=lambda x: x["relevance_score"], reverse=True)
                    relevant_concepts = relevant_concepts[:max_associations]
                
                # Create CONTAINS relationships
                for concept_match in relevant_concepts:
                    concept = concept_match["concept"]
                    
                    # Create relationship properties
                    rel_props = {
                        "confidence": concept_match["relevance_score"],
                        "extraction_method": concept_match["extraction_method"],
                        "frequency": concept_match.get("frequency", 1),
                        "position": concept_match.get("position", "content"),
                        "created_at": datetime.utcnow().isoformat(),
                        "source": "document_analysis"
                    }
                    
                    # Create CONTAINS relationship
                    rel_id = await neo4j_client.create_relationship(
                        doc_node["neo4j_id"],
                        concept["id"],
                        "CONTAINS",
                        rel_props
                    )
                    
                    association_data = {
                        "id": rel_id,
                        "document_title": doc_node["title"],
                        "concept_name": concept["name"],
                        "confidence": rel_props["confidence"],
                        "extraction_method": rel_props["extraction_method"],
                        "concept_domain": concept["domain"]
                    }
                    
                    created_associations.append(association_data)
                    logger.debug(f"Associated document '{doc_node['title']}' with concept '{concept['name']}' (confidence: {rel_props['confidence']:.3f})")
                
            except Exception as e:
                logger.warning(f"Failed to create associations for document {doc_node['title']}: {e}")
        
        return created_associations
    
    def _find_relevant_concepts(self, document: Dict[str, Any], concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find concepts relevant to a document based on content analysis."""
        relevant_concepts = []
        
        # Prepare document text for analysis
        doc_text = self._prepare_document_text(document)
        doc_text_lower = doc_text.lower()
        
        for concept in concepts:
            relevance_score = 0.0
            extraction_methods = []
            frequency = 0
            position = "content"
            
            # 1. Direct name matching
            concept_name_lower = concept["name"].lower()
            if concept_name_lower in doc_text_lower:
                relevance_score += 0.8
                extraction_methods.append("direct_name_match")
                frequency += doc_text_lower.count(concept_name_lower)
                
                # Check if in title (higher relevance)
                if concept_name_lower in document["title"].lower():
                    relevance_score += 0.2
                    position = "title"
            
            # 2. Alias matching
            for alias in concept.get("aliases", []):
                if alias.lower() in doc_text_lower:
                    relevance_score += 0.6
                    extraction_methods.append("alias_match")
                    frequency += doc_text_lower.count(alias.lower())
            
            # 3. Keyword matching
            concept_key = concept["name"].lower().replace(" ", "_")
            if concept_key in self.concept_keywords:
                keywords = self.concept_keywords[concept_key]
                keyword_matches = 0
                
                for keyword in keywords:
                    if keyword.lower() in doc_text_lower:
                        keyword_matches += 1
                        frequency += doc_text_lower.count(keyword.lower())
                
                if keyword_matches > 0:
                    keyword_score = min(0.7, keyword_matches * 0.1)
                    relevance_score += keyword_score
                    extraction_methods.append("keyword_matching")
            
            # 4. Subject/domain matching
            doc_subject = document.get("subject", "")
            if doc_subject and concept.get("domain"):
                domain_mapping = self.subject_to_domain.get(doc_subject)
                if domain_mapping == concept["domain"]:
                    relevance_score += 0.4
                    extraction_methods.append("subject_mapping")
            
            # 5. Content type matching
            content_type = document.get("content_type", "")
            if content_type == "technical" and concept.get("type") in ["algorithm", "technique"]:
                relevance_score += 0.2
                extraction_methods.append("content_type_match")
            elif content_type == "academic" and concept.get("type") in ["concept", "theory"]:
                relevance_score += 0.2
                extraction_methods.append("content_type_match")
            
            # 6. Description similarity (simple keyword overlap)
            if concept.get("description"):
                concept_desc_words = set(re.findall(r'\w+', concept["description"].lower()))
                doc_desc_words = set(re.findall(r'\w+', document.get("description", "").lower()))
                
                if concept_desc_words and doc_desc_words:
                    overlap = len(concept_desc_words.intersection(doc_desc_words))
                    if overlap > 0:
                        similarity_score = min(0.3, overlap * 0.05)
                        relevance_score += similarity_score
                        extraction_methods.append("description_similarity")
            
            # Only include concepts with meaningful relevance
            if relevance_score > 0.1:
                # Normalize relevance score
                relevance_score = min(1.0, relevance_score)
                
                relevant_concepts.append({
                    "concept": concept,
                    "relevance_score": round(relevance_score, 3),
                    "extraction_method": ",".join(extraction_methods) if extraction_methods else "unknown",
                    "frequency": frequency,
                    "position": position
                })
        
        return relevant_concepts
    
    def _prepare_document_text(self, document: Dict[str, Any]) -> str:
        """Prepare document text for analysis by combining title, description, and keywords."""
        text_parts = []
        
        # Add title (most important)
        if document.get("title"):
            text_parts.append(document["title"])
        
        # Add description
        if document.get("description"):
            text_parts.append(document["description"])
        
        # Add subject
        if document.get("subject"):
            text_parts.append(document["subject"])
        
        # Add keywords
        keywords = document.get("keywords", [])
        if keywords:
            text_parts.extend(keywords)
        
        return " ".join(text_parts)
    
    async def _create_chunk_concept_associations(
        self,
        postgres_client,
        neo4j_client,
        documents: List[Dict[str, Any]],
        concepts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create chunk nodes and MENTIONS relationships with concepts."""
        logger.info("Creating chunk-concept associations")
        
        created_associations = []
        
        # Get document chunks from PostgreSQL
        try:
            async with postgres_client.get_async_session() as session:
                result = await session.execute("""
                    SELECT dc.id, dc.document_id, dc.chunk_index, dc.content, 
                           dc.page_number, dc.section_title, dc.chunk_type
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    WHERE d.status = 'completed'
                    ORDER BY dc.document_id, dc.chunk_index
                    LIMIT 500
                """)
                
                chunks = []
                for row in result.fetchall():
                    chunks.append({
                        "id": row[0],
                        "document_id": row[1],
                        "chunk_index": row[2],
                        "content": row[3] or "",
                        "page_number": row[4] or 1,
                        "section_title": row[5] or "",
                        "chunk_type": row[6] or "text"
                    })
                
                logger.info(f"Retrieved {len(chunks)} document chunks")
                
        except Exception as e:
            logger.warning(f"Failed to get document chunks: {e}")
            chunks = []
        
        if not chunks:
            return created_associations
        
        # Create chunk nodes and associations
        for chunk in chunks:
            try:
                # Find the corresponding document node
                doc_query = "MATCH (d:Document {document_id: $doc_id}) RETURN id(d) as doc_node_id"
                doc_result = await neo4j_client.execute_query(doc_query, {"doc_id": chunk["document_id"]})
                
                if not doc_result:
                    continue
                
                doc_node_id = str(doc_result[0]["doc_node_id"])
                
                # Create chunk properties
                chunk_props = {
                    "chunk_id": chunk["id"],
                    "document_id": chunk["document_id"],
                    "chunk_index": chunk["chunk_index"],
                    "content": chunk["content"][:1000],  # Limit content length
                    "page_number": chunk["page_number"],
                    "section_title": chunk["section_title"],
                    "chunk_type": chunk["chunk_type"],
                    "created_at": datetime.utcnow().isoformat()
                }
                
                # Create chunk node
                chunk_node_id = await neo4j_client.create_node(["Chunk"], chunk_props)
                
                # Create HAS_CHUNK relationship between document and chunk
                await neo4j_client.create_relationship(
                    doc_node_id,
                    chunk_node_id,
                    "HAS_CHUNK",
                    {
                        "chunk_order": chunk["chunk_index"],
                        "extraction_method": "document_processing"
                    }
                )
                
                # Find concepts mentioned in this chunk
                chunk_concepts = self._find_chunk_concepts(chunk, concepts)
                
                # Create MENTIONS relationships
                for concept_match in chunk_concepts[:5]:  # Limit to 5 concepts per chunk
                    concept = concept_match["concept"]
                    
                    rel_props = {
                        "confidence": concept_match["confidence"],
                        "frequency": concept_match["frequency"],
                        "position": concept_match.get("position", "content"),
                        "created_at": datetime.utcnow().isoformat(),
                        "extraction_method": "chunk_analysis"
                    }
                    
                    # Create MENTIONS relationship
                    rel_id = await neo4j_client.create_relationship(
                        chunk_node_id,
                        concept["id"],
                        "MENTIONS",
                        rel_props
                    )
                    
                    association_data = {
                        "id": rel_id,
                        "chunk_id": chunk["id"],
                        "concept_name": concept["name"],
                        "confidence": rel_props["confidence"],
                        "page_number": chunk["page_number"],
                        "concept_domain": concept["domain"]
                    }
                    
                    created_associations.append(association_data)
                
                logger.debug(f"Created chunk node and associations for chunk {chunk['id']}")
                
            except Exception as e:
                logger.warning(f"Failed to create chunk associations for chunk {chunk['id']}: {e}")
        
        return created_associations
    
    def _find_chunk_concepts(self, chunk: Dict[str, Any], concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find concepts mentioned in a specific chunk."""
        chunk_concepts = []
        chunk_content = chunk["content"].lower()
        
        for concept in concepts:
            confidence = 0.0
            frequency = 0
            position = "content"
            
            # Direct name matching
            concept_name_lower = concept["name"].lower()
            if concept_name_lower in chunk_content:
                confidence += 0.9
                frequency += chunk_content.count(concept_name_lower)
                
                # Check if in section title
                if concept_name_lower in chunk.get("section_title", "").lower():
                    confidence += 0.1
                    position = "section_title"
            
            # Alias matching
            for alias in concept.get("aliases", []):
                if alias.lower() in chunk_content:
                    confidence += 0.7
                    frequency += chunk_content.count(alias.lower())
            
            # Keyword matching (more selective for chunks)
            concept_key = concept["name"].lower().replace(" ", "_")
            if concept_key in self.concept_keywords:
                keywords = self.concept_keywords[concept_key]
                keyword_matches = 0
                
                for keyword in keywords:
                    if keyword.lower() in chunk_content:
                        keyword_matches += 1
                        frequency += chunk_content.count(keyword.lower())
                
                if keyword_matches > 0:
                    keyword_score = min(0.5, keyword_matches * 0.1)
                    confidence += keyword_score
            
            # Only include concepts with meaningful confidence
            if confidence > 0.3:
                confidence = min(1.0, confidence)
                
                chunk_concepts.append({
                    "concept": concept,
                    "confidence": round(confidence, 3),
                    "frequency": frequency,
                    "position": position
                })
        
        # Sort by confidence
        chunk_concepts.sort(key=lambda x: x["confidence"], reverse=True)
        return chunk_concepts
    
    async def close(self) -> None:
        """Close database connections."""
        await self.factory.close()


async def main():
    """Main function to run the document-concept association generator."""
    parser = argparse.ArgumentParser(description="Generate document-concept associations for local development")
    parser.add_argument("--max-associations", type=int, default=8, help="Maximum associations per document")
    parser.add_argument("--reset", action="store_true", help="Reset existing associations first")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    try:
        config = LocalDatabaseConfig()
        logger.info(f"Loaded configuration for {config.database_type} environment")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1
    
    # Generate document-concept associations
    generator = DocumentConceptAssociationGenerator(config)
    
    try:
        result = await generator.generate_document_concept_associations(
            max_associations_per_document=args.max_associations,
            reset=args.reset
        )
        
        doc_associations = result["document_associations"]
        chunk_associations = result["chunk_associations"]
        
        print(f"\n✅ Successfully created document-concept associations!")
        print(f"📄 Documents processed: {result['documents_processed']}")
        print(f"🔬 Concepts available: {result['concepts_available']}")
        print(f"🏗️  Document nodes created: {result['document_nodes_created']}")
        print(f"🔗 Document-concept associations: {len(doc_associations)}")
        print(f"📝 Chunk-concept associations: {len(chunk_associations)}")
        
        # Show association statistics
        if doc_associations:
            # Domain distribution
            domain_counts = {}
            confidence_sum = 0
            
            for assoc in doc_associations:
                domain = assoc["concept_domain"]
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                confidence_sum += assoc["confidence"]
            
            avg_confidence = confidence_sum / len(doc_associations)
            
            print(f"\n📊 Association Statistics:")
            print("=" * 50)
            print(f"Average confidence: {avg_confidence:.3f}")
            
            print(f"\n🔬 Domain Distribution:")
            for domain, count in sorted(domain_counts.items(), key=lambda x: x[1], reverse=True):
                domain_display = domain.replace('_', ' ').title()
                print(f"  {domain_display:30} | {count:3d} associations")
            
            # Show extraction methods
            method_counts = {}
            for assoc in doc_associations:
                methods = assoc["extraction_method"].split(",")
                for method in methods:
                    method_counts[method] = method_counts.get(method, 0) + 1
            
            print(f"\n🔍 Extraction Methods:")
            for method, count in sorted(method_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {method:25} | {count:3d} uses")
        
        # Show sample associations
        if doc_associations:
            print(f"\n📋 Sample Document-Concept Associations:")
            print("=" * 80)
            for assoc in doc_associations[:6]:
                conf_bar = "█" * int(assoc["confidence"] * 10)
                print(f"📄 {assoc['document_title'][:30]:30} → 🔬 {assoc['concept_name'][:25]:25} | {conf_bar} {assoc['confidence']:.3f}")
        
        if chunk_associations:
            print(f"\n📝 Sample Chunk-Concept Associations:")
            print("=" * 80)
            for assoc in chunk_associations[:6]:
                conf_bar = "█" * int(assoc["confidence"] * 10)
                print(f"📝 Chunk {assoc['chunk_id'][:8]:8} (p.{assoc['page_number']:2d}) → 🔬 {assoc['concept_name'][:25]:25} | {conf_bar} {assoc['confidence']:.3f}")
        
        print(f"\n💡 Associations created based on content analysis, keyword matching, and domain classification")
        print(f"🔍 Use Neo4j Browser to explore: MATCH (d:Document)-[:CONTAINS]->(c:Concept) RETURN d, c LIMIT 25")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate document-concept associations: {e}")
        return 1
    
    finally:
        await generator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)