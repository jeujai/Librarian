#!/usr/bin/env python3
"""
Create Enrichment Indexes Migration Script

This script creates the necessary indexes for the Knowledge Graph External Enrichment feature:
- ExternalEntity.q_number: For fast YAGO entity lookups
- Concept.yago_qid: For fast entity resolution

These indexes support efficient cross-document linking and entity disambiguation queries.

Usage:
    python scripts/create-enrichment-indexes.py

Requirements: 8.1, 8.2
"""

import asyncio
import logging
import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def create_enrichment_indexes():
    """Create enrichment indexes for the knowledge graph."""
    logger.info("=" * 80)
    logger.info("ENRICHMENT INDEX CREATION SCRIPT")
    logger.info("=" * 80)
    
    try:
        from multimodal_librarian.services.knowledge_graph_service import (
            get_knowledge_graph_service,
        )
        
        logger.info("Getting knowledge graph service...")
        kg_service = get_knowledge_graph_service()
        
        logger.info("Creating enrichment indexes...")
        result = await kg_service.ensure_enrichment_indexes()
        
        logger.info("=" * 80)
        logger.info("INDEX CREATION RESULTS")
        logger.info("=" * 80)
        logger.info(f"Status: {result['status']}")
        
        if result.get('indexes_created'):
            logger.info(f"Indexes created: {', '.join(result['indexes_created'])}")
        
        if result.get('indexes_skipped'):
            logger.info(f"Indexes skipped (already exist): {', '.join(result['indexes_skipped'])}")
        
        if result.get('errors'):
            logger.warning(f"Errors: {result['errors']}")
        
        # Get index info
        logger.info("")
        logger.info("Current index information:")
        index_info = await kg_service.get_index_info()
        
        if index_info.get('status') == 'success':
            if index_info.get('client_type') == 'neo4j':
                for idx in index_info.get('indexes', []):
                    logger.info(
                        f"  - {idx.get('name')}: {idx.get('labels')} "
                        f"({idx.get('properties')}) [{idx.get('state')}]"
                    )
            else:
                logger.info(f"  Client type: {index_info.get('client_type')}")
                if index_info.get('note'):
                    logger.info(f"  Note: {index_info.get('note')}")
                for idx in index_info.get('enrichment_indexes', []):
                    logger.info(
                        f"  - {idx.get('name')}: {idx.get('label')}.{idx.get('property')} "
                        f"(auto_indexed: {idx.get('auto_indexed')})"
                    )
        else:
            logger.warning(f"Could not get index info: {index_info.get('error')}")
        
        logger.info("=" * 80)
        
        if result['status'] in ('success', 'skipped'):
            logger.info("✓ Enrichment index creation completed successfully")
            return 0
        elif result['status'] == 'partial':
            logger.warning("⚠ Enrichment index creation partially completed")
            return 1
        else:
            logger.error("✗ Enrichment index creation failed")
            return 2
            
    except Exception as e:
        logger.error(f"Failed to create enrichment indexes: {e}", exc_info=True)
        return 2


def main():
    """Main entry point."""
    exit_code = asyncio.run(create_enrichment_indexes())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
