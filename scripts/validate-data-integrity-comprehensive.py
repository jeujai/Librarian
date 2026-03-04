#!/usr/bin/env python3
"""
Comprehensive Data Integrity Validation for Local Development

This script extends the existing data integrity validation with additional checks
specifically designed for local development environments. It validates data
consistency, referential integrity, and cross-database relationships.

Features:
- Enhanced cross-database validation
- Data consistency checks between local services
- Referential integrity validation
- Performance impact assessment
- Automated fix suggestions
- Integration with existing validation framework

Usage:
    python scripts/validate-data-integrity-comprehensive.py [OPTIONS]

Examples:
    # Full comprehensive validation
    python scripts/validate-data-integrity-comprehensive.py --comprehensive

    # Quick validation for development
    python scripts/validate-data-integrity-comprehensive.py --quick

    # Validate with auto-fix suggestions
    python scripts/validate-data-integrity-comprehensive.py --suggest-fixes

    # Generate detailed report
    python scripts/validate-data-integrity-comprehensive.py --report ./integrity-report.json
"""

import asyncio
import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.multimodal_librarian.config.config_factory import get_database_config
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from src.multimodal_librarian.clients.protocols import (
    RelationalStoreClient, VectorStoreClient, GraphStoreClient,
    DatabaseClientError
)

# Import existing validation framework
try:
    from scripts.validate_data_integrity import (
        DataIntegrityValidator, ValidationIssue, ValidationResult, ValidationSummary
    )
    EXISTING_VALIDATOR_AVAILABLE = True
except ImportError:
    EXISTING_VALIDATOR_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class IntegrityCheckResult:
    """Result of a specific integrity check."""
    check_name: str
    success: bool
    issues_found: int
    execution_time: float
    details: Dict[str, Any]
    suggestions: List[str]


@dataclass
class ComprehensiveValidationReport:
    """Comprehensive validation report."""
    timestamp: str
    environment: str
    total_checks: int
    successful_checks: int
    failed_checks: int
    total_issues: int
    critical_issues: int
    execution_time: float
    check_results: List[IntegrityCheckResult]
    summary: Dict[str, Any]


class ComprehensiveDataValidator:
    """
    Comprehensive data integrity validator for local development.
    
    This class extends the basic validation with additional checks for
    local development environments, focusing on data consistency and
    referential integrity across all database services.
    """
    
    def __init__(self, config: Any):
        """Initialize the comprehensive validator."""
        self.config = config
        self.factory: Optional[DatabaseClientFactory] = None
        self.check_results: List[IntegrityCheckResult] = []
        self.start_time: Optional[float] = None
        
    async def initialize(self) -> None:
        """Initialize database connections."""
        try:
            self.factory = DatabaseClientFactory(self.config)
            logger.info(f"Initialized validator for {self.config.database_type} environment")
        except Exception as e:
            logger.error(f"Failed to initialize database factory: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up database connections."""
        if self.factory:
            await self.factory.close()
            self.factory = None
    
    async def run_comprehensive_validation(
        self, 
        quick_mode: bool = False,
        suggest_fixes: bool = False
    ) -> ComprehensiveValidationReport:
        """Run comprehensive data integrity validation."""
        self.start_time = time.time()
        self.check_results = []
        
        logger.info("Starting comprehensive data integrity validation...")
        
        # Define checks to run
        checks = [
            ("Database Connectivity", self._check_database_connectivity),
            ("Schema Integrity", self._check_schema_integrity),
            ("Data Consistency", self._check_data_consistency),
            ("Referential Integrity", self._check_referential_integrity),
            ("Cross-Database Sync", self._check_cross_database_sync),
        ]
        
        if not quick_mode:
            checks.extend([
                ("Performance Impact", self._check_performance_impact),
                ("Data Quality", self._check_data_quality),
                ("Constraint Validation", self._check_constraint_validation),
                ("Index Integrity", self._check_index_integrity),
                ("Backup Consistency", self._check_backup_consistency),
            ])
        
        # Run each check
        for check_name, check_function in checks:
            try:
                logger.info(f"Running check: {check_name}")
                result = await check_function(suggest_fixes)
                self.check_results.append(result)
                
                if result.success:
                    logger.info(f"✓ {check_name}: {result.issues_found} issues found")
                else:
                    logger.warning(f"✗ {check_name}: Check failed")
                    
            except Exception as e:
                logger.error(f"Check '{check_name}' failed with error: {e}")
                self.check_results.append(IntegrityCheckResult(
                    check_name=check_name,
                    success=False,
                    issues_found=0,
                    execution_time=0.0,
                    details={"error": str(e)},
                    suggestions=[f"Fix the underlying issue: {e}"]
                ))
        
        # Generate report
        return self._generate_comprehensive_report()
    
    async def _check_database_connectivity(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check connectivity to all database services."""
        start_time = time.time()
        issues = []
        suggestions = []
        
        try:
            if not self.factory:
                raise RuntimeError("Database factory not initialized")
            
            # Check each database service
            services_to_check = ["relational", "graph", "vector"]
            connectivity_results = {}
            
            for service in services_to_check:
                try:
                    if service == "relational":
                        client = await self.factory.get_relational_client()
                        info = await client.get_database_info()
                        connectivity_results[service] = {"status": "connected", "info": info}
                    elif service == "graph":
                        client = await self.factory.get_graph_client()
                        result = await client.execute_query("RETURN 1 as test")
                        connectivity_results[service] = {"status": "connected", "result": result}
                    elif service == "vector":
                        client = await self.factory.get_vector_client()
                        collections = await client.list_collections()
                        connectivity_results[service] = {"status": "connected", "collections": len(collections)}
                        
                except Exception as e:
                    connectivity_results[service] = {"status": "failed", "error": str(e)}
                    issues.append(f"{service} database connection failed: {e}")
                    
                    if suggest_fixes:
                        if "connection refused" in str(e).lower():
                            suggestions.append(f"Start the {service} database service")
                        elif "authentication" in str(e).lower():
                            suggestions.append(f"Check {service} database credentials")
                        else:
                            suggestions.append(f"Verify {service} database configuration")
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Database Connectivity",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=connectivity_results,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Database Connectivity",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database configuration and service status"]
            )
    
    async def _check_schema_integrity(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check schema integrity across all databases."""
        start_time = time.time()
        issues = []
        suggestions = []
        schema_info = {}
        
        try:
            # Check PostgreSQL schema
            try:
                client = await self.factory.get_relational_client()
                
                # Check for required tables
                required_tables = [
                    "users", "documents", "conversations", "messages", 
                    "document_chunks", "knowledge_chunks"
                ]
                
                existing_tables = await client.get_table_list()
                missing_tables = set(required_tables) - set(existing_tables)
                
                if missing_tables:
                    issues.append(f"Missing PostgreSQL tables: {missing_tables}")
                    if suggest_fixes:
                        suggestions.append("Run database migrations to create missing tables")
                
                schema_info["postgresql"] = {
                    "tables": len(existing_tables),
                    "missing_tables": list(missing_tables)
                }
                
            except Exception as e:
                issues.append(f"PostgreSQL schema check failed: {e}")
                schema_info["postgresql"] = {"error": str(e)}
            
            # Check Neo4j schema
            try:
                client = await self.factory.get_graph_client()
                
                # Check for required node types
                labels_result = await client.execute_query("CALL db.labels() YIELD label RETURN label")
                existing_labels = {row["label"] for row in labels_result}
                
                required_labels = {"User", "Document", "Conversation", "Concept", "Chunk"}
                missing_labels = required_labels - existing_labels
                
                if missing_labels:
                    issues.append(f"Missing Neo4j node types: {missing_labels}")
                    if suggest_fixes:
                        suggestions.append("Initialize Neo4j schema with required node types")
                
                schema_info["neo4j"] = {
                    "labels": len(existing_labels),
                    "missing_labels": list(missing_labels)
                }
                
            except Exception as e:
                issues.append(f"Neo4j schema check failed: {e}")
                schema_info["neo4j"] = {"error": str(e)}
            
            # Check Milvus schema
            try:
                client = await self.factory.get_vector_client()
                
                collections = await client.list_collections()
                required_collections = ["knowledge_chunks", "document_embeddings"]
                missing_collections = set(required_collections) - set(collections)
                
                if missing_collections:
                    issues.append(f"Missing Milvus collections: {missing_collections}")
                    if suggest_fixes:
                        suggestions.append("Create missing Milvus collections")
                
                schema_info["milvus"] = {
                    "collections": len(collections),
                    "missing_collections": list(missing_collections)
                }
                
            except Exception as e:
                issues.append(f"Milvus schema check failed: {e}")
                schema_info["milvus"] = {"error": str(e)}
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Schema Integrity",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=schema_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Schema Integrity",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and permissions"]
            )
    
    async def _check_data_consistency(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check data consistency within each database."""
        start_time = time.time()
        issues = []
        suggestions = []
        consistency_info = {}
        
        try:
            # Check PostgreSQL data consistency
            try:
                client = await self.factory.get_relational_client()
                
                # Check for orphaned records
                orphan_checks = [
                    ("messages without conversations", 
                     "SELECT COUNT(*) FROM messages m LEFT JOIN conversations c ON m.conversation_id = c.id WHERE c.id IS NULL"),
                    ("document_chunks without documents",
                     "SELECT COUNT(*) FROM document_chunks dc LEFT JOIN documents d ON dc.document_id = d.id WHERE d.id IS NULL"),
                ]
                
                pg_issues = []
                for check_name, query in orphan_checks:
                    try:
                        result = await client.execute_query(query)
                        count = result[0]["count"] if result else 0
                        if count > 0:
                            pg_issues.append(f"{count} {check_name}")
                            issues.append(f"PostgreSQL: {count} {check_name}")
                            if suggest_fixes:
                                suggestions.append(f"Clean up orphaned records: {check_name}")
                    except Exception as e:
                        logger.debug(f"Orphan check failed: {e}")
                
                consistency_info["postgresql"] = {"orphan_issues": pg_issues}
                
            except Exception as e:
                issues.append(f"PostgreSQL consistency check failed: {e}")
                consistency_info["postgresql"] = {"error": str(e)}
            
            # Check Neo4j data consistency
            try:
                client = await self.factory.get_graph_client()
                
                # Check for isolated nodes
                isolated_query = """
                MATCH (n) 
                WHERE NOT (n)--() 
                RETURN labels(n) as labels, count(n) as count
                """
                
                result = await client.execute_query(isolated_query)
                isolated_nodes = []
                
                for row in result:
                    if row["count"] > 0:
                        isolated_nodes.append(f"{row['count']} isolated {row['labels']} nodes")
                        issues.append(f"Neo4j: {row['count']} isolated {row['labels']} nodes")
                        if suggest_fixes:
                            suggestions.append(f"Review isolated {row['labels']} nodes for missing relationships")
                
                consistency_info["neo4j"] = {"isolated_nodes": isolated_nodes}
                
            except Exception as e:
                issues.append(f"Neo4j consistency check failed: {e}")
                consistency_info["neo4j"] = {"error": str(e)}
            
            # Check Milvus data consistency
            try:
                client = await self.factory.get_vector_client()
                
                collections = await client.list_collections()
                collection_stats = {}
                
                for collection in collections:
                    try:
                        stats = await client.get_collection_stats(collection)
                        vector_count = stats.get("vector_count", 0)
                        
                        # Check for empty collections
                        if vector_count == 0:
                            issues.append(f"Milvus: Empty collection '{collection}'")
                            if suggest_fixes:
                                suggestions.append(f"Populate collection '{collection}' with vectors or remove if unused")
                        
                        collection_stats[collection] = stats
                        
                    except Exception as e:
                        issues.append(f"Milvus: Failed to get stats for collection '{collection}': {e}")
                
                consistency_info["milvus"] = {"collection_stats": collection_stats}
                
            except Exception as e:
                issues.append(f"Milvus consistency check failed: {e}")
                consistency_info["milvus"] = {"error": str(e)}
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Data Consistency",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=consistency_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Data Consistency",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and query permissions"]
            )
    
    async def _check_referential_integrity(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check referential integrity across databases."""
        start_time = time.time()
        issues = []
        suggestions = []
        integrity_info = {}
        
        try:
            # Get data counts from each database
            pg_counts = {}
            neo4j_counts = {}
            milvus_counts = {}
            
            # PostgreSQL counts
            try:
                client = await self.factory.get_relational_client()
                
                count_queries = {
                    "users": "SELECT COUNT(*) FROM users",
                    "documents": "SELECT COUNT(*) FROM documents", 
                    "conversations": "SELECT COUNT(*) FROM conversations",
                    "document_chunks": "SELECT COUNT(*) FROM document_chunks"
                }
                
                for entity, query in count_queries.items():
                    try:
                        result = await client.execute_query(query)
                        pg_counts[entity] = result[0]["count"] if result else 0
                    except Exception:
                        pg_counts[entity] = 0
                        
            except Exception as e:
                integrity_info["postgresql_error"] = str(e)
            
            # Neo4j counts
            try:
                client = await self.factory.get_graph_client()
                
                count_queries = {
                    "User": "MATCH (n:User) RETURN count(n) as count",
                    "Document": "MATCH (n:Document) RETURN count(n) as count",
                    "Conversation": "MATCH (n:Conversation) RETURN count(n) as count"
                }
                
                for label, query in count_queries.items():
                    try:
                        result = await client.execute_query(query)
                        neo4j_counts[label] = result[0]["count"] if result else 0
                    except Exception:
                        neo4j_counts[label] = 0
                        
            except Exception as e:
                integrity_info["neo4j_error"] = str(e)
            
            # Milvus counts
            try:
                client = await self.factory.get_vector_client()
                
                collections = await client.list_collections()
                for collection in collections:
                    try:
                        stats = await client.get_collection_stats(collection)
                        milvus_counts[collection] = stats.get("vector_count", 0)
                    except Exception:
                        milvus_counts[collection] = 0
                        
            except Exception as e:
                integrity_info["milvus_error"] = str(e)
            
            # Compare counts and identify discrepancies
            discrepancies = []
            
            # User count comparison
            pg_users = pg_counts.get("users", 0)
            neo4j_users = neo4j_counts.get("User", 0)
            
            if abs(pg_users - neo4j_users) > 5:  # Allow small differences
                discrepancies.append({
                    "type": "user_count_mismatch",
                    "postgresql": pg_users,
                    "neo4j": neo4j_users,
                    "difference": abs(pg_users - neo4j_users)
                })
                issues.append(f"User count mismatch: PostgreSQL({pg_users}) vs Neo4j({neo4j_users})")
                if suggest_fixes:
                    suggestions.append("Synchronize user data between PostgreSQL and Neo4j")
            
            # Document count comparison
            pg_docs = pg_counts.get("documents", 0)
            neo4j_docs = neo4j_counts.get("Document", 0)
            
            if abs(pg_docs - neo4j_docs) > 5:
                discrepancies.append({
                    "type": "document_count_mismatch",
                    "postgresql": pg_docs,
                    "neo4j": neo4j_docs,
                    "difference": abs(pg_docs - neo4j_docs)
                })
                issues.append(f"Document count mismatch: PostgreSQL({pg_docs}) vs Neo4j({neo4j_docs})")
                if suggest_fixes:
                    suggestions.append("Synchronize document data between PostgreSQL and Neo4j")
            
            # Document chunks vs vectors comparison
            pg_chunks = pg_counts.get("document_chunks", 0)
            total_vectors = sum(milvus_counts.values())
            
            if abs(pg_chunks - total_vectors) > 10:
                discrepancies.append({
                    "type": "chunk_vector_mismatch",
                    "postgresql_chunks": pg_chunks,
                    "milvus_vectors": total_vectors,
                    "difference": abs(pg_chunks - total_vectors)
                })
                issues.append(f"Chunk/vector count mismatch: PostgreSQL({pg_chunks}) vs Milvus({total_vectors})")
                if suggest_fixes:
                    suggestions.append("Re-generate vector embeddings for document chunks")
            
            integrity_info.update({
                "postgresql_counts": pg_counts,
                "neo4j_counts": neo4j_counts,
                "milvus_counts": milvus_counts,
                "discrepancies": discrepancies
            })
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Referential Integrity",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=integrity_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Referential Integrity",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and data access permissions"]
            )
    
    async def _check_cross_database_sync(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check synchronization between databases."""
        start_time = time.time()
        issues = []
        suggestions = []
        sync_info = {}
        
        try:
            # This is a placeholder for more sophisticated sync checks
            # In a real implementation, you would check timestamps, checksums, etc.
            
            # Check if data exists in all databases
            has_data = {"postgresql": False, "neo4j": False, "milvus": False}
            
            # PostgreSQL data check
            try:
                client = await self.factory.get_relational_client()
                result = await client.execute_query("SELECT COUNT(*) FROM users")
                has_data["postgresql"] = (result[0]["count"] if result else 0) > 0
            except Exception:
                pass
            
            # Neo4j data check
            try:
                client = await self.factory.get_graph_client()
                result = await client.execute_query("MATCH (n) RETURN count(n) as count LIMIT 1")
                has_data["neo4j"] = (result[0]["count"] if result else 0) > 0
            except Exception:
                pass
            
            # Milvus data check
            try:
                client = await self.factory.get_vector_client()
                collections = await client.list_collections()
                total_vectors = 0
                for collection in collections:
                    try:
                        stats = await client.get_collection_stats(collection)
                        total_vectors += stats.get("vector_count", 0)
                    except Exception:
                        pass
                has_data["milvus"] = total_vectors > 0
            except Exception:
                pass
            
            # Check for sync issues
            data_databases = [db for db, has_data_flag in has_data.items() if has_data_flag]
            empty_databases = [db for db, has_data_flag in has_data.items() if not has_data_flag]
            
            if len(data_databases) > 0 and len(empty_databases) > 0:
                issues.append(f"Data sync issue: {data_databases} have data, {empty_databases} are empty")
                if suggest_fixes:
                    suggestions.append("Run data synchronization to populate empty databases")
            
            sync_info.update({
                "data_status": has_data,
                "databases_with_data": data_databases,
                "empty_databases": empty_databases
            })
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Cross-Database Sync",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=sync_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Cross-Database Sync",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and synchronization processes"]
            )
    
    async def _check_performance_impact(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check performance impact of current data state."""
        start_time = time.time()
        issues = []
        suggestions = []
        performance_info = {}
        
        try:
            # This is a simplified performance check
            # In a real implementation, you would measure query times, index usage, etc.
            
            # Check database sizes
            sizes = {}
            
            # PostgreSQL size
            try:
                client = await self.factory.get_relational_client()
                result = await client.execute_query(
                    "SELECT pg_size_pretty(pg_database_size(current_database())) as size"
                )
                sizes["postgresql"] = result[0]["size"] if result else "Unknown"
            except Exception as e:
                sizes["postgresql"] = f"Error: {e}"
            
            # Neo4j size (approximate)
            try:
                client = await self.factory.get_graph_client()
                result = await client.execute_query("MATCH (n) RETURN count(n) as nodes")
                node_count = result[0]["nodes"] if result else 0
                sizes["neo4j"] = f"{node_count} nodes"
                
                if node_count > 100000:
                    issues.append(f"Neo4j has {node_count} nodes, may impact performance")
                    if suggest_fixes:
                        suggestions.append("Consider adding indexes or optimizing queries for large Neo4j dataset")
                        
            except Exception as e:
                sizes["neo4j"] = f"Error: {e}"
            
            # Milvus size
            try:
                client = await self.factory.get_vector_client()
                collections = await client.list_collections()
                total_vectors = 0
                
                for collection in collections:
                    try:
                        stats = await client.get_collection_stats(collection)
                        total_vectors += stats.get("vector_count", 0)
                    except Exception:
                        pass
                
                sizes["milvus"] = f"{total_vectors} vectors"
                
                if total_vectors > 1000000:
                    issues.append(f"Milvus has {total_vectors} vectors, may impact search performance")
                    if suggest_fixes:
                        suggestions.append("Consider optimizing Milvus indexes for large vector dataset")
                        
            except Exception as e:
                sizes["milvus"] = f"Error: {e}"
            
            performance_info["database_sizes"] = sizes
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Performance Impact",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=performance_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Performance Impact",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and performance monitoring tools"]
            )
    
    async def _check_data_quality(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check data quality issues."""
        start_time = time.time()
        issues = []
        suggestions = []
        quality_info = {}
        
        try:
            # Check for common data quality issues
            
            # PostgreSQL data quality
            try:
                client = await self.factory.get_relational_client()
                
                quality_checks = [
                    ("NULL emails in users", "SELECT COUNT(*) FROM users WHERE email IS NULL OR email = ''"),
                    ("Documents without titles", "SELECT COUNT(*) FROM documents WHERE title IS NULL OR title = ''"),
                    ("Future timestamps", "SELECT COUNT(*) FROM documents WHERE created_at > NOW()"),
                ]
                
                pg_quality = {}
                for check_name, query in quality_checks:
                    try:
                        result = await client.execute_query(query)
                        count = result[0]["count"] if result else 0
                        pg_quality[check_name] = count
                        
                        if count > 0:
                            issues.append(f"PostgreSQL: {count} records with {check_name}")
                            if suggest_fixes:
                                suggestions.append(f"Clean up {check_name} in PostgreSQL")
                    except Exception as e:
                        pg_quality[check_name] = f"Error: {e}"
                
                quality_info["postgresql"] = pg_quality
                
            except Exception as e:
                quality_info["postgresql"] = {"error": str(e)}
            
            # Neo4j data quality
            try:
                client = await self.factory.get_graph_client()
                
                quality_checks = [
                    ("Nodes without required properties", "MATCH (n:User) WHERE n.id IS NULL RETURN count(n) as count"),
                    ("Documents without titles", "MATCH (n:Document) WHERE n.title IS NULL OR n.title = '' RETURN count(n) as count"),
                ]
                
                neo4j_quality = {}
                for check_name, query in quality_checks:
                    try:
                        result = await client.execute_query(query)
                        count = result[0]["count"] if result else 0
                        neo4j_quality[check_name] = count
                        
                        if count > 0:
                            issues.append(f"Neo4j: {count} {check_name}")
                            if suggest_fixes:
                                suggestions.append(f"Fix {check_name} in Neo4j")
                    except Exception as e:
                        neo4j_quality[check_name] = f"Error: {e}"
                
                quality_info["neo4j"] = neo4j_quality
                
            except Exception as e:
                quality_info["neo4j"] = {"error": str(e)}
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Data Quality",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=quality_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Data Quality",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and data access permissions"]
            )
    
    async def _check_constraint_validation(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check database constraints."""
        start_time = time.time()
        issues = []
        suggestions = []
        constraint_info = {}
        
        try:
            # PostgreSQL constraints
            try:
                client = await self.factory.get_relational_client()
                
                # Check for missing primary keys
                pk_query = """
                SELECT t.table_name
                FROM information_schema.tables t
                LEFT JOIN information_schema.table_constraints tc 
                    ON t.table_name = tc.table_name 
                    AND tc.constraint_type = 'PRIMARY KEY'
                WHERE t.table_schema = 'public' 
                    AND t.table_type = 'BASE TABLE'
                    AND tc.constraint_name IS NULL
                """
                
                result = await client.execute_query(pk_query)
                tables_without_pk = [row["table_name"] for row in result]
                
                if tables_without_pk:
                    issues.append(f"PostgreSQL tables without primary keys: {tables_without_pk}")
                    if suggest_fixes:
                        suggestions.append("Add primary key constraints to tables")
                
                constraint_info["postgresql"] = {
                    "tables_without_primary_keys": tables_without_pk
                }
                
            except Exception as e:
                constraint_info["postgresql"] = {"error": str(e)}
            
            # Neo4j constraints
            try:
                client = await self.factory.get_graph_client()
                
                # Check existing constraints
                constraints_result = await client.execute_query("SHOW CONSTRAINTS")
                constraint_count = len(constraints_result)
                
                # Expected minimum constraints
                expected_constraints = 3  # Adjust based on your schema
                
                if constraint_count < expected_constraints:
                    issues.append(f"Neo4j has only {constraint_count} constraints, expected at least {expected_constraints}")
                    if suggest_fixes:
                        suggestions.append("Add missing uniqueness and existence constraints in Neo4j")
                
                constraint_info["neo4j"] = {
                    "constraint_count": constraint_count,
                    "constraints": [c.get("name", "unnamed") for c in constraints_result]
                }
                
            except Exception as e:
                constraint_info["neo4j"] = {"error": str(e)}
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Constraint Validation",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=constraint_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Constraint Validation",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and constraint access permissions"]
            )
    
    async def _check_index_integrity(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check database indexes."""
        start_time = time.time()
        issues = []
        suggestions = []
        index_info = {}
        
        try:
            # PostgreSQL indexes
            try:
                client = await self.factory.get_relational_client()
                
                # Check for tables without indexes
                index_query = """
                SELECT t.table_name, COUNT(i.indexname) as index_count
                FROM information_schema.tables t
                LEFT JOIN pg_indexes i ON t.table_name = i.tablename
                WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
                GROUP BY t.table_name
                HAVING COUNT(i.indexname) <= 1  -- Only primary key index
                """
                
                result = await client.execute_query(index_query)
                tables_needing_indexes = [row["table_name"] for row in result]
                
                if tables_needing_indexes:
                    issues.append(f"PostgreSQL tables that may need additional indexes: {tables_needing_indexes}")
                    if suggest_fixes:
                        suggestions.append("Consider adding indexes on frequently queried columns")
                
                index_info["postgresql"] = {
                    "tables_needing_indexes": tables_needing_indexes
                }
                
            except Exception as e:
                index_info["postgresql"] = {"error": str(e)}
            
            # Neo4j indexes
            try:
                client = await self.factory.get_graph_client()
                
                # Check existing indexes
                indexes_result = await client.execute_query("SHOW INDEXES")
                index_count = len([idx for idx in indexes_result if idx.get("state") == "ONLINE"])
                
                # Expected minimum indexes
                expected_indexes = 2  # Adjust based on your schema
                
                if index_count < expected_indexes:
                    issues.append(f"Neo4j has only {index_count} online indexes, consider adding more for performance")
                    if suggest_fixes:
                        suggestions.append("Add indexes on frequently queried properties in Neo4j")
                
                index_info["neo4j"] = {
                    "online_index_count": index_count,
                    "indexes": [idx.get("name", "unnamed") for idx in indexes_result if idx.get("state") == "ONLINE"]
                }
                
            except Exception as e:
                index_info["neo4j"] = {"error": str(e)}
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Index Integrity",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=index_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Index Integrity",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check database connectivity and index access permissions"]
            )
    
    async def _check_backup_consistency(self, suggest_fixes: bool) -> IntegrityCheckResult:
        """Check backup consistency and availability."""
        start_time = time.time()
        issues = []
        suggestions = []
        backup_info = {}
        
        try:
            # Check if backup directories exist and have recent backups
            backup_root = Path("./backups")
            
            if not backup_root.exists():
                issues.append("Backup directory does not exist")
                if suggest_fixes:
                    suggestions.append("Create backup directory and run initial backup")
                backup_info["backup_directory_exists"] = False
            else:
                backup_info["backup_directory_exists"] = True
                
                # Check each database backup directory
                db_backup_dirs = ["postgresql", "neo4j", "milvus", "redis"]
                backup_status = {}
                
                for db_dir in db_backup_dirs:
                    db_backup_path = backup_root / db_dir
                    
                    if db_backup_path.exists():
                        # Count backup files
                        backup_files = list(db_backup_path.glob("*"))
                        backup_count = len(backup_files)
                        
                        if backup_count == 0:
                            issues.append(f"No backup files found for {db_dir}")
                            if suggest_fixes:
                                suggestions.append(f"Create backup for {db_dir} database")
                        
                        # Check for recent backups (within last 7 days)
                        import time
                        week_ago = time.time() - (7 * 24 * 60 * 60)
                        recent_backups = [
                            f for f in backup_files 
                            if f.is_file() and f.stat().st_mtime > week_ago
                        ]
                        
                        if len(recent_backups) == 0 and backup_count > 0:
                            issues.append(f"No recent backups for {db_dir} (older than 7 days)")
                            if suggest_fixes:
                                suggestions.append(f"Create fresh backup for {db_dir}")
                        
                        backup_status[db_dir] = {
                            "total_backups": backup_count,
                            "recent_backups": len(recent_backups)
                        }
                    else:
                        issues.append(f"Backup directory missing for {db_dir}")
                        if suggest_fixes:
                            suggestions.append(f"Create backup directory and backup for {db_dir}")
                        backup_status[db_dir] = {"exists": False}
                
                backup_info["database_backups"] = backup_status
            
            execution_time = time.time() - start_time
            
            return IntegrityCheckResult(
                check_name="Backup Consistency",
                success=len(issues) == 0,
                issues_found=len(issues),
                execution_time=execution_time,
                details=backup_info,
                suggestions=suggestions
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return IntegrityCheckResult(
                check_name="Backup Consistency",
                success=False,
                issues_found=1,
                execution_time=execution_time,
                details={"error": str(e)},
                suggestions=["Check file system permissions and backup directory access"]
            )
    
    def _generate_comprehensive_report(self) -> ComprehensiveValidationReport:
        """Generate comprehensive validation report."""
        if not self.start_time:
            raise RuntimeError("Validation not started")
        
        total_execution_time = time.time() - self.start_time
        
        successful_checks = sum(1 for result in self.check_results if result.success)
        failed_checks = len(self.check_results) - successful_checks
        total_issues = sum(result.issues_found for result in self.check_results)
        critical_issues = sum(
            1 for result in self.check_results 
            if not result.success or result.issues_found > 5
        )
        
        # Generate summary
        summary = {
            "overall_status": "healthy" if failed_checks == 0 and total_issues == 0 else 
                            "warning" if failed_checks == 0 else "critical",
            "environment": self.config.database_type,
            "databases_checked": ["postgresql", "neo4j", "milvus"],
            "most_common_issues": self._get_most_common_issues(),
            "recommended_actions": self._get_recommended_actions()
        }
        
        return ComprehensiveValidationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            environment=self.config.database_type,
            total_checks=len(self.check_results),
            successful_checks=successful_checks,
            failed_checks=failed_checks,
            total_issues=total_issues,
            critical_issues=critical_issues,
            execution_time=total_execution_time,
            check_results=self.check_results,
            summary=summary
        )
    
    def _get_most_common_issues(self) -> List[str]:
        """Get most common issues across all checks."""
        # This is a simplified implementation
        # In practice, you would analyze issue patterns
        common_issues = []
        
        for result in self.check_results:
            if result.issues_found > 0:
                common_issues.append(f"{result.check_name}: {result.issues_found} issues")
        
        return common_issues[:5]  # Top 5
    
    def _get_recommended_actions(self) -> List[str]:
        """Get recommended actions based on validation results."""
        actions = []
        
        for result in self.check_results:
            if result.suggestions:
                actions.extend(result.suggestions[:2])  # Top 2 suggestions per check
        
        return list(set(actions))[:10]  # Top 10 unique actions


def print_validation_report(report: ComprehensiveValidationReport) -> None:
    """Print comprehensive validation report."""
    print("\n" + "="*80)
    print("COMPREHENSIVE DATA INTEGRITY VALIDATION REPORT")
    print("="*80)
    
    print(f"Timestamp: {report.timestamp}")
    print(f"Environment: {report.environment}")
    print(f"Total Execution Time: {report.execution_time:.2f} seconds")
    print()
    
    # Summary
    print("SUMMARY")
    print("-" * 40)
    print(f"Total Checks: {report.total_checks}")
    print(f"Successful: {report.successful_checks}")
    print(f"Failed: {report.failed_checks}")
    print(f"Total Issues: {report.total_issues}")
    print(f"Critical Issues: {report.critical_issues}")
    print(f"Overall Status: {report.summary['overall_status'].upper()}")
    print()
    
    # Check Results
    print("CHECK RESULTS")
    print("-" * 40)
    for result in report.check_results:
        status = "✓" if result.success else "✗"
        print(f"{status} {result.check_name:25} {result.issues_found:3} issues  {result.execution_time:6.3f}s")
    print()
    
    # Most Common Issues
    if report.summary["most_common_issues"]:
        print("MOST COMMON ISSUES")
        print("-" * 40)
        for issue in report.summary["most_common_issues"]:
            print(f"• {issue}")
        print()
    
    # Recommended Actions
    if report.summary["recommended_actions"]:
        print("RECOMMENDED ACTIONS")
        print("-" * 40)
        for i, action in enumerate(report.summary["recommended_actions"], 1):
            print(f"{i:2}. {action}")
        print()
    
    print("="*80)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Comprehensive data integrity validation for Multimodal Librarian",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Run comprehensive validation (all checks)"
    )
    parser.add_argument(
        "--quick",
        action="store_true", 
        help="Run quick validation (essential checks only)"
    )
    parser.add_argument(
        "--suggest-fixes",
        action="store_true",
        help="Include fix suggestions in output"
    )
    parser.add_argument(
        "--report",
        type=str,
        help="Save detailed report to JSON file"
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
    
    # Determine validation mode
    if args.quick:
        quick_mode = True
    else:
        quick_mode = not args.comprehensive
    
    try:
        # Get database configuration
        config = get_database_config()
        
        # Initialize validator
        validator = ComprehensiveDataValidator(config)
        await validator.initialize()
        
        try:
            # Run validation
            report = await validator.run_comprehensive_validation(
                quick_mode=quick_mode,
                suggest_fixes=args.suggest_fixes
            )
            
            # Print report
            print_validation_report(report)
            
            # Save detailed report if requested
            if args.report:
                report_path = Path(args.report)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(report_path, 'w') as f:
                    json.dump(asdict(report), f, indent=2, default=str)
                
                print(f"\nDetailed report saved to: {report_path}")
            
            # Return appropriate exit code
            if report.failed_checks > 0 or report.critical_issues > 0:
                return 2  # Critical issues
            elif report.total_issues > 0:
                return 1  # Warnings
            else:
                return 0  # All good
                
        finally:
            await validator.cleanup()
            
    except KeyboardInterrupt:
        print("\nValidation cancelled by user")
        return 1
    except Exception as e:
        print(f"Validation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))