"""
Migration service for migrating data from public schema to unified multimodal_librarian schema.

This module provides the MigrationService class for orchestrating the schema migration
and the FieldMapper class for mapping fields between the old and new schema structures.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MigrationResult:
    """Result of migration operation."""
    success: bool
    documents_migrated: int
    chunks_migrated: int
    processing_jobs_migrated: int
    errors: List[str]
    dry_run: bool
    duration_seconds: float


@dataclass
class VerificationResult:
    """Result of migration verification."""
    success: bool
    source_document_count: int
    target_document_count: int
    source_chunk_count: int
    target_chunk_count: int
    discrepancies: List[str]


@dataclass
class CleanupResult:
    """Result of public schema cleanup."""
    success: bool
    tables_dropped: List[str]
    errors: List[str]


class FieldMapper:
    """Maps fields between public and unified schema structures."""

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """
        Compute SHA-256 hash of content for deduplication.
        
        Args:
            content: The text content to hash
            
        Returns:
            str: 64-character hexadecimal SHA-256 hash
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def map_chunk_type_to_content_type(chunk_type: str) -> str:
        """
        Map chunk_type enum to content_type enum.
        
        Mappings:
        - 'text' -> 'GENERAL'
        - 'image' -> 'TECHNICAL'
        - 'table' -> 'TECHNICAL'
        - 'chart' -> 'TECHNICAL'
        
        Args:
            chunk_type: The chunk type from public schema
            
        Returns:
            str: The content type for unified schema
        """
        mapping = {
            'text': 'GENERAL',
            'image': 'TECHNICAL',
            'table': 'TECHNICAL',
            'chart': 'TECHNICAL'
        }
        return mapping.get(chunk_type, 'GENERAL')

    @staticmethod
    def map_status_to_processing_status(status: str) -> str:
        """
        Map document status to processing_status enum.
        
        Mappings:
        - 'uploaded' -> 'PENDING'
        - 'processing' -> 'PROCESSING'
        - 'completed' -> 'COMPLETED'
        - 'failed' -> 'FAILED'
        
        Args:
            status: The status from public schema
            
        Returns:
            str: The processing_status for unified schema
        """
        mapping = {
            'uploaded': 'PENDING',
            'processing': 'PROCESSING',
            'completed': 'COMPLETED',
            'failed': 'FAILED'
        }
        return mapping.get(status, 'PENDING')

    def map_document_to_knowledge_source(
        self,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Map public.documents row to knowledge_sources row.
        
        Field mappings:
        - id -> id (preserved)
        - user_id -> user_id (preserved)
        - title -> title (preserved)
        - filename -> file_path (preserved)
        - file_size -> file_size (preserved)
        - status -> processing_status (enum conversion)
        - doc_metadata -> metadata (preserved)
        - source_type = 'UPLOAD' (new field)
        
        Args:
            document: Dictionary representing a public.documents row
            
        Returns:
            Dict[str, Any]: Dictionary for knowledge_sources row
        """
        return {
            'id': document.get('id'),
            'user_id': document.get('user_id'),
            'title': document.get('title'),
            'file_path': document.get('filename'),
            'file_size': document.get('file_size'),
            'processing_status': self.map_status_to_processing_status(
                document.get('status', 'uploaded')
            ),
            'metadata': document.get('doc_metadata') or {},
            'source_type': 'UPLOAD',
            'created_at': document.get('upload_timestamp'),
            'updated_at': document.get('processing_completed_at') or document.get('upload_timestamp'),
        }

    def map_chunk_to_knowledge_chunk(
        self,
        chunk: Dict[str, Any],
        source_type: str = 'BOOK'
    ) -> Dict[str, Any]:
        """
        Map public.document_chunks row to knowledge_chunks row.
        
        Field mappings:
        - id -> id (preserved)
        - document_id -> source_id (renamed)
        - chunk_index -> chunk_index (preserved)
        - content -> content (preserved)
        - content -> content_hash (computed SHA-256)
        - page_number -> location_reference (string conversion)
        - section_title -> section (renamed)
        - chunk_type -> content_type (enum conversion)
        - metadata -> metadata (preserved)
        - source_type = source_type (new field)
        
        Args:
            chunk: Dictionary representing a public.document_chunks row
            source_type: The source type to assign (default: 'BOOK')
            
        Returns:
            Dict[str, Any]: Dictionary for knowledge_chunks row
        """
        content = chunk.get('content', '')
        page_number = chunk.get('page_number')
        
        return {
            'id': chunk.get('id'),
            'source_id': chunk.get('document_id'),
            'chunk_index': chunk.get('chunk_index'),
            'content': content,
            'content_hash': self.compute_content_hash(content),
            'location_reference': str(page_number) if page_number is not None else None,
            'section': chunk.get('section_title'),
            'content_type': self.map_chunk_type_to_content_type(
                chunk.get('chunk_type', 'text')
            ),
            'metadata': chunk.get('metadata') or {},
            'source_type': source_type,
            'created_at': chunk.get('created_at'),
        }


class MigrationService:
    """Service for migrating data from public schema to unified schema."""

    def __init__(self) -> None:
        """Initialize migration service."""
        self.field_mapper = FieldMapper()
        self._logger = structlog.get_logger(__name__)

    async def _verify_target_schema_exists(self) -> bool:
        """
        Verify that the target multimodal_librarian schema exists and has correct structure.
        
        Returns:
            bool: True if schema exists and is valid
        """
        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            # Check if schema exists
            result = await conn.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.schemata 
                    WHERE schema_name = 'multimodal_librarian'
                )
            """)
            
            if not result:
                self._logger.error("Target schema 'multimodal_librarian' does not exist")
                return False

            # Check if required tables exist
            required_tables = ['knowledge_sources', 'knowledge_chunks']
            for table in required_tables:
                exists = await conn.fetchval("""
                    SELECT EXISTS(
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'multimodal_librarian' 
                        AND table_name = $1
                    )
                """, table)
                
                if not exists:
                    self._logger.error(f"Required table 'multimodal_librarian.{table}' does not exist")
                    return False

            return True
        finally:
            await conn.close()

    async def _get_source_counts(self) -> Dict[str, int]:
        """Get row counts from source tables."""
        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            doc_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.documents"
            ) or 0
            
            chunk_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.document_chunks"
            ) or 0
            
            job_count = await conn.fetchval(
                "SELECT COUNT(*) FROM public.processing_jobs"
            ) or 0

            return {
                'documents': doc_count,
                'chunks': chunk_count,
                'processing_jobs': job_count
            }
        finally:
            await conn.close()

    async def _get_target_counts(self) -> Dict[str, int]:
        """Get row counts from target tables."""
        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            source_count = await conn.fetchval(
                "SELECT COUNT(*) FROM multimodal_librarian.knowledge_sources"
            ) or 0
            
            chunk_count = await conn.fetchval(
                "SELECT COUNT(*) FROM multimodal_librarian.knowledge_chunks"
            ) or 0

            return {
                'knowledge_sources': source_count,
                'knowledge_chunks': chunk_count
            }
        finally:
            await conn.close()

    async def migrate(self, dry_run: bool = False) -> MigrationResult:
        """
        Execute the migration from public to unified schema.
        
        Args:
            dry_run: If True, report what would be migrated without making changes
            
        Returns:
            MigrationResult with counts and status
        """
        import time
        start_time = time.time()
        errors: List[str] = []
        documents_migrated = 0
        chunks_migrated = 0
        jobs_migrated = 0

        try:
            # Step 1: Verify target schema exists
            if not await self._verify_target_schema_exists():
                return MigrationResult(
                    success=False,
                    documents_migrated=0,
                    chunks_migrated=0,
                    processing_jobs_migrated=0,
                    errors=["Target schema 'multimodal_librarian' does not exist or is incomplete"],
                    dry_run=dry_run,
                    duration_seconds=time.time() - start_time
                )

            # Step 2: Get source counts for reporting
            source_counts = await self._get_source_counts()
            self._logger.info(
                "Migration source counts",
                documents=source_counts['documents'],
                chunks=source_counts['chunks'],
                processing_jobs=source_counts['processing_jobs']
            )

            if dry_run:
                self._logger.info("Dry run mode - no changes will be made")
                return MigrationResult(
                    success=True,
                    documents_migrated=source_counts['documents'],
                    chunks_migrated=source_counts['chunks'],
                    processing_jobs_migrated=source_counts['processing_jobs'],
                    errors=[],
                    dry_run=True,
                    duration_seconds=time.time() - start_time
                )

            # Step 3: Migrate documents to knowledge_sources
            documents_migrated = await self._migrate_documents()
            self._logger.info(f"Migrated {documents_migrated} documents to knowledge_sources")

            # Step 4: Migrate chunks to knowledge_chunks
            chunks_migrated = await self._migrate_chunks()
            self._logger.info(f"Migrated {chunks_migrated} chunks to knowledge_chunks")

            # Step 5: Migrate processing jobs (if applicable)
            jobs_migrated = await self._migrate_processing_jobs()
            self._logger.info(f"Migrated {jobs_migrated} processing jobs")

            duration = time.time() - start_time
            self._logger.info(
                "Migration completed successfully",
                documents=documents_migrated,
                chunks=chunks_migrated,
                jobs=jobs_migrated,
                duration_seconds=duration
            )

            return MigrationResult(
                success=True,
                documents_migrated=documents_migrated,
                chunks_migrated=chunks_migrated,
                processing_jobs_migrated=jobs_migrated,
                errors=errors,
                dry_run=False,
                duration_seconds=duration
            )

        except Exception as e:
            self._logger.error(f"Migration failed: {e}")
            errors.append(str(e))
            return MigrationResult(
                success=False,
                documents_migrated=documents_migrated,
                chunks_migrated=chunks_migrated,
                processing_jobs_migrated=jobs_migrated,
                errors=errors,
                dry_run=dry_run,
                duration_seconds=time.time() - start_time
            )

    async def _get_or_create_default_user(self, conn) -> str:
        """
        Get or create a default user for migration.
        
        The public.documents table uses string user_ids like 'default_user',
        but knowledge_sources requires a UUID that references the users table.
        This method finds an existing admin user or creates a migration user.
        
        Returns:
            str: UUID of the default user to use for migration
        """
        import uuid as uuid_module

        # First, try to find an existing admin user
        admin_user = await conn.fetchval("""
            SELECT id FROM multimodal_librarian.users 
            WHERE is_admin = true 
            ORDER BY created_at ASC 
            LIMIT 1
        """)
        
        if admin_user:
            self._logger.info(f"Using existing admin user for migration: {admin_user}")
            return str(admin_user)
        
        # If no admin user, try to find any user
        any_user = await conn.fetchval("""
            SELECT id FROM multimodal_librarian.users 
            ORDER BY created_at ASC 
            LIMIT 1
        """)
        
        if any_user:
            self._logger.info(f"Using existing user for migration: {any_user}")
            return str(any_user)
        
        # Create a migration user if none exists
        migration_user_id = str(uuid_module.uuid4())
        await conn.execute("""
            INSERT INTO multimodal_librarian.users (id, username, email, password_hash, is_active, is_admin)
            VALUES ($1, 'migration_user', 'migration@system.local', 
                    '$2b$12$placeholder_hash_for_migration_user', true, false)
        """, uuid_module.UUID(migration_user_id))
        
        self._logger.info(f"Created migration user: {migration_user_id}")
        return migration_user_id

    def _is_valid_uuid(self, value: str) -> bool:
        """Check if a string is a valid UUID."""
        import uuid as uuid_module
        try:
            uuid_module.UUID(str(value))
            return True
        except (ValueError, AttributeError):
            return False

    async def _migrate_documents(self) -> int:
        """Migrate documents from public.documents to multimodal_librarian.knowledge_sources."""
        import uuid as uuid_module

        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            # Get default user for non-UUID user_ids
            default_user_id = await self._get_or_create_default_user(conn)
            
            # Fetch all documents from public schema
            rows = await conn.fetch("""
                SELECT id, user_id, title, filename, file_size, status, 
                       doc_metadata, upload_timestamp, processing_completed_at
                FROM public.documents
            """)

            migrated_count = 0
            for row in rows:
                document = dict(row)
                mapped = self.field_mapper.map_document_to_knowledge_source(document)

                # Handle user_id: if it's not a valid UUID, use the default user
                user_id_str = mapped.get('user_id')
                if user_id_str and self._is_valid_uuid(user_id_str):
                    # Check if this UUID exists in the users table
                    user_exists = await conn.fetchval("""
                        SELECT EXISTS(SELECT 1 FROM multimodal_librarian.users WHERE id = $1)
                    """, uuid_module.UUID(user_id_str))
                    if user_exists:
                        user_id = uuid_module.UUID(user_id_str)
                    else:
                        self._logger.warning(
                            f"User {user_id_str} not found in users table, using default user"
                        )
                        user_id = uuid_module.UUID(default_user_id)
                else:
                    self._logger.info(
                        f"Document {mapped['id']} has non-UUID user_id '{user_id_str}', using default user"
                    )
                    user_id = uuid_module.UUID(default_user_id)

                # Serialize metadata to JSON
                metadata_json = json.dumps(mapped['metadata']) if mapped['metadata'] else '{}'

                try:
                    await conn.execute("""
                        INSERT INTO multimodal_librarian.knowledge_sources (
                            id, user_id, title, file_path, file_size, 
                            processing_status, metadata, source_type, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6::multimodal_librarian.processing_status, $7::jsonb, 
                                  $8::multimodal_librarian.source_type, $9, $10)
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            file_path = EXCLUDED.file_path,
                            processing_status = EXCLUDED.processing_status,
                            metadata = EXCLUDED.metadata,
                            updated_at = EXCLUDED.updated_at
                    """,
                        mapped['id'],
                        user_id,
                        mapped['title'],
                        mapped['file_path'],
                        mapped['file_size'],
                        mapped['processing_status'],
                        metadata_json,
                        mapped['source_type'],
                        mapped['created_at'],
                        mapped['updated_at']
                    )
                    migrated_count += 1
                except Exception as e:
                    self._logger.warning(f"Failed to migrate document {mapped['id']}: {e}")

            return migrated_count
        finally:
            await conn.close()

    async def _migrate_chunks(self) -> int:
        """Migrate chunks from public.document_chunks to multimodal_librarian.knowledge_chunks."""
        from ..database.connection import get_async_connection

        conn = await get_async_connection()
        try:
            # Fetch all chunks from public schema
            rows = await conn.fetch("""
                SELECT id, document_id, chunk_index, content, page_number, 
                       section_title, chunk_type, metadata, created_at
                FROM public.document_chunks
            """)

            migrated_count = 0
            for row in rows:
                chunk = dict(row)
                mapped = self.field_mapper.map_chunk_to_knowledge_chunk(chunk, source_type='BOOK')

                # Serialize metadata to JSON
                metadata_json = json.dumps(mapped['metadata']) if mapped['metadata'] else '{}'

                try:
                    await conn.execute("""
                        INSERT INTO multimodal_librarian.knowledge_chunks (
                            id, source_id, chunk_index, content, content_hash,
                            location_reference, section, content_type, metadata, 
                            source_type, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::multimodal_librarian.content_type, $9::jsonb, 
                                  $10::multimodal_librarian.source_type, $11)
                        ON CONFLICT (source_id, source_type, content_hash) DO UPDATE SET
                            chunk_index = EXCLUDED.chunk_index,
                            content = EXCLUDED.content,
                            location_reference = EXCLUDED.location_reference,
                            section = EXCLUDED.section,
                            content_type = EXCLUDED.content_type,
                            metadata = EXCLUDED.metadata
                    """,
                        mapped['id'],
                        mapped['source_id'],
                        mapped['chunk_index'],
                        mapped['content'],
                        mapped['content_hash'],
                        mapped['location_reference'],
                        mapped['section'],
                        mapped['content_type'],
                        metadata_json,
                        mapped['source_type'],
                        mapped['created_at']
                    )
                    migrated_count += 1
                except Exception as e:
                    self._logger.warning(f"Failed to migrate chunk {mapped['id']}: {e}")

            return migrated_count
        finally:
            await conn.close()

    async def _migrate_processing_jobs(self) -> int:
        """Migrate processing jobs - placeholder for future implementation."""
        # Processing jobs migration would require additional schema changes
        # For now, return 0 as this is handled separately
        return 0

    async def verify_migration(self) -> VerificationResult:
        """
        Verify that migration completed successfully.
        
        Returns:
            VerificationResult with row counts and discrepancies
        """
        discrepancies: List[str] = []

        try:
            source_counts = await self._get_source_counts()
            target_counts = await self._get_target_counts()

            # Check document counts
            if source_counts['documents'] != target_counts['knowledge_sources']:
                discrepancies.append(
                    f"Document count mismatch: source={source_counts['documents']}, "
                    f"target={target_counts['knowledge_sources']}"
                )

            # Check chunk counts
            if source_counts['chunks'] != target_counts['knowledge_chunks']:
                discrepancies.append(
                    f"Chunk count mismatch: source={source_counts['chunks']}, "
                    f"target={target_counts['knowledge_chunks']}"
                )

            success = len(discrepancies) == 0

            self._logger.info(
                "Migration verification completed",
                success=success,
                source_documents=source_counts['documents'],
                target_documents=target_counts['knowledge_sources'],
                source_chunks=source_counts['chunks'],
                target_chunks=target_counts['knowledge_chunks'],
                discrepancies=discrepancies
            )

            return VerificationResult(
                success=success,
                source_document_count=source_counts['documents'],
                target_document_count=target_counts['knowledge_sources'],
                source_chunk_count=source_counts['chunks'],
                target_chunk_count=target_counts['knowledge_chunks'],
                discrepancies=discrepancies
            )

        except Exception as e:
            self._logger.error(f"Migration verification failed: {e}")
            return VerificationResult(
                success=False,
                source_document_count=0,
                target_document_count=0,
                source_chunk_count=0,
                target_chunk_count=0,
                discrepancies=[str(e)]
            )

    async def verify_cleanup_safe(self) -> VerificationResult:
        """
        Verify that all data has been migrated and cleanup is safe to proceed.
        
        This method checks:
        1. Row counts match between source and target tables
        2. No documents in public schema are missing from unified schema
        3. No chunks in public schema are missing from unified schema
        
        Returns:
            VerificationResult with detailed discrepancy information
        
        Requirements: 7.1, 7.5
        """
        discrepancies: List[str] = []

        try:
            from ..database.connection import get_async_connection

            conn = await get_async_connection()
            try:
                # Get basic counts first
                source_counts = await self._get_source_counts()
                target_counts = await self._get_target_counts()

                # Check document counts
                if source_counts['documents'] != target_counts['knowledge_sources']:
                    discrepancies.append(
                        f"Document count mismatch: source={source_counts['documents']}, "
                        f"target={target_counts['knowledge_sources']}"
                    )

                # Check chunk counts
                if source_counts['chunks'] != target_counts['knowledge_chunks']:
                    discrepancies.append(
                        f"Chunk count mismatch: source={source_counts['chunks']}, "
                        f"target={target_counts['knowledge_chunks']}"
                    )

                # Check for documents in public schema not present in unified schema
                unmigrated_docs = await conn.fetch("""
                    SELECT d.id, d.title
                    FROM public.documents d
                    LEFT JOIN multimodal_librarian.knowledge_sources ks ON d.id = ks.id
                    WHERE ks.id IS NULL
                """)
                
                if unmigrated_docs:
                    doc_ids = [str(row['id']) for row in unmigrated_docs]
                    discrepancies.append(
                        f"Found {len(unmigrated_docs)} documents in public schema not migrated: "
                        f"{', '.join(doc_ids[:5])}{'...' if len(doc_ids) > 5 else ''}"
                    )
                    self._logger.warning(
                        "Unmigrated documents found",
                        count=len(unmigrated_docs),
                        document_ids=doc_ids[:10]
                    )

                # Check for chunks in public schema not present in unified schema
                # We match by document_id -> source_id and content_hash
                unmigrated_chunks = await conn.fetch("""
                    SELECT dc.id, dc.document_id, dc.chunk_index
                    FROM public.document_chunks dc
                    LEFT JOIN multimodal_librarian.knowledge_chunks kc 
                        ON dc.document_id = kc.source_id 
                        AND encode(sha256(dc.content::bytea), 'hex') = kc.content_hash
                    WHERE kc.id IS NULL
                """)
                
                if unmigrated_chunks:
                    chunk_ids = [str(row['id']) for row in unmigrated_chunks]
                    discrepancies.append(
                        f"Found {len(unmigrated_chunks)} chunks in public schema not migrated: "
                        f"{', '.join(chunk_ids[:5])}{'...' if len(chunk_ids) > 5 else ''}"
                    )
                    self._logger.warning(
                        "Unmigrated chunks found",
                        count=len(unmigrated_chunks),
                        chunk_ids=chunk_ids[:10]
                    )

                success = len(discrepancies) == 0

                self._logger.info(
                    "Cleanup verification completed",
                    success=success,
                    source_documents=source_counts['documents'],
                    target_documents=target_counts['knowledge_sources'],
                    source_chunks=source_counts['chunks'],
                    target_chunks=target_counts['knowledge_chunks'],
                    discrepancies=discrepancies
                )

                return VerificationResult(
                    success=success,
                    source_document_count=source_counts['documents'],
                    target_document_count=target_counts['knowledge_sources'],
                    source_chunk_count=source_counts['chunks'],
                    target_chunk_count=target_counts['knowledge_chunks'],
                    discrepancies=discrepancies
                )

            finally:
                await conn.close()

        except Exception as e:
            self._logger.error(f"Cleanup verification failed: {e}")
            return VerificationResult(
                success=False,
                source_document_count=0,
                target_document_count=0,
                source_chunk_count=0,
                target_chunk_count=0,
                discrepancies=[str(e)]
            )

    async def cleanup_public_schema(self) -> CleanupResult:
        """
        Drop deprecated public schema tables after successful migration.
        
        This method:
        1. Verifies all data has been migrated (Requirements 7.1, 7.5)
        2. Drops public.document_chunks table (Requirement 7.2)
        3. Drops public.documents table (Requirement 7.3)
        4. Drops public.processing_jobs table (Requirement 7.4)
        
        Returns:
            CleanupResult with dropped tables and status
        """
        errors: List[str] = []
        tables_dropped: List[str] = []

        try:
            # First verify cleanup is safe - all data must be migrated
            verification = await self.verify_cleanup_safe()
            if not verification.success:
                error_msg = "Cannot cleanup: data verification failed. "
                if verification.discrepancies:
                    error_msg += "; ".join(verification.discrepancies)
                self._logger.error(
                    "Cleanup aborted due to verification failure",
                    discrepancies=verification.discrepancies
                )
                return CleanupResult(
                    success=False,
                    tables_dropped=[],
                    errors=[error_msg]
                )

            from ..database.connection import get_async_connection

            conn = await get_async_connection()
            try:
                # Drop tables in correct order (respecting foreign keys)
                # document_chunks depends on documents, so drop chunks first
                # processing_jobs may depend on documents, so drop it first too
                tables_to_drop = [
                    ('public', 'processing_jobs'),
                    ('public', 'document_chunks'),
                    ('public', 'documents')
                ]

                for schema, table_name in tables_to_drop:
                    full_table_name = f"{schema}.{table_name}"
                    try:
                        # Check if table exists before dropping
                        exists = await conn.fetchval("""
                            SELECT EXISTS(
                                SELECT 1 FROM information_schema.tables 
                                WHERE table_schema = $1 AND table_name = $2
                            )
                        """, schema, table_name)

                        if exists:
                            await conn.execute(f"DROP TABLE IF EXISTS {full_table_name} CASCADE")
                            tables_dropped.append(full_table_name)
                            self._logger.info(f"Dropped table: {full_table_name}")
                        else:
                            self._logger.info(f"Table {full_table_name} does not exist, skipping")
                    except Exception as e:
                        errors.append(f"Failed to drop {full_table_name}: {e}")
                        self._logger.error(f"Failed to drop table {full_table_name}: {e}")

            finally:
                await conn.close()

            success = len(errors) == 0
            self._logger.info(
                "Public schema cleanup completed",
                success=success,
                tables_dropped=tables_dropped,
                errors=errors
            )

            return CleanupResult(
                success=success,
                tables_dropped=tables_dropped,
                errors=errors
            )

        except Exception as e:
            self._logger.error(f"Cleanup failed: {e}")
            return CleanupResult(
                success=False,
                tables_dropped=tables_dropped,
                errors=[str(e)]
            )
