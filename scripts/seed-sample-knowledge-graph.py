#!/usr/bin/env python3
"""
Sample Knowledge Graph Test Data Generator

This script generates sample concepts, relationships, and knowledge graph data
for local development. It creates realistic knowledge graph structures with
concepts, document-concept associations, and multi-hop relationships.

Usage:
    python scripts/seed-sample-knowledge-graph.py [--concepts N] [--reset] [--with-relationships]
    
    --concepts N: Number of concepts to create (default: 50)
    --reset: Drop existing knowledge graph data before creating new ones
    --with-relationships: Generate relationships between concepts
"""

import asyncio
import argparse
import logging
import uuid
import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
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


class SampleKnowledgeGraphGenerator:
    """Generator for sample knowledge graph concepts and relationships."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize the generator with database configuration."""
        self.config = config
        self.factory = DatabaseClientFactory(config)
        
        # Sample concept templates organized by domain
        self.concept_domains = {
            "machine_learning": {
                "concepts": [
                    {"name": "Machine Learning", "type": "field", "category": "technology", "description": "A subset of artificial intelligence that enables computers to learn from data"},
                    {"name": "Supervised Learning", "type": "technique", "category": "ml_method", "description": "Learning from labeled training data"},
                    {"name": "Unsupervised Learning", "type": "technique", "category": "ml_method", "description": "Finding patterns in unlabeled data"},
                    {"name": "Reinforcement Learning", "type": "technique", "category": "ml_method", "description": "Learning through interaction and feedback"},
                    {"name": "Neural Networks", "type": "algorithm", "category": "ml_algorithm", "description": "Computing systems inspired by biological neural networks"},
                    {"name": "Deep Learning", "type": "technique", "category": "ml_method", "description": "Machine learning using deep neural networks"},
                    {"name": "Convolutional Neural Network", "type": "algorithm", "category": "ml_algorithm", "description": "Neural network designed for processing grid-like data such as images"},
                    {"name": "Recurrent Neural Network", "type": "algorithm", "category": "ml_algorithm", "description": "Neural network designed for sequential data"},
                    {"name": "Transformer", "type": "algorithm", "category": "ml_algorithm", "description": "Neural network architecture using attention mechanisms"},
                    {"name": "Gradient Descent", "type": "algorithm", "category": "optimization", "description": "Optimization algorithm for minimizing loss functions"},
                    {"name": "Backpropagation", "type": "algorithm", "category": "training", "description": "Algorithm for training neural networks using gradient descent"},
                    {"name": "Overfitting", "type": "concept", "category": "ml_problem", "description": "When a model performs well on training data but poorly on new data"},
                    {"name": "Cross Validation", "type": "technique", "category": "evaluation", "description": "Method for assessing model performance on unseen data"},
                    {"name": "Feature Engineering", "type": "technique", "category": "preprocessing", "description": "Process of selecting and transforming variables for machine learning"},
                    {"name": "Regularization", "type": "technique", "category": "training", "description": "Techniques to prevent overfitting in machine learning models"}
                ],
                "relationships": [
                    ("Machine Learning", "INCLUDES", "Supervised Learning"),
                    ("Machine Learning", "INCLUDES", "Unsupervised Learning"),
                    ("Machine Learning", "INCLUDES", "Reinforcement Learning"),
                    ("Deep Learning", "IS_SUBSET_OF", "Machine Learning"),
                    ("Neural Networks", "USED_IN", "Deep Learning"),
                    ("Convolutional Neural Network", "IS_TYPE_OF", "Neural Networks"),
                    ("Recurrent Neural Network", "IS_TYPE_OF", "Neural Networks"),
                    ("Transformer", "IS_TYPE_OF", "Neural Networks"),
                    ("Gradient Descent", "USED_IN", "Backpropagation"),
                    ("Backpropagation", "USED_FOR", "Neural Networks"),
                    ("Overfitting", "PREVENTED_BY", "Regularization"),
                    ("Cross Validation", "HELPS_DETECT", "Overfitting"),
                    ("Feature Engineering", "IMPROVES", "Machine Learning"),
                    ("Regularization", "APPLIED_TO", "Neural Networks")
                ]
            },
            "natural_language_processing": {
                "concepts": [
                    {"name": "Natural Language Processing", "type": "field", "category": "technology", "description": "Field of AI focused on interaction between computers and human language"},
                    {"name": "Tokenization", "type": "technique", "category": "preprocessing", "description": "Process of breaking text into individual tokens"},
                    {"name": "Named Entity Recognition", "type": "task", "category": "nlp_task", "description": "Identifying and classifying named entities in text"},
                    {"name": "Part-of-Speech Tagging", "type": "task", "category": "nlp_task", "description": "Assigning grammatical categories to words"},
                    {"name": "Sentiment Analysis", "type": "task", "category": "nlp_task", "description": "Determining emotional tone or opinion in text"},
                    {"name": "Machine Translation", "type": "task", "category": "nlp_task", "description": "Automatically translating text from one language to another"},
                    {"name": "Text Summarization", "type": "task", "category": "nlp_task", "description": "Creating concise summaries of longer texts"},
                    {"name": "Question Answering", "type": "task", "category": "nlp_task", "description": "Automatically answering questions posed in natural language"},
                    {"name": "Language Model", "type": "model", "category": "nlp_model", "description": "Statistical model that predicts probability of word sequences"},
                    {"name": "BERT", "type": "model", "category": "nlp_model", "description": "Bidirectional Encoder Representations from Transformers"},
                    {"name": "GPT", "type": "model", "category": "nlp_model", "description": "Generative Pre-trained Transformer"},
                    {"name": "Word Embeddings", "type": "technique", "category": "representation", "description": "Dense vector representations of words"},
                    {"name": "Attention Mechanism", "type": "technique", "category": "architecture", "description": "Method for focusing on relevant parts of input"},
                    {"name": "Seq2Seq", "type": "architecture", "category": "model_architecture", "description": "Sequence-to-sequence model architecture"}
                ],
                "relationships": [
                    ("Natural Language Processing", "INCLUDES", "Named Entity Recognition"),
                    ("Natural Language Processing", "INCLUDES", "Sentiment Analysis"),
                    ("Natural Language Processing", "INCLUDES", "Machine Translation"),
                    ("Tokenization", "PREREQUISITE_FOR", "Named Entity Recognition"),
                    ("Part-of-Speech Tagging", "HELPS", "Named Entity Recognition"),
                    ("Language Model", "USED_FOR", "Machine Translation"),
                    ("BERT", "IS_TYPE_OF", "Language Model"),
                    ("GPT", "IS_TYPE_OF", "Language Model"),
                    ("Transformer", "USED_IN", "BERT"),
                    ("Transformer", "USED_IN", "GPT"),
                    ("Attention Mechanism", "CORE_OF", "Transformer"),
                    ("Word Embeddings", "INPUT_TO", "Language Model"),
                    ("Seq2Seq", "USED_FOR", "Machine Translation"),
                    ("Question Answering", "USES", "Language Model")
                ]
            },
            "computer_vision": {
                "concepts": [
                    {"name": "Computer Vision", "type": "field", "category": "technology", "description": "Field of AI that enables computers to interpret visual information"},
                    {"name": "Image Classification", "type": "task", "category": "cv_task", "description": "Categorizing images into predefined classes"},
                    {"name": "Object Detection", "type": "task", "category": "cv_task", "description": "Identifying and locating objects in images"},
                    {"name": "Semantic Segmentation", "type": "task", "category": "cv_task", "description": "Classifying each pixel in an image"},
                    {"name": "Face Recognition", "type": "task", "category": "cv_task", "description": "Identifying or verifying faces in images"},
                    {"name": "Image Generation", "type": "task", "category": "cv_task", "description": "Creating new images using AI models"},
                    {"name": "Feature Extraction", "type": "technique", "category": "preprocessing", "description": "Identifying important characteristics in images"},
                    {"name": "Edge Detection", "type": "technique", "category": "preprocessing", "description": "Identifying boundaries between objects in images"},
                    {"name": "ResNet", "type": "model", "category": "cv_model", "description": "Residual Neural Network architecture"},
                    {"name": "YOLO", "type": "model", "category": "cv_model", "description": "You Only Look Once object detection model"},
                    {"name": "GAN", "type": "model", "category": "generative_model", "description": "Generative Adversarial Network"},
                    {"name": "U-Net", "type": "model", "category": "cv_model", "description": "Convolutional network for biomedical image segmentation"},
                    {"name": "Transfer Learning", "type": "technique", "category": "training", "description": "Using pre-trained models for new tasks"}
                ],
                "relationships": [
                    ("Computer Vision", "INCLUDES", "Image Classification"),
                    ("Computer Vision", "INCLUDES", "Object Detection"),
                    ("Computer Vision", "INCLUDES", "Semantic Segmentation"),
                    ("Convolutional Neural Network", "USED_FOR", "Image Classification"),
                    ("Feature Extraction", "PREREQUISITE_FOR", "Image Classification"),
                    ("Edge Detection", "TYPE_OF", "Feature Extraction"),
                    ("ResNet", "IS_TYPE_OF", "Convolutional Neural Network"),
                    ("YOLO", "USED_FOR", "Object Detection"),
                    ("U-Net", "USED_FOR", "Semantic Segmentation"),
                    ("GAN", "USED_FOR", "Image Generation"),
                    ("Transfer Learning", "APPLIED_TO", "Computer Vision"),
                    ("Face Recognition", "USES", "Convolutional Neural Network"),
                    ("Object Detection", "MORE_COMPLEX_THAN", "Image Classification")
                ]
            },
            "data_science": {
                "concepts": [
                    {"name": "Data Science", "type": "field", "category": "technology", "description": "Interdisciplinary field using scientific methods to extract knowledge from data"},
                    {"name": "Data Mining", "type": "technique", "category": "analysis", "description": "Process of discovering patterns in large datasets"},
                    {"name": "Statistical Analysis", "type": "technique", "category": "analysis", "description": "Collection and analysis of data to identify patterns and trends"},
                    {"name": "Data Visualization", "type": "technique", "category": "presentation", "description": "Graphical representation of data and information"},
                    {"name": "Exploratory Data Analysis", "type": "technique", "category": "analysis", "description": "Analyzing datasets to summarize main characteristics"},
                    {"name": "Hypothesis Testing", "type": "technique", "category": "statistics", "description": "Statistical method for testing assumptions about data"},
                    {"name": "Regression Analysis", "type": "technique", "category": "statistics", "description": "Statistical method for modeling relationships between variables"},
                    {"name": "Clustering", "type": "technique", "category": "unsupervised", "description": "Grouping similar data points together"},
                    {"name": "Dimensionality Reduction", "type": "technique", "category": "preprocessing", "description": "Reducing the number of features while preserving information"},
                    {"name": "A/B Testing", "type": "technique", "category": "experimentation", "description": "Comparing two versions to determine which performs better"},
                    {"name": "Big Data", "type": "concept", "category": "data_type", "description": "Datasets that are too large or complex for traditional processing"},
                    {"name": "Data Pipeline", "type": "system", "category": "infrastructure", "description": "Series of data processing steps"}
                ],
                "relationships": [
                    ("Data Science", "INCLUDES", "Data Mining"),
                    ("Data Science", "INCLUDES", "Statistical Analysis"),
                    ("Data Science", "INCLUDES", "Data Visualization"),
                    ("Machine Learning", "SUBSET_OF", "Data Science"),
                    ("Exploratory Data Analysis", "USES", "Data Visualization"),
                    ("Hypothesis Testing", "PART_OF", "Statistical Analysis"),
                    ("Regression Analysis", "TYPE_OF", "Statistical Analysis"),
                    ("Clustering", "TYPE_OF", "Unsupervised Learning"),
                    ("Dimensionality Reduction", "HELPS", "Data Visualization"),
                    ("A/B Testing", "USES", "Statistical Analysis"),
                    ("Big Data", "REQUIRES", "Data Pipeline"),
                    ("Feature Engineering", "PART_OF", "Data Science")
                ]
            }
        }
        
        # Relationship types and their properties
        self.relationship_types = {
            "IS_TYPE_OF": {"strength": 0.9, "bidirectional": False, "description": "Taxonomic relationship"},
            "IS_SUBSET_OF": {"strength": 0.85, "bidirectional": False, "description": "Subset relationship"},
            "INCLUDES": {"strength": 0.8, "bidirectional": False, "description": "Containment relationship"},
            "USED_IN": {"strength": 0.7, "bidirectional": False, "description": "Usage relationship"},
            "USED_FOR": {"strength": 0.7, "bidirectional": False, "description": "Purpose relationship"},
            "APPLIED_TO": {"strength": 0.6, "bidirectional": False, "description": "Application relationship"},
            "HELPS": {"strength": 0.6, "bidirectional": False, "description": "Assistance relationship"},
            "PREREQUISITE_FOR": {"strength": 0.8, "bidirectional": False, "description": "Dependency relationship"},
            "RELATED_TO": {"strength": 0.5, "bidirectional": True, "description": "General relationship"},
            "SIMILAR_TO": {"strength": 0.6, "bidirectional": True, "description": "Similarity relationship"},
            "OPPOSITE_OF": {"strength": 0.7, "bidirectional": True, "description": "Opposition relationship"},
            "PART_OF": {"strength": 0.8, "bidirectional": False, "description": "Component relationship"},
            "CORE_OF": {"strength": 0.9, "bidirectional": False, "description": "Essential component relationship"},
            "MORE_COMPLEX_THAN": {"strength": 0.6, "bidirectional": False, "description": "Complexity relationship"},
            "PREVENTS": {"strength": 0.7, "bidirectional": False, "description": "Prevention relationship"},
            "PREVENTED_BY": {"strength": 0.7, "bidirectional": False, "description": "Prevention relationship (reverse)"},
            "HELPS_DETECT": {"strength": 0.6, "bidirectional": False, "description": "Detection assistance relationship"},
            "IMPROVES": {"strength": 0.6, "bidirectional": False, "description": "Improvement relationship"},
            "REQUIRES": {"strength": 0.8, "bidirectional": False, "description": "Requirement relationship"}
        }
    
    async def generate_knowledge_graph(
        self, 
        concept_count: int = 50, 
        reset: bool = False, 
        with_relationships: bool = True
    ) -> Dict[str, Any]:
        """
        Generate sample knowledge graph with concepts and relationships.
        
        Args:
            concept_count: Total number of concepts to create
            reset: Whether to reset existing knowledge graph data first
            with_relationships: Whether to generate relationships between concepts
            
        Returns:
            Dictionary with created concepts and relationships data
        """
        logger.info(f"Generating knowledge graph with {concept_count} concepts (reset={reset}, with_relationships={with_relationships})")
        
        try:
            # Get Neo4j client
            neo4j_client = await self.factory.get_graph_client()
            await neo4j_client.connect()
            
            # Reset knowledge graph if requested
            if reset:
                await self._reset_knowledge_graph(neo4j_client)
            
            # Create concepts
            created_concepts = await self._create_concepts(neo4j_client, concept_count)
            
            # Create relationships if requested
            created_relationships = []
            if with_relationships and created_concepts:
                created_relationships = await self._create_relationships(neo4j_client, created_concepts)
            
            # Create additional cross-domain relationships
            if with_relationships and len(created_concepts) > 10:
                cross_domain_relationships = await self._create_cross_domain_relationships(neo4j_client, created_concepts)
                created_relationships.extend(cross_domain_relationships)
            
            logger.info(f"Successfully created {len(created_concepts)} concepts and {len(created_relationships)} relationships")
            
            return {
                "concepts": created_concepts,
                "relationships": created_relationships,
                "domains": list(self.concept_domains.keys()),
                "relationship_types": list(self.relationship_types.keys())
            }
            
        except Exception as e:
            logger.error(f"Failed to generate knowledge graph: {e}")
            raise
        finally:
            if 'neo4j_client' in locals():
                await neo4j_client.disconnect()
    
    async def _reset_knowledge_graph(self, neo4j_client) -> None:
        """Reset existing knowledge graph data."""
        logger.info("Resetting existing knowledge graph data")
        
        try:
            # Delete all relationships first
            await neo4j_client.execute_write_query("MATCH ()-[r]->() DELETE r")
            
            # Delete all concept nodes
            await neo4j_client.execute_write_query("MATCH (c:Concept) DELETE c")
            
            # Delete all topic nodes
            await neo4j_client.execute_write_query("MATCH (t:Topic) DELETE t")
            
            logger.info("Successfully reset knowledge graph data")
            
        except Exception as e:
            logger.error(f"Failed to reset knowledge graph: {e}")
            raise
    
    async def _create_concepts(self, neo4j_client, concept_count: int) -> List[Dict[str, Any]]:
        """Create sample concepts from all domains."""
        logger.info(f"Creating {concept_count} concepts")
        
        created_concepts = []
        concepts_per_domain = concept_count // len(self.concept_domains)
        remaining_concepts = concept_count % len(self.concept_domains)
        
        for domain_name, domain_data in self.concept_domains.items():
            domain_concepts = domain_data["concepts"]
            
            # Calculate how many concepts to create for this domain
            domain_count = concepts_per_domain
            if remaining_concepts > 0:
                domain_count += 1
                remaining_concepts -= 1
            
            # Create concepts for this domain
            for i in range(min(domain_count, len(domain_concepts))):
                concept_template = domain_concepts[i]
                
                # Create concept properties
                concept_props = {
                    "name": concept_template["name"],
                    "type": concept_template["type"],
                    "category": concept_template["category"],
                    "description": concept_template["description"],
                    "domain": domain_name,
                    "confidence": round(random.uniform(0.8, 1.0), 3),
                    "created_at": datetime.utcnow().isoformat(),
                    "source": "sample_data",
                    "aliases": self._generate_aliases(concept_template["name"]),
                    "external_ids": {
                        "wikipedia": f"wiki_{concept_template['name'].lower().replace(' ', '_')}",
                        "dbpedia": f"dbpedia_{concept_template['name'].lower().replace(' ', '_')}"
                    }
                }
                
                # Create concept node
                try:
                    node_id = await neo4j_client.create_node(["Concept"], concept_props)
                    
                    concept_data = {
                        "id": node_id,
                        "name": concept_props["name"],
                        "type": concept_props["type"],
                        "category": concept_props["category"],
                        "domain": domain_name,
                        "description": concept_props["description"]
                    }
                    
                    created_concepts.append(concept_data)
                    logger.debug(f"Created concept: {concept_props['name']} ({concept_props['type']})")
                    
                except Exception as e:
                    logger.warning(f"Failed to create concept {concept_template['name']}: {e}")
            
            # Generate additional random concepts if needed
            if domain_count > len(domain_concepts):
                additional_count = domain_count - len(domain_concepts)
                for i in range(additional_count):
                    random_concept = self._generate_random_concept(domain_name, i + len(domain_concepts))
                    
                    try:
                        node_id = await neo4j_client.create_node(["Concept"], random_concept)
                        
                        concept_data = {
                            "id": node_id,
                            "name": random_concept["name"],
                            "type": random_concept["type"],
                            "category": random_concept["category"],
                            "domain": domain_name,
                            "description": random_concept["description"]
                        }
                        
                        created_concepts.append(concept_data)
                        logger.debug(f"Created random concept: {random_concept['name']} ({random_concept['type']})")
                        
                    except Exception as e:
                        logger.warning(f"Failed to create random concept: {e}")
        
        return created_concepts
    
    def _generate_aliases(self, concept_name: str) -> List[str]:
        """Generate aliases for a concept."""
        aliases = []
        
        # Add acronym if applicable
        words = concept_name.split()
        if len(words) > 1:
            acronym = ''.join(word[0].upper() for word in words if word[0].isupper() or len(word) > 3)
            if len(acronym) >= 2:
                aliases.append(acronym)
        
        # Add variations
        if "Neural Network" in concept_name:
            aliases.extend(["NN", "Neural Net"])
        elif "Machine Learning" in concept_name:
            aliases.extend(["ML", "Machine Learning"])
        elif "Natural Language Processing" in concept_name:
            aliases.extend(["NLP"])
        elif "Computer Vision" in concept_name:
            aliases.extend(["CV"])
        elif "Artificial Intelligence" in concept_name:
            aliases.extend(["AI"])
        
        return aliases[:3]  # Limit to 3 aliases
    
    def _generate_random_concept(self, domain: str, index: int) -> Dict[str, Any]:
        """Generate a random concept for a domain."""
        
        concept_types = ["technique", "algorithm", "model", "concept", "task", "tool"]
        categories = {
            "machine_learning": ["ml_method", "ml_algorithm", "optimization", "evaluation"],
            "natural_language_processing": ["nlp_task", "nlp_model", "preprocessing", "representation"],
            "computer_vision": ["cv_task", "cv_model", "preprocessing", "architecture"],
            "data_science": ["analysis", "statistics", "visualization", "infrastructure"]
        }
        
        concept_type = random.choice(concept_types)
        category = random.choice(categories.get(domain, ["general"]))
        
        name = f"{domain.replace('_', ' ').title()} {concept_type.title()} {index:02d}"
        
        return {
            "name": name,
            "type": concept_type,
            "category": category,
            "description": f"Sample {concept_type} in {domain.replace('_', ' ')} domain",
            "domain": domain,
            "confidence": round(random.uniform(0.7, 0.9), 3),
            "created_at": datetime.utcnow().isoformat(),
            "source": "generated_sample",
            "aliases": [],
            "external_ids": {}
        }
    
    async def _create_relationships(self, neo4j_client, concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create relationships between concepts based on domain templates."""
        logger.info("Creating relationships between concepts")
        
        created_relationships = []
        
        # Create relationships within each domain
        for domain_name, domain_data in self.concept_domains.items():
            domain_concepts = [c for c in concepts if c["domain"] == domain_name]
            domain_relationships = domain_data.get("relationships", [])
            
            # Create concept name to ID mapping for this domain
            concept_map = {c["name"]: c["id"] for c in domain_concepts}
            
            for from_name, rel_type, to_name in domain_relationships:
                if from_name in concept_map and to_name in concept_map:
                    try:
                        # Get relationship properties
                        rel_props = self.relationship_types.get(rel_type, {})
                        
                        # Create relationship properties
                        relationship_props = {
                            "strength": rel_props.get("strength", 0.5),
                            "relationship_type": rel_type,
                            "source": "domain_template",
                            "bidirectional": rel_props.get("bidirectional", False),
                            "description": rel_props.get("description", ""),
                            "created_at": datetime.utcnow().isoformat(),
                            "domain": domain_name
                        }
                        
                        # Create relationship
                        rel_id = await neo4j_client.create_relationship(
                            concept_map[from_name],
                            concept_map[to_name],
                            rel_type,
                            relationship_props
                        )
                        
                        relationship_data = {
                            "id": rel_id,
                            "from_concept": from_name,
                            "to_concept": to_name,
                            "type": rel_type,
                            "strength": relationship_props["strength"],
                            "domain": domain_name
                        }
                        
                        created_relationships.append(relationship_data)
                        logger.debug(f"Created relationship: {from_name} -{rel_type}-> {to_name}")
                        
                        # Create bidirectional relationship if specified
                        if rel_props.get("bidirectional", False):
                            reverse_rel_id = await neo4j_client.create_relationship(
                                concept_map[to_name],
                                concept_map[from_name],
                                rel_type,
                                relationship_props
                            )
                            
                            reverse_relationship_data = {
                                "id": reverse_rel_id,
                                "from_concept": to_name,
                                "to_concept": from_name,
                                "type": rel_type,
                                "strength": relationship_props["strength"],
                                "domain": domain_name
                            }
                            
                            created_relationships.append(reverse_relationship_data)
                            logger.debug(f"Created reverse relationship: {to_name} -{rel_type}-> {from_name}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to create relationship {from_name} -{rel_type}-> {to_name}: {e}")
        
        return created_relationships
    
    async def _create_cross_domain_relationships(self, neo4j_client, concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create relationships between concepts from different domains."""
        logger.info("Creating cross-domain relationships")
        
        created_relationships = []
        
        # Define cross-domain relationship patterns
        cross_domain_patterns = [
            # ML and NLP connections
            ("Machine Learning", "INCLUDES", "Natural Language Processing"),
            ("Neural Networks", "USED_IN", "Language Model"),
            ("Deep Learning", "APPLIED_TO", "Natural Language Processing"),
            ("Transformer", "USED_IN", "BERT"),
            ("Attention Mechanism", "PART_OF", "Transformer"),
            
            # ML and CV connections
            ("Machine Learning", "INCLUDES", "Computer Vision"),
            ("Convolutional Neural Network", "SPECIALIZED_FOR", "Computer Vision"),
            ("Deep Learning", "APPLIED_TO", "Computer Vision"),
            ("Transfer Learning", "USED_IN", "Computer Vision"),
            
            # Data Science connections
            ("Data Science", "INCLUDES", "Machine Learning"),
            ("Statistical Analysis", "FOUNDATION_OF", "Machine Learning"),
            ("Feature Engineering", "PART_OF", "Data Science"),
            ("Data Visualization", "HELPS", "Exploratory Data Analysis"),
            
            # General AI connections
            ("Artificial Intelligence", "INCLUDES", "Machine Learning"),
            ("Artificial Intelligence", "INCLUDES", "Natural Language Processing"),
            ("Artificial Intelligence", "INCLUDES", "Computer Vision")
        ]
        
        # Create concept name to concept mapping
        concept_map = {c["name"]: c for c in concepts}
        
        for from_name, rel_type, to_name in cross_domain_patterns:
            if from_name in concept_map and to_name in concept_map:
                from_concept = concept_map[from_name]
                to_concept = concept_map[to_name]
                
                # Skip if concepts are from the same domain
                if from_concept["domain"] == to_concept["domain"]:
                    continue
                
                try:
                    # Get relationship properties
                    rel_props = self.relationship_types.get(rel_type, {})
                    
                    # Create relationship properties
                    relationship_props = {
                        "strength": rel_props.get("strength", 0.6),
                        "relationship_type": rel_type,
                        "source": "cross_domain",
                        "bidirectional": rel_props.get("bidirectional", False),
                        "description": rel_props.get("description", "Cross-domain relationship"),
                        "created_at": datetime.utcnow().isoformat(),
                        "from_domain": from_concept["domain"],
                        "to_domain": to_concept["domain"]
                    }
                    
                    # Create relationship
                    rel_id = await neo4j_client.create_relationship(
                        from_concept["id"],
                        to_concept["id"],
                        rel_type,
                        relationship_props
                    )
                    
                    relationship_data = {
                        "id": rel_id,
                        "from_concept": from_name,
                        "to_concept": to_name,
                        "type": rel_type,
                        "strength": relationship_props["strength"],
                        "cross_domain": True,
                        "from_domain": from_concept["domain"],
                        "to_domain": to_concept["domain"]
                    }
                    
                    created_relationships.append(relationship_data)
                    logger.debug(f"Created cross-domain relationship: {from_name} -{rel_type}-> {to_name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to create cross-domain relationship {from_name} -{rel_type}-> {to_name}: {e}")
        
        # Create some random cross-domain relationships
        random_cross_relationships = await self._create_random_cross_relationships(neo4j_client, concepts, 10)
        created_relationships.extend(random_cross_relationships)
        
        return created_relationships
    
    async def _create_random_cross_relationships(self, neo4j_client, concepts: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:
        """Create random relationships between concepts from different domains."""
        created_relationships = []
        
        # Group concepts by domain
        domains = {}
        for concept in concepts:
            domain = concept["domain"]
            if domain not in domains:
                domains[domain] = []
            domains[domain].append(concept)
        
        domain_names = list(domains.keys())
        
        for _ in range(count):
            try:
                # Select two different domains
                if len(domain_names) < 2:
                    break
                
                from_domain, to_domain = random.sample(domain_names, 2)
                from_concept = random.choice(domains[from_domain])
                to_concept = random.choice(domains[to_domain])
                
                # Select random relationship type
                rel_type = random.choice(["RELATED_TO", "SIMILAR_TO", "APPLIED_TO", "USED_IN"])
                rel_props = self.relationship_types.get(rel_type, {})
                
                # Create relationship properties
                relationship_props = {
                    "strength": round(random.uniform(0.3, 0.7), 3),
                    "relationship_type": rel_type,
                    "source": "random_cross_domain",
                    "bidirectional": rel_props.get("bidirectional", False),
                    "description": f"Random cross-domain relationship",
                    "created_at": datetime.utcnow().isoformat(),
                    "from_domain": from_domain,
                    "to_domain": to_domain
                }
                
                # Create relationship
                rel_id = await neo4j_client.create_relationship(
                    from_concept["id"],
                    to_concept["id"],
                    rel_type,
                    relationship_props
                )
                
                relationship_data = {
                    "id": rel_id,
                    "from_concept": from_concept["name"],
                    "to_concept": to_concept["name"],
                    "type": rel_type,
                    "strength": relationship_props["strength"],
                    "cross_domain": True,
                    "from_domain": from_domain,
                    "to_domain": to_domain,
                    "random": True
                }
                
                created_relationships.append(relationship_data)
                logger.debug(f"Created random cross-domain relationship: {from_concept['name']} -{rel_type}-> {to_concept['name']}")
                
            except Exception as e:
                logger.warning(f"Failed to create random cross-domain relationship: {e}")
        
        return created_relationships
    
    async def close(self) -> None:
        """Close database connections."""
        await self.factory.close()


async def main():
    """Main function to run the sample knowledge graph generator."""
    parser = argparse.ArgumentParser(description="Generate sample knowledge graph for local development")
    parser.add_argument("--concepts", type=int, default=50, help="Number of concepts to create")
    parser.add_argument("--reset", action="store_true", help="Reset existing knowledge graph first")
    parser.add_argument("--with-relationships", action="store_true", default=True, help="Generate relationships between concepts")
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
    
    # Generate sample knowledge graph
    generator = SampleKnowledgeGraphGenerator(config)
    
    try:
        result = await generator.generate_knowledge_graph(
            concept_count=args.concepts,
            reset=args.reset,
            with_relationships=args.with_relationships
        )
        
        concepts = result["concepts"]
        relationships = result["relationships"]
        
        print(f"\n✅ Successfully created knowledge graph!")
        print(f"📊 Concepts: {len(concepts)}")
        print(f"🔗 Relationships: {len(relationships)}")
        
        # Show domain distribution
        domain_counts = {}
        for concept in concepts:
            domain = concept["domain"]
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        print(f"\n📚 Domain Distribution:")
        print("=" * 50)
        for domain, count in domain_counts.items():
            domain_display = domain.replace('_', ' ').title()
            print(f"🔬 {domain_display:30} | {count:3d} concepts")
        
        # Show relationship type distribution
        if relationships:
            rel_type_counts = {}
            cross_domain_count = 0
            
            for rel in relationships:
                rel_type = rel["type"]
                rel_type_counts[rel_type] = rel_type_counts.get(rel_type, 0) + 1
                if rel.get("cross_domain", False):
                    cross_domain_count += 1
            
            print(f"\n🔗 Relationship Types:")
            print("=" * 50)
            for rel_type, count in sorted(rel_type_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"➡️  {rel_type:25} | {count:3d} relationships")
            
            print(f"\n🌐 Cross-domain relationships: {cross_domain_count}")
        
        # Show sample concepts
        print(f"\n📝 Sample Concepts:")
        print("=" * 80)
        for concept in concepts[:8]:
            domain_emoji = {
                "machine_learning": "🤖",
                "natural_language_processing": "💬",
                "computer_vision": "👁️",
                "data_science": "📊"
            }.get(concept["domain"], "🔬")
            
            print(f"{domain_emoji} {concept['name'][:35]:35} | {concept['type']:12} | {concept['category']}")
        
        if len(concepts) > 8:
            print(f"... and {len(concepts) - 8} more concepts")
        
        print(f"\n💡 Knowledge graph includes concepts, relationships, and cross-domain connections")
        print(f"🔍 Use Neo4j Browser at http://localhost:7474 to explore the graph")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate knowledge graph: {e}")
        return 1
    
    finally:
        await generator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)