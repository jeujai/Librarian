#!/usr/bin/env python3
"""
Vector Database Test Data Generator - Similarity Search Scenarios

This script generates comprehensive test scenarios for vector similarity search,
including edge cases, clustering patterns, and realistic search queries.
It creates structured test data to validate search accuracy, performance,
and behavior under various conditions.

The script generates:
- Clustered document groups for testing similarity detection
- Query-document pairs with known relevance scores
- Edge cases (identical vectors, orthogonal vectors, noise)
- Multi-modal content scenarios
- Cross-domain similarity tests
- Hierarchical similarity relationships

Usage:
    python scripts/seed-vector-similarity-scenarios.py [--scenarios N] [--reset] [--verbose]
    
    --scenarios N: Number of test scenarios to generate (default: 20)
    --reset: Clear existing test data before generating new scenarios
    --verbose: Enable detailed logging and validation
"""

import asyncio
import argparse
import logging
import sys
import time
import hashlib
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import random
import json
import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.config_factory import get_database_config
from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SimilarityScenarioGenerator:
    """Generator for comprehensive similarity search test scenarios."""
    
    def __init__(self, verbose: bool = False, dimension: int = 384):
        """Initialize the scenario generator."""
        self.verbose = verbose
        self.dimension = dimension
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        # Test scenario templates
        self.scenario_templates = [
            {
                "name": "Exact Duplicate Detection",
                "description": "Test detection of identical or near-identical documents",
                "type": "exact_match",
                "expected_similarity": 0.99,
                "tolerance": 0.02
            },
            {
                "name": "Semantic Similarity",
                "description": "Test detection of semantically similar but textually different content",
                "type": "semantic_match",
                "expected_similarity": 0.75,
                "tolerance": 0.15
            },
            {
                "name": "Domain Clustering",
                "description": "Test clustering of documents within the same domain",
                "type": "domain_cluster",
                "expected_similarity": 0.65,
                "tolerance": 0.20
            },
            {
                "name": "Cross-Domain Similarity",
                "description": "Test similarity detection across different domains",
                "type": "cross_domain",
                "expected_similarity": 0.45,
                "tolerance": 0.25
            },
            {
                "name": "Hierarchical Relationships",
                "description": "Test parent-child document relationships",
                "type": "hierarchical",
                "expected_similarity": 0.70,
                "tolerance": 0.15
            },
            {
                "name": "Negative Similarity",
                "description": "Test detection of unrelated or opposite content",
                "type": "negative",
                "expected_similarity": 0.20,
                "tolerance": 0.15
            },
            {
                "name": "Multilingual Similarity",
                "description": "Test similarity across different languages",
                "type": "multilingual",
                "expected_similarity": 0.60,
                "tolerance": 0.20
            },
            {
                "name": "Temporal Evolution",
                "description": "Test similarity of documents showing evolution over time",
                "type": "temporal",
                "expected_similarity": 0.55,
                "tolerance": 0.20
            }
        ]
        
        # Content templates for different scenario types
        self.content_templates = {
            "exact_match": [
                {
                    "base": "Machine learning is a subset of artificial intelligence that focuses on algorithms that can learn from data.",
                    "variants": [
                        "Machine learning is a subset of artificial intelligence that focuses on algorithms that can learn from data.",
                        "Machine learning is a subset of AI that focuses on algorithms that can learn from data.",
                        "ML is a subset of artificial intelligence that focuses on algorithms that can learn from data."
                    ]
                },
                {
                    "base": "Deep neural networks have revolutionized computer vision and natural language processing.",
                    "variants": [
                        "Deep neural networks have revolutionized computer vision and natural language processing.",
                        "Deep neural networks have revolutionized computer vision and NLP.",
                        "Deep neural networks have transformed computer vision and natural language processing."
                    ]
                }
            ],
            "semantic_match": [
                {
                    "base": "Artificial intelligence systems can process and analyze large datasets to identify patterns.",
                    "variants": [
                        "AI algorithms excel at discovering hidden patterns in massive data collections.",
                        "Machine learning models can uncover insights from big data through pattern recognition.",
                        "Intelligent systems leverage data mining techniques to extract meaningful patterns."
                    ]
                },
                {
                    "base": "Cloud computing provides scalable infrastructure for modern applications.",
                    "variants": [
                        "Distributed computing platforms offer elastic resources for contemporary software systems.",
                        "Modern applications benefit from the scalability of cloud-based infrastructure.",
                        "Scalable cloud services enable flexible deployment of digital solutions."
                    ]
                }
            ],
            "domain_cluster": {
                "machine_learning": [
                    "Supervised learning algorithms require labeled training data to make predictions.",
                    "Unsupervised learning discovers hidden structures in unlabeled datasets.",
                    "Reinforcement learning agents learn through interaction with their environment.",
                    "Transfer learning leverages pre-trained models for new tasks.",
                    "Ensemble methods combine multiple models to improve prediction accuracy."
                ],
                "software_engineering": [
                    "Microservices architecture decomposes applications into loosely coupled services.",
                    "Continuous integration automates the process of code integration and testing.",
                    "Design patterns provide reusable solutions to common programming problems.",
                    "Code refactoring improves software structure without changing functionality.",
                    "Version control systems track changes in source code over time."
                ],
                "data_science": [
                    "Exploratory data analysis reveals insights through statistical visualization.",
                    "Feature engineering transforms raw data into meaningful model inputs.",
                    "Cross-validation techniques assess model performance and generalization.",
                    "Statistical hypothesis testing validates assumptions about data distributions.",
                    "Data preprocessing cleans and prepares datasets for analysis."
                ]
            },
            "cross_domain": [
                {
                    "domain1": "machine_learning",
                    "content1": "Neural networks use backpropagation to optimize model parameters.",
                    "domain2": "neuroscience",
                    "content2": "Biological neurons transmit signals through synaptic connections in the brain."
                },
                {
                    "domain1": "software_engineering",
                    "content1": "Distributed systems require careful coordination between multiple nodes.",
                    "domain2": "organizational_management",
                    "content2": "Team coordination requires clear communication channels and shared objectives."
                }
            ],
            "hierarchical": [
                {
                    "parent": "Artificial intelligence encompasses various computational approaches to intelligent behavior.",
                    "children": [
                        "Machine learning is a branch of AI that focuses on learning from data.",
                        "Computer vision enables machines to interpret and understand visual information.",
                        "Natural language processing allows computers to understand human language."
                    ]
                },
                {
                    "parent": "Software development involves multiple phases from design to deployment.",
                    "children": [
                        "Requirements analysis defines what the software system should accomplish.",
                        "System design creates the architectural blueprint for implementation.",
                        "Testing ensures the software meets quality and functional requirements."
                    ]
                }
            ],
            "negative": [
                {
                    "content1": "Machine learning algorithms optimize objective functions through iterative training.",
                    "content2": "Traditional cooking recipes require precise measurements and timing for best results."
                },
                {
                    "content1": "Distributed database systems ensure data consistency across multiple nodes.",
                    "content2": "Classical music composition follows established harmonic and melodic principles."
                }
            ],
            "multilingual": [
                {
                    "english": "Artificial intelligence is transforming industries worldwide.",
                    "spanish": "La inteligencia artificial está transformando industrias en todo el mundo.",
                    "french": "L'intelligence artificielle transforme les industries du monde entier.",
                    "german": "Künstliche Intelligenz verändert Branchen weltweit."
                },
                {
                    "english": "Data science combines statistics, programming, and domain expertise.",
                    "spanish": "La ciencia de datos combina estadísticas, programación y experiencia en el dominio.",
                    "french": "La science des données combine statistiques, programmation et expertise métier.",
                    "german": "Data Science kombiniert Statistik, Programmierung und Fachkenntnisse."
                }
            ],
            "temporal": [
                {
                    "timeline": [
                        "Early artificial intelligence focused on symbolic reasoning and expert systems.",
                        "The rise of machine learning shifted focus to statistical learning from data.",
                        "Deep learning breakthrough enabled complex pattern recognition in neural networks.",
                        "Modern AI integrates multiple approaches for robust intelligent systems."
                    ]
                },
                {
                    "timeline": [
                        "Traditional software development followed waterfall methodologies with sequential phases.",
                        "Agile methodologies introduced iterative development and continuous feedback.",
                        "DevOps practices integrated development and operations for faster deployment.",
                        "Modern software engineering emphasizes automation, monitoring, and continuous improvement."
                    ]
                }
            ]
        }
        
        # Query templates for testing search scenarios
        self.query_templates = [
            # Specific concept queries
            "What is {concept}?",
            "How does {concept} work?",
            "Explain {concept} in simple terms",
            "What are the applications of {concept}?",
            "What are the advantages of {concept}?",
            
            # Comparison queries
            "Compare {concept1} and {concept2}",
            "What is the difference between {concept1} and {concept2}?",
            "Which is better: {concept1} or {concept2}?",
            
            # Problem-solving queries
            "How to implement {concept}?",
            "Best practices for {concept}",
            "Common challenges with {concept}",
            "How to optimize {concept}?",
            
            # Exploratory queries
            "Latest developments in {concept}",
            "Future of {concept}",
            "Research trends in {concept}",
            "Industry applications of {concept}"
        ]
        
        # Concepts for different domains
        self.domain_concepts = {
            "machine_learning": [
                "neural networks", "deep learning", "supervised learning", "unsupervised learning",
                "reinforcement learning", "transfer learning", "ensemble methods", "feature selection",
                "model validation", "overfitting", "regularization", "gradient descent"
            ],
            "software_engineering": [
                "microservices", "API design", "database optimization", "code refactoring",
                "design patterns", "continuous integration", "version control", "testing strategies",
                "performance optimization", "security practices", "scalability", "maintainability"
            ],
            "data_science": [
                "data visualization", "statistical analysis", "hypothesis testing", "regression analysis",
                "clustering algorithms", "dimensionality reduction", "feature engineering",
                "data preprocessing", "exploratory analysis", "predictive modeling"
            ]
        }
    
    def generate_embedding_with_similarity(
        self, 
        base_embedding: List[float], 
        target_similarity: float,
        noise_level: float = 0.1
    ) -> List[float]:
        """
        Generate an embedding with a specific similarity to a base embedding.
        
        Args:
            base_embedding: Reference embedding vector
            target_similarity: Desired cosine similarity (0-1)
            noise_level: Amount of random noise to add
            
        Returns:
            New embedding with approximately the target similarity
        """
        base_array = np.array(base_embedding)
        
        # Generate a random orthogonal component
        random_vector = np.random.normal(0, 1, self.dimension)
        
        # Make it orthogonal to base vector
        projection = np.dot(random_vector, base_array) / np.dot(base_array, base_array)
        orthogonal_component = random_vector - projection * base_array
        
        # Normalize orthogonal component
        if np.linalg.norm(orthogonal_component) > 0:
            orthogonal_component = orthogonal_component / np.linalg.norm(orthogonal_component)
        
        # Calculate mixing coefficients for target similarity
        # For cosine similarity s, we need: cos(θ) = s
        # If new_vector = a * base + b * orthogonal, then similarity ≈ a / sqrt(a² + b²)
        if target_similarity >= 0.99:
            # Very high similarity - mostly base vector
            alpha = 0.95
            beta = 0.31
        elif target_similarity <= 0.01:
            # Very low similarity - mostly orthogonal
            alpha = 0.1
            beta = 0.99
        else:
            # Calculate coefficients for target similarity
            # Approximate: similarity ≈ alpha / sqrt(alpha² + beta²)
            alpha = target_similarity
            beta = math.sqrt(max(0, 1 - target_similarity * target_similarity))
        
        # Create new vector
        new_vector = alpha * base_array + beta * orthogonal_component
        
        # Add small amount of noise
        noise = np.random.normal(0, noise_level, self.dimension)
        new_vector += noise
        
        # Normalize the result
        if np.linalg.norm(new_vector) > 0:
            new_vector = new_vector / np.linalg.norm(new_vector)
        
        return new_vector.tolist()
    
    def calculate_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        arr1 = np.array(vec1)
        arr2 = np.array(vec2)
        
        dot_product = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def generate_base_embedding(self, content: str) -> List[float]:
        """Generate a base embedding from content using hash-based approach."""
        # Create reproducible embedding based on content
        content_hash = hashlib.md5(content.encode()).hexdigest()
        seed = int(content_hash[:8], 16)
        np.random.seed(seed)
        
        # Generate embedding with normal distribution
        embedding = np.random.normal(0, 0.1, self.dimension)
        
        # Add content-specific patterns
        words = content.lower().split()
        for i, word in enumerate(words[:min(10, len(words))]):
            word_hash = hash(word) % self.dimension
            embedding[word_hash] += 0.05
        
        # Normalize
        if np.linalg.norm(embedding) > 0:
            embedding = embedding / np.linalg.norm(embedding)
        
        return embedding.tolist()
    
    def create_exact_match_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Create exact match test scenario."""
        template = random.choice(self.content_templates["exact_match"])
        base_content = template["base"]
        
        # Generate base embedding
        base_embedding = self.generate_base_embedding(base_content)
        
        # Create variants with high similarity
        documents = []
        queries = []
        
        # Add base document
        documents.append({
            "id": f"{scenario_id}_doc_0",
            "content": base_content,
            "embedding": base_embedding,
            "metadata": {
                "scenario_id": scenario_id,
                "doc_type": "base",
                "content_type": "exact_match"
            }
        })
        
        # Add variant documents
        for i, variant in enumerate(template["variants"]):
            # Generate embedding with very high similarity
            variant_embedding = self.generate_embedding_with_similarity(
                base_embedding, 
                target_similarity=random.uniform(0.95, 0.99),
                noise_level=0.02
            )
            
            documents.append({
                "id": f"{scenario_id}_doc_{i+1}",
                "content": variant,
                "embedding": variant_embedding,
                "metadata": {
                    "scenario_id": scenario_id,
                    "doc_type": "variant",
                    "content_type": "exact_match",
                    "variant_index": i
                }
            })
        
        # Generate test queries
        query_content = base_content[:50] + "..."  # Truncated version
        query_embedding = self.generate_embedding_with_similarity(
            base_embedding,
            target_similarity=0.98,
            noise_level=0.01
        )
        
        queries.append({
            "id": f"{scenario_id}_query_0",
            "content": query_content,
            "embedding": query_embedding,
            "expected_results": [doc["id"] for doc in documents],
            "expected_similarities": [0.98, 0.97, 0.96, 0.95][:len(documents)]
        })
        
        return {
            "scenario_id": scenario_id,
            "scenario_type": "exact_match",
            "documents": documents,
            "queries": queries,
            "validation_criteria": {
                "min_similarity": 0.95,
                "max_similarity": 1.0,
                "expected_rank_order": True
            }
        }
    
    def create_semantic_match_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Create semantic similarity test scenario."""
        template = random.choice(self.content_templates["semantic_match"])
        base_content = template["base"]
        
        # Generate base embedding
        base_embedding = self.generate_base_embedding(base_content)
        
        documents = []
        queries = []
        
        # Add base document
        documents.append({
            "id": f"{scenario_id}_doc_0",
            "content": base_content,
            "embedding": base_embedding,
            "metadata": {
                "scenario_id": scenario_id,
                "doc_type": "base",
                "content_type": "semantic_match"
            }
        })
        
        # Add semantically similar documents
        for i, variant in enumerate(template["variants"]):
            # Generate embedding with moderate similarity
            variant_embedding = self.generate_embedding_with_similarity(
                base_embedding,
                target_similarity=random.uniform(0.65, 0.85),
                noise_level=0.1
            )
            
            documents.append({
                "id": f"{scenario_id}_doc_{i+1}",
                "content": variant,
                "embedding": variant_embedding,
                "metadata": {
                    "scenario_id": scenario_id,
                    "doc_type": "semantic_variant",
                    "content_type": "semantic_match",
                    "variant_index": i
                }
            })
        
        # Generate semantic query
        query_concepts = ["pattern", "analysis", "system", "method", "approach"]
        query_content = f"How to use {random.choice(query_concepts)} for {base_content.split()[0:3]}"
        query_embedding = self.generate_embedding_with_similarity(
            base_embedding,
            target_similarity=0.75,
            noise_level=0.05
        )
        
        queries.append({
            "id": f"{scenario_id}_query_0",
            "content": " ".join(query_content),
            "embedding": query_embedding,
            "expected_results": [doc["id"] for doc in documents],
            "expected_similarities": [0.75, 0.70, 0.68, 0.65][:len(documents)]
        })
        
        return {
            "scenario_id": scenario_id,
            "scenario_type": "semantic_match",
            "documents": documents,
            "queries": queries,
            "validation_criteria": {
                "min_similarity": 0.60,
                "max_similarity": 0.90,
                "expected_rank_order": True
            }
        }
    
    def create_domain_cluster_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Create domain clustering test scenario."""
        domain = random.choice(list(self.content_templates["domain_cluster"].keys()))
        domain_contents = self.content_templates["domain_cluster"][domain]
        
        # Select a subset of contents
        selected_contents = random.sample(domain_contents, min(4, len(domain_contents)))
        
        # Generate base embedding for domain
        domain_seed = f"domain_{domain}"
        base_embedding = self.generate_base_embedding(domain_seed)
        
        documents = []
        
        # Create documents within the domain
        for i, content in enumerate(selected_contents):
            # Generate embedding with domain similarity
            doc_embedding = self.generate_embedding_with_similarity(
                base_embedding,
                target_similarity=random.uniform(0.55, 0.75),
                noise_level=0.15
            )
            
            documents.append({
                "id": f"{scenario_id}_doc_{i}",
                "content": content,
                "embedding": doc_embedding,
                "metadata": {
                    "scenario_id": scenario_id,
                    "domain": domain,
                    "doc_type": "domain_member",
                    "content_type": "domain_cluster"
                }
            })
        
        # Generate domain-specific query
        domain_concepts = self.domain_concepts.get(domain, ["concept", "method", "approach"])
        concept = random.choice(domain_concepts)
        query_template = random.choice(self.query_templates)
        query_content = query_template.format(concept=concept, concept1=concept, concept2=random.choice(domain_concepts))
        
        query_embedding = self.generate_embedding_with_similarity(
            base_embedding,
            target_similarity=0.65,
            noise_level=0.1
        )
        
        queries = [{
            "id": f"{scenario_id}_query_0",
            "content": query_content,
            "embedding": query_embedding,
            "expected_results": [doc["id"] for doc in documents],
            "expected_similarities": [0.65, 0.62, 0.60, 0.58][:len(documents)]
        }]
        
        return {
            "scenario_id": scenario_id,
            "scenario_type": "domain_cluster",
            "domain": domain,
            "documents": documents,
            "queries": queries,
            "validation_criteria": {
                "min_similarity": 0.50,
                "max_similarity": 0.80,
                "cluster_cohesion": True
            }
        }
    
    def create_negative_similarity_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Create negative similarity test scenario."""
        template = random.choice(self.content_templates["negative"])
        
        # Generate embeddings for unrelated content
        embedding1 = self.generate_base_embedding(template["content1"])
        embedding2 = self.generate_base_embedding(template["content2"])
        
        # Ensure they are dissimilar by making them more orthogonal
        embedding2 = self.generate_embedding_with_similarity(
            embedding1,
            target_similarity=random.uniform(0.05, 0.25),
            noise_level=0.2
        )
        
        documents = [
            {
                "id": f"{scenario_id}_doc_0",
                "content": template["content1"],
                "embedding": embedding1,
                "metadata": {
                    "scenario_id": scenario_id,
                    "doc_type": "content_a",
                    "content_type": "negative_similarity"
                }
            },
            {
                "id": f"{scenario_id}_doc_1",
                "content": template["content2"],
                "embedding": embedding2,
                "metadata": {
                    "scenario_id": scenario_id,
                    "doc_type": "content_b",
                    "content_type": "negative_similarity"
                }
            }
        ]
        
        # Query should be similar to first document but not second
        query_embedding = self.generate_embedding_with_similarity(
            embedding1,
            target_similarity=0.70,
            noise_level=0.1
        )
        
        queries = [{
            "id": f"{scenario_id}_query_0",
            "content": template["content1"][:30] + "...",
            "embedding": query_embedding,
            "expected_results": [documents[0]["id"]],  # Only first document should match
            "expected_similarities": [0.70],
            "negative_results": [documents[1]["id"]],  # Second should not match
            "max_negative_similarity": 0.30
        }]
        
        return {
            "scenario_id": scenario_id,
            "scenario_type": "negative_similarity",
            "documents": documents,
            "queries": queries,
            "validation_criteria": {
                "positive_min_similarity": 0.60,
                "negative_max_similarity": 0.30,
                "clear_separation": True
            }
        }
    
    def create_hierarchical_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Create hierarchical relationship test scenario."""
        template = random.choice(self.content_templates["hierarchical"])
        
        # Generate parent embedding
        parent_embedding = self.generate_base_embedding(template["parent"])
        
        documents = []
        
        # Add parent document
        documents.append({
            "id": f"{scenario_id}_doc_parent",
            "content": template["parent"],
            "embedding": parent_embedding,
            "metadata": {
                "scenario_id": scenario_id,
                "doc_type": "parent",
                "content_type": "hierarchical",
                "hierarchy_level": 0
            }
        })
        
        # Add child documents
        for i, child_content in enumerate(template["children"]):
            # Children should be moderately similar to parent
            child_embedding = self.generate_embedding_with_similarity(
                parent_embedding,
                target_similarity=random.uniform(0.60, 0.80),
                noise_level=0.12
            )
            
            documents.append({
                "id": f"{scenario_id}_doc_child_{i}",
                "content": child_content,
                "embedding": child_embedding,
                "metadata": {
                    "scenario_id": scenario_id,
                    "doc_type": "child",
                    "content_type": "hierarchical",
                    "hierarchy_level": 1,
                    "parent_id": f"{scenario_id}_doc_parent"
                }
            })
        
        # Query about the general topic should find parent and children
        query_content = f"Overview of {template['parent'].split()[0:3]}"
        query_embedding = self.generate_embedding_with_similarity(
            parent_embedding,
            target_similarity=0.75,
            noise_level=0.08
        )
        
        queries = [{
            "id": f"{scenario_id}_query_0",
            "content": " ".join(query_content),
            "embedding": query_embedding,
            "expected_results": [doc["id"] for doc in documents],
            "expected_similarities": [0.75] + [0.65] * len(template["children"]),
            "hierarchy_preserved": True
        }]
        
        return {
            "scenario_id": scenario_id,
            "scenario_type": "hierarchical",
            "documents": documents,
            "queries": queries,
            "validation_criteria": {
                "parent_child_similarity": 0.60,
                "hierarchy_order": True,
                "parent_highest_similarity": True
            }
        }
    
    async def generate_similarity_scenarios(self, count: int) -> List[Dict[str, Any]]:
        """Generate comprehensive similarity test scenarios."""
        logger.info(f"Generating {count} similarity test scenarios...")
        
        scenarios = []
        scenario_types = [
            "exact_match", "semantic_match", "domain_cluster", 
            "negative_similarity", "hierarchical"
        ]
        
        for i in range(count):
            scenario_type = scenario_types[i % len(scenario_types)]
            scenario_id = f"scenario_{i+1:03d}_{scenario_type}"
            
            if scenario_type == "exact_match":
                scenario = self.create_exact_match_scenario(scenario_id)
            elif scenario_type == "semantic_match":
                scenario = self.create_semantic_match_scenario(scenario_id)
            elif scenario_type == "domain_cluster":
                scenario = self.create_domain_cluster_scenario(scenario_id)
            elif scenario_type == "negative_similarity":
                scenario = self.create_negative_similarity_scenario(scenario_id)
            elif scenario_type == "hierarchical":
                scenario = self.create_hierarchical_scenario(scenario_id)
            
            # Validate scenario embeddings
            self.validate_scenario_embeddings(scenario)
            
            scenarios.append(scenario)
            
            if self.verbose and (i + 1) % 5 == 0:
                logger.debug(f"Generated {i + 1}/{count} scenarios")
        
        logger.info(f"Successfully generated {len(scenarios)} similarity test scenarios")
        return scenarios
    
    def validate_scenario_embeddings(self, scenario: Dict[str, Any]) -> None:
        """Validate that scenario embeddings meet expected similarity criteria."""
        documents = scenario["documents"]
        queries = scenario["queries"]
        
        # Validate document embeddings
        for doc in documents:
            embedding = doc["embedding"]
            if len(embedding) != self.dimension:
                logger.warning(f"Document {doc['id']} has incorrect embedding dimension: {len(embedding)}")
            
            # Check if embedding is normalized
            magnitude = sum(x * x for x in embedding) ** 0.5
            if abs(magnitude - 1.0) > 0.1:
                logger.warning(f"Document {doc['id']} embedding not normalized: magnitude = {magnitude}")
        
        # Validate query-document similarities
        for query in queries:
            query_embedding = query["embedding"]
            expected_similarities = query.get("expected_similarities", [])
            
            for i, doc_id in enumerate(query.get("expected_results", [])):
                doc = next((d for d in documents if d["id"] == doc_id), None)
                if doc:
                    actual_similarity = self.calculate_cosine_similarity(
                        query_embedding, doc["embedding"]
                    )
                    
                    if i < len(expected_similarities):
                        expected = expected_similarities[i]
                        tolerance = 0.15  # Allow some tolerance
                        
                        if abs(actual_similarity - expected) > tolerance:
                            logger.warning(
                                f"Similarity mismatch for {query['id']} -> {doc_id}: "
                                f"expected {expected:.3f}, got {actual_similarity:.3f}"
                            )
    
    def print_scenario_summary(self, scenarios: List[Dict[str, Any]], sample_size: int = 3):
        """Print a summary of generated scenarios."""
        print(f"\n📊 Generated {len(scenarios)} similarity test scenarios")
        print("=" * 70)
        
        # Scenario type distribution
        type_counts = {}
        total_documents = 0
        total_queries = 0
        
        for scenario in scenarios:
            scenario_type = scenario["scenario_type"]
            type_counts[scenario_type] = type_counts.get(scenario_type, 0) + 1
            total_documents += len(scenario["documents"])
            total_queries += len(scenario["queries"])
        
        print("📈 Scenario Type Distribution:")
        for scenario_type, count in sorted(type_counts.items()):
            percentage = (count / len(scenarios)) * 100
            print(f"   • {scenario_type.replace('_', ' ').title()}: {count} ({percentage:.1f}%)")
        
        print(f"\n📄 Total Test Data:")
        print(f"   • Documents: {total_documents}")
        print(f"   • Queries: {total_queries}")
        print(f"   • Vector dimension: {self.dimension}")
        
        print(f"\n📋 Sample Scenarios (showing {min(sample_size, len(scenarios))}):")
        for i, scenario in enumerate(scenarios[:sample_size]):
            print(f"\n   {i+1}. {scenario['scenario_id']} ({scenario['scenario_type']})")
            print(f"      Documents: {len(scenario['documents'])}")
            print(f"      Queries: {len(scenario['queries'])}")
            
            # Show sample content
            if scenario["documents"]:
                sample_doc = scenario["documents"][0]
                content_preview = sample_doc["content"][:80] + "..." if len(sample_doc["content"]) > 80 else sample_doc["content"]
                print(f"      Sample: {content_preview}")
            
            # Show validation criteria
            criteria = scenario.get("validation_criteria", {})
            if criteria:
                print(f"      Criteria: {', '.join(criteria.keys())}")


async def main():
    """Main function to generate similarity test scenarios."""
    parser = argparse.ArgumentParser(description="Generate similarity search test scenarios for vector database")
    parser.add_argument("--scenarios", type=int, default=20, help="Number of test scenarios to generate")
    parser.add_argument("--reset", action="store_true", help="Clear existing test data before generating new scenarios")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging and validation")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("🚀 Similarity Search Scenarios Generator")
    print("=" * 55)
    print(f"Generating {args.scenarios} test scenarios...")
    if args.reset:
        print("⚠️  Reset mode: Will clear existing test data")
    print()
    
    try:
        # Initialize generator
        generator = SimilarityScenarioGenerator(verbose=args.verbose)
        
        # Generate scenarios
        start_time = time.time()
        scenarios = await generator.generate_similarity_scenarios(args.scenarios)
        generation_time = time.time() - start_time
        
        # Print summary
        generator.print_scenario_summary(scenarios)
        
        print(f"\n⏱️  Generation completed in {generation_time:.2f} seconds")
        print(f"📊 Average: {generation_time/len(scenarios)*1000:.1f}ms per scenario")
        
        # Calculate total test vectors
        total_vectors = sum(len(s["documents"]) + len(s["queries"]) for s in scenarios)
        print(f"\n💾 Test Data Summary:")
        print(f"   • Total test vectors: {total_vectors}")
        print(f"   • Vector dimension: {generator.dimension}")
        print(f"   • Estimated memory: {total_vectors * generator.dimension * 4 / 1024 / 1024:.1f} MB")
        
        # Save scenarios to JSON for inspection and testing
        output_file = Path(__file__).parent.parent / "test_data" / "similarity_scenarios.json"
        output_file.parent.mkdir(exist_ok=True)
        
        # Save scenarios with truncated embeddings for readability
        export_scenarios = []
        for scenario in scenarios:
            export_scenario = scenario.copy()
            
            # Truncate embeddings for JSON export
            for doc in export_scenario["documents"]:
                if "embedding" in doc:
                    doc["embedding"] = doc["embedding"][:5] + ["..."] + [f"({len(scenario['documents'][0]['embedding'])} total)"]
            
            for query in export_scenario["queries"]:
                if "embedding" in query:
                    query["embedding"] = query["embedding"][:5] + ["..."] + [f"({len(scenario['queries'][0]['embedding'])} total)"]
            
            export_scenarios.append(export_scenario)
        
        with open(output_file, 'w') as f:
            json.dump(export_scenarios, f, indent=2, default=str)
        
        print(f"\n💾 Test scenarios saved to: {output_file}")
        print("\n✅ Similarity search scenarios generation completed successfully!")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Generation interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)