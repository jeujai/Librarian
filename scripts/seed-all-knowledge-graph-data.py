#!/usr/bin/env python3
"""
Complete Knowledge Graph Test Data Generator

This script orchestrates the creation of comprehensive knowledge graph test data
by running all the individual generators in the correct order. It creates:
1. Sample concepts and relationships
2. Document-concept associations  
3. Multi-hop relationship examples

Usage:
    python scripts/seed-all-knowledge-graph-data.py [--concepts N] [--reset] [--verbose]
    
    --concepts N: Number of concepts to create (default: 50)
    --reset: Reset all existing knowledge graph data
    --verbose: Enable verbose logging
"""

import asyncio
import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.config.local_config import LocalDatabaseConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_knowledge_graph_generation(
    concept_count: int = 50,
    reset: bool = False,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Run complete knowledge graph test data generation.
    
    Args:
        concept_count: Number of concepts to create
        reset: Whether to reset existing data
        verbose: Enable verbose logging
        
    Returns:
        Dictionary with generation results
    """
    start_time = time.time()
    results = {
        "concepts": {},
        "associations": {},
        "multi_hop": {},
        "total_time": 0,
        "success": False
    }
    
    try:
        logger.info("🚀 Starting comprehensive knowledge graph data generation")
        logger.info(f"📊 Configuration: {concept_count} concepts, reset={reset}")
        
        # Step 1: Generate concepts and basic relationships
        logger.info("\n" + "="*60)
        logger.info("📚 STEP 1: Creating sample concepts and relationships")
        logger.info("="*60)
        
        step1_start = time.time()
        
        # Import and run the knowledge graph generator
        from seed_sample_knowledge_graph import SampleKnowledgeGraphGenerator
        
        config = LocalDatabaseConfig()
        kg_generator = SampleKnowledgeGraphGenerator(config)
        
        try:
            concepts_result = await kg_generator.generate_knowledge_graph(
                concept_count=concept_count,
                reset=reset,
                with_relationships=True
            )
            
            results["concepts"] = {
                "concepts_created": len(concepts_result["concepts"]),
                "relationships_created": len(concepts_result["relationships"]),
                "domains": concepts_result["domains"],
                "relationship_types": concepts_result["relationship_types"],
                "time": time.time() - step1_start,
                "success": True
            }
            
            logger.info(f"✅ Step 1 completed in {results['concepts']['time']:.2f}s")
            logger.info(f"   📊 Created {results['concepts']['concepts_created']} concepts")
            logger.info(f"   🔗 Created {results['concepts']['relationships_created']} relationships")
            
        except Exception as e:
            logger.error(f"❌ Step 1 failed: {e}")
            results["concepts"]["success"] = False
            results["concepts"]["error"] = str(e)
            raise
        finally:
            await kg_generator.close()
        
        # Step 2: Create document-concept associations
        logger.info("\n" + "="*60)
        logger.info("📄 STEP 2: Creating document-concept associations")
        logger.info("="*60)
        
        step2_start = time.time()
        
        # Import and run the document-concept association generator
        from seed_document_concept_associations import DocumentConceptAssociationGenerator
        
        assoc_generator = DocumentConceptAssociationGenerator(config)
        
        try:
            associations_result = await assoc_generator.generate_document_concept_associations(
                max_associations_per_document=8,
                reset=False  # Don't reset, we want to keep the concepts from step 1
            )
            
            results["associations"] = {
                "document_associations": len(associations_result["document_associations"]),
                "chunk_associations": len(associations_result["chunk_associations"]),
                "documents_processed": associations_result["documents_processed"],
                "concepts_available": associations_result["concepts_available"],
                "document_nodes_created": associations_result["document_nodes_created"],
                "time": time.time() - step2_start,
                "success": True
            }
            
            logger.info(f"✅ Step 2 completed in {results['associations']['time']:.2f}s")
            logger.info(f"   📄 Processed {results['associations']['documents_processed']} documents")
            logger.info(f"   🔗 Created {results['associations']['document_associations']} document-concept associations")
            logger.info(f"   📝 Created {results['associations']['chunk_associations']} chunk-concept associations")
            
        except Exception as e:
            logger.error(f"❌ Step 2 failed: {e}")
            results["associations"]["success"] = False
            results["associations"]["error"] = str(e)
            # Continue to step 3 even if step 2 fails
            
        finally:
            await assoc_generator.close()
        
        # Step 3: Create multi-hop relationship examples
        logger.info("\n" + "="*60)
        logger.info("🕸️  STEP 3: Creating multi-hop relationship examples")
        logger.info("="*60)
        
        step3_start = time.time()
        
        # Import and run the multi-hop relationship generator
        from seed_multi_hop_relationships import MultiHopRelationshipGenerator
        
        multihop_generator = MultiHopRelationshipGenerator(config)
        
        try:
            multihop_result = await multihop_generator.generate_multi_hop_relationships(
                max_depth=4,
                reset=False  # Don't reset, we want to build on existing data
            )
            
            results["multi_hop"] = {
                "patterns_created": len(multihop_result["patterns"]),
                "additional_concepts": len(multihop_result["additional_concepts"]),
                "inferred_relationships": len(multihop_result["inferred_relationships"]),
                "topic_hierarchy": len(multihop_result["topic_hierarchy"]),
                "query_examples": len(multihop_result["query_examples"]),
                "successful_queries": len([q for q in multihop_result["query_examples"] if q["success"]]),
                "max_depth_achieved": multihop_result["max_depth_achieved"],
                "time": time.time() - step3_start,
                "success": True
            }
            
            logger.info(f"✅ Step 3 completed in {results['multi_hop']['time']:.2f}s")
            logger.info(f"   🔗 Created {results['multi_hop']['patterns_created']} relationship patterns")
            logger.info(f"   🧠 Created {results['multi_hop']['inferred_relationships']} inferred relationships")
            logger.info(f"   🏗️  Created {results['multi_hop']['topic_hierarchy']} topic hierarchy nodes")
            logger.info(f"   🔍 Tested {results['multi_hop']['successful_queries']}/{results['multi_hop']['query_examples']} query patterns")
            
        except Exception as e:
            logger.error(f"❌ Step 3 failed: {e}")
            results["multi_hop"]["success"] = False
            results["multi_hop"]["error"] = str(e)
            
        finally:
            await multihop_generator.close()
        
        # Calculate total time and success
        results["total_time"] = time.time() - start_time
        results["success"] = (
            results["concepts"].get("success", False) and
            (results["associations"].get("success", False) or results["multi_hop"].get("success", False))
        )
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Knowledge graph generation failed: {e}")
        results["total_time"] = time.time() - start_time
        results["success"] = False
        results["error"] = str(e)
        return results


def print_generation_summary(results: Dict[str, Any]) -> None:
    """Print a comprehensive summary of the generation results."""
    
    print("\n" + "="*80)
    print("🎉 KNOWLEDGE GRAPH GENERATION COMPLETE")
    print("="*80)
    
    if results["success"]:
        print("✅ Overall Status: SUCCESS")
    else:
        print("❌ Overall Status: FAILED")
        if "error" in results:
            print(f"   Error: {results['error']}")
    
    print(f"⏱️  Total Time: {results['total_time']:.2f} seconds")
    
    # Step 1 Summary
    print(f"\n📚 STEP 1: Sample Concepts and Relationships")
    print("-" * 50)
    if results["concepts"].get("success"):
        print(f"✅ Status: SUCCESS ({results['concepts']['time']:.2f}s)")
        print(f"   🔬 Concepts: {results['concepts']['concepts_created']}")
        print(f"   🔗 Relationships: {results['concepts']['relationships_created']}")
        print(f"   🏷️  Domains: {', '.join(results['concepts']['domains'])}")
    else:
        print(f"❌ Status: FAILED")
        if "error" in results["concepts"]:
            print(f"   Error: {results['concepts']['error']}")
    
    # Step 2 Summary
    print(f"\n📄 STEP 2: Document-Concept Associations")
    print("-" * 50)
    if results["associations"].get("success"):
        print(f"✅ Status: SUCCESS ({results['associations']['time']:.2f}s)")
        print(f"   📄 Documents: {results['associations']['documents_processed']}")
        print(f"   🔗 Doc-Concept Links: {results['associations']['document_associations']}")
        print(f"   📝 Chunk-Concept Links: {results['associations']['chunk_associations']}")
        print(f"   🏗️  Document Nodes: {results['associations']['document_nodes_created']}")
    else:
        print(f"❌ Status: FAILED")
        if "error" in results["associations"]:
            print(f"   Error: {results['associations']['error']}")
    
    # Step 3 Summary
    print(f"\n🕸️  STEP 3: Multi-Hop Relationships")
    print("-" * 50)
    if results["multi_hop"].get("success"):
        print(f"✅ Status: SUCCESS ({results['multi_hop']['time']:.2f}s)")
        print(f"   🔗 Patterns: {results['multi_hop']['patterns_created']}")
        print(f"   🧠 Inferred: {results['multi_hop']['inferred_relationships']}")
        print(f"   🏗️  Topics: {results['multi_hop']['topic_hierarchy']}")
        print(f"   🔍 Queries: {results['multi_hop']['successful_queries']}/{results['multi_hop']['query_examples']}")
        print(f"   📏 Max Depth: {results['multi_hop']['max_depth_achieved']}")
    else:
        print(f"❌ Status: FAILED")
        if "error" in results["multi_hop"]:
            print(f"   Error: {results['multi_hop']['error']}")
    
    # Usage Instructions
    print(f"\n💡 NEXT STEPS")
    print("-" * 50)
    print("🔍 Explore the knowledge graph:")
    print("   • Neo4j Browser: http://localhost:7474")
    print("   • Username: neo4j")
    print("   • Password: ml_password (or your configured password)")
    
    print(f"\n📋 Sample Queries to Try:")
    sample_queries = [
        "MATCH (c:Concept) RETURN c.name, c.domain LIMIT 10",
        "MATCH (d:Document)-[:CONTAINS]->(c:Concept) RETURN d.title, c.name LIMIT 10",
        "MATCH path = (c1:Concept)-[*2..3]-(c2:Concept) RETURN path LIMIT 5",
        "MATCH (t:Topic)-[:INCLUDES*1..2]->(c:Concept) RETURN t.name, collect(c.name) LIMIT 5"
    ]
    
    for i, query in enumerate(sample_queries, 1):
        print(f"   {i}. {query}")
    
    print(f"\n🔧 Troubleshooting:")
    print("   • Check Neo4j is running: docker-compose -f docker-compose.local.yml ps")
    print("   • View logs: docker-compose -f docker-compose.local.yml logs neo4j")
    print("   • Restart services: docker-compose -f docker-compose.local.yml restart")


async def main():
    """Main function to run the complete knowledge graph generation."""
    parser = argparse.ArgumentParser(description="Generate complete knowledge graph test data")
    parser.add_argument("--concepts", type=int, default=50, help="Number of concepts to create")
    parser.add_argument("--reset", action="store_true", help="Reset all existing knowledge graph data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Run the complete generation process
        results = await run_knowledge_graph_generation(
            concept_count=args.concepts,
            reset=args.reset,
            verbose=args.verbose
        )
        
        # Print comprehensive summary
        print_generation_summary(results)
        
        # Return appropriate exit code
        return 0 if results["success"] else 1
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Generation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)