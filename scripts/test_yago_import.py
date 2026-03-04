#!/usr/bin/env python3
"""
Test YAGO bulk load with YAGO 4.5 dump files.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.clients.neo4j_client import Neo4jClient
from multimodal_librarian.components.yago.loader import YagoNeo4jLoader
from multimodal_librarian.components.yago.processor import YagoDumpProcessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("yago_test")


async def test_import():
    """Test the YAGO import pipeline with a sample file."""
    logger.info("=" * 60)
    logger.info("YAGO IMPORT TEST")
    logger.info("=" * 60)
    
    # Connect to Neo4j
    logger.info("\n[1/3] Connecting to Neo4j...")
    neo4j_client = Neo4jClient()
    await neo4j_client.connect()
    logger.info("Connected to Neo4j")
    
    # Create loader
    loader = YagoNeo4jLoader(neo4j_client=neo4j_client, batch_size=100)
    
    # Clear existing data
    logger.info("\n[2/3] Clearing existing YAGO data...")
    await loader.clear_all()
    
    # Create processor with YAGO dump directory
    dump_dir = Path(__file__).parent.parent / "yago-dumps"
    logger.info(f"\n[3/3] Processing YAGO files from: {dump_dir}")

    processor = YagoDumpProcessor(dump_dir=dump_dir)

    # Process and import
    entity_count = 0
    async for entity in processor.process(file_keys=["facts"]):
        logger.info(f"  Entity: {entity.entity_id} - {entity.label}")
        logger.info(f"    Description: {entity.description}")
        logger.info(f"    Instance of: {entity.instance_of}")
        logger.info(f"    Subclass of: {entity.subclass_of}")
        logger.info(f"    Aliases: {entity.aliases}")
        
        await loader.create_entity_node(entity)
        
        # Create relationships
        relationships = []
        for target_id in entity.instance_of:
            if target_id:
                relationships.append({"target_id": target_id, "type": "INSTANCE_OF"})
        for target_id in entity.subclass_of:
            if target_id:
                relationships.append({"target_id": target_id, "type": "SUBCLASS_OF"})
        
        if relationships:
            await loader.create_relationships(entity.entity_id, relationships)
        
        entity_count += 1
    
    # Get stats
    stats = await loader.get_stats()
    
    logger.info("\n" + "=" * 60)
    logger.info("TEST COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Entities imported: {stats.entity_count}")
    logger.info(f"Relationships created: {stats.relationship_count}")
    logger.info(f"  - INSTANCE_OF: {stats.instance_of_count}")
    logger.info(f"  - SUBCLASS_OF: {stats.subclass_of_count}")
    
    # Verify with Cypher query
    logger.info("\nVerifying with Cypher query...")
    result = await neo4j_client.execute_query("MATCH (e:YagoEntity) RETURN e.entity_id, e.label, e.description")
    for record in result:
        logger.info(f"  {record['e.entity_id']}: {record['e.label']} - {record['e.description']}")
    
    await neo4j_client.close()
    logger.info("\nNeo4j connection closed")


if __name__ == "__main__":
    asyncio.run(test_import())