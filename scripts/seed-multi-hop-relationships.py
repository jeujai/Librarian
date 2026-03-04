#!/usr/bin/env python3
"""
Multi-Hop Relationship Examples Generator

This script creates complex multi-hop relationship patterns in the knowledge graph
to demonstrate advanced graph traversal capabilities. It creates hierarchical
structures, inference chains, and complex relationship patterns that require
multi-step graph queries to discover.

Usage:
    python scripts/seed-multi-hop-relationships.py [--max-depth N] [--reset]
    
    --max-depth N: Maximum depth for relationship chains (default: 4)
    --reset: Reset existing multi-hop patterns
"""

import asyncio
import argparse
import logging
import uuid
import json
import random
from datetime import datetime, timedelta
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


class MultiHopRelationshipGenerator:
    """Generator for multi-hop relationship patterns in the knowledge graph."""
    
    def __init__(self, config: LocalDatabaseConfig):
        """Initialize the generator with database configuration."""
        self.config = config
        self.factory = DatabaseClientFactory(config)
        
        # Multi-hop relationship patterns
        self.relationship_patterns = {
            # Hierarchical patterns (IS_A, PART_OF chains)
            "taxonomic_hierarchy": [
                # AI -> ML -> Deep Learning -> CNN -> ResNet
                ("Artificial Intelligence", "INCLUDES", "Machine Learning"),
                ("Machine Learning", "INCLUDES", "Deep Learning"),
                ("Deep Learning", "USES", "Neural Networks"),
                ("Neural Networks", "SPECIALIZED_AS", "Convolutional Neural Network"),
                ("Convolutional Neural Network", "IMPLEMENTED_AS", "ResNet")
            ],
            
            # Application chains (USED_FOR, APPLIED_TO)
            "application_chain": [
                # Data -> Preprocessing -> Feature Engineering -> ML -> Prediction
                ("Data Science", "INVOLVES", "Data Preprocessing"),
                ("Data Preprocessing", "INCLUDES", "Feature Engineering"),
                ("Feature Engineering", "FEEDS_INTO", "Machine Learning"),
                ("Machine Learning", "PRODUCES", "Predictions"),
                ("Predictions", "ENABLE", "Decision Making")
            ],
            
            # Problem-solution chains
            "problem_solution": [
                # Problem -> Technique -> Algorithm -> Implementation -> Evaluation
                ("Overfitting", "SOLVED_BY", "Regularization"),
                ("Regularization", "IMPLEMENTED_AS", "Dropout"),
                ("Dropout", "APPLIED_TO", "Neural Networks"),
                ("Neural Networks", "EVALUATED_WITH", "Cross Validation"),
                ("Cross Validation", "MEASURES", "Model Performance")
            ],
            
            # Workflow chains (NLP pipeline)
            "nlp_pipeline": [
                ("Raw Text", "PROCESSED_BY", "Tokenization"),
                ("Tokenization", "FOLLOWED_BY", "Part-of-Speech Tagging"),
                ("Part-of-Speech Tagging", "ENABLES", "Named Entity Recognition"),
                ("Named Entity Recognition", "FEEDS_INTO", "Semantic Analysis"),
                ("Semantic Analysis", "PRODUCES", "Text Understanding")
            ],
            
            # Computer Vision pipeline
            "cv_pipeline": [
                ("Raw Image", "PROCESSED_BY", "Image Preprocessing"),
                ("Image Preprocessing", "FOLLOWED_BY", "Feature Extraction"),
                ("Feature Extraction", "USES", "Convolutional Neural Network"),
                ("Convolutional Neural Network", "PRODUCES", "Feature Maps"),
                ("Feature Maps", "CLASSIFIED_BY", "Image Classification")
            ],
            
            # Learning paradigm relationships
            "learning_paradigms": [
                ("Supervised Learning", "REQUIRES", "Labeled Data"),
                ("Labeled Data", "USED_FOR", "Training"),
                ("Training", "PRODUCES", "Trained Model"),
                ("Trained Model", "EVALUATED_ON", "Test Data"),
                ("Test Data", "PROVIDES", "Performance Metrics")
            ],
            
            # Research evolution chains
            "research_evolution": [
                ("Perceptron", "EVOLVED_INTO", "Multi-Layer Perceptron"),
                ("Multi-Layer Perceptron", "IMPROVED_BY", "Backpropagation"),
                ("Backpropagation", "ENABLED", "Deep Learning"),
                ("Deep Learning", "ADVANCED_TO", "Transformer"),
                ("Transformer", "REVOLUTIONIZED", "Natural Language Processing")
            ]
        }
        
        # Inference patterns (A->B, B->C implies A->C)
        self.inference_patterns = [
            # Transitive relationships
            {
                "pattern": "transitivity",
                "rules": [
                    ("IS_SUBSET_OF", "IS_SUBSET_OF", "IS_SUBSET_OF"),
                    ("PART_OF", "PART_OF", "PART_OF"),
                    ("INCLUDES", "INCLUDES", "INCLUDES"),
                    ("PREREQUISITE_FOR", "PREREQUISITE_FOR", "PREREQUISITE_FOR")
                ]
            },
            
            # Composition patterns
            {
                "pattern": "composition",
                "rules": [
                    ("USES", "PART_OF", "DEPENDS_ON"),
                    ("APPLIED_TO", "INCLUDES", "RELEVANT_TO"),
                    ("IMPLEMENTED_AS", "USES", "BASED_ON")
                ]
            },
            
            # Causal chains
            {
                "pattern": "causality",
                "rules": [
                    ("CAUSES", "LEADS_TO", "ULTIMATELY_CAUSES"),
                    ("PREVENTS", "REDUCES", "MITIGATES"),
                    ("IMPROVES", "ENHANCES", "OPTIMIZES")
                ]
            }
        ]
        
        # Complex query patterns for testing
        self.query_patterns = [
            {
                "name": "find_learning_path",
                "description": "Find learning path from basic concept to advanced application",
                "query": """
                MATCH path = (start:Concept)-[:PREREQUISITE_FOR|LEADS_TO|ENABLES*1..5]->(end:Concept)
                WHERE start.name = $start_concept AND end.name = $end_concept
                RETURN path, length(path) as depth
                ORDER BY depth
                LIMIT 5
                """,
                "example_params": {"start_concept": "Statistics", "end_concept": "Deep Learning"}
            },
            
            {
                "name": "find_application_domains",
                "description": "Find all domains where a technique is applied",
                "query": """
                MATCH (technique:Concept)-[:APPLIED_TO|USED_IN*1..3]->(domain:Concept)
                WHERE technique.name = $technique_name
                RETURN DISTINCT domain.name as domain, domain.category as category
                """,
                "example_params": {"technique_name": "Neural Networks"}
            },
            
            {
                "name": "find_problem_solutions",
                "description": "Find multi-step solutions to a problem",
                "query": """
                MATCH path = (problem:Concept)-[:SOLVED_BY|ADDRESSED_BY|MITIGATED_BY*1..4]->(solution:Concept)
                WHERE problem.name = $problem_name
                RETURN path, [n in nodes(path) | n.name] as solution_path
                ORDER BY length(path)
                """,
                "example_params": {"problem_name": "Overfitting"}
            },
            
            {
                "name": "find_technology_evolution",
                "description": "Find evolution chain of technologies",
                "query": """
                MATCH path = (old:Concept)-[:EVOLVED_INTO|IMPROVED_BY|REPLACED_BY*1..5]->(new:Concept)
                WHERE old.name = $old_tech
                RETURN path, [n in nodes(path) | n.name] as evolution_chain
                ORDER BY length(path) DESC
                LIMIT 3
                """,
                "example_params": {"old_tech": "Perceptron"}
            },
            
            {
                "name": "find_concept_dependencies",
                "description": "Find all prerequisites for understanding a concept",
                "query": """
                MATCH path = (prereq:Concept)-[:PREREQUISITE_FOR|FOUNDATION_OF*1..4]->(target:Concept)
                WHERE target.name = $target_concept
                RETURN DISTINCT prereq.name as prerequisite, 
                       prereq.domain as domain,
                       length(path) as distance
                ORDER BY distance, prerequisite
                """,
                "example_params": {"target_concept": "Transformer"}
            },
            
            {
                "name": "find_cross_domain_connections",
                "description": "Find connections between different domains",
                "query": """
                MATCH path = (c1:Concept)-[*2..4]-(c2:Concept)
                WHERE c1.domain = $domain1 AND c2.domain = $domain2 
                      AND c1.domain <> c2.domain
                RETURN DISTINCT c1.name as concept1, c2.name as concept2,
                       length(path) as connection_distance,
                       [r in relationships(path) | type(r)] as relationship_types
                ORDER BY connection_distance
                LIMIT 10
                """,
                "example_params": {"domain1": "machine_learning", "domain2": "natural_language_processing"}
            }
        ]
    
    async def generate_multi_hop_relationships(
        self,
        max_depth: int = 4,
        reset: bool = False
    ) -> Dict[str, Any]:
        """
        Generate multi-hop relationship patterns in the knowledge graph.
        
        Args:
            max_depth: Maximum depth for relationship chains
            reset: Whether to reset existing multi-hop patterns
            
        Returns:
            Dictionary with created patterns and query examples
        """
        logger.info(f"Generating multi-hop relationships (max_depth={max_depth}, reset={reset})")
        
        try:
            # Get Neo4j client
            neo4j_client = await self.factory.get_graph_client()
            await neo4j_client.connect()
            
            # Get existing concepts
            concepts = await self._get_concepts(neo4j_client)
            
            if not concepts:
                logger.warning("No concepts found. Run seed-sample-knowledge-graph.py first.")
                return {"patterns": [], "inferred_relationships": [], "query_examples": []}
            
            # Reset multi-hop patterns if requested
            if reset:
                await self._reset_multi_hop_patterns(neo4j_client)
            
            # Create structured relationship patterns
            created_patterns = await self._create_relationship_patterns(neo4j_client, concepts)
            
            # Create additional concepts for complex patterns
            additional_concepts = await self._create_additional_concepts(neo4j_client)
            
            # Create inferred relationships
            inferred_relationships = await self._create_inferred_relationships(neo4j_client, concepts + additional_concepts)
            
            # Create hierarchical topic structure
            topic_hierarchy = await self._create_topic_hierarchy(neo4j_client, concepts)
            
            # Test query patterns
            query_examples = await self._test_query_patterns(neo4j_client)
            
            logger.info(f"Successfully created {len(created_patterns)} relationship patterns")
            logger.info(f"Successfully created {len(inferred_relationships)} inferred relationships")
            logger.info(f"Successfully created {len(topic_hierarchy)} topic hierarchy nodes")
            
            return {
                "patterns": created_patterns,
                "additional_concepts": additional_concepts,
                "inferred_relationships": inferred_relationships,
                "topic_hierarchy": topic_hierarchy,
                "query_examples": query_examples,
                "max_depth_achieved": max_depth
            }
            
        except Exception as e:
            logger.error(f"Failed to generate multi-hop relationships: {e}")
            raise
        finally:
            if 'neo4j_client' in locals():
                await neo4j_client.disconnect()
    
    async def _get_concepts(self, neo4j_client) -> List[Dict[str, Any]]:
        """Get existing concepts from Neo4j."""
        try:
            query = """
            MATCH (c:Concept)
            RETURN id(c) as id, c.name as name, c.type as type, 
                   c.category as category, c.domain as domain
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
                    "domain": record["domain"]
                })
            
            logger.info(f"Retrieved {len(concepts)} existing concepts")
            return concepts
            
        except Exception as e:
            logger.error(f"Failed to get concepts: {e}")
            return []
    
    async def _reset_multi_hop_patterns(self, neo4j_client) -> None:
        """Reset existing multi-hop patterns."""
        logger.info("Resetting existing multi-hop patterns")
        
        try:
            # Delete inferred relationships
            await neo4j_client.execute_write_query(
                "MATCH ()-[r]->() WHERE r.source = 'multi_hop_inference' DELETE r"
            )
            
            # Delete pattern-based relationships
            await neo4j_client.execute_write_query(
                "MATCH ()-[r]->() WHERE r.source = 'relationship_pattern' DELETE r"
            )
            
            # Delete topic hierarchy
            await neo4j_client.execute_write_query("MATCH (t:Topic) DETACH DELETE t")
            
            # Delete additional concepts created for patterns
            await neo4j_client.execute_write_query(
                "MATCH (c:Concept) WHERE c.source = 'multi_hop_pattern' DETACH DELETE c"
            )
            
            logger.info("Successfully reset multi-hop patterns")
            
        except Exception as e:
            logger.error(f"Failed to reset multi-hop patterns: {e}")
            raise
    
    async def _create_relationship_patterns(self, neo4j_client, concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create structured relationship patterns."""
        logger.info("Creating structured relationship patterns")
        
        created_patterns = []
        concept_map = {c["name"]: c for c in concepts}
        
        for pattern_name, relationships in self.relationship_patterns.items():
            logger.debug(f"Creating pattern: {pattern_name}")
            pattern_relationships = []
            
            for from_name, rel_type, to_name in relationships:
                # Check if both concepts exist, if not create them
                from_concept = concept_map.get(from_name)
                to_concept = concept_map.get(to_name)
                
                # Create missing concepts
                if not from_concept:
                    from_concept = await self._create_pattern_concept(neo4j_client, from_name)
                    concept_map[from_name] = from_concept
                
                if not to_concept:
                    to_concept = await self._create_pattern_concept(neo4j_client, to_name)
                    concept_map[to_name] = to_concept
                
                try:
                    # Create relationship properties
                    rel_props = {
                        "strength": round(random.uniform(0.7, 0.9), 3),
                        "relationship_type": rel_type,
                        "source": "relationship_pattern",
                        "pattern_name": pattern_name,
                        "created_at": datetime.utcnow().isoformat(),
                        "description": f"Part of {pattern_name} pattern"
                    }
                    
                    # Create relationship
                    rel_id = await neo4j_client.create_relationship(
                        from_concept["id"],
                        to_concept["id"],
                        rel_type,
                        rel_props
                    )
                    
                    relationship_data = {
                        "id": rel_id,
                        "from_concept": from_name,
                        "to_concept": to_name,
                        "type": rel_type,
                        "pattern": pattern_name,
                        "strength": rel_props["strength"]
                    }
                    
                    pattern_relationships.append(relationship_data)
                    logger.debug(f"Created relationship: {from_name} -{rel_type}-> {to_name}")
                    
                except Exception as e:
                    logger.warning(f"Failed to create relationship {from_name} -{rel_type}-> {to_name}: {e}")
            
            if pattern_relationships:
                created_patterns.append({
                    "pattern_name": pattern_name,
                    "relationships": pattern_relationships,
                    "depth": len(pattern_relationships)
                })
        
        return created_patterns
    
    async def _create_pattern_concept(self, neo4j_client, concept_name: str) -> Dict[str, Any]:
        """Create a concept needed for patterns."""
        try:
            # Infer concept properties from name
            concept_type = "concept"
            category = "general"
            domain = "general"
            
            # Simple heuristics for concept classification
            if any(word in concept_name.lower() for word in ["data", "preprocessing", "feature"]):
                domain = "data_science"
                category = "technique"
            elif any(word in concept_name.lower() for word in ["neural", "network", "deep", "learning"]):
                domain = "machine_learning"
                category = "algorithm"
            elif any(word in concept_name.lower() for word in ["text", "language", "nlp"]):
                domain = "natural_language_processing"
                category = "task"
            elif any(word in concept_name.lower() for word in ["image", "vision", "visual"]):
                domain = "computer_vision"
                category = "task"
            
            concept_props = {
                "name": concept_name,
                "type": concept_type,
                "category": category,
                "domain": domain,
                "description": f"Concept created for multi-hop pattern: {concept_name}",
                "confidence": 0.8,
                "created_at": datetime.utcnow().isoformat(),
                "source": "multi_hop_pattern"
            }
            
            node_id = await neo4j_client.create_node(["Concept"], concept_props)
            
            return {
                "id": node_id,
                "name": concept_name,
                "type": concept_type,
                "category": category,
                "domain": domain
            }
            
        except Exception as e:
            logger.error(f"Failed to create pattern concept {concept_name}: {e}")
            raise
    
    async def _create_additional_concepts(self, neo4j_client) -> List[Dict[str, Any]]:
        """Create additional concepts needed for complex patterns."""
        logger.info("Creating additional concepts for complex patterns")
        
        additional_concepts_data = [
            # Abstract concepts
            {"name": "Artificial Intelligence", "type": "field", "category": "technology", "domain": "artificial_intelligence"},
            {"name": "Data Preprocessing", "type": "technique", "category": "preprocessing", "domain": "data_science"},
            {"name": "Predictions", "type": "output", "category": "result", "domain": "machine_learning"},
            {"name": "Decision Making", "type": "process", "category": "application", "domain": "general"},
            {"name": "Model Performance", "type": "metric", "category": "evaluation", "domain": "machine_learning"},
            
            # Pipeline concepts
            {"name": "Raw Text", "type": "input", "category": "data", "domain": "natural_language_processing"},
            {"name": "Text Understanding", "type": "output", "category": "result", "domain": "natural_language_processing"},
            {"name": "Raw Image", "type": "input", "category": "data", "domain": "computer_vision"},
            {"name": "Feature Maps", "type": "intermediate", "category": "representation", "domain": "computer_vision"},
            
            # Learning concepts
            {"name": "Labeled Data", "type": "resource", "category": "data", "domain": "machine_learning"},
            {"name": "Training", "type": "process", "category": "learning", "domain": "machine_learning"},
            {"name": "Trained Model", "type": "artifact", "category": "model", "domain": "machine_learning"},
            {"name": "Test Data", "type": "resource", "category": "data", "domain": "machine_learning"},
            {"name": "Performance Metrics", "type": "measurement", "category": "evaluation", "domain": "machine_learning"},
            
            # Historical concepts
            {"name": "Perceptron", "type": "algorithm", "category": "historical", "domain": "machine_learning"},
            {"name": "Multi-Layer Perceptron", "type": "algorithm", "category": "neural_network", "domain": "machine_learning"}
        ]
        
        created_concepts = []
        
        for concept_data in additional_concepts_data:
            try:
                # Check if concept already exists
                existing_query = "MATCH (c:Concept {name: $name}) RETURN id(c) as id"
                existing_result = await neo4j_client.execute_query(existing_query, {"name": concept_data["name"]})
                
                if existing_result:
                    # Concept already exists
                    concept_id = str(existing_result[0]["id"])
                    created_concepts.append({
                        "id": concept_id,
                        "name": concept_data["name"],
                        "existed": True
                    })
                    continue
                
                # Create new concept
                concept_props = {
                    **concept_data,
                    "description": f"Additional concept for multi-hop patterns: {concept_data['name']}",
                    "confidence": 0.9,
                    "created_at": datetime.utcnow().isoformat(),
                    "source": "multi_hop_pattern"
                }
                
                node_id = await neo4j_client.create_node(["Concept"], concept_props)
                
                created_concepts.append({
                    "id": node_id,
                    "name": concept_data["name"],
                    "type": concept_data["type"],
                    "category": concept_data["category"],
                    "domain": concept_data["domain"],
                    "existed": False
                })
                
                logger.debug(f"Created additional concept: {concept_data['name']}")
                
            except Exception as e:
                logger.warning(f"Failed to create additional concept {concept_data['name']}: {e}")
        
        return created_concepts
    
    async def _create_inferred_relationships(self, neo4j_client, concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create inferred relationships based on existing patterns."""
        logger.info("Creating inferred relationships")
        
        inferred_relationships = []
        
        for inference_pattern in self.inference_patterns:
            pattern_name = inference_pattern["pattern"]
            rules = inference_pattern["rules"]
            
            logger.debug(f"Applying inference pattern: {pattern_name}")
            
            for rel1_type, rel2_type, inferred_type in rules:
                try:
                    # Find chains of relationships that match the pattern
                    query = f"""
                    MATCH (a:Concept)-[r1:{rel1_type}]->(b:Concept)-[r2:{rel2_type}]->(c:Concept)
                    WHERE NOT EXISTS((a)-[:{inferred_type}]->(c))
                    RETURN id(a) as a_id, a.name as a_name,
                           id(c) as c_id, c.name as c_name,
                           r1.strength as r1_strength, r2.strength as r2_strength
                    LIMIT 20
                    """
                    
                    result = await neo4j_client.execute_query(query)
                    
                    for record in result:
                        try:
                            # Calculate inferred relationship strength
                            r1_strength = record.get("r1_strength", 0.5)
                            r2_strength = record.get("r2_strength", 0.5)
                            inferred_strength = round(r1_strength * r2_strength * 0.8, 3)  # Reduce confidence for inference
                            
                            # Create inferred relationship
                            rel_props = {
                                "strength": inferred_strength,
                                "relationship_type": inferred_type,
                                "source": "multi_hop_inference",
                                "inference_pattern": pattern_name,
                                "inferred_from": f"{rel1_type} + {rel2_type}",
                                "created_at": datetime.utcnow().isoformat(),
                                "description": f"Inferred via {pattern_name}: {rel1_type} + {rel2_type} -> {inferred_type}"
                            }
                            
                            rel_id = await neo4j_client.create_relationship(
                                str(record["a_id"]),
                                str(record["c_id"]),
                                inferred_type,
                                rel_props
                            )
                            
                            relationship_data = {
                                "id": rel_id,
                                "from_concept": record["a_name"],
                                "to_concept": record["c_name"],
                                "type": inferred_type,
                                "strength": inferred_strength,
                                "inference_pattern": pattern_name,
                                "source_relationships": [rel1_type, rel2_type]
                            }
                            
                            inferred_relationships.append(relationship_data)
                            logger.debug(f"Inferred: {record['a_name']} -{inferred_type}-> {record['c_name']}")
                            
                        except Exception as e:
                            logger.warning(f"Failed to create inferred relationship: {e}")
                
                except Exception as e:
                    logger.warning(f"Failed to process inference rule {rel1_type} + {rel2_type} -> {inferred_type}: {e}")
        
        return inferred_relationships
    
    async def _create_topic_hierarchy(self, neo4j_client, concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create hierarchical topic structure."""
        logger.info("Creating topic hierarchy")
        
        # Define topic hierarchy
        topic_hierarchy_data = [
            {"name": "Artificial Intelligence", "level": 1, "parent": None},
            {"name": "Machine Learning", "level": 2, "parent": "Artificial Intelligence"},
            {"name": "Deep Learning", "level": 3, "parent": "Machine Learning"},
            {"name": "Natural Language Processing", "level": 2, "parent": "Artificial Intelligence"},
            {"name": "Computer Vision", "level": 2, "parent": "Artificial Intelligence"},
            {"name": "Data Science", "level": 1, "parent": None},
            {"name": "Statistics", "level": 2, "parent": "Data Science"},
            {"name": "Data Mining", "level": 2, "parent": "Data Science"},
            {"name": "Neural Network Architectures", "level": 3, "parent": "Deep Learning"},
            {"name": "Optimization Algorithms", "level": 3, "parent": "Machine Learning"},
            {"name": "Text Processing", "level": 3, "parent": "Natural Language Processing"},
            {"name": "Image Processing", "level": 3, "parent": "Computer Vision"}
        ]
        
        created_topics = []
        topic_map = {}
        
        # Create topic nodes
        for topic_data in topic_hierarchy_data:
            try:
                topic_props = {
                    "name": topic_data["name"],
                    "level": topic_data["level"],
                    "description": f"Topic hierarchy node: {topic_data['name']}",
                    "created_at": datetime.utcnow().isoformat(),
                    "source": "topic_hierarchy"
                }
                
                node_id = await neo4j_client.create_node(["Topic"], topic_props)
                
                topic_node = {
                    "id": node_id,
                    "name": topic_data["name"],
                    "level": topic_data["level"],
                    "parent": topic_data["parent"]
                }
                
                created_topics.append(topic_node)
                topic_map[topic_data["name"]] = topic_node
                
                logger.debug(f"Created topic: {topic_data['name']} (level {topic_data['level']})")
                
            except Exception as e:
                logger.warning(f"Failed to create topic {topic_data['name']}: {e}")
        
        # Create parent-child relationships
        for topic in created_topics:
            if topic["parent"] and topic["parent"] in topic_map:
                try:
                    parent_topic = topic_map[topic["parent"]]
                    
                    rel_props = {
                        "hierarchy_level": topic["level"] - parent_topic["level"],
                        "relationship_type": "INCLUDES",
                        "source": "topic_hierarchy",
                        "created_at": datetime.utcnow().isoformat()
                    }
                    
                    await neo4j_client.create_relationship(
                        parent_topic["id"],
                        topic["id"],
                        "INCLUDES",
                        rel_props
                    )
                    
                    logger.debug(f"Created hierarchy: {parent_topic['name']} INCLUDES {topic['name']}")
                    
                except Exception as e:
                    logger.warning(f"Failed to create hierarchy relationship: {e}")
        
        # Connect concepts to topics
        for concept in concepts:
            try:
                # Find matching topic based on concept domain/name
                matching_topic = None
                
                if concept["domain"] == "machine_learning":
                    if "deep" in concept["name"].lower() or "neural" in concept["name"].lower():
                        matching_topic = topic_map.get("Deep Learning")
                    else:
                        matching_topic = topic_map.get("Machine Learning")
                elif concept["domain"] == "natural_language_processing":
                    matching_topic = topic_map.get("Natural Language Processing")
                elif concept["domain"] == "computer_vision":
                    matching_topic = topic_map.get("Computer Vision")
                elif concept["domain"] == "data_science":
                    matching_topic = topic_map.get("Data Science")
                
                if matching_topic:
                    rel_props = {
                        "relationship_type": "BELONGS_TO",
                        "source": "topic_hierarchy",
                        "created_at": datetime.utcnow().isoformat()
                    }
                    
                    await neo4j_client.create_relationship(
                        concept["id"],
                        matching_topic["id"],
                        "BELONGS_TO",
                        rel_props
                    )
                    
                    logger.debug(f"Connected concept {concept['name']} to topic {matching_topic['name']}")
                
            except Exception as e:
                logger.warning(f"Failed to connect concept {concept['name']} to topic: {e}")
        
        return created_topics
    
    async def _test_query_patterns(self, neo4j_client) -> List[Dict[str, Any]]:
        """Test complex query patterns on the multi-hop graph."""
        logger.info("Testing multi-hop query patterns")
        
        query_results = []
        
        for pattern in self.query_patterns:
            try:
                logger.debug(f"Testing query pattern: {pattern['name']}")
                
                # Execute the query with example parameters
                result = await neo4j_client.execute_query(
                    pattern["query"], 
                    pattern["example_params"]
                )
                
                query_result = {
                    "name": pattern["name"],
                    "description": pattern["description"],
                    "query": pattern["query"],
                    "parameters": pattern["example_params"],
                    "result_count": len(result),
                    "sample_results": result[:3] if result else [],
                    "success": True
                }
                
                query_results.append(query_result)
                logger.debug(f"Query {pattern['name']} returned {len(result)} results")
                
            except Exception as e:
                logger.warning(f"Query pattern {pattern['name']} failed: {e}")
                
                query_results.append({
                    "name": pattern["name"],
                    "description": pattern["description"],
                    "query": pattern["query"],
                    "parameters": pattern["example_params"],
                    "error": str(e),
                    "success": False
                })
        
        return query_results
    
    async def close(self) -> None:
        """Close database connections."""
        await self.factory.close()


async def main():
    """Main function to run the multi-hop relationship generator."""
    parser = argparse.ArgumentParser(description="Generate multi-hop relationships for local development")
    parser.add_argument("--max-depth", type=int, default=4, help="Maximum depth for relationship chains")
    parser.add_argument("--reset", action="store_true", help="Reset existing multi-hop patterns")
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
    
    # Generate multi-hop relationships
    generator = MultiHopRelationshipGenerator(config)
    
    try:
        result = await generator.generate_multi_hop_relationships(
            max_depth=args.max_depth,
            reset=args.reset
        )
        
        patterns = result["patterns"]
        inferred_relationships = result["inferred_relationships"]
        topic_hierarchy = result["topic_hierarchy"]
        query_examples = result["query_examples"]
        
        print(f"\n✅ Successfully created multi-hop relationship patterns!")
        print(f"🔗 Relationship patterns: {len(patterns)}")
        print(f"🧠 Inferred relationships: {len(inferred_relationships)}")
        print(f"🏗️  Topic hierarchy nodes: {len(topic_hierarchy)}")
        print(f"🔍 Query examples tested: {len(query_examples)}")
        
        # Show pattern statistics
        if patterns:
            print(f"\n📊 Relationship Patterns:")
            print("=" * 60)
            for pattern in patterns:
                depth = pattern["depth"]
                name = pattern["pattern_name"].replace('_', ' ').title()
                print(f"🔗 {name:30} | {depth:2d} relationships | Depth: {depth}")
        
        # Show inference statistics
        if inferred_relationships:
            inference_counts = {}
            for rel in inferred_relationships:
                pattern = rel["inference_pattern"]
                inference_counts[pattern] = inference_counts.get(pattern, 0) + 1
            
            print(f"\n🧠 Inference Patterns:")
            print("=" * 50)
            for pattern, count in inference_counts.items():
                pattern_display = pattern.replace('_', ' ').title()
                print(f"🔮 {pattern_display:20} | {count:3d} inferences")
        
        # Show topic hierarchy
        if topic_hierarchy:
            print(f"\n🏗️  Topic Hierarchy:")
            print("=" * 50)
            
            # Group by level
            levels = {}
            for topic in topic_hierarchy:
                level = topic["level"]
                if level not in levels:
                    levels[level] = []
                levels[level].append(topic["name"])
            
            for level in sorted(levels.keys()):
                topics = levels[level]
                indent = "  " * (level - 1)
                level_emoji = ["🌟", "📚", "📖", "📄"][min(level - 1, 3)]
                print(f"{indent}{level_emoji} Level {level}: {', '.join(topics)}")
        
        # Show query examples
        successful_queries = [q for q in query_examples if q["success"]]
        failed_queries = [q for q in query_examples if not q["success"]]
        
        print(f"\n🔍 Query Pattern Results:")
        print("=" * 60)
        print(f"✅ Successful queries: {len(successful_queries)}")
        print(f"❌ Failed queries: {len(failed_queries)}")
        
        if successful_queries:
            print(f"\n📋 Sample Query Results:")
            for query in successful_queries[:3]:
                print(f"🔍 {query['name']}: {query['result_count']} results")
                if query.get('sample_results'):
                    for i, sample in enumerate(query['sample_results'][:2]):
                        print(f"   {i+1}. {sample}")
        
        # Show example queries for exploration
        print(f"\n💡 Example Multi-Hop Queries to Try:")
        print("=" * 80)
        
        example_queries = [
            "MATCH path = (a:Concept)-[*2..4]-(b:Concept) WHERE a.name = 'Machine Learning' RETURN path LIMIT 5",
            "MATCH (c:Concept)-[:PREREQUISITE_FOR*1..3]->(target:Concept {name: 'Deep Learning'}) RETURN c.name",
            "MATCH path = (start:Topic)-[:INCLUDES*1..3]->(end:Concept) RETURN path LIMIT 10",
            "MATCH (d:Document)-[:CONTAINS]->(c:Concept)-[:RELATED_TO*1..2]->(related:Concept) RETURN d.title, related.name"
        ]
        
        for i, query in enumerate(example_queries, 1):
            print(f"{i}. {query}")
        
        print(f"\n🔍 Use Neo4j Browser at http://localhost:7474 to explore multi-hop relationships")
        print(f"💡 Try queries with variable-length paths: -[*1..3]- for 1-3 hop relationships")
        
        return 0
        
    except Exception as e:
        logger.error(f"Failed to generate multi-hop relationships: {e}")
        return 1
    
    finally:
        await generator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)