#!/usr/bin/env python3
"""
Database Data Integrity Validation Utility

This script validates data integrity across all database services in the
Multimodal Librarian application, checking for consistency, constraints,
and relationships between different data stores.

Usage:
    python scripts/validate-data-integrity.py [OPTIONS]

Examples:
    # Validate all databases
    python scripts/validate-data-integrity.py

    # Validate specific databases
    python scripts/validate-data-integrity.py --databases postgresql,neo4j

    # Deep validation with relationship checks
    python scripts/validate-data-integrity.py --deep

    # Generate detailed report
    python scripts/validate-data-integrity.py --report ./validation-report.json

    # Validate AWS environment
    ML_ENVIRONMENT=aws python scripts/validate-data-integrity.py
"""

import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal, Set, Tuple
from dataclasses import dataclass, asdict

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multimodal_librarian.config.config_factory import get_database_config
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from src.multimodal_librarian.clients.protocols import (
    RelationalStoreClient, VectorStoreClient, GraphStoreClient,
    DatabaseClientError
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Type aliases
DatabaseType = Literal["postgresql", "neo4j", "milvus"]
ValidationLevel = Literal["basic", "standard", "deep"]
IssueType = Literal["error", "warning", "info"]


@dataclass
class ValidationIssue:
    """A data integrity issue found during validation."""
    type: IssueType
    database: str
    category: str
    description: str
    details: Dict[str, Any]
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of data integrity validation."""
    database_type: str
    success: bool
    issues: List[ValidationIssue]
    statistics: Dict[str, Any]
    duration_seconds: float
    error: Optional[str] = None


@dataclass
class ValidationSummary:
    """Summary of all validation results."""
    timestamp: str
    environment: str
    validation_level: str
    databases_validated: List[str]
    total_issues: int
    errors: int
    warnings: int
    infos: int
    overall_status: str
    results: Dict[str, ValidationResult]
    cross_database_issues: List[ValidationIssue]


class DataIntegrityValidator:
    """
    Comprehensive data integrity validator.
    
    This class validates data integrity across all database services,
    checking for consistency, constraints, and relationships.
    """
    
    def __init__(
        self,
        validation_level: ValidationLevel = "standard",
        include_cross_db_checks: bool = True
    ):
        """
        Initialize the data integrity validator.
        
        Args:
            validation_level: Level of validation (basic, standard, deep)
            include_cross_db_checks: Whether to check relationships between databases
        """
        self.validation_level = validation_level
        self.include_cross_db_checks = include_cross_db_checks
        
        # Initialize database factory
        self.config = get_database_config()
        self.factory = DatabaseClientFactory(self.config)
        
        logger.info(f"Initialized validator for {self.config.database_type} environment")
        logger.info(f"Validation level: {validation_level}")
    
    async def validate_all_databases(
        self, 
        databases: Optional[List[DatabaseType]] = None
    ) -> ValidationSummary:
        """
        Validate data integrity across all specified databases.
        
        Args:
            databases: List of databases to validate (None = all available)
            
        Returns:
            ValidationSummary with all validation results
        """
        if databases is None:
            databases = ["postgresql", "neo4j", "milvus"]
        
        logger.info(f"Starting validation of databases: {', '.join(databases)}")
        
        results = {}
        cross_database_issues = []
        
        # Validate each database
        for db_type in databases:
            try:
                logger.info(f"Validating {db_type} database...")
                result = await self._validate_database(db_type)
                results[db_type] = result
                
                if result.success:
                    issue_count = len(result.issues)
                    error_count = sum(1 for issue in result.issues if issue.type == "error")
                    logger.info(
                        f"✓ {db_type}: {issue_count} issues found "
                        f"({error_count} errors) in {result.duration_seconds:.2f}s"
                    )
                else:
                    logger.error(f"✗ {db_type}: {result.error}")
                    
            except Exception as e:
                logger.error(f"Failed to validate {db_type}: {e}")
                results[db_type] = ValidationResult(
                    database_type=db_type,
                    success=False,
                    issues=[],
                    statistics={},
                    duration_seconds=0.0,
                    error=str(e)
                )
        
        # Perform cross-database validation if requested
        if self.include_cross_db_checks and len(results) > 1:
            logger.info("Performing cross-database validation...")
            cross_database_issues = await self._validate_cross_database_integrity(results)
        
        # Create summary
        summary = self._create_validation_summary(results, cross_database_issues)
        
        return summary
    
    async def _validate_database(self, db_type: DatabaseType) -> ValidationResult:
        """Validate a specific database type."""
        start_time = datetime.now()
        
        try:
            if db_type == "postgresql":
                return await self._validate_postgresql()
            elif db_type == "neo4j":
                return await self._validate_neo4j()
            elif db_type == "milvus":
                return await self._validate_milvus()
            else:
                raise ValueError(f"Unsupported database type: {db_type}")
                
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return ValidationResult(
                database_type=db_type,
                success=False,
                issues=[],
                statistics={},
                duration_seconds=duration,
                error=str(e)
            )
    
    async def _validate_postgresql(self) -> ValidationResult:
        """Validate PostgreSQL data integrity."""
        start_time = datetime.now()
        issues = []
        statistics = {}
        
        try:
            client: RelationalStoreClient = await self.factory.get_relational_client()
            
            # Get database statistics
            db_info = await client.get_database_info()
            statistics.update(db_info)
            
            # Get all tables
            tables_query = """
            SELECT table_name, 
                   (SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = t.table_name AND table_schema = 'public') as column_count
            FROM information_schema.tables t
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
            
            tables_result = await client.execute_query(tables_query)
            tables = {row["table_name"]: row for row in tables_result}
            
            statistics["table_count"] = len(tables)
            statistics["tables"] = list(tables.keys())
            
            logger.debug(f"Found {len(tables)} PostgreSQL tables")
            
            # Validate each table
            for table_name, table_info in tables.items():
                table_issues = await self._validate_postgresql_table(client, table_name)
                issues.extend(table_issues)
            
            # Check for orphaned records (if validation level is deep)
            if self.validation_level == "deep":
                orphan_issues = await self._check_postgresql_orphaned_records(client, tables)
                issues.extend(orphan_issues)
            
            # Check constraints and indexes
            constraint_issues = await self._check_postgresql_constraints(client)
            issues.extend(constraint_issues)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ValidationResult(
                database_type="postgresql",
                success=True,
                issues=issues,
                statistics=statistics,
                duration_seconds=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"PostgreSQL validation failed: {e}",
                original_exception=e
            )
    
    async def _validate_postgresql_table(
        self, 
        client: RelationalStoreClient, 
        table_name: str
    ) -> List[ValidationIssue]:
        """Validate a specific PostgreSQL table."""
        issues = []
        
        try:
            # Get table info
            table_info = await client.get_table_info(table_name)
            
            # Check for empty tables
            if table_info.get("row_count", 0) == 0:
                issues.append(ValidationIssue(
                    type="warning",
                    database="postgresql",
                    category="data_completeness",
                    description=f"Table '{table_name}' is empty",
                    details={"table": table_name, "row_count": 0},
                    suggestion="Verify if this table should contain data"
                ))
            
            # Check for tables with very few records (potential data loss)
            elif table_info.get("row_count", 0) < 10 and table_name not in ["migrations", "schema_version"]:
                issues.append(ValidationIssue(
                    type="warning",
                    database="postgresql",
                    category="data_completeness",
                    description=f"Table '{table_name}' has very few records",
                    details={"table": table_name, "row_count": table_info.get("row_count", 0)},
                    suggestion="Verify if this is expected for this table"
                ))
            
            # Check for NULL values in critical columns
            if self.validation_level in ["standard", "deep"]:
                null_issues = await self._check_postgresql_null_values(client, table_name)
                issues.extend(null_issues)
            
            # Check for duplicate records
            if self.validation_level == "deep":
                duplicate_issues = await self._check_postgresql_duplicates(client, table_name)
                issues.extend(duplicate_issues)
            
        except Exception as e:
            issues.append(ValidationIssue(
                type="error",
                database="postgresql",
                category="validation_error",
                description=f"Failed to validate table '{table_name}'",
                details={"table": table_name, "error": str(e)},
                suggestion="Check table permissions and structure"
            ))
        
        return issues
    
    async def _check_postgresql_null_values(
        self, 
        client: RelationalStoreClient, 
        table_name: str
    ) -> List[ValidationIssue]:
        """Check for unexpected NULL values in PostgreSQL table."""
        issues = []
        
        try:
            # Get columns that should not be NULL
            critical_columns = ["id", "created_at", "updated_at"]
            
            for column in critical_columns:
                null_check_query = f"""
                SELECT COUNT(*) as null_count
                FROM {table_name}
                WHERE {column} IS NULL
                """
                
                try:
                    result = await client.execute_query(null_check_query)
                    null_count = result[0]["null_count"] if result else 0
                    
                    if null_count > 0:
                        issues.append(ValidationIssue(
                            type="error",
                            database="postgresql",
                            category="data_integrity",
                            description=f"NULL values found in critical column '{column}' of table '{table_name}'",
                            details={
                                "table": table_name,
                                "column": column,
                                "null_count": null_count
                            },
                            suggestion=f"Update NULL values in {column} column or add NOT NULL constraint"
                        ))
                
                except Exception:
                    # Column might not exist, which is fine
                    pass
        
        except Exception as e:
            logger.debug(f"Failed to check NULL values for table {table_name}: {e}")
        
        return issues
    
    async def _check_postgresql_duplicates(
        self, 
        client: RelationalStoreClient, 
        table_name: str
    ) -> List[ValidationIssue]:
        """Check for duplicate records in PostgreSQL table."""
        issues = []
        
        try:
            # Check for duplicate IDs (if id column exists)
            duplicate_check_query = f"""
            SELECT id, COUNT(*) as count
            FROM {table_name}
            WHERE id IS NOT NULL
            GROUP BY id
            HAVING COUNT(*) > 1
            LIMIT 10
            """
            
            try:
                result = await client.execute_query(duplicate_check_query)
                
                if result:
                    total_duplicates = len(result)
                    issues.append(ValidationIssue(
                        type="error",
                        database="postgresql",
                        category="data_integrity",
                        description=f"Duplicate IDs found in table '{table_name}'",
                        details={
                            "table": table_name,
                            "duplicate_count": total_duplicates,
                            "examples": result[:5]  # Show first 5 examples
                        },
                        suggestion="Remove or merge duplicate records"
                    ))
            
            except Exception:
                # ID column might not exist, which is fine
                pass
        
        except Exception as e:
            logger.debug(f"Failed to check duplicates for table {table_name}: {e}")
        
        return issues
    
    async def _check_postgresql_orphaned_records(
        self, 
        client: RelationalStoreClient, 
        tables: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Check for orphaned records in PostgreSQL."""
        issues = []
        
        # Define common foreign key relationships to check
        relationships = [
            ("documents", "user_id", "users", "id"),
            ("conversations", "user_id", "users", "id"),
            ("messages", "conversation_id", "conversations", "id"),
            ("document_chunks", "document_id", "documents", "id"),
        ]
        
        for child_table, child_column, parent_table, parent_column in relationships:
            if child_table in tables and parent_table in tables:
                try:
                    orphan_query = f"""
                    SELECT COUNT(*) as orphan_count
                    FROM {child_table} c
                    LEFT JOIN {parent_table} p ON c.{child_column} = p.{parent_column}
                    WHERE c.{child_column} IS NOT NULL AND p.{parent_column} IS NULL
                    """
                    
                    result = await client.execute_query(orphan_query)
                    orphan_count = result[0]["orphan_count"] if result else 0
                    
                    if orphan_count > 0:
                        issues.append(ValidationIssue(
                            type="error",
                            database="postgresql",
                            category="referential_integrity",
                            description=f"Orphaned records found in '{child_table}' table",
                            details={
                                "child_table": child_table,
                                "parent_table": parent_table,
                                "orphan_count": orphan_count,
                                "relationship": f"{child_table}.{child_column} -> {parent_table}.{parent_column}"
                            },
                            suggestion="Remove orphaned records or add missing parent records"
                        ))
                
                except Exception as e:
                    logger.debug(f"Failed to check orphaned records for {child_table}: {e}")
        
        return issues
    
    async def _check_postgresql_constraints(
        self, 
        client: RelationalStoreClient
    ) -> List[ValidationIssue]:
        """Check PostgreSQL constraints and indexes."""
        issues = []
        
        try:
            # Check for missing primary keys
            missing_pk_query = """
            SELECT table_name
            FROM information_schema.tables t
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            AND NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints tc
                WHERE tc.table_name = t.table_name 
                AND tc.table_schema = 'public'
                AND tc.constraint_type = 'PRIMARY KEY'
            )
            """
            
            result = await client.execute_query(missing_pk_query)
            
            for row in result:
                table_name = row["table_name"]
                issues.append(ValidationIssue(
                    type="warning",
                    database="postgresql",
                    category="schema_integrity",
                    description=f"Table '{table_name}' has no primary key",
                    details={"table": table_name},
                    suggestion="Add a primary key constraint to improve performance and data integrity"
                ))
        
        except Exception as e:
            logger.debug(f"Failed to check constraints: {e}")
        
        return issues
    
    async def _validate_neo4j(self) -> ValidationResult:
        """Validate Neo4j data integrity."""
        start_time = datetime.now()
        issues = []
        statistics = {}
        
        try:
            client: GraphStoreClient = await self.factory.get_graph_client()
            
            # Get database statistics
            db_info = await client.get_database_info()
            statistics.update(db_info)
            
            # Get node and relationship counts by type
            node_stats = await self._get_neo4j_node_statistics(client)
            rel_stats = await self._get_neo4j_relationship_statistics(client)
            
            statistics["node_statistics"] = node_stats
            statistics["relationship_statistics"] = rel_stats
            
            # Check for isolated nodes
            if self.validation_level in ["standard", "deep"]:
                isolation_issues = await self._check_neo4j_isolated_nodes(client)
                issues.extend(isolation_issues)
            
            # Check for missing properties
            property_issues = await self._check_neo4j_missing_properties(client)
            issues.extend(property_issues)
            
            # Check for relationship consistency
            if self.validation_level == "deep":
                relationship_issues = await self._check_neo4j_relationship_consistency(client)
                issues.extend(relationship_issues)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ValidationResult(
                database_type="neo4j",
                success=True,
                issues=issues,
                statistics=statistics,
                duration_seconds=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"Neo4j validation failed: {e}",
                original_exception=e
            )
    
    async def _get_neo4j_node_statistics(
        self, 
        client: GraphStoreClient
    ) -> Dict[str, int]:
        """Get Neo4j node statistics by label."""
        try:
            labels_query = "CALL db.labels() YIELD label RETURN label ORDER BY label"
            labels_result = await client.execute_query(labels_query)
            
            node_stats = {}
            
            for row in labels_result:
                label = row["label"]
                count_query = f"MATCH (n:{label}) RETURN count(n) as count"
                count_result = await client.execute_query(count_query)
                node_stats[label] = count_result[0]["count"] if count_result else 0
            
            return node_stats
            
        except Exception as e:
            logger.debug(f"Failed to get Neo4j node statistics: {e}")
            return {}
    
    async def _get_neo4j_relationship_statistics(
        self, 
        client: GraphStoreClient
    ) -> Dict[str, int]:
        """Get Neo4j relationship statistics by type."""
        try:
            types_query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
            types_result = await client.execute_query(types_query)
            
            rel_stats = {}
            
            for row in types_result:
                rel_type = row["relationshipType"]
                count_query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count"
                count_result = await client.execute_query(count_query)
                rel_stats[rel_type] = count_result[0]["count"] if count_result else 0
            
            return rel_stats
            
        except Exception as e:
            logger.debug(f"Failed to get Neo4j relationship statistics: {e}")
            return {}
    
    async def _check_neo4j_isolated_nodes(
        self, 
        client: GraphStoreClient
    ) -> List[ValidationIssue]:
        """Check for isolated nodes in Neo4j."""
        issues = []
        
        try:
            # Find nodes with no relationships
            isolated_query = """
            MATCH (n)
            WHERE NOT (n)--()
            RETURN labels(n) as labels, count(n) as count
            ORDER BY count DESC
            """
            
            result = await client.execute_query(isolated_query)
            
            for row in result:
                labels = row["labels"]
                count = row["count"]
                
                if count > 0:
                    issues.append(ValidationIssue(
                        type="warning",
                        database="neo4j",
                        category="graph_structure",
                        description=f"Isolated nodes found with labels {labels}",
                        details={
                            "labels": labels,
                            "isolated_count": count
                        },
                        suggestion="Verify if these nodes should have relationships"
                    ))
        
        except Exception as e:
            logger.debug(f"Failed to check isolated nodes: {e}")
        
        return issues
    
    async def _check_neo4j_missing_properties(
        self, 
        client: GraphStoreClient
    ) -> List[ValidationIssue]:
        """Check for nodes missing critical properties."""
        issues = []
        
        # Define critical properties for different node types
        critical_properties = {
            "User": ["id", "email"],
            "Document": ["id", "title"],
            "Conversation": ["id", "created_at"],
            "Concept": ["name"]
        }
        
        for label, properties in critical_properties.items():
            try:
                for prop in properties:
                    missing_query = f"""
                    MATCH (n:{label})
                    WHERE n.{prop} IS NULL OR n.{prop} = ''
                    RETURN count(n) as missing_count
                    """
                    
                    result = await client.execute_query(missing_query)
                    missing_count = result[0]["missing_count"] if result else 0
                    
                    if missing_count > 0:
                        issues.append(ValidationIssue(
                            type="error",
                            database="neo4j",
                            category="data_integrity",
                            description=f"Nodes with label '{label}' missing property '{prop}'",
                            details={
                                "label": label,
                                "property": prop,
                                "missing_count": missing_count
                            },
                            suggestion=f"Add missing {prop} property to {label} nodes"
                        ))
            
            except Exception as e:
                logger.debug(f"Failed to check missing properties for {label}: {e}")
        
        return issues
    
    async def _check_neo4j_relationship_consistency(
        self, 
        client: GraphStoreClient
    ) -> List[ValidationIssue]:
        """Check for relationship consistency issues."""
        issues = []
        
        try:
            # Check for relationships with missing nodes (shouldn't happen but worth checking)
            orphan_rel_query = """
            MATCH ()-[r]->()
            WHERE startNode(r) IS NULL OR endNode(r) IS NULL
            RETURN type(r) as rel_type, count(r) as count
            """
            
            result = await client.execute_query(orphan_rel_query)
            
            for row in result:
                if row["count"] > 0:
                    issues.append(ValidationIssue(
                        type="error",
                        database="neo4j",
                        category="referential_integrity",
                        description=f"Orphaned relationships of type '{row['rel_type']}'",
                        details={
                            "relationship_type": row["rel_type"],
                            "orphan_count": row["count"]
                        },
                        suggestion="Remove orphaned relationships"
                    ))
        
        except Exception as e:
            logger.debug(f"Failed to check relationship consistency: {e}")
        
        return issues
    
    async def _validate_milvus(self) -> ValidationResult:
        """Validate Milvus data integrity."""
        start_time = datetime.now()
        issues = []
        statistics = {}
        
        try:
            client: VectorStoreClient = await self.factory.get_vector_client()
            
            # Get collections
            collections = await client.list_collections()
            statistics["collection_count"] = len(collections)
            statistics["collections"] = collections
            
            collection_stats = {}
            
            # Validate each collection
            for collection_name in collections:
                try:
                    stats = await client.get_collection_stats(collection_name)
                    collection_stats[collection_name] = stats
                    
                    # Check for empty collections
                    vector_count = stats.get("vector_count", 0)
                    if vector_count == 0:
                        issues.append(ValidationIssue(
                            type="warning",
                            database="milvus",
                            category="data_completeness",
                            description=f"Collection '{collection_name}' is empty",
                            details={"collection": collection_name, "vector_count": 0},
                            suggestion="Verify if this collection should contain vectors"
                        ))
                    
                    # Check for collections with very few vectors
                    elif vector_count < 10:
                        issues.append(ValidationIssue(
                            type="warning",
                            database="milvus",
                            category="data_completeness",
                            description=f"Collection '{collection_name}' has very few vectors",
                            details={"collection": collection_name, "vector_count": vector_count},
                            suggestion="Verify if this is expected for this collection"
                        ))
                    
                    # Check dimension consistency
                    dimension = stats.get("dimension")
                    if dimension and dimension not in [384, 512, 768, 1024, 1536]:  # Common embedding dimensions
                        issues.append(ValidationIssue(
                            type="info",
                            database="milvus",
                            category="configuration",
                            description=f"Collection '{collection_name}' has unusual dimension",
                            details={"collection": collection_name, "dimension": dimension},
                            suggestion="Verify if this dimension is correct for your embedding model"
                        ))
                
                except Exception as e:
                    issues.append(ValidationIssue(
                        type="error",
                        database="milvus",
                        category="validation_error",
                        description=f"Failed to validate collection '{collection_name}'",
                        details={"collection": collection_name, "error": str(e)},
                        suggestion="Check collection status and permissions"
                    ))
            
            statistics["collection_statistics"] = collection_stats
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return ValidationResult(
                database_type="milvus",
                success=True,
                issues=issues,
                statistics=statistics,
                duration_seconds=duration
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            raise DatabaseClientError(
                f"Milvus validation failed: {e}",
                original_exception=e
            )
    
    async def _validate_cross_database_integrity(
        self, 
        results: Dict[str, ValidationResult]
    ) -> List[ValidationIssue]:
        """Validate integrity across different databases."""
        issues = []
        
        try:
            # Check if we have data in all databases
            successful_dbs = [db for db, result in results.items() if result.success]
            
            if len(successful_dbs) < 2:
                return issues  # Need at least 2 databases for cross-validation
            
            # Check for data consistency between PostgreSQL and Neo4j
            if "postgresql" in successful_dbs and "neo4j" in successful_dbs:
                pg_stats = results["postgresql"].statistics
                neo4j_stats = results["neo4j"].statistics
                
                # Compare user counts
                pg_user_count = self._extract_table_count(pg_stats, "users")
                neo4j_user_count = neo4j_stats.get("node_statistics", {}).get("User", 0)
                
                if pg_user_count is not None and abs(pg_user_count - neo4j_user_count) > 5:
                    issues.append(ValidationIssue(
                        type="warning",
                        database="cross_database",
                        category="data_consistency",
                        description="User count mismatch between PostgreSQL and Neo4j",
                        details={
                            "postgresql_users": pg_user_count,
                            "neo4j_users": neo4j_user_count,
                            "difference": abs(pg_user_count - neo4j_user_count)
                        },
                        suggestion="Investigate data synchronization between databases"
                    ))
                
                # Compare document counts
                pg_doc_count = self._extract_table_count(pg_stats, "documents")
                neo4j_doc_count = neo4j_stats.get("node_statistics", {}).get("Document", 0)
                
                if pg_doc_count is not None and abs(pg_doc_count - neo4j_doc_count) > 5:
                    issues.append(ValidationIssue(
                        type="warning",
                        database="cross_database",
                        category="data_consistency",
                        description="Document count mismatch between PostgreSQL and Neo4j",
                        details={
                            "postgresql_documents": pg_doc_count,
                            "neo4j_documents": neo4j_doc_count,
                            "difference": abs(pg_doc_count - neo4j_doc_count)
                        },
                        suggestion="Investigate document synchronization between databases"
                    ))
            
            # Check for data consistency between PostgreSQL and Milvus
            if "postgresql" in successful_dbs and "milvus" in successful_dbs:
                pg_stats = results["postgresql"].statistics
                milvus_stats = results["milvus"].statistics
                
                pg_chunk_count = self._extract_table_count(pg_stats, "document_chunks")
                milvus_vector_count = sum(
                    stats.get("vector_count", 0) 
                    for stats in milvus_stats.get("collection_statistics", {}).values()
                )
                
                if pg_chunk_count is not None and abs(pg_chunk_count - milvus_vector_count) > 10:
                    issues.append(ValidationIssue(
                        type="warning",
                        database="cross_database",
                        category="data_consistency",
                        description="Document chunk count mismatch between PostgreSQL and Milvus",
                        details={
                            "postgresql_chunks": pg_chunk_count,
                            "milvus_vectors": milvus_vector_count,
                            "difference": abs(pg_chunk_count - milvus_vector_count)
                        },
                        suggestion="Investigate vector embedding synchronization"
                    ))
        
        except Exception as e:
            logger.debug(f"Failed to perform cross-database validation: {e}")
            issues.append(ValidationIssue(
                type="error",
                database="cross_database",
                category="validation_error",
                description="Failed to perform cross-database validation",
                details={"error": str(e)},
                suggestion="Check database connectivity and permissions"
            ))
        
        return issues
    
    def _extract_table_count(self, pg_stats: Dict[str, Any], table_name: str) -> Optional[int]:
        """Extract table count from PostgreSQL statistics."""
        # This would need to be implemented based on how statistics are stored
        # For now, return None to indicate unknown
        return None
    
    def _create_validation_summary(
        self, 
        results: Dict[str, ValidationResult],
        cross_database_issues: List[ValidationIssue]
    ) -> ValidationSummary:
        """Create validation summary from results."""
        # Count issues by type
        all_issues = cross_database_issues.copy()
        for result in results.values():
            all_issues.extend(result.issues)
        
        errors = sum(1 for issue in all_issues if issue.type == "error")
        warnings = sum(1 for issue in all_issues if issue.type == "warning")
        infos = sum(1 for issue in all_issues if issue.type == "info")
        
        # Determine overall status
        if errors > 0:
            overall_status = "critical"
        elif warnings > 0:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        return ValidationSummary(
            timestamp=datetime.now().isoformat(),
            environment=self.config.database_type,
            validation_level=self.validation_level,
            databases_validated=[db for db, result in results.items() if result.success],
            total_issues=len(all_issues),
            errors=errors,
            warnings=warnings,
            infos=infos,
            overall_status=overall_status,
            results=results,
            cross_database_issues=cross_database_issues
        )
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            await self.factory.close()
        except Exception as e:
            logger.warning(f"Error closing database factory: {e}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Validate data integrity in Multimodal Librarian databases",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Validate all databases (standard level)
  %(prog)s --databases postgresql,neo4j       # Validate specific databases
  %(prog)s --level deep                       # Deep validation with comprehensive checks
  %(prog)s --no-cross-db                      # Skip cross-database validation
  %(prog)s --report ./validation-report.json # Generate detailed report
  
Validation Levels:
  basic     - Basic connectivity and structure checks
  standard  - Standard integrity checks (default)
  deep      - Comprehensive validation including relationships and constraints
  
Environment Variables:
  ML_ENVIRONMENT=local|aws                    # Environment to validate
  ML_POSTGRES_HOST, ML_NEO4J_HOST, etc.      # Database connection settings
        """
    )
    
    parser.add_argument(
        "--databases",
        type=str,
        help="Comma-separated list of databases to validate (postgresql,neo4j,milvus)"
    )
    
    parser.add_argument(
        "--level",
        type=str,
        choices=["basic", "standard", "deep"],
        default="standard",
        help="Validation level (default: standard)"
    )
    
    parser.add_argument(
        "--no-cross-db",
        action="store_true",
        help="Skip cross-database validation checks"
    )
    
    parser.add_argument(
        "--report",
        type=str,
        help="Path to save detailed validation report (JSON format)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Parse databases list
    databases = None
    if args.databases:
        databases = [db.strip() for db in args.databases.split(",")]
        
        # Validate database names
        valid_databases = {"postgresql", "neo4j", "milvus"}
        invalid_databases = set(databases) - valid_databases
        if invalid_databases:
            logger.error(f"Invalid database names: {', '.join(invalid_databases)}")
            logger.error(f"Valid options: {', '.join(valid_databases)}")
            return 1
    
    # Initialize validator
    validator = DataIntegrityValidator(
        validation_level=args.level,
        include_cross_db_checks=not args.no_cross_db
    )
    
    try:
        # Run validation
        summary = await validator.validate_all_databases(databases)
        
        # Print summary
        print(f"\nData Integrity Validation Summary:")
        print(f"  Environment: {summary.environment}")
        print(f"  Validation Level: {summary.validation_level}")
        print(f"  Databases Validated: {', '.join(summary.databases_validated)}")
        print(f"  Overall Status: {summary.overall_status.upper()}")
        print(f"  Total Issues: {summary.total_issues}")
        print(f"    Errors: {summary.errors}")
        print(f"    Warnings: {summary.warnings}")
        print(f"    Info: {summary.infos}")
        
        # Show database-specific results
        for db_type, result in summary.results.items():
            status = "✓" if result.success else "✗"
            if result.success:
                issue_count = len(result.issues)
                error_count = sum(1 for issue in result.issues if issue.type == "error")
                print(f"  {status} {db_type}: {issue_count} issues "
                      f"({error_count} errors) in {result.duration_seconds:.2f}s")
            else:
                print(f"  {status} {db_type}: {result.error}")
        
        # Show cross-database issues
        if summary.cross_database_issues:
            print(f"\nCross-Database Issues:")
            for issue in summary.cross_database_issues:
                print(f"  {issue.type.upper()}: {issue.description}")
        
        # Show critical issues
        critical_issues = [
            issue for result in summary.results.values() 
            for issue in result.issues if issue.type == "error"
        ] + [issue for issue in summary.cross_database_issues if issue.type == "error"]
        
        if critical_issues:
            print(f"\nCritical Issues Requiring Attention:")
            for issue in critical_issues[:10]:  # Show first 10
                print(f"  • {issue.database}: {issue.description}")
                if issue.suggestion:
                    print(f"    Suggestion: {issue.suggestion}")
        
        # Save detailed report if requested
        if args.report:
            report_path = Path(args.report)
            with open(report_path, 'w') as f:
                json.dump(asdict(summary), f, indent=2, default=str)
            print(f"\nDetailed report saved to: {report_path}")
        
        # Return appropriate exit code
        if summary.errors > 0:
            return 2  # Critical issues
        elif summary.warnings > 0:
            return 1  # Warnings
        else:
            return 0  # All good
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1
        
    finally:
        await validator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)