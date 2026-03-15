"""
Knowledge Graph Service for Multimodal Librarian

This service provides high-level operations for managing knowledge graphs,
including CRUD operations for nodes and relationships.

This service now uses AWS Neptune (AWS-native graph database).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..clients.database_factory import get_database_factory

logger = logging.getLogger(__name__)


class KnowledgeGraphError(Exception):
    """Raised when knowledge graph operations fail."""
    pass


class KnowledgeGraphService:
    """
    Service for managing knowledge graph operations using AWS Neptune.
    """
    
    def __init__(self):
        """Initialize the knowledge graph service with Neptune client."""
        factory = get_database_factory()
        self.client = factory.get_graph_client()
        self._indexes_created = False
    
    async def ensure_enrichment_indexes(self) -> Dict[str, Any]:
        """
        Create indexes for enrichment-related properties.
        
        Creates indexes on:
        - ExternalEntity.q_number: For fast YAGO entity lookups
        - Concept.yago_qid: For fast entity resolution
        
        These indexes support efficient cross-document linking and
        entity disambiguation queries.
        
        Returns:
            Dictionary with index creation results
            
        Requirements: 8.1, 8.2
        """
        if self._indexes_created:
            logger.debug("Enrichment indexes already created, skipping")
            return {"status": "skipped", "reason": "already_created"}
        
        results = {
            "status": "success",
            "indexes_created": [],
            "indexes_skipped": [],
            "errors": []
        }
        
        # Define indexes to create
        # Format: (index_name, label, property)
        indexes = [
            ("external_entity_qnum_idx", "ExternalEntity", "q_number"),
            ("concept_yago_idx", "Concept", "yago_qid"),
        ]
        
        for index_name, label, property_name in indexes:
            try:
                created = await self._create_index_if_not_exists(
                    index_name, label, property_name
                )
                if created:
                    results["indexes_created"].append(index_name)
                    logger.info(f"Created index: {index_name} on {label}.{property_name}")
                else:
                    results["indexes_skipped"].append(index_name)
                    logger.debug(f"Index already exists: {index_name}")
            except Exception as e:
                error_msg = f"Failed to create index {index_name}: {e}"
                results["errors"].append(error_msg)
                logger.warning(error_msg)
        
        if results["errors"]:
            results["status"] = "partial" if results["indexes_created"] else "failed"
        
        self._indexes_created = True
        
        logger.info(
            f"Enrichment index creation complete: "
            f"{len(results['indexes_created'])} created, "
            f"{len(results['indexes_skipped'])} skipped, "
            f"{len(results['errors'])} errors"
        )
        
        return results
    
    async def _create_index_if_not_exists(
        self,
        index_name: str,
        label: str,
        property_name: str
    ) -> bool:
        """
        Create an index if it doesn't already exist.
        
        Supports both Neo4j (Cypher) and Neptune (Gremlin) backends.
        
        Args:
            index_name: Name for the index
            label: Node label to index
            property_name: Property to index
            
        Returns:
            True if index was created, False if it already existed
            
        Raises:
            KnowledgeGraphError: If index creation fails
        """
        try:
            # Check if this is a Neo4j client (has execute_query with Cypher support)
            # or Neptune client (uses Gremlin)
            client_type = self._detect_client_type()
            
            if client_type == "neo4j":
                return await self._create_neo4j_index(index_name, label, property_name)
            elif client_type == "neptune":
                return await self._create_neptune_index(index_name, label, property_name)
            else:
                logger.warning(f"Unknown client type: {client_type}, skipping index creation")
                return False
                
        except Exception as e:
            raise KnowledgeGraphError(f"Index creation failed: {e}")
    
    def _detect_client_type(self) -> str:
        """
        Detect the type of graph database client.
        
        Returns:
            "neo4j" for Neo4j client, "neptune" for Neptune client
        """
        client_class_name = self.client.__class__.__name__.lower()
        
        if "neo4j" in client_class_name:
            return "neo4j"
        elif "neptune" in client_class_name:
            return "neptune"
        else:
            # Check for specific attributes
            if hasattr(self.client, 'g'):  # Gremlin traversal source
                return "neptune"
            return "neo4j"  # Default to Neo4j for Cypher-based clients
    
    async def _create_neo4j_index(
        self,
        index_name: str,
        label: str,
        property_name: str
    ) -> bool:
        """
        Create a Neo4j index using Cypher.
        
        Args:
            index_name: Name for the index
            label: Node label to index
            property_name: Property to index
            
        Returns:
            True if index was created, False if it already existed
        """
        try:
            # Check if index already exists
            check_query = """
            SHOW INDEXES
            WHERE name = $index_name
            """
            
            try:
                existing = await self.client.execute_query(
                    check_query, 
                    {"index_name": index_name}
                )
                if existing:
                    return False
            except Exception:
                # SHOW INDEXES might not be supported in all Neo4j versions
                # Try alternative approach
                pass
            
            # Create the index using CREATE INDEX IF NOT EXISTS
            # This syntax works in Neo4j 4.x and 5.x
            create_query = f"""
            CREATE INDEX {index_name} IF NOT EXISTS
            FOR (n:{label})
            ON (n.{property_name})
            """
            
            await self.client.execute_query(create_query, {})
            return True
            
        except Exception as e:
            # Check if error is because index already exists
            error_str = str(e).lower()
            if "already exists" in error_str or "equivalent index" in error_str:
                return False
            raise
    
    async def _create_neptune_index(
        self,
        index_name: str,
        label: str,
        property_name: str
    ) -> bool:
        """
        Create a Neptune index.
        
        Note: Neptune automatically indexes all properties, so this method
        primarily ensures the property is being used in a way that Neptune
        can optimize. For explicit index control, Neptune uses different
        mechanisms than Neo4j.
        
        Args:
            index_name: Name for the index (used for logging)
            label: Vertex label to index
            property_name: Property to index
            
        Returns:
            True (Neptune auto-indexes properties)
        """
        # Neptune automatically indexes all vertex and edge properties
        # There's no explicit CREATE INDEX command in Gremlin
        # However, we can verify the property exists on some vertices
        # and log that Neptune will auto-index it
        
        logger.info(
            f"Neptune auto-indexes property '{property_name}' on label '{label}'. "
            f"Index name '{index_name}' is for reference only."
        )
        
        # Optionally, we could create a property key constraint or
        # verify the property exists, but Neptune handles this automatically
        return True
    
    async def get_index_info(self) -> Dict[str, Any]:
        """
        Get information about existing indexes.
        
        Returns:
            Dictionary with index information
        """
        try:
            client_type = self._detect_client_type()
            
            if client_type == "neo4j":
                return await self._get_neo4j_index_info()
            else:
                return await self._get_neptune_index_info()
                
        except Exception as e:
            logger.warning(f"Error getting index info: {e}")
            return {"status": "error", "error": str(e)}
    
    async def _get_neo4j_index_info(self) -> Dict[str, Any]:
        """Get Neo4j index information."""
        try:
            query = "SHOW INDEXES"
            result = await self.client.execute_query(query, {})
            
            indexes = []
            for record in result:
                indexes.append({
                    "name": record.get("name"),
                    "type": record.get("type"),
                    "labels": record.get("labelsOrTypes"),
                    "properties": record.get("properties"),
                    "state": record.get("state")
                })
            
            return {
                "status": "success",
                "client_type": "neo4j",
                "indexes": indexes
            }
        except Exception as e:
            return {
                "status": "error",
                "client_type": "neo4j",
                "error": str(e)
            }
    
    async def _get_neptune_index_info(self) -> Dict[str, Any]:
        """Get Neptune index information."""
        # Neptune doesn't have explicit index listing like Neo4j
        # Return information about auto-indexing
        return {
            "status": "success",
            "client_type": "neptune",
            "note": "Neptune automatically indexes all vertex and edge properties",
            "enrichment_indexes": [
                {
                    "name": "external_entity_qnum_idx",
                    "label": "ExternalEntity",
                    "property": "q_number",
                    "auto_indexed": True
                },
                {
                    "name": "concept_yago_idx",
                    "label": "Concept",
                    "property": "yago_qid",
                    "auto_indexed": True
                }
            ]
        }
    
    # Node Operations
    
    async def create_node(self, label: str, properties: Dict[str, Any], 
                   merge_on: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Create a node with given label and properties.
        
        Args:
            label: Node label (e.g., "Document", "Entity", "Person")
            properties: Node properties
            merge_on: Properties to use for MERGE instead of CREATE (prevents duplicates)
            
        Returns:
            Created or merged node information
        """
        try:
            # Add metadata
            properties["created_at"] = datetime.utcnow().isoformat()
            properties["updated_at"] = datetime.utcnow().isoformat()
            
            if merge_on:
                # Use MERGE to avoid duplicates
                merge_props = {key: properties[key] for key in merge_on if key in properties}
                set_props = {key: value for key, value in properties.items() if key not in merge_on}
                
                # Build MERGE clause with proper Cypher syntax: {key: $key}
                merge_clause = ", ".join([f"{key}: ${key}" for key in merge_props.keys()])
                # Build SET clause for ON CREATE
                set_clause = ", ".join([f"n.{key} = $set_{key}" for key in set_props.keys()])
                
                query = f"""
                MERGE (n:{label} {{{merge_clause}}})
                ON CREATE SET {set_clause}
                ON MATCH SET n.updated_at = $updated_at
                RETURN n, elementId(n) as node_id
                """
                
                params = {**merge_props}
                params.update({f"set_{key}": value for key, value in set_props.items()})
                params["updated_at"] = properties["updated_at"]
                
            else:
                # Simple CREATE
                query = f"CREATE (n:{label} $props) RETURN n, elementId(n) as node_id"
                params = {"props": properties}
            
            result = await self.client.execute_query(query, params)
            
            if result:
                node_data = dict(result[0]["n"])
                node_data["id"] = result[0]["node_id"]
                logger.info(f"Created/merged node {label} with ID {node_data['id']}")
                return node_data
            else:
                raise KnowledgeGraphError("Failed to create node")
                
        except Exception as e:
            logger.error(f"Error creating node {label}: {e}")
            raise
    
    def get_node_by_id(self, node_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        """
        Get a node by its ID.
        
        Args:
            node_id: Node ID
            
        Returns:
            Node information if found, None otherwise
        """
        try:
            query = "MATCH (n) WHERE id(n) = $node_id RETURN n, id(n) as node_id, labels(n) as labels"
            result = self.client.execute_query(query, {"node_id": int(node_id)})
            
            if result:
                node_data = dict(result[0]["n"])
                node_data["id"] = result[0]["node_id"]
                node_data["labels"] = result[0]["labels"]
                return node_data
            return None
            
        except Exception as e:
            logger.error(f"Error getting node by ID {node_id}: {e}")
            raise
    
    def get_nodes_by_label(self, label: str, properties: Optional[Dict[str, Any]] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get nodes by label and optional properties.
        
        Args:
            label: Node label
            properties: Properties to filter by
            limit: Maximum number of nodes to return
            
        Returns:
            List of matching nodes
        """
        try:
            where_clause = ""
            params = {"limit": limit}
            
            if properties:
                where_clauses = [f"n.{key} = ${key}" for key in properties.keys()]
                where_clause = "WHERE " + " AND ".join(where_clauses)
                params.update(properties)
            
            query = f"""
            MATCH (n:{label})
            {where_clause}
            RETURN n, id(n) as node_id, labels(n) as labels
            LIMIT $limit
            """
            
            result = self.client.execute_query(query, params)
            
            nodes = []
            for record in result:
                node_data = dict(record["n"])
                node_data["id"] = record["node_id"]
                node_data["labels"] = record["labels"]
                nodes.append(node_data)
            
            return nodes
            
        except Exception as e:
            logger.error(f"Error getting nodes by label {label}: {e}")
            raise
    
    def update_node(self, node_id: Union[int, str], properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a node's properties.
        
        Args:
            node_id: Node ID
            properties: Properties to update
            
        Returns:
            Updated node information
        """
        try:
            properties["updated_at"] = datetime.utcnow().isoformat()
            
            set_clauses = [f"n.{key} = ${key}" for key in properties.keys()]
            set_clause = ", ".join(set_clauses)
            
            query = f"""
            MATCH (n) WHERE id(n) = $node_id
            SET {set_clause}
            RETURN n, id(n) as node_id, labels(n) as labels
            """
            
            params = {"node_id": int(node_id), **properties}
            result = self.client.execute_query(query, params)
            
            if result:
                node_data = dict(result[0]["n"])
                node_data["id"] = result[0]["node_id"]
                node_data["labels"] = result[0]["labels"]
                logger.info(f"Updated node {node_id}")
                return node_data
            else:
                raise KnowledgeGraphError(f"Node {node_id} not found")
                
        except Exception as e:
            logger.error(f"Error updating node {node_id}: {e}")
            raise
    
    def delete_node(self, node_id: Union[int, str], delete_relationships: bool = True) -> bool:
        """
        Delete a node and optionally its relationships.
        
        Args:
            node_id: Node ID
            delete_relationships: Whether to delete connected relationships
            
        Returns:
            True if deleted successfully
        """
        try:
            if delete_relationships:
                query = "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n"
            else:
                query = "MATCH (n) WHERE id(n) = $node_id DELETE n"
            
            self.client.execute_query(query, {"node_id": int(node_id)})
            logger.info(f"Deleted node {node_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting node {node_id}: {e}")
            raise
    
    # Relationship Operations
    
    async def create_relationship(self, from_node_id: Union[int, str], to_node_id: Union[int, str],
                          relationship_type: str, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a relationship between two nodes.
        
        Args:
            from_node_id: Source node ID
            to_node_id: Target node ID
            relationship_type: Type of relationship (e.g., "CONTAINS", "RELATES_TO")
            properties: Relationship properties
            
        Returns:
            Created relationship information
        """
        try:
            if properties is None:
                properties = {}
            
            # Sanitize relationship type for Neo4j (no slashes, spaces, etc.)
            import re
            sanitized_type = re.sub(r'[^A-Za-z0-9_]', '_', relationship_type)
            
            # Add metadata
            properties["created_at"] = datetime.utcnow().isoformat()
            
            params = {"from_id": str(from_node_id), "to_id": str(to_node_id), "props": properties}
            
            query = f"""
            MATCH (a), (b)
            WHERE elementId(a) = $from_id AND elementId(b) = $to_id
            MERGE (a)-[r:{sanitized_type}]->(b)
            ON CREATE SET r += $props
            ON MATCH SET r += $props
            RETURN r, elementId(r) as rel_id, type(r) as rel_type
            """
            
            result = await self.client.execute_query(query, params)
            
            if result:
                rel_data = dict(result[0]["r"])
                rel_data["id"] = result[0]["rel_id"]
                rel_data["type"] = result[0]["rel_type"]
                logger.info(f"Created relationship {relationship_type} between {from_node_id} and {to_node_id}")
                return rel_data
            else:
                raise KnowledgeGraphError("Failed to create relationship")
                
        except Exception as e:
            logger.error(f"Error creating relationship {relationship_type}: {e}")
            raise
    
    def get_node_relationships(self, node_id: Union[int, str], 
                             direction: str = "both") -> List[Dict[str, Any]]:
        """
        Get relationships for a node.
        
        Args:
            node_id: Node ID
            direction: "incoming", "outgoing", or "both"
            
        Returns:
            List of relationships
        """
        try:
            if direction == "incoming":
                pattern = "(other)-[r]->(n)"
            elif direction == "outgoing":
                pattern = "(n)-[r]->(other)"
            else:  # both
                pattern = "(n)-[r]-(other)"
            
            query = f"""
            MATCH {pattern}
            WHERE id(n) = $node_id
            RETURN r, id(r) as rel_id, type(r) as rel_type,
                   other, id(other) as other_id, labels(other) as other_labels
            """
            
            result = self.client.execute_query(query, {"node_id": int(node_id)})
            
            relationships = []
            for record in result:
                rel_data = dict(record["r"])
                rel_data["id"] = record["rel_id"]
                rel_data["type"] = record["rel_type"]
                
                other_node = dict(record["other"])
                other_node["id"] = record["other_id"]
                other_node["labels"] = record["other_labels"]
                
                rel_data["other_node"] = other_node
                relationships.append(rel_data)
            
            return relationships
            
        except Exception as e:
            logger.error(f"Error getting relationships for node {node_id}: {e}")
            raise
    
    def delete_relationship(self, relationship_id: Union[int, str]) -> bool:
        """
        Delete a relationship by ID.
        
        Args:
            relationship_id: Relationship ID
            
        Returns:
            True if deleted successfully
        """
        try:
            query = "MATCH ()-[r]->() WHERE id(r) = $rel_id DELETE r"
            self.client.execute_query(query, {"rel_id": int(relationship_id)})
            logger.info(f"Deleted relationship {relationship_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting relationship {relationship_id}: {e}")
            raise
    
    # Query Operations
    
    def execute_cypher(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a custom Cypher query.
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            Query results
        """
        try:
            logger.info(f"Executing Cypher query: {query[:100]}...")
            return self.client.execute_query(query, parameters or {})
            
        except Exception as e:
            logger.error(f"Error executing Cypher query: {e}")
            raise
    
    def search_nodes(self, search_term: str, labels: Optional[List[str]] = None,
                    properties: Optional[List[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search for nodes containing a term in their properties.
        
        Args:
            search_term: Term to search for
            labels: Node labels to search in (optional)
            properties: Properties to search in (optional, defaults to common text properties)
            limit: Maximum number of results
            
        Returns:
            List of matching nodes
        """
        try:
            if properties is None:
                properties = ["name", "title", "content", "description", "text"]
            
            # Build label clause
            label_clause = ""
            if labels:
                label_clause = ":" + ":".join(labels)
            
            # Build search conditions
            search_conditions = []
            for prop in properties:
                search_conditions.append(f"toLower(toString(n.{prop})) CONTAINS toLower($search_term)")
            
            where_clause = " OR ".join(search_conditions)
            
            query = f"""
            MATCH (n{label_clause})
            WHERE {where_clause}
            RETURN n, id(n) as node_id, labels(n) as labels
            LIMIT $limit
            """
            
            params = {"search_term": search_term, "limit": limit}
            result = self.client.execute_query(query, params)
            
            nodes = []
            for record in result:
                node_data = dict(record["n"])
                node_data["id"] = record["node_id"]
                node_data["labels"] = record["labels"]
                nodes.append(node_data)
            
            return nodes
            
        except Exception as e:
            logger.error(f"Error searching nodes: {e}")
            raise
    
    # Cross-Document Linking Operations
    
    async def find_documents_by_entity(self, q_number: str) -> List[str]:
        """
        Find all documents containing concepts linked to a YAGO entity.
        
        This method supports cross-document entity linking by finding all
        documents that contain concepts with the same YAGO Q-number.
        
        Args:
            q_number: YAGO Q-number (e.g., "Q42")
            
        Returns:
            List of document IDs containing concepts linked to this entity
            
        Requirements: 5.3
        """
        try:
            query = """
            MATCH (c:Concept)
            WHERE c.yago_qid = $q_number
            RETURN DISTINCT c.source_document as document_id
            """
            
            result = await self.client.execute_query(query, {"q_number": q_number})
            
            document_ids = [
                r["document_id"] for r in result 
                if r.get("document_id") is not None
            ]
            
            logger.info(
                f"Found {len(document_ids)} documents for entity {q_number}"
            )
            return document_ids
            
        except Exception as e:
            logger.error(f"Error finding documents by entity {q_number}: {e}")
            return []
    
    async def query_with_same_as_traversal(
        self,
        concept_id: str,
        max_hops: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Query for related concepts by traversing SAME_AS relationships.

        This method finds concepts from other documents that are linked
        via SAME_AS relationships (shared YAGO Q-numbers). Document IDs
        are derived from EXTRACTED_FROM traversal to Chunk nodes instead
        of reading source_document properties.

        Args:
            concept_id: Starting concept ID
            max_hops: Maximum number of SAME_AS hops to traverse (default 2)

        Returns:
            List of related concepts from other documents

        Requirements: 10.1
        """
        try:
            # Build the SAME_AS path pattern based on max_hops
            if max_hops == 1:
                same_as_pattern = "(start)-[:SAME_AS]-(related:Concept)"
            elif max_hops == 2:
                same_as_pattern = "(start)-[:SAME_AS*1..2]-(related:Concept)"
            else:
                same_as_pattern = "(start)-[:SAME_AS*1..3]-(related:Concept)"

            # Use Chunk-based document derivation instead of source_document property
            query = f"""
            MATCH (start:Concept {{concept_id: $concept_id}})
            MATCH {same_as_pattern}
            WITH start, related
            MATCH (start)-[:EXTRACTED_FROM]->(sch:Chunk)
            WITH start, related, collect(DISTINCT sch.source_id) AS start_source_ids
            MATCH (related)-[:EXTRACTED_FROM]->(rch:Chunk)
            WITH related, start_source_ids, collect(DISTINCT rch.source_id) AS related_source_ids
            WHERE NONE(sid IN related_source_ids WHERE sid IN start_source_ids)
            RETURN DISTINCT
                related.concept_id as concept_id,
                related.name as name,
                related_source_ids as document_ids,
                related.yago_qid as q_number
            """

            result = await self.client.execute_query(
                query, 
                {"concept_id": concept_id}
            )

            related_concepts = []
            for record in result:
                related_concepts.append({
                    "concept_id": record["concept_id"],
                    "name": record["name"],
                    "document_ids": record.get("document_ids", []),
                    "q_number": record.get("q_number"),
                    "hops": record.get("hops", 1)
                })

            logger.info(
                f"Found {len(related_concepts)} cross-document concepts "
                f"for {concept_id}"
            )
            return related_concepts

        except Exception as e:
            logger.error(
                f"Error querying with SAME_AS traversal for {concept_id}: {e}"
            )
            return []
    
    async def get_concepts_by_q_number(self, q_number: str) -> List[Dict[str, Any]]:
        """
        Get all concepts that share a YAGO Q-number.
        
        Args:
            q_number: YAGO Q-number
            
        Returns:
            List of concept dictionaries
        """
        try:
            query = """
            MATCH (c:Concept)
            WHERE c.yago_qid = $q_number
            RETURN c, id(c) as node_id
            """
            
            result = await self.client.execute_query(query, {"q_number": q_number})
            
            concepts = []
            for record in result:
                concept_data = dict(record["c"])
                concept_data["id"] = record["node_id"]
                concepts.append(concept_data)
            
            return concepts
            
        except Exception as e:
            logger.error(f"Error getting concepts by Q-number {q_number}: {e}")
            return []
    
    async def create_same_as_relationship(
        self,
        concept_id_1: str,
        concept_id_2: str,
        q_number: str
    ) -> bool:
        """
        Create a SAME_AS relationship between two concepts.
        
        Args:
            concept_id_1: First concept ID
            concept_id_2: Second concept ID
            q_number: Shared YAGO Q-number
            
        Returns:
            True if relationship was created successfully
            
        Requirements: 5.1
        """
        try:
            # Check if relationship already exists
            check_query = """
            MATCH (c1:Concept {concept_id: $concept_id_1})
            MATCH (c2:Concept {concept_id: $concept_id_2})
            MATCH (c1)-[r:SAME_AS]-(c2)
            RETURN r
            """
            
            existing = await self.client.execute_query(check_query, {
                "concept_id_1": concept_id_1,
                "concept_id_2": concept_id_2
            })
            
            if existing:
                logger.debug(
                    f"SAME_AS relationship already exists between "
                    f"{concept_id_1} and {concept_id_2}"
                )
                return True
            
            # Create the relationship (MERGE for idempotency)
            create_query = """
            MATCH (c1:Concept {concept_id: $concept_id_1})
            MATCH (c2:Concept {concept_id: $concept_id_2})
            MERGE (c1)-[r:SAME_AS]->(c2)
            ON CREATE SET r.q_number = $q_number, r.created_at = $created_at
            ON MATCH SET r.q_number = $q_number
            RETURN r
            """
            
            result = await self.client.execute_query(create_query, {
                "concept_id_1": concept_id_1,
                "concept_id_2": concept_id_2,
                "q_number": q_number,
                "created_at": datetime.utcnow().isoformat()
            })
            
            if result:
                logger.info(
                    f"Created SAME_AS relationship: {concept_id_1} <-> "
                    f"{concept_id_2} (Q: {q_number})"
                )
                return True
            
            return False
            
        except Exception as e:
            logger.error(
                f"Error creating SAME_AS relationship between "
                f"{concept_id_1} and {concept_id_2}: {e}"
            )
            return False
    
    # Statistics and Info
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """
        Get basic statistics about the knowledge graph.
        
        Returns:
            Graph statistics
        """
        try:
            stats = {}
            
            # Node count by label
            node_stats = self.client.execute_query("""
                MATCH (n)
                RETURN labels(n) as labels, count(n) as count
                ORDER BY count DESC
            """)
            
            stats["nodes_by_label"] = {}
            total_nodes = 0
            for record in node_stats:
                labels = record["labels"]
                count = record["count"]
                total_nodes += count
                
                if labels:
                    label_key = ":".join(sorted(labels))
                    stats["nodes_by_label"][label_key] = count
                else:
                    stats["nodes_by_label"]["unlabeled"] = count
            
            stats["total_nodes"] = total_nodes
            
            # Relationship count by type
            rel_stats = self.client.execute_query("""
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(r) as count
                ORDER BY count DESC
            """)
            
            stats["relationships_by_type"] = {}
            total_relationships = 0
            for record in rel_stats:
                rel_type = record["rel_type"]
                count = record["count"]
                total_relationships += count
                stats["relationships_by_type"][rel_type] = count
            
            stats["total_relationships"] = total_relationships
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting graph stats: {e}")
            raise


# Global service instance
_kg_service: Optional[KnowledgeGraphService] = None


def get_knowledge_graph_service() -> KnowledgeGraphService:
    """Get or create global knowledge graph service instance."""
    global _kg_service
    
    if _kg_service is None:
        _kg_service = KnowledgeGraphService()
    
    return _kg_service