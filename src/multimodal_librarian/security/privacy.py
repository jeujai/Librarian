"""
Privacy protection and data deletion service.

This module provides comprehensive data privacy protection including
complete data deletion, conversation privacy, and compliance with
data protection regulations.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import get_settings
from ..database.connection import get_database_session
from ..database.models import (
    CitationDB,
    ConversationDB,
    InteractionFeedbackDB,
    KnowledgeChunkDB,
    KnowledgeSource,
    MediaElementDB,
    MessageDB,
)
from ..logging_config import get_logger
from .audit import get_audit_logger
from .encryption import get_encryption_service

logger = get_logger(__name__)


class PrivacyService:
    """Service for data privacy protection and complete data deletion."""
    
    def __init__(self):
        """Initialize privacy service."""
        self.settings = get_settings()
        self.audit_logger = get_audit_logger()
        self.encryption_service = get_encryption_service()
    
    async def delete_book_completely(
        self,
        book_id: str,
        user_id: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Completely delete a book and all associated data."""
        try:
            deletion_report = {
                "book_id": book_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "deleted_components": [],
                "errors": []
            }
            
            # Log the deletion request
            self.audit_logger.log_privacy_operation(
                operation="purge",
                user_id=user_id,
                resource_type="book",
                resource_id=book_id,
                details={"operation": "complete_book_deletion"}
            )
            
            with get_database_session() as session:
                # Find the book
                book = session.query(KnowledgeSource).filter(
                    KnowledgeSource.id == book_id,
                    KnowledgeSource.source_type == 'book'
                ).first()
                
                if not book:
                    error_msg = f"Book not found: {book_id}"
                    deletion_report["errors"].append(error_msg)
                    logger.warning(error_msg)
                    return deletion_report
                
                # 1. Delete from vector database
                try:
                    await self._delete_from_vector_store(book_id)
                    deletion_report["deleted_components"].append("vector_embeddings")
                except Exception as e:
                    error_msg = f"Failed to delete vector embeddings: {e}"
                    deletion_report["errors"].append(error_msg)
                    logger.error(error_msg)
                
                # 2. Delete media files
                try:
                    media_elements = session.query(MediaElementDB).join(
                        KnowledgeChunkDB
                    ).filter(KnowledgeChunkDB.source_id == book_id).all()
                    
                    for media in media_elements:
                        if media.file_path and os.path.exists(media.file_path):
                            os.remove(media.file_path)
                    
                    deletion_report["deleted_components"].append(f"media_files_{len(media_elements)}")
                except Exception as e:
                    error_msg = f"Failed to delete media files: {e}"
                    deletion_report["errors"].append(error_msg)
                    logger.error(error_msg)
                
                # 3. Delete original book file
                try:
                    if book.file_path and os.path.exists(book.file_path):
                        os.remove(book.file_path)
                        deletion_report["deleted_components"].append("original_file")
                except Exception as e:
                    error_msg = f"Failed to delete original file: {e}"
                    deletion_report["errors"].append(error_msg)
                    logger.error(error_msg)
                
                # 4. Delete database records (cascading deletes will handle related records)
                try:
                    # Delete citations
                    citations_deleted = session.query(CitationDB).filter(
                        CitationDB.chunk_id.in_(
                            session.query(KnowledgeChunkDB.chunk_id).filter(
                                KnowledgeChunkDB.source_id == book_id
                            )
                        )
                    ).delete(synchronize_session=False)
                    
                    # Delete interaction feedback
                    feedback_deleted = session.query(InteractionFeedbackDB).filter(
                        InteractionFeedbackDB.chunk_id.in_(
                            session.query(KnowledgeChunkDB.chunk_id).filter(
                                KnowledgeChunkDB.source_id == book_id
                            )
                        )
                    ).delete(synchronize_session=False)
                    
                    # Delete the book (cascading will delete chunks and media)
                    session.delete(book)
                    session.commit()
                    
                    deletion_report["deleted_components"].extend([
                        f"citations_{citations_deleted}",
                        f"feedback_records_{feedback_deleted}",
                        "database_records"
                    ])
                    
                except Exception as e:
                    session.rollback()
                    error_msg = f"Failed to delete database records: {e}"
                    deletion_report["errors"].append(error_msg)
                    logger.error(error_msg)
                
                # 5. Delete from knowledge graph
                try:
                    await self._delete_from_knowledge_graph(book_id)
                    deletion_report["deleted_components"].append("knowledge_graph")
                except Exception as e:
                    error_msg = f"Failed to delete from knowledge graph: {e}"
                    deletion_report["errors"].append(error_msg)
                    logger.error(error_msg)
            
            # Log completion
            result = "success" if not deletion_report["errors"] else "partial_failure"
            self.audit_logger.log_privacy_operation(
                operation="purge",
                user_id=user_id,
                resource_type="book",
                resource_id=book_id,
                result=result,
                details=deletion_report
            )
            
            logger.info(f"Book deletion completed: {book_id}, result: {result}")
            return deletion_report
            
        except Exception as e:
            error_msg = f"Failed to delete book {book_id}: {e}"
            logger.error(error_msg)
            
            self.audit_logger.log_privacy_operation(
                operation="purge",
                user_id=user_id,
                resource_type="book",
                resource_id=book_id,
                result="failure",
                details={"error": error_msg}
            )
            
            return {
                "book_id": book_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "deleted_components": [],
                "errors": [error_msg]
            }
    
    async def delete_conversation_completely(
        self,
        conversation_id: str,
        user_id: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Completely delete a conversation and all associated data."""
        try:
            deletion_report = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "deleted_components": [],
                "errors": []
            }
            
            # Log the deletion request
            self.audit_logger.log_privacy_operation(
                operation="purge",
                user_id=user_id,
                resource_type="conversation",
                resource_id=conversation_id,
                details={"operation": "complete_conversation_deletion"}
            )
            
            with get_database_session() as session:
                # Find the conversation
                conversation = session.query(ConversationDB).filter(
                    ConversationDB.thread_id == conversation_id
                ).first()
                
                if not conversation:
                    error_msg = f"Conversation not found: {conversation_id}"
                    deletion_report["errors"].append(error_msg)
                    logger.warning(error_msg)
                    return deletion_report
                
                # Get the associated knowledge source
                knowledge_source = session.query(KnowledgeSource).filter(
                    KnowledgeSource.id == conversation.source_id
                ).first()
                
                if knowledge_source:
                    # 1. Delete from vector database
                    try:
                        await self._delete_from_vector_store(str(knowledge_source.id))
                        deletion_report["deleted_components"].append("vector_embeddings")
                    except Exception as e:
                        error_msg = f"Failed to delete vector embeddings: {e}"
                        deletion_report["errors"].append(error_msg)
                        logger.error(error_msg)
                    
                    # 2. Delete from knowledge graph
                    try:
                        await self._delete_from_knowledge_graph(str(knowledge_source.id))
                        deletion_report["deleted_components"].append("knowledge_graph")
                    except Exception as e:
                        error_msg = f"Failed to delete from knowledge graph: {e}"
                        deletion_report["errors"].append(error_msg)
                        logger.error(error_msg)
                
                # 3. Delete database records
                try:
                    # Delete citations for conversation chunks
                    if knowledge_source:
                        citations_deleted = session.query(CitationDB).filter(
                            CitationDB.chunk_id.in_(
                                session.query(KnowledgeChunkDB.chunk_id).filter(
                                    KnowledgeChunkDB.source_id == knowledge_source.id
                                )
                            )
                        ).delete(synchronize_session=False)
                        
                        # Delete interaction feedback
                        feedback_deleted = session.query(InteractionFeedbackDB).filter(
                            InteractionFeedbackDB.chunk_id.in_(
                                session.query(KnowledgeChunkDB.chunk_id).filter(
                                    KnowledgeChunkDB.source_id == knowledge_source.id
                                )
                            )
                        ).delete(synchronize_session=False)
                        
                        deletion_report["deleted_components"].extend([
                            f"citations_{citations_deleted}",
                            f"feedback_records_{feedback_deleted}"
                        ])
                    
                    # Delete the conversation (cascading will delete messages)
                    session.delete(conversation)
                    
                    # Delete the knowledge source if it exists
                    if knowledge_source:
                        session.delete(knowledge_source)
                    
                    session.commit()
                    deletion_report["deleted_components"].append("database_records")
                    
                except Exception as e:
                    session.rollback()
                    error_msg = f"Failed to delete database records: {e}"
                    deletion_report["errors"].append(error_msg)
                    logger.error(error_msg)
            
            # Log completion
            result = "success" if not deletion_report["errors"] else "partial_failure"
            self.audit_logger.log_privacy_operation(
                operation="purge",
                user_id=user_id,
                resource_type="conversation",
                resource_id=conversation_id,
                result=result,
                details=deletion_report
            )
            
            logger.info(f"Conversation deletion completed: {conversation_id}, result: {result}")
            return deletion_report
            
        except Exception as e:
            error_msg = f"Failed to delete conversation {conversation_id}: {e}"
            logger.error(error_msg)
            
            self.audit_logger.log_privacy_operation(
                operation="purge",
                user_id=user_id,
                resource_type="conversation",
                resource_id=conversation_id,
                result="failure",
                details={"error": error_msg}
            )
            
            return {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow(),
                "deleted_components": [],
                "errors": [error_msg]
            }
    
    async def _delete_from_vector_store(self, source_id: str):
        """Delete embeddings from vector store."""
        try:
            logger.info(f"Deleting vector embeddings for source: {source_id}")
            
            # Import and use the vector store component
            from ..components.vector_store.vector_store import VectorStore
            
            vector_store = VectorStore()
            vector_store.connect()
            
            try:
                deleted_count = vector_store.delete_chunks_by_source(source_id)
                logger.info(f"Deleted {deleted_count} embeddings from vector store for source: {source_id}")
            finally:
                vector_store.disconnect()
            
        except Exception as e:
            logger.error(f"Failed to delete from vector store: {e}")
            raise
    

    async def _delete_from_knowledge_graph(self, source_id: str):
        """Delete chunks, EXTRACTED_FROM relationships, and orphaned concepts from knowledge graph."""
        try:
            logger.info(f"Deleting knowledge graph data for source: {source_id}")

            from ..services.knowledge_graph_service import KnowledgeGraphService

            kg_service = KnowledgeGraphService()

            try:
                # Step 0: Delete RELATED_DOCS edges involving this document
                result_rd = kg_service.execute_cypher(
                    """
                    MATCH ()-[r:RELATED_DOCS]->()
                    WHERE r.source_doc_id = $source_id
                       OR r.target_doc_id = $source_id
                    DELETE r
                    RETURN count(r) AS deleted_rd
                    """,
                    {"source_id": source_id}
                )
                deleted_rd = result_rd[0].get("deleted_rd", 0) if result_rd else 0

                # Step 1: Delete EXTRACTED_FROM relationships to this source's Chunk nodes
                result_rels = kg_service.execute_cypher(
                    """
                    MATCH (ch:Chunk {source_id: $source_id})<-[r:EXTRACTED_FROM]-(c:Concept)
                    DELETE r
                    RETURN count(r) AS deleted_rels
                    """,
                    {"source_id": source_id}
                )
                deleted_rels = result_rels[0].get("deleted_rels", 0) if result_rels else 0

                # Step 2: Delete Chunk nodes for this source_id
                result_chunks = kg_service.execute_cypher(
                    """
                    MATCH (ch:Chunk {source_id: $source_id})
                    DELETE ch
                    RETURN count(ch) AS deleted_chunks
                    """,
                    {"source_id": source_id}
                )
                deleted_chunks = result_chunks[0].get("deleted_chunks", 0) if result_chunks else 0

                # Step 3: Delete orphaned Concepts (no remaining EXTRACTED_FROM and no SAME_AS)
                result_concepts = kg_service.execute_cypher(
                    """
                    MATCH (c:Concept)
                    WHERE NOT EXISTS { MATCH (c)-[:EXTRACTED_FROM]->() }
                      AND NOT EXISTS { MATCH (c)<-[:SAME_AS]-() }
                    DETACH DELETE c
                    RETURN count(c) AS deleted_concepts
                    """,
                    {}
                )
                deleted_concepts = result_concepts[0].get("deleted_concepts", 0) if result_concepts else 0

                logger.info(
                    f"Knowledge graph cleanup for source {source_id}: "
                    f"deleted {deleted_rd} RELATED_DOCS, "
                    f"{deleted_rels} EXTRACTED_FROM rels, "
                    f"{deleted_chunks} Chunk nodes, "
                    f"{deleted_concepts} orphaned Concepts"
                )

            except Exception as e:
                logger.warning(f"Knowledge graph deletion partially completed: {e}")

        except Exception as e:
            logger.error(f"Failed to delete from knowledge graph: {e}")
            raise

    def sanitize_conversation_content(
        self,
        content: str,
        sensitive_patterns: Optional[List[str]] = None
    ) -> str:
        """Sanitize conversation content to remove sensitive information."""
        try:
            import re

            # Default sensitive patterns
            if sensitive_patterns is None:
                sensitive_patterns = [
                    r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
                    r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',  # Credit card
                    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
                    r'\b\d{3}[- ]?\d{3}[- ]?\d{4}\b',  # Phone number
                ]
            
            sanitized_content = content
            
            for pattern in sensitive_patterns:
                sanitized_content = re.sub(pattern, '[REDACTED]', sanitized_content)
            
            logger.debug("Conversation content sanitized")
            return sanitized_content
            
        except Exception as e:
            logger.error(f"Failed to sanitize conversation content: {e}")
            return content  # Return original if sanitization fails
    
    def anonymize_user_data(
        self,
        user_id: str,
        admin_user_id: str
    ) -> Dict[str, Any]:
        """Anonymize user data while preserving system functionality.
        
        This implements GDPR-compliant anonymization by:
        1. Replacing user_id with anonymous_id in all records
        2. Removing or hashing personally identifiable information
        3. Preserving data relationships for system functionality
        """
        try:
            anonymization_report = {
                "user_id": user_id,
                "admin_user_id": admin_user_id,
                "timestamp": datetime.utcnow(),
                "anonymized_components": [],
                "errors": []
            }
            
            # Log the anonymization request
            self.audit_logger.log_privacy_operation(
                operation="anonymize",
                user_id=admin_user_id,
                resource_type="user_data",
                resource_id=user_id,
                details={"operation": "user_data_anonymization"}
            )
            
            # Generate anonymous identifier
            anonymous_id = f"anon_{self.encryption_service.generate_secure_token(8)}"
            
            with get_database_session() as session:
                # 1. Anonymize conversations - replace user_id with anonymous_id
                try:
                    conversations_updated = session.query(ConversationDB).filter(
                        ConversationDB.user_id == user_id
                    ).update(
                        {ConversationDB.user_id: anonymous_id},
                        synchronize_session=False
                    )
                    anonymization_report["anonymized_components"].append(
                        f"conversations_{conversations_updated}"
                    )
                except Exception as e:
                    anonymization_report["errors"].append(f"Failed to anonymize conversations: {e}")
                    logger.error(f"Failed to anonymize conversations: {e}")
                
                # 2. Anonymize knowledge sources - replace user references
                try:
                    sources_updated = session.query(KnowledgeSource).filter(
                        KnowledgeSource.uploaded_by == user_id
                    ).update(
                        {KnowledgeSource.uploaded_by: anonymous_id},
                        synchronize_session=False
                    )
                    anonymization_report["anonymized_components"].append(
                        f"knowledge_sources_{sources_updated}"
                    )
                except Exception as e:
                    anonymization_report["errors"].append(f"Failed to anonymize knowledge sources: {e}")
                    logger.error(f"Failed to anonymize knowledge sources: {e}")
                
                # 3. Anonymize interaction feedback
                try:
                    feedback_updated = session.query(InteractionFeedbackDB).filter(
                        InteractionFeedbackDB.user_id == user_id
                    ).update(
                        {InteractionFeedbackDB.user_id: anonymous_id},
                        synchronize_session=False
                    )
                    anonymization_report["anonymized_components"].append(
                        f"interaction_feedback_{feedback_updated}"
                    )
                except Exception as e:
                    anonymization_report["errors"].append(f"Failed to anonymize feedback: {e}")
                    logger.error(f"Failed to anonymize feedback: {e}")
                
                # 4. Anonymize messages - sanitize content for PII
                try:
                    user_messages = session.query(MessageDB).join(
                        ConversationDB
                    ).filter(
                        ConversationDB.user_id == anonymous_id  # Already updated above
                    ).all()
                    
                    messages_sanitized = 0
                    for message in user_messages:
                        if message.content:
                            message.content = self.sanitize_conversation_content(message.content)
                            messages_sanitized += 1
                    
                    anonymization_report["anonymized_components"].append(
                        f"messages_sanitized_{messages_sanitized}"
                    )
                except Exception as e:
                    anonymization_report["errors"].append(f"Failed to sanitize messages: {e}")
                    logger.error(f"Failed to sanitize messages: {e}")
                
                session.commit()
            
            anonymization_report["anonymous_id"] = anonymous_id
            
            # Log completion
            result = "success" if not anonymization_report["errors"] else "partial_failure"
            self.audit_logger.log_privacy_operation(
                operation="anonymize",
                user_id=admin_user_id,
                resource_type="user_data",
                resource_id=user_id,
                result=result,
                details=anonymization_report
            )
            
            logger.info(f"User data anonymized: {user_id} -> {anonymous_id}")
            return anonymization_report
            
        except Exception as e:
            error_msg = f"Failed to anonymize user data: {e}"
            logger.error(error_msg)
            return {
                "user_id": user_id,
                "admin_user_id": admin_user_id,
                "timestamp": datetime.utcnow(),
                "anonymized_components": [],
                "errors": [error_msg]
            }
    
    def export_user_data(
        self,
        user_id: str,
        requesting_user_id: str,
        export_format: str = "json"
    ) -> Dict[str, Any]:
        """Export all user data for privacy compliance (GDPR, etc.).
        
        This collects all user data from:
        1. User profile information
        2. Uploaded books and metadata
        3. Conversation history
        4. Interaction feedback
        5. System preferences
        """
        try:
            export_report = {
                "user_id": user_id,
                "requesting_user_id": requesting_user_id,
                "timestamp": datetime.utcnow(),
                "export_format": export_format,
                "exported_data": {},
                "errors": []
            }
            
            # Log the export request
            self.audit_logger.log_privacy_operation(
                operation="request",
                user_id=requesting_user_id,
                resource_type="user_data",
                resource_id=user_id,
                details={"operation": "data_export", "format": export_format}
            )
            
            with get_database_session() as session:
                # 1. Export user's uploaded books and metadata
                try:
                    books = session.query(KnowledgeSource).filter(
                        KnowledgeSource.uploaded_by == user_id,
                        KnowledgeSource.source_type == 'book'
                    ).all()
                    
                    export_report["exported_data"]["books"] = [
                        {
                            "id": str(book.id),
                            "title": book.title,
                            "author": book.author,
                            "file_path": book.file_path,
                            "upload_date": book.created_at.isoformat() if book.created_at else None,
                            "metadata": book.metadata if hasattr(book, 'metadata') else {}
                        }
                        for book in books
                    ]
                except Exception as e:
                    export_report["errors"].append(f"Failed to export books: {e}")
                    logger.error(f"Failed to export books: {e}")
                    export_report["exported_data"]["books"] = []
                
                # 2. Export conversation history
                try:
                    conversations = session.query(ConversationDB).filter(
                        ConversationDB.user_id == user_id
                    ).all()
                    
                    conversation_data = []
                    for conv in conversations:
                        # Get messages for this conversation
                        messages = session.query(MessageDB).filter(
                            MessageDB.conversation_id == conv.id
                        ).order_by(MessageDB.timestamp).all()
                        
                        conversation_data.append({
                            "thread_id": conv.thread_id,
                            "created_at": conv.created_at.isoformat() if conv.created_at else None,
                            "last_updated": conv.last_updated.isoformat() if conv.last_updated else None,
                            "knowledge_summary": conv.knowledge_summary,
                            "messages": [
                                {
                                    "message_id": msg.message_id,
                                    "content": msg.content,
                                    "message_type": msg.message_type,
                                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
                                }
                                for msg in messages
                            ]
                        })
                    
                    export_report["exported_data"]["conversations"] = conversation_data
                except Exception as e:
                    export_report["errors"].append(f"Failed to export conversations: {e}")
                    logger.error(f"Failed to export conversations: {e}")
                    export_report["exported_data"]["conversations"] = []
                
                # 3. Export interaction feedback
                try:
                    feedback = session.query(InteractionFeedbackDB).filter(
                        InteractionFeedbackDB.user_id == user_id
                    ).all()
                    
                    export_report["exported_data"]["interactions"] = [
                        {
                            "chunk_id": fb.chunk_id,
                            "interaction_type": fb.interaction_type,
                            "feedback_score": fb.feedback_score,
                            "timestamp": fb.timestamp.isoformat() if fb.timestamp else None,
                            "context_query": fb.context_query
                        }
                        for fb in feedback
                    ]
                except Exception as e:
                    export_report["errors"].append(f"Failed to export interactions: {e}")
                    logger.error(f"Failed to export interactions: {e}")
                    export_report["exported_data"]["interactions"] = []
                
                # 4. Export citations made by user
                try:
                    # Get all chunk IDs from user's conversations
                    user_chunk_ids = session.query(KnowledgeChunkDB.chunk_id).join(
                        KnowledgeSource
                    ).filter(
                        KnowledgeSource.uploaded_by == user_id
                    ).all()
                    
                    chunk_id_list = [c[0] for c in user_chunk_ids]
                    
                    citations = session.query(CitationDB).filter(
                        CitationDB.chunk_id.in_(chunk_id_list)
                    ).all() if chunk_id_list else []
                    
                    export_report["exported_data"]["citations"] = [
                        {
                            "chunk_id": cit.chunk_id,
                            "source_title": cit.source_title,
                            "location_reference": cit.location_reference,
                            "relevance_score": cit.relevance_score
                        }
                        for cit in citations
                    ]
                except Exception as e:
                    export_report["errors"].append(f"Failed to export citations: {e}")
                    logger.error(f"Failed to export citations: {e}")
                    export_report["exported_data"]["citations"] = []
                
                # 5. User profile placeholder (would come from auth system)
                export_report["exported_data"]["user_profile"] = {
                    "user_id": user_id,
                    "export_date": datetime.utcnow().isoformat()
                }
                
                # 6. System preferences placeholder
                export_report["exported_data"]["preferences"] = {}
            
            # Log completion
            result = "success" if not export_report["errors"] else "partial_success"
            self.audit_logger.log_privacy_operation(
                operation="request",
                user_id=requesting_user_id,
                resource_type="user_data",
                resource_id=user_id,
                result=result,
                details={
                    "books_count": len(export_report["exported_data"].get("books", [])),
                    "conversations_count": len(export_report["exported_data"].get("conversations", [])),
                    "interactions_count": len(export_report["exported_data"].get("interactions", []))
                }
            )
            
            logger.info(f"User data exported: {user_id}")
            return export_report
            
        except Exception as e:
            error_msg = f"Failed to export user data: {e}"
            logger.error(error_msg)
            return {
                "user_id": user_id,
                "requesting_user_id": requesting_user_id,
                "timestamp": datetime.utcnow(),
                "export_format": export_format,
                "exported_data": {},
                "errors": [error_msg]
            }
    
    def check_data_retention_compliance(self) -> Dict[str, Any]:
        """Check data retention compliance and identify data for deletion.
        
        This implements:
        1. Check configured retention policies
        2. Identify data that exceeds retention periods
        3. Generate recommendations for data deletion
        4. Flag compliance issues
        """
        try:
            compliance_report = {
                "timestamp": datetime.utcnow(),
                "retention_policies": {},
                "data_for_deletion": [],
                "compliance_status": "compliant",
                "recommendations": []
            }
            
            # Define retention policies (could be loaded from config)
            retention_policies = {
                "conversations": {
                    "retention_days": self.settings.conversation_retention_days if hasattr(self.settings, 'conversation_retention_days') else 365,
                    "description": "Conversation threads and messages"
                },
                "interaction_feedback": {
                    "retention_days": self.settings.feedback_retention_days if hasattr(self.settings, 'feedback_retention_days') else 180,
                    "description": "User interaction and feedback data"
                },
                "audit_logs": {
                    "retention_days": self.settings.audit_log_retention_days if hasattr(self.settings, 'audit_log_retention_days') else 730,
                    "description": "Security and audit logs"
                },
                "deleted_content": {
                    "retention_days": 30,
                    "description": "Soft-deleted content awaiting permanent deletion"
                }
            }
            
            compliance_report["retention_policies"] = retention_policies
            
            with get_database_session() as session:
                # 1. Check conversations exceeding retention period
                try:
                    conversation_cutoff = datetime.utcnow() - timedelta(
                        days=retention_policies["conversations"]["retention_days"]
                    )
                    
                    old_conversations = session.query(ConversationDB).filter(
                        ConversationDB.last_updated < conversation_cutoff
                    ).count()
                    
                    if old_conversations > 0:
                        compliance_report["data_for_deletion"].append({
                            "type": "conversations",
                            "count": old_conversations,
                            "cutoff_date": conversation_cutoff.isoformat(),
                            "policy": retention_policies["conversations"]
                        })
                        compliance_report["recommendations"].append(
                            f"Delete {old_conversations} conversations older than {retention_policies['conversations']['retention_days']} days"
                        )
                except Exception as e:
                    logger.warning(f"Failed to check conversation retention: {e}")
                
                # 2. Check interaction feedback exceeding retention period
                try:
                    feedback_cutoff = datetime.utcnow() - timedelta(
                        days=retention_policies["interaction_feedback"]["retention_days"]
                    )
                    
                    old_feedback = session.query(InteractionFeedbackDB).filter(
                        InteractionFeedbackDB.timestamp < feedback_cutoff
                    ).count()
                    
                    if old_feedback > 0:
                        compliance_report["data_for_deletion"].append({
                            "type": "interaction_feedback",
                            "count": old_feedback,
                            "cutoff_date": feedback_cutoff.isoformat(),
                            "policy": retention_policies["interaction_feedback"]
                        })
                        compliance_report["recommendations"].append(
                            f"Delete {old_feedback} feedback records older than {retention_policies['interaction_feedback']['retention_days']} days"
                        )
                except Exception as e:
                    logger.warning(f"Failed to check feedback retention: {e}")
                
                # 3. Check for orphaned data (chunks without sources)
                try:
                    orphaned_chunks = session.query(KnowledgeChunkDB).filter(
                        ~KnowledgeChunkDB.source_id.in_(
                            session.query(KnowledgeSource.id)
                        )
                    ).count()
                    
                    if orphaned_chunks > 0:
                        compliance_report["data_for_deletion"].append({
                            "type": "orphaned_chunks",
                            "count": orphaned_chunks,
                            "reason": "No associated knowledge source"
                        })
                        compliance_report["recommendations"].append(
                            f"Clean up {orphaned_chunks} orphaned knowledge chunks"
                        )
                except Exception as e:
                    logger.warning(f"Failed to check orphaned chunks: {e}")
                
                # 4. Check for orphaned media elements
                try:
                    orphaned_media = session.query(MediaElementDB).filter(
                        ~MediaElementDB.chunk_id.in_(
                            session.query(KnowledgeChunkDB.chunk_id)
                        )
                    ).count()
                    
                    if orphaned_media > 0:
                        compliance_report["data_for_deletion"].append({
                            "type": "orphaned_media",
                            "count": orphaned_media,
                            "reason": "No associated knowledge chunk"
                        })
                        compliance_report["recommendations"].append(
                            f"Clean up {orphaned_media} orphaned media elements"
                        )
                except Exception as e:
                    logger.warning(f"Failed to check orphaned media: {e}")
            
            # Determine overall compliance status
            if compliance_report["data_for_deletion"]:
                total_items = sum(
                    item.get("count", 0) for item in compliance_report["data_for_deletion"]
                )
                if total_items > 1000:
                    compliance_report["compliance_status"] = "action_required"
                else:
                    compliance_report["compliance_status"] = "review_recommended"
            
            # Log the compliance check
            self.audit_logger.log_privacy_operation(
                operation="compliance_check",
                user_id="system",
                resource_type="data_retention",
                resource_id="all",
                result=compliance_report["compliance_status"],
                details={
                    "items_for_deletion": len(compliance_report["data_for_deletion"]),
                    "recommendations_count": len(compliance_report["recommendations"])
                }
            )
            
            logger.info("Data retention compliance check completed")
            return compliance_report
            
        except Exception as e:
            error_msg = f"Failed to check data retention compliance: {e}"
            logger.error(error_msg)
            return {
                "timestamp": datetime.utcnow(),
                "compliance_status": "error",
                "error": error_msg
            }


# Global privacy service instance
_privacy_service = None


def get_privacy_service() -> PrivacyService:
    """Get global privacy service instance."""
    global _privacy_service
    if _privacy_service is None:
        _privacy_service = PrivacyService()
    return _privacy_service
