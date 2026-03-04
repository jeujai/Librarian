#!/usr/bin/env python3
"""Clear YAGO data from Neo4j."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from multimodal_librarian.clients.neo4j_client import Neo4jClient
from multimodal_librarian.components.yago.loader import YagoNeo4jLoader


async def clear_yago():
    """Clear all YAGO data from Neo4j."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    print(f"Connecting to Neo4j at {uri}...")
    neo4j_client = Neo4jClient(uri=uri, user=user, password=password)
    await neo4j_client.connect()
    
    print("Creating loader...")
    loader = YagoNeo4jLoader(neo4j_client=neo4j_client, batch_size=1000)
    
    print("Clearing YAGO data...")
    await loader.clear_all()
    
    print("YAGO data cleared successfully!")
    
    await neo4j_client.close()
    print("Connection closed.")


if __name__ == "__main__":
    asyncio.run(clear_yago())