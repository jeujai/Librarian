#!/usr/bin/env python3
"""
Data Validation Utilities for Local Development

This module provides utility functions for data validation and integrity checks
that can be used by other data management scripts. It includes functions for
validating data consistency, checking referential integrity, and ensuring
data quality across all database services.

Usage:
    from scripts.data_validation_utils import DataValidationUtils
    
    # Initialize validator
    validator = DataValidationUtils(config)
    await validator.initialize()
    
    # Run specific validations
    result = await validator.validate_user_data_consistency()
    
    # Clean up
    await validator.cleanup()
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass
from pathlib import Path

# Database client imports
from src.multimodal_librarian.config.config_factory import get_database_config
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from src.multimodal_librarian.clients.protocols import (
    RelationalStoreClient, VectorStoreClient, GraphStoreClient,
    DatabaseClientError
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    success: bool
    message: str
    details: Dict[str, Any]
    suggestions: List[str]
    timestamp: datetime


@dataclass
class DataConsistencyReport:
    """Report of data consistency across databases."""
    user_consistency: ValidationResult
    document_consistency: ValidationResult
    conversation_consistency: ValidationResult
    vector_consistency: ValidationResult
    overall_status: str
    total_issues: int


class DataValidationUtils:
    """
    Utility class for data validation operations.
    
    This class provides reusable validation functions that can be used
    by backup, restore, and other data management scripts to ensure
    data integrity and consistency.
    """
    
    def __init__(self, config: Any):
        """Initialize the validation utilities."""
        self.config = config
        self.factory: Optional[DatabaseClientFactory] = None
        
    async def initialize(self) -> None:
        """Initialize database connections."""
        try:
            self.factory = DatabaseClientFactory(self.config)
            logger.debug(f"Initialized validation utils for {self.config.database_type} environment")
        except Exception as e:
            logger.error(f"Failed to initialize database factory: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up database connections."""
        if self.factory:
            await self.factory.close()
            self.factory = None
    
    async def validate_database_connectivity(self) -> Dict[str, ValidationResult]:
        """Validate connectivity to all database services."""
        if not self.factory:
            raise RuntimeError("Factory not initialized")
        
        results = {}
        
        # Test PostgreSQL connectivity
        try:
            client = await self.factory.get_relational_client()
            info = await client.get_database_info()
            results["postgresql"] = ValidationResult(
                success=True,
                message="PostgreSQL connection successful",
                details=info,
                suggestions=[],
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            results["postgresql"] = ValidationResult(
                success=False,
                message=f"PostgreSQL connection failed: {e}",
                details={"error": str(e)},
                suggestions=["Check PostgreSQL service status", "Verify connection parameters"],
                timestamp=datetime.now(timezone.utc)
            )
        
        # Test Neo4j connectivity
        try:
            client = await self.factory.get_graph_client()
            result = await client.execute_query("RETURN 1 as test")
            results["neo4j"] = ValidationResult(
                success=True,
                message="Neo4j connection successful",
                details={"test_result": result},
                suggestions=[],
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            results["neo4j"] = ValidationResult(
                success=False,
                message=f"Neo4j connection failed: {e}",
                details={"error": str(e)},
                suggestions=["Check Neo4j service status", "Verify authentication credentials"],
                timestamp=datetime.now(timezone.utc)
            )
        
        # Test Milvus connectivity
        try:
            client = await self.factory.get_vector_client()
            collections = await client.list_collections()
            results["milvus"] = ValidationResult(
                success=True,
                message="Milvus connection successful",
                details={"collections": collections},
                suggestions=[],
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            results["milvus"] = ValidationResult(
                success=False,
                message=f"Milvus connection failed: {e}",
                details={"error": str(e)},
                suggestions=["Check Milvus service status", "Verify connection parameters"],
                timestamp=datetime.now(timezone.utc)
            )
        
        return results
    
    async def validate_user_data_consistency(self) -> ValidationResult:
        """Validate user data consistency between PostgreSQL and Neo4j."""
        try:
            # Get user counts from both databases
            pg_client = await self.factory.get_relational_client()
            neo4j_client = await self.factory.get_graph_client()
            
            # PostgreSQL user count
            pg_result = await pg_client.execute_query("SELECT COUNT(*) as count FROM users")
            pg_user_count = pg_result[0]["count"] if pg_result else 0
            
            # Neo4j user count
            neo4j_result = await neo4j_client.execute_query("MATCH (u:User) RETURN count(u) as count")
            neo4j_user_count = neo4j_result[0]["count"] if neo4j_result else 0
            
            # Check for consistency
            difference = abs(pg_user_count - neo4j_user_count)
            
            if difference == 0:
                return ValidationResult(
                    success=True,
                    message=f"User data is consistent ({pg_user_count} users in both databases)",
                    details={
                        "postgresql_users": pg_user_count,
                        "neo4j_users": neo4j_user_count,
                        "difference": difference
                    },
                    suggestions=[],
                    timestamp=datetime.now(timezone.utc)
                )
            elif difference <= 5:  # Allow small differences
                return ValidationResult(
                    success=True,
                    message=f"User data has minor inconsistency (difference: {difference})",
                    details={
                        "postgresql_users": pg_user_count,
                        "neo4j_users": neo4j_user_count,
                        "difference": difference
                    },
                    suggestions=["Monitor for data sync issues"],
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                return ValidationResult(
                    success=False,
                    message=f"User data is inconsistent (difference: {difference})",
                    details={
                        "postgresql_users": pg_user_count,
                        "neo4j_users": neo4j_user_count,
                        "difference": difference
                    },
                    suggestions=[
                        "Run data synchronization between PostgreSQL and Neo4j",
                        "Check for failed data operations",
                        "Investigate data integrity issues"
                    ],
                    timestamp=datetime.now(timezone.utc)
                )
                
        except Exception as e:
            return ValidationResult(
                success=False,
                message=f"User data consistency check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check database connectivity", "Verify table/node existence"],
                timestamp=datetime.now(timezone.utc)
            )
    
    async def validate_document_data_consistency(self) -> ValidationResult:
        """Validate document data consistency across all databases."""
        try:
            # Get document counts from all databases
            pg_client = await self.factory.get_relational_client()
            neo4j_client = await self.factory.get_graph_client()
            milvus_client = await self.factory.get_vector_client()
            
            # PostgreSQL document count
            pg_result = await pg_client.execute_query("SELECT COUNT(*) as count FROM documents")
            pg_doc_count = pg_result[0]["count"] if pg_result else 0
            
            # Neo4j document count
            neo4j_result = await neo4j_client.execute_query("MATCH (d:Document) RETURN count(d) as count")
            neo4j_doc_count = neo4j_result[0]["count"] if neo4j_result else 0
            
            # Milvus vector count (approximate document representation)
            collections = await milvus_client.list_collections()
            total_vectors = 0
            for collection in collections:
                try:
                    stats = await milvus_client.get_collection_stats(collection)
                    total_vectors += stats.get("vector_count", 0)
                except Exception:
                    pass
            
            # Check for consistency
            pg_neo4j_diff = abs(pg_doc_count - neo4j_doc_count)
            
            details = {
                "postgresql_documents": pg_doc_count,
                "neo4j_documents": neo4j_doc_count,
                "milvus_vectors": total_vectors,
                "pg_neo4j_difference": pg_neo4j_diff
            }
            
            issues = []
            suggestions = []
            
            if pg_neo4j_diff > 5:
                issues.append(f"Document count mismatch between PostgreSQL ({pg_doc_count}) and Neo4j ({neo4j_doc_count})")
                suggestions.append("Synchronize document data between PostgreSQL and Neo4j")
            
            # Check if we have documents but no vectors (or vice versa)
            if pg_doc_count > 0 and total_vectors == 0:
                issues.append("Documents exist but no vectors found in Milvus")
                suggestions.append("Generate vector embeddings for existing documents")
            elif pg_doc_count == 0 and total_vectors > 0:
                issues.append("Vectors exist but no documents found in PostgreSQL")
                suggestions.append("Clean up orphaned vectors or restore document data")
            
            success = len(issues) == 0
            message = "Document data is consistent across all databases" if success else f"Found {len(issues)} document consistency issues"
            
            return ValidationResult(
                success=success,
                message=message,
                details=details,
                suggestions=suggestions,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            return ValidationResult(
                success=False,
                message=f"Document data consistency check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check database connectivity", "Verify schema existence"],
                timestamp=datetime.now(timezone.utc)
            )
    
    async def validate_conversation_data_consistency(self) -> ValidationResult:
        """Validate conversation data consistency."""
        try:
            pg_client = await self.factory.get_relational_client()
            neo4j_client = await self.factory.get_graph_client()
            
            # PostgreSQL conversation count
            pg_conv_result = await pg_client.execute_query("SELECT COUNT(*) as count FROM conversations")
            pg_conv_count = pg_conv_result[0]["count"] if pg_conv_result else 0
            
            # PostgreSQL message count
            pg_msg_result = await pg_client.execute_query("SELECT COUNT(*) as count FROM messages")
            pg_msg_count = pg_msg_result[0]["count"] if pg_msg_result else 0
            
            # Neo4j conversation count
            neo4j_conv_result = await neo4j_client.execute_query("MATCH (c:Conversation) RETURN count(c) as count")
            neo4j_conv_count = neo4j_conv_result[0]["count"] if neo4j_conv_result else 0
            
            # Check for orphaned messages
            orphan_result = await pg_client.execute_query("""
                SELECT COUNT(*) as count 
                FROM messages m 
                LEFT JOIN conversations c ON m.conversation_id = c.id 
                WHERE c.id IS NULL
            """)
            orphaned_messages = orphan_result[0]["count"] if orphan_result else 0
            
            details = {
                "postgresql_conversations": pg_conv_count,
                "postgresql_messages": pg_msg_count,
                "neo4j_conversations": neo4j_conv_count,
                "orphaned_messages": orphaned_messages
            }
            
            issues = []
            suggestions = []
            
            # Check conversation consistency
            conv_diff = abs(pg_conv_count - neo4j_conv_count)
            if conv_diff > 3:
                issues.append(f"Conversation count mismatch: PostgreSQL ({pg_conv_count}) vs Neo4j ({neo4j_conv_count})")
                suggestions.append("Synchronize conversation data between databases")
            
            # Check for orphaned messages
            if orphaned_messages > 0:
                issues.append(f"Found {orphaned_messages} orphaned messages without conversations")
                suggestions.append("Clean up orphaned messages or restore missing conversations")
            
            # Check message-to-conversation ratio
            if pg_conv_count > 0:
                msg_per_conv = pg_msg_count / pg_conv_count
                if msg_per_conv < 1:
                    issues.append("Conversations exist without messages")
                    suggestions.append("Verify conversation data integrity")
            
            success = len(issues) == 0
            message = "Conversation data is consistent" if success else f"Found {len(issues)} conversation consistency issues"
            
            return ValidationResult(
                success=success,
                message=message,
                details=details,
                suggestions=suggestions,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            return ValidationResult(
                success=False,
                message=f"Conversation data consistency check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check database connectivity", "Verify table existence"],
                timestamp=datetime.now(timezone.utc)
            )
    
    async def validate_vector_data_consistency(self) -> ValidationResult:
        """Validate vector data consistency and quality."""
        try:
            milvus_client = await self.factory.get_vector_client()
            pg_client = await self.factory.get_relational_client()
            
            # Get Milvus collection information
            collections = await milvus_client.list_collections()
            collection_stats = {}
            total_vectors = 0
            
            for collection in collections:
                try:
                    stats = await milvus_client.get_collection_stats(collection)
                    collection_stats[collection] = stats
                    total_vectors += stats.get("vector_count", 0)
                except Exception as e:
                    collection_stats[collection] = {"error": str(e)}
            
            # Get document chunk count from PostgreSQL
            try:
                chunk_result = await pg_client.execute_query("SELECT COUNT(*) as count FROM document_chunks")
                chunk_count = chunk_result[0]["count"] if chunk_result else 0
            except Exception:
                chunk_count = 0
            
            details = {
                "milvus_collections": len(collections),
                "total_vectors": total_vectors,
                "postgresql_chunks": chunk_count,
                "collection_stats": collection_stats
            }
            
            issues = []
            suggestions = []
            
            # Check if we have collections
            if len(collections) == 0:
                issues.append("No Milvus collections found")
                suggestions.append("Create required Milvus collections")
            
            # Check vector-chunk consistency
            vector_chunk_diff = abs(total_vectors - chunk_count)
            if vector_chunk_diff > 10:  # Allow some difference
                issues.append(f"Vector-chunk count mismatch: {total_vectors} vectors vs {chunk_count} chunks")
                suggestions.append("Re-generate vector embeddings for document chunks")
            
            # Check for empty collections
            empty_collections = [
                name for name, stats in collection_stats.items() 
                if isinstance(stats, dict) and stats.get("vector_count", 0) == 0
            ]
            
            if empty_collections:
                issues.append(f"Empty collections found: {empty_collections}")
                suggestions.append("Populate empty collections or remove if unused")
            
            success = len(issues) == 0
            message = "Vector data is consistent" if success else f"Found {len(issues)} vector consistency issues"
            
            return ValidationResult(
                success=success,
                message=message,
                details=details,
                suggestions=suggestions,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            return ValidationResult(
                success=False,
                message=f"Vector data consistency check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check Milvus connectivity", "Verify collection existence"],
                timestamp=datetime.now(timezone.utc)
            )
    
    async def validate_referential_integrity(self) -> Dict[str, ValidationResult]:
        """Validate referential integrity across all databases."""
        results = {}
        
        # Check PostgreSQL referential integrity
        try:
            pg_client = await self.factory.get_relational_client()
            
            # Check for foreign key violations
            fk_checks = [
                ("messages_conversation_fk", """
                    SELECT COUNT(*) as count 
                    FROM messages m 
                    LEFT JOIN conversations c ON m.conversation_id = c.id 
                    WHERE m.conversation_id IS NOT NULL AND c.id IS NULL
                """),
                ("documents_user_fk", """
                    SELECT COUNT(*) as count 
                    FROM documents d 
                    LEFT JOIN users u ON d.user_id = u.id 
                    WHERE d.user_id IS NOT NULL AND u.id IS NULL
                """),
                ("chunks_document_fk", """
                    SELECT COUNT(*) as count 
                    FROM document_chunks dc 
                    LEFT JOIN documents d ON dc.document_id = d.id 
                    WHERE dc.document_id IS NOT NULL AND d.id IS NULL
                """)
            ]
            
            pg_issues = []
            pg_suggestions = []
            
            for check_name, query in fk_checks:
                try:
                    result = await pg_client.execute_query(query)
                    violation_count = result[0]["count"] if result else 0
                    
                    if violation_count > 0:
                        pg_issues.append(f"{check_name}: {violation_count} violations")
                        pg_suggestions.append(f"Fix {check_name} violations")
                        
                except Exception as e:
                    pg_issues.append(f"{check_name}: Check failed - {e}")
            
            results["postgresql"] = ValidationResult(
                success=len(pg_issues) == 0,
                message=f"PostgreSQL referential integrity: {len(pg_issues)} issues found",
                details={"issues": pg_issues},
                suggestions=pg_suggestions,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            results["postgresql"] = ValidationResult(
                success=False,
                message=f"PostgreSQL referential integrity check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check PostgreSQL connectivity"],
                timestamp=datetime.now(timezone.utc)
            )
        
        # Check Neo4j referential integrity
        try:
            neo4j_client = await self.factory.get_graph_client()
            
            # Check for dangling relationships
            dangling_check = """
                MATCH ()-[r]->() 
                WHERE startNode(r) IS NULL OR endNode(r) IS NULL 
                RETURN count(r) as count
            """
            
            result = await neo4j_client.execute_query(dangling_check)
            dangling_count = result[0]["count"] if result else 0
            
            neo4j_issues = []
            neo4j_suggestions = []
            
            if dangling_count > 0:
                neo4j_issues.append(f"Dangling relationships: {dangling_count}")
                neo4j_suggestions.append("Remove dangling relationships")
            
            results["neo4j"] = ValidationResult(
                success=len(neo4j_issues) == 0,
                message=f"Neo4j referential integrity: {len(neo4j_issues)} issues found",
                details={"issues": neo4j_issues, "dangling_relationships": dangling_count},
                suggestions=neo4j_suggestions,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            results["neo4j"] = ValidationResult(
                success=False,
                message=f"Neo4j referential integrity check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check Neo4j connectivity"],
                timestamp=datetime.now(timezone.utc)
            )
        
        return results
    
    async def generate_data_consistency_report(self) -> DataConsistencyReport:
        """Generate comprehensive data consistency report."""
        user_result = await self.validate_user_data_consistency()
        document_result = await self.validate_document_data_consistency()
        conversation_result = await self.validate_conversation_data_consistency()
        vector_result = await self.validate_vector_data_consistency()
        
        # Calculate overall status
        all_results = [user_result, document_result, conversation_result, vector_result]
        failed_count = sum(1 for result in all_results if not result.success)
        total_issues = sum(len(result.suggestions) for result in all_results)
        
        if failed_count == 0:
            overall_status = "healthy"
        elif failed_count <= 2:
            overall_status = "warning"
        else:
            overall_status = "critical"
        
        return DataConsistencyReport(
            user_consistency=user_result,
            document_consistency=document_result,
            conversation_consistency=conversation_result,
            vector_consistency=vector_result,
            overall_status=overall_status,
            total_issues=total_issues
        )
    
    async def validate_data_quality(self) -> Dict[str, ValidationResult]:
        """Validate data quality across databases."""
        results = {}
        
        # PostgreSQL data quality
        try:
            pg_client = await self.factory.get_relational_client()
            
            quality_checks = [
                ("null_emails", "SELECT COUNT(*) as count FROM users WHERE email IS NULL OR email = ''"),
                ("null_document_titles", "SELECT COUNT(*) as count FROM documents WHERE title IS NULL OR title = ''"),
                ("future_timestamps", "SELECT COUNT(*) as count FROM documents WHERE created_at > NOW()"),
                ("invalid_email_format", "SELECT COUNT(*) as count FROM users WHERE email NOT LIKE '%@%'")
            ]
            
            pg_issues = []
            pg_details = {}
            
            for check_name, query in quality_checks:
                try:
                    result = await pg_client.execute_query(query)
                    count = result[0]["count"] if result else 0
                    pg_details[check_name] = count
                    
                    if count > 0:
                        pg_issues.append(f"{check_name}: {count} records")
                        
                except Exception as e:
                    pg_details[check_name] = f"Error: {e}"
            
            results["postgresql"] = ValidationResult(
                success=len(pg_issues) == 0,
                message=f"PostgreSQL data quality: {len(pg_issues)} issues found",
                details=pg_details,
                suggestions=[f"Fix {issue}" for issue in pg_issues],
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            results["postgresql"] = ValidationResult(
                success=False,
                message=f"PostgreSQL data quality check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check PostgreSQL connectivity"],
                timestamp=datetime.now(timezone.utc)
            )
        
        return results
    
    async def check_backup_integrity(self, backup_path: str) -> ValidationResult:
        """Check integrity of backup files."""
        try:
            backup_dir = Path(backup_path)
            
            if not backup_dir.exists():
                return ValidationResult(
                    success=False,
                    message="Backup directory does not exist",
                    details={"path": str(backup_dir)},
                    suggestions=["Create backup directory", "Run backup operation"],
                    timestamp=datetime.now(timezone.utc)
                )
            
            # Check for backup files
            backup_files = {
                "postgresql": list(backup_dir.glob("postgresql/*.sql")),
                "neo4j": list(backup_dir.glob("neo4j/*.cypher")),
                "milvus": list(backup_dir.glob("milvus/*.json")),
            }
            
            issues = []
            details = {}
            
            for db_type, files in backup_files.items():
                file_count = len(files)
                details[f"{db_type}_backup_count"] = file_count
                
                if file_count == 0:
                    issues.append(f"No {db_type} backup files found")
                else:
                    # Check file sizes (basic integrity check)
                    total_size = sum(f.stat().st_size for f in files if f.exists())
                    details[f"{db_type}_backup_size"] = total_size
                    
                    if total_size == 0:
                        issues.append(f"{db_type} backup files are empty")
            
            success = len(issues) == 0
            message = "Backup integrity check passed" if success else f"Found {len(issues)} backup issues"
            
            return ValidationResult(
                success=success,
                message=message,
                details=details,
                suggestions=[f"Fix {issue}" for issue in issues],
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            return ValidationResult(
                success=False,
                message=f"Backup integrity check failed: {e}",
                details={"error": str(e)},
                suggestions=["Check backup directory permissions"],
                timestamp=datetime.now(timezone.utc)
            )


# Convenience functions for use in other scripts

async def quick_connectivity_check(config: Any) -> bool:
    """Quick check if all databases are accessible."""
    validator = DataValidationUtils(config)
    await validator.initialize()
    
    try:
        results = await validator.validate_database_connectivity()
        return all(result.success for result in results.values())
    finally:
        await validator.cleanup()


async def validate_before_backup(config: Any) -> Dict[str, Any]:
    """Validate data before creating backup."""
    validator = DataValidationUtils(config)
    await validator.initialize()
    
    try:
        connectivity = await validator.validate_database_connectivity()
        consistency = await validator.generate_data_consistency_report()
        
        return {
            "connectivity": connectivity,
            "consistency": consistency,
            "ready_for_backup": all(r.success for r in connectivity.values()) and consistency.overall_status != "critical"
        }
    finally:
        await validator.cleanup()


async def validate_after_restore(config: Any) -> Dict[str, Any]:
    """Validate data after restore operation."""
    validator = DataValidationUtils(config)
    await validator.initialize()
    
    try:
        connectivity = await validator.validate_database_connectivity()
        consistency = await validator.generate_data_consistency_report()
        referential = await validator.validate_referential_integrity()
        
        return {
            "connectivity": connectivity,
            "consistency": consistency,
            "referential_integrity": referential,
            "restore_successful": (
                all(r.success for r in connectivity.values()) and
                consistency.overall_status != "critical" and
                all(r.success for r in referential.values())
            )
        }
    finally:
        await validator.cleanup()


if __name__ == "__main__":
    # Example usage
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    async def main():
        config = get_database_config()
        validator = DataValidationUtils(config)
        await validator.initialize()
        
        try:
            print("Running data validation checks...")
            
            # Test connectivity
            connectivity = await validator.validate_database_connectivity()
            print(f"Connectivity: {sum(1 for r in connectivity.values() if r.success)}/{len(connectivity)} services")
            
            # Test consistency
            consistency = await validator.generate_data_consistency_report()
            print(f"Consistency: {consistency.overall_status} ({consistency.total_issues} issues)")
            
        finally:
            await validator.cleanup()
    
    asyncio.run(main())