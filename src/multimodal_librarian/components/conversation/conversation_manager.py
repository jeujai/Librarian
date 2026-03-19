"""
Conversation Management Component.

This module implements conversation thread creation and management,
message processing with multimedia support, and conversation-to-knowledge
conversion functionality.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import text

from ...database.connection import db_manager
from ...models.core import (
    ContentType,
    ConversationThread,
    KnowledgeChunk,
    KnowledgeMetadata,
    Message,
    MessageType,
    MultimediaElement,
    SourceType,
)

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Context information for conversation processing."""
    thread: ConversationThread
    recent_messages: List[Message]
    knowledge_references: List[str]
    context_summary: str
    multimedia_elements: List[MultimediaElement]


@dataclass
class MultimediaInput:
    """Processed multimedia input from chat interface."""
    input_type: str  # text, image, document, data
    content: Union[str, bytes]
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ProcessedInput:
    """Result of processing multimedia input."""
    text_content: str
    multimedia_elements: List[MultimediaElement]
    extracted_data: Dict[str, Any]
    processing_notes: List[str]


class ConversationManager:
    """
    Manages conversation threads and message processing.
    
    Handles conversation thread creation, message processing with multimedia support,
    and conversion of conversations into knowledge chunks equivalent to book content.
    """
    
    def __init__(self):
        """Initialize the conversation manager."""
        self.active_conversations: Dict[str, ConversationThread] = {}
        self.conversation_stats = {
            'total_conversations': 0,
            'total_messages': 0,
            'multimedia_messages': 0,
            'knowledge_chunks_created': 0,
            'average_messages_per_conversation': 0.0
        }
        
        logger.info("Initialized ConversationManager")
    
    def start_conversation(self, user_id: str, initial_message: Optional[str] = None) -> ConversationThread:
        """
        Initialize new conversation thread.
        
        Args:
            user_id: Identifier for the user
            initial_message: Optional initial message content
            
        Returns:
            ConversationThread: New conversation thread
        """
        thread_id = str(uuid.uuid4())
        
        # Create conversation thread
        conversation = ConversationThread(
            thread_id=thread_id,
            user_id=user_id,
            messages=[],
            created_at=datetime.now(),
            last_updated=datetime.now(),
            knowledge_summary=""
        )
        
        # Add initial message if provided
        if initial_message:
            initial_msg = Message(
                message_id=str(uuid.uuid4()),
                content=initial_message,
                multimedia_content=[],
                timestamp=datetime.now(),
                message_type=MessageType.USER,
                knowledge_references=[]
            )
            conversation.add_message(initial_msg)
        
        # Store in active conversations
        self.active_conversations[thread_id] = conversation
        
        # Persist to database
        self._persist_conversation(conversation)
        
        # Update statistics
        self.conversation_stats['total_conversations'] += 1
        if initial_message:
            self.conversation_stats['total_messages'] += 1
        
        logger.info(f"Started new conversation {thread_id} for user {user_id}")
        return conversation
    
    def get_conversation(self, thread_id: str) -> Optional[ConversationThread]:
        """
        Get conversation thread by ID.
        
        Args:
            thread_id: Conversation thread identifier
            
        Returns:
            ConversationThread or None if not found
        """
        # Check active conversations first
        if thread_id in self.active_conversations:
            return self.active_conversations[thread_id]
        
        # Load from database
        conversation = self._load_conversation(thread_id)
        if conversation:
            self.active_conversations[thread_id] = conversation
        
        return conversation
    
    def list_user_conversations(self, user_id: str, limit: int = 50) -> List[ConversationThread]:
        """
        List conversations for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of conversations to return
            
        Returns:
            List of ConversationThread objects
        """
        conversations = []

        try:
            with db_manager.get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT id, user_id::text, title, created_at, updated_at "
                        "FROM multimodal_librarian.conversation_threads "
                        "WHERE (is_archived IS NULL OR is_archived = false) "
                        "ORDER BY COALESCE(last_message_at, updated_at) DESC "
                        "LIMIT :lim"
                    ),
                    {"lim": limit},
                ).fetchall()

                for r in rows:
                    conv = ConversationThread(
                        thread_id=str(r[0]),
                        user_id=r[1] or "",
                        messages=[],
                        created_at=r[3],
                        last_updated=r[4],
                        knowledge_summary="",
                    )
                    conversations.append(conv)

        except Exception as e:
            logger.error(f"Failed to list conversations for user {user_id}: {e}")

        return conversations
    
    def process_message(self, thread_id: str, message_content: str,
                       multimedia_content: Optional[List[MultimediaElement]] = None,
                       message_type: MessageType = MessageType.USER,
                       knowledge_references: Optional[List] = None) -> ConversationContext:
        """
        Process user message with conversation context.

        Args:
            thread_id: Conversation thread identifier
            message_content: Text content of the message
            multimedia_content: Optional multimedia elements
            message_type: Type of message (user, system, upload)
            knowledge_references: Optional list of knowledge references (citations)

        Returns:
            ConversationContext with updated conversation state
        """
        conversation = self.get_conversation(thread_id)
        if not conversation:
            raise ValueError(f"Conversation {thread_id} not found")

        # Create new message
        message = Message(
            message_id=str(uuid.uuid4()),
            content=message_content,
            multimedia_content=multimedia_content or [],
            timestamp=datetime.now(),
            message_type=message_type,
            knowledge_references=knowledge_references or []
        )

        # Add message to conversation
        conversation.add_message(message)

        # Update conversation in active cache
        self.active_conversations[thread_id] = conversation

        # Persist message to database
        self._persist_message(conversation, message)

        # Update statistics
        self.conversation_stats['total_messages'] += 1
        if message.has_multimedia():
            self.conversation_stats['multimedia_messages'] += 1

        # Create conversation context
        context = self._create_conversation_context(conversation)

        logger.info(f"Processed message in conversation {thread_id}")
        return context
    
    def accept_multimedia_input(self, input_data: MultimediaInput) -> ProcessedInput:
        """
        Process various input formats in chat.
        
        Args:
            input_data: Multimedia input to process
            
        Returns:
            ProcessedInput with extracted content and elements
        """
        processing_notes = []
        text_content = ""
        multimedia_elements = []
        extracted_data = {}
        
        try:
            if input_data.input_type == "text":
                text_content = str(input_data.content)
                processing_notes.append("Processed text input")
            
            elif input_data.input_type == "image":
                # Create multimedia element for image
                element = MultimediaElement(
                    element_type="image",
                    content=input_data.content,
                    filename=input_data.filename,
                    mime_type=input_data.mime_type,
                    metadata=input_data.metadata
                )
                multimedia_elements.append(element)
                text_content = f"[Image uploaded: {input_data.filename or 'image'}]"
                processing_notes.append("Processed image input")
            
            elif input_data.input_type == "document":
                # Create multimedia element for document
                element = MultimediaElement(
                    element_type="document",
                    content=input_data.content,
                    filename=input_data.filename,
                    mime_type=input_data.mime_type,
                    metadata=input_data.metadata
                )
                multimedia_elements.append(element)
                text_content = f"[Document uploaded: {input_data.filename or 'document'}]"
                processing_notes.append("Processed document input")
                
                # Extract basic document info
                if isinstance(input_data.content, bytes):
                    extracted_data['file_size'] = len(input_data.content)
                extracted_data['mime_type'] = input_data.mime_type
            
            elif input_data.input_type == "data":
                # Handle structured data input
                if isinstance(input_data.content, str):
                    text_content = input_data.content
                    # Try to parse as JSON or CSV
                    try:
                        import json
                        data = json.loads(input_data.content)
                        extracted_data['parsed_json'] = data
                        processing_notes.append("Parsed JSON data")
                    except json.JSONDecodeError:
                        # Try CSV parsing
                        lines = input_data.content.split('\n')
                        if len(lines) > 1 and ',' in lines[0]:
                            extracted_data['csv_rows'] = len(lines)
                            extracted_data['csv_columns'] = len(lines[0].split(','))
                            processing_notes.append("Detected CSV data")
                
                processing_notes.append("Processed data input")
            
            else:
                text_content = str(input_data.content)
                processing_notes.append(f"Processed unknown input type: {input_data.input_type}")
        
        except Exception as e:
            logger.error(f"Failed to process multimedia input: {e}")
            text_content = f"[Error processing {input_data.input_type} input]"
            processing_notes.append(f"Error: {str(e)}")
        
        return ProcessedInput(
            text_content=text_content,
            multimedia_elements=multimedia_elements,
            extracted_data=extracted_data,
            processing_notes=processing_notes
        )
    
    def convert_to_knowledge_chunks(
        self, conversation: ConversationThread, thread_title: Optional[str] = None
    ) -> List[KnowledgeChunk]:
        """
        Convert conversation to searchable knowledge chunks.

        Args:
            conversation: Conversation thread to convert
            thread_title: Optional title for the thread. If not provided,
                derived from knowledge_summary or first user message content.

        Returns:
            List of KnowledgeChunk objects
        """
        chunks = []

        try:
            # Derive thread title: explicit param > knowledge_summary > first user message
            title = thread_title
            if not title:
                title = conversation.knowledge_summary.strip() if conversation.knowledge_summary else ""
            if not title:
                for msg in conversation.messages:
                    if msg.message_type == MessageType.USER and msg.content.strip():
                        title = msg.content.strip()[:80]
                        break
            if not title:
                title = "Untitled Conversation"

            # Group messages into meaningful chunks
            message_groups = self._group_messages_for_chunking(conversation.messages)

            for i, group in enumerate(message_groups):
                # Combine messages in group
                combined_content, segments = self._combine_message_group(group)

                # Extract multimedia elements
                multimedia_elements = []
                for message in group:
                    for elem in message.multimedia_content:
                        # Convert MultimediaElement to MediaElement
                        from ...models.core import MediaElement
                        media_elem = MediaElement(
                            element_id=str(uuid.uuid4()),
                            element_type=elem.element_type,
                            content_data=elem.content if isinstance(elem.content, bytes) else None,
                            caption=elem.filename or "",
                            metadata=elem.metadata
                        )
                        multimedia_elements.append(media_elem)

                # Create knowledge metadata
                knowledge_metadata = KnowledgeMetadata(
                    complexity_score=self._calculate_conversation_complexity(group),
                    domain_tags=self._extract_domain_tags(combined_content),
                    extraction_confidence=0.9,  # High confidence for conversation content
                    processing_timestamp=datetime.now(),
                    chunk_index=i,
                    total_chunks=len(message_groups),
                    segments=segments
                )

                # Build location_reference: "{title} | {start} – {end}"
                start_ts = group[0].timestamp.isoformat()
                end_ts = group[-1].timestamp.isoformat()
                location_reference = f"{title} | {start_ts} – {end_ts}"

                # Create knowledge chunk
                # Deterministic UUID so KG and Milvus share the same ID
                chunk_id = str(uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"conv_{conversation.thread_id}_chunk_{i}",
                ))
                chunk = KnowledgeChunk(
                    id=chunk_id,
                    content=combined_content,
                    source_type=SourceType.CONVERSATION,
                    source_id=conversation.thread_id,
                    location_reference=location_reference,
                    section=title,
                    content_type=self._determine_content_type(combined_content),
                    associated_media=multimedia_elements,
                    knowledge_metadata=knowledge_metadata
                )

                chunks.append(chunk)

        except Exception as e:
            logger.error(f"Failed to convert conversation to knowledge chunks: {e}")

        # Update statistics
        self.conversation_stats['knowledge_chunks_created'] += len(chunks)

        logger.info(f"Created {len(chunks)} knowledge chunks from conversation {conversation.thread_id}")
        return chunks
    
    def delete_conversation(self, thread_id: str, user_id: str) -> bool:
        """
        Delete conversation and remove from knowledge base.
        
        Args:
            thread_id: Conversation thread identifier
            user_id: User identifier for authorization
            
        Returns:
            bool: True if successfully deleted
        """
        try:
            # Remove from active conversations
            if thread_id in self.active_conversations:
                del self.active_conversations[thread_id]

            with db_manager.get_session() as session:
                thread_uuid = uuid.UUID(thread_id)

                # Archive the conversation (soft delete)
                session.execute(
                    text(
                        "UPDATE multimodal_librarian.conversation_threads "
                        "SET is_archived = true, updated_at = NOW() "
                        "WHERE id = :tid"
                    ),
                    {"tid": thread_uuid},
                )

                # Also remove the knowledge_sources row (UUID5 mapping)
                source_id = uuid.uuid5(uuid.NAMESPACE_URL, thread_id)
                session.execute(
                    text(
                        "DELETE FROM multimodal_librarian.knowledge_sources "
                        "WHERE id = :sid"
                    ),
                    {"sid": source_id},
                )

                session.commit()

            logger.info(f"Deleted conversation {thread_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete conversation {thread_id}: {e}")
            return False

    async def delete_conversation_completely(self, thread_id: str, user_id: str = "") -> Dict[str, Any]:
        """
        Delete conversation from Postgres, Milvus, and Neo4j.

        This is the async counterpart of delete_conversation that also
        removes vector embeddings and knowledge-graph nodes so that
        deleted conversations no longer appear as citation sources.
        """
        source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, thread_id))
        results: Dict[str, Any] = {"errors": [], "milvus_deleted": 0, "neo4j_deleted": 0}

        # --- Milvus cleanup ---
        results["milvus_deleted"] = await self._delete_vectors_from_milvus(source_id, results)

        # --- Neo4j cleanup ---
        results["neo4j_deleted"] = await self._delete_nodes_from_neo4j(source_id, results)

        # --- Postgres cleanup (existing sync logic) ---
        pg_ok = self.delete_conversation(thread_id, user_id)
        results["postgres_deleted"] = pg_ok

        if results["errors"]:
            logger.warning(f"Conversation {thread_id} deleted with errors: {results['errors']}")
        else:
            logger.info(
                f"Conversation {thread_id} fully deleted — "
                f"milvus={results['milvus_deleted']}, neo4j={results['neo4j_deleted']}"
            )
        return results

    # ------------------------------------------------------------------
    # Milvus / Neo4j helpers (mirrors DocumentManager patterns)
    # ------------------------------------------------------------------

    async def _delete_vectors_from_milvus(self, source_id: str, results: Dict[str, Any]) -> int:
        """Delete conversation vectors from Milvus with a 15-second timeout."""
        try:
            return await asyncio.wait_for(
                self._delete_vectors_from_milvus_inner(source_id, results),
                timeout=15,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Milvus deletion timed out for conversation source {source_id}")
            results["errors"].append("Milvus: timed out after 15s")
            return 0
        except Exception as e:
            logger.warning(f"Milvus deletion failed for conversation source {source_id}: {e}")
            results["errors"].append(f"Milvus: {e}")
            return 0

    async def _delete_vectors_from_milvus_inner(self, source_id: str, results: Dict[str, Any]) -> int:
        from pymilvus import Collection, connections, utility

        host = os.environ.get("MILVUS_HOST", "milvus")
        port = os.environ.get("MILVUS_PORT", "19530")
        collection_name = os.environ.get("MILVUS_COLLECTION_NAME", "knowledge_chunks")
        alias = f"conv_del_{source_id[:8]}"
        loop = asyncio.get_event_loop()

        await loop.run_in_executor(
            None, lambda: connections.connect(alias=alias, host=host, port=port, timeout=10)
        )
        try:
            has = await loop.run_in_executor(
                None, lambda: utility.has_collection(collection_name, using=alias)
            )
            if not has:
                return 0

            col = await loop.run_in_executor(
                None, lambda: Collection(collection_name, using=alias)
            )
            await loop.run_in_executor(None, col.load)

            expr = f'metadata["source_id"] == "{source_id}"'
            mut = await loop.run_in_executor(None, col.delete, expr)
            deleted = mut.delete_count if hasattr(mut, "delete_count") else 0
            logger.info(f"Milvus: deleted {deleted} conversation vectors for source {source_id}")
            return deleted
        finally:
            await loop.run_in_executor(None, connections.disconnect, alias)

    async def _delete_nodes_from_neo4j(self, source_id: str, results: Dict[str, Any]) -> int:
        """Delete conversation nodes from Neo4j with a 30-second timeout."""
        try:
            return await asyncio.wait_for(
                self._delete_nodes_from_neo4j_inner(source_id, results),
                timeout=30,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Neo4j deletion timed out for conversation source {source_id}")
            results["errors"].append("Neo4j: timed out after 30s")
            return 0
        except Exception as e:
            logger.warning(f"Neo4j deletion failed for conversation source {source_id}: {e}")
            results["errors"].append(f"Neo4j: {e}")
            return 0

    async def _delete_nodes_from_neo4j_inner(self, source_id: str, results: Dict[str, Any]) -> int:
        try:
            from ...services.knowledge_graph_service import KnowledgeGraphService
            kg = KnowledgeGraphService()
            await kg.client.connect()
            try:
                res_rels = await kg.client.execute_write_query(
                    "MATCH (ch:Chunk {source_id: $sid})<-[r:EXTRACTED_FROM]-(c:Concept) "
                    "DELETE r RETURN count(r) AS deleted_rels",
                    {"sid": source_id},
                )
                deleted_rels = res_rels[0]["deleted_rels"] if res_rels else 0

                res_chunks = await kg.client.execute_write_query(
                    "MATCH (ch:Chunk {source_id: $sid}) DELETE ch RETURN count(ch) AS deleted_chunks",
                    {"sid": source_id},
                )
                deleted_chunks = res_chunks[0]["deleted_chunks"] if res_chunks else 0

                res_concepts = await kg.client.execute_write_query(
                    "MATCH (c:Concept) "
                    "WHERE NOT EXISTS { MATCH (c)-[:EXTRACTED_FROM]->() } "
                    "AND NOT EXISTS { MATCH (c)<-[:SAME_AS]-() } "
                    "DETACH DELETE c RETURN count(c) AS deleted_concepts",
                    {},
                )
                deleted_concepts = res_concepts[0]["deleted_concepts"] if res_concepts else 0

                total = deleted_rels + deleted_chunks + deleted_concepts
                logger.info(
                    f"Neo4j: deleted {deleted_rels} rels, {deleted_chunks} chunks, "
                    f"{deleted_concepts} orphaned concepts for conversation source {source_id}"
                )
                return total
            finally:
                await kg.client.disconnect()
        except Exception as e:
            logger.warning(f"Neo4j deletion failed for conversation source {source_id}: {e}")
            results["errors"].append(f"Neo4j: {e}")
            return 0

    def _create_conversation_context(self, conversation: ConversationThread) -> ConversationContext:
        """Create conversation context for processing."""
        
        # Get recent messages (last 10)
        recent_messages = conversation.messages[-10:] if len(conversation.messages) > 10 else conversation.messages
        
        # Extract knowledge references (may be str or dict from citations)
        knowledge_references = []
        seen = set()
        for message in recent_messages:
            for ref in message.knowledge_references:
                # Deduplicate: use document_id for dicts, raw value for strings
                if isinstance(ref, dict):
                    key = ref.get('document_id', '') or ref.get('chunk_id', '')
                else:
                    key = ref
                if key and key not in seen:
                    seen.add(key)
                    knowledge_references.append(ref if isinstance(ref, str) else str(ref))
        
        # Extract multimedia elements
        multimedia_elements = []
        for message in recent_messages:
            multimedia_elements.extend(message.multimedia_content)
        
        # Create context summary
        context_summary = self._create_context_summary(recent_messages)
        
        return ConversationContext(
            thread=conversation,
            recent_messages=recent_messages,
            knowledge_references=knowledge_references,
            context_summary=context_summary,
            multimedia_elements=multimedia_elements
        )
    
    def _create_context_summary(self, messages: List[Message]) -> str:
        """Create a summary of conversation context."""
        if not messages:
            return ""
        
        # Simple summary based on recent messages
        user_messages = [msg for msg in messages if msg.message_type == MessageType.USER]
        system_messages = [msg for msg in messages if msg.message_type == MessageType.SYSTEM]
        
        summary_parts = []
        
        if user_messages:
            recent_user_msg = user_messages[-1].content[:100]
            summary_parts.append(f"Recent user query: {recent_user_msg}")
        
        if system_messages:
            recent_system_msg = system_messages[-1].content[:100]
            summary_parts.append(f"Recent response: {recent_system_msg}")
        
        summary_parts.append(f"Total messages: {len(messages)}")
        
        return " | ".join(summary_parts)
    
    def _group_messages_for_chunking(self, messages: List[Message]) -> List[List[Message]]:
        """Group messages into meaningful chunks for knowledge extraction."""
        if not messages:
            return []
        
        groups = []
        current_group = []
        current_size = 0
        max_chunk_size = 500  # words
        
        for message in messages:
            message_size = len(message.content.split())
            
            # Start new group if current group is too large or if there's a significant time gap
            if current_group and (current_size + message_size > max_chunk_size or 
                                self._has_significant_time_gap(current_group[-1], message)):
                groups.append(current_group)
                current_group = [message]
                current_size = message_size
            else:
                current_group.append(message)
                current_size += message_size
        
        # Add final group
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def _has_significant_time_gap(self, msg1: Message, msg2: Message) -> bool:
        """Check if there's a significant time gap between messages."""
        time_diff = abs((msg2.timestamp - msg1.timestamp).total_seconds())
        return time_diff > 3600  # 1 hour gap
    
    def _combine_message_group(self, messages: List[Message]) -> tuple:
        """Combine messages in a group into coherent content.

        Returns:
            A tuple of (combined_text, segments) where combined_text is the
            backward-compatible string and segments is a list of
            {"role": "user"|"assistant", "content": "..."} dicts preserving
            conversation structure.
        """
        content_parts = []
        segments = []

        for message in messages:
            timestamp_str = message.timestamp.strftime("%Y-%m-%d %H:%M")
            message_type_str = message.message_type.value.upper()

            content_parts.append(f"[{timestamp_str}] {message_type_str}: {message.content}")

            # Add multimedia descriptions
            for elem in message.multimedia_content:
                content_parts.append(f"[MULTIMEDIA: {elem.element_type} - {elem.filename or 'unnamed'}]")

            # Map message type to segment role
            role = "user" if message.message_type == MessageType.USER else "assistant"
            segments.append({"role": role, "content": message.content})

        return "\n".join(content_parts), segments
    
    def _calculate_conversation_complexity(self, messages: List[Message]) -> float:
        """Calculate complexity score for conversation chunk."""
        if not messages:
            return 0.0
        
        # Factors for complexity
        total_words = sum(len(msg.content.split()) for msg in messages)
        multimedia_count = sum(len(msg.multimedia_content) for msg in messages)
        unique_message_types = len(set(msg.message_type for msg in messages))
        
        # Simple complexity calculation
        word_complexity = min(total_words / 1000.0, 1.0)  # Normalize to 0-1
        multimedia_complexity = min(multimedia_count / 10.0, 1.0)  # Normalize to 0-1
        type_complexity = unique_message_types / 3.0  # Max 3 types
        
        return (word_complexity + multimedia_complexity + type_complexity) / 3.0
    
    def _extract_domain_tags(self, content: str) -> List[str]:
        """Extract domain tags from conversation content."""
        tags = []
        
        # Simple keyword-based tagging
        content_lower = content.lower()
        
        domain_keywords = {
            'technical': ['code', 'programming', 'software', 'algorithm', 'database', 'api'],
            'academic': ['research', 'study', 'analysis', 'theory', 'methodology'],
            'business': ['strategy', 'market', 'revenue', 'customer', 'sales'],
            'creative': ['design', 'art', 'creative', 'visual', 'aesthetic'],
            'data': ['data', 'statistics', 'analytics', 'metrics', 'visualization']
        }
        
        for domain, keywords in domain_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                tags.append(domain)
        
        return tags[:3]  # Limit to top 3 tags
    
    def _determine_content_type(self, content: str) -> ContentType:
        """Determine content type for conversation chunk."""
        content_lower = content.lower()
        
        # Simple heuristics for content type detection
        if any(word in content_lower for word in ['code', 'programming', 'software', 'technical']):
            return ContentType.TECHNICAL
        elif any(word in content_lower for word in ['research', 'academic', 'study', 'analysis']):
            return ContentType.ACADEMIC
        elif any(word in content_lower for word in ['legal', 'law', 'regulation', 'compliance']):
            return ContentType.LEGAL
        elif any(word in content_lower for word in ['medical', 'health', 'diagnosis', 'treatment']):
            return ContentType.MEDICAL
        elif any(word in content_lower for word in ['story', 'narrative', 'character', 'plot']):
            return ContentType.NARRATIVE
        else:
            return ContentType.GENERAL
    
    def _persist_conversation(self, conversation: ConversationThread):
        """Persist conversation to the real conversation_threads table."""
        try:
            with db_manager.get_session() as session:
                # Resolve a valid user_id UUID for the FK constraint
                row = session.execute(
                    text("SELECT id FROM multimodal_librarian.users LIMIT 1")
                ).fetchone()
                if row:
                    user_uuid = row[0]
                else:
                    user_uuid = uuid.uuid4()
                    session.execute(
                        text(
                            "INSERT INTO multimodal_librarian.users "
                            "(id, username, email, password_hash) "
                            "VALUES (:uid, 'chat_user', "
                            "'chat@multimodal-librarian.local', 'not_for_login') "
                            "ON CONFLICT (username) DO NOTHING"
                        ),
                        {"uid": user_uuid},
                    )
                    fetched = session.execute(
                        text(
                            "SELECT id FROM multimodal_librarian.users "
                            "WHERE username = 'chat_user'"
                        )
                    ).fetchone()
                    if fetched:
                        user_uuid = fetched[0]

                thread_uuid = uuid.UUID(conversation.thread_id)
                now = conversation.created_at or datetime.utcnow()

                session.execute(
                    text(
                        "INSERT INTO multimodal_librarian.conversation_threads "
                        "(id, user_id, title, created_at, updated_at, last_message_at) "
                        "VALUES (:tid, :uid, :title, :created, :updated, :lm) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "tid": thread_uuid,
                        "uid": user_uuid,
                        "title": f"Conversation {conversation.thread_id[:8]}",
                        "created": now,
                        "updated": now,
                        "lm": now,
                    },
                )
                session.commit()

        except Exception as e:
            logger.error(f"Failed to persist conversation {conversation.thread_id}: {e}")
    
    def _persist_message(self, conversation: ConversationThread, message: Message):
        """Persist message to the real messages table."""
        try:
            import json as _json

            with db_manager.get_session() as session:
                thread_uuid = uuid.UUID(conversation.thread_id)

                # Resolve user_id from the conversation_threads row
                row = session.execute(
                    text(
                        "SELECT user_id FROM multimodal_librarian.conversation_threads "
                        "WHERE id = :tid"
                    ),
                    {"tid": thread_uuid},
                ).fetchone()
                if not row:
                    logger.warning(
                        f"conversation_threads row not found for {conversation.thread_id}, "
                        "skipping message persist"
                    )
                    return
                user_uuid = row[0]

                # Map MessageType to the DB enum value (uppercase)
                msg_type_str = message.message_type.value.upper()

                # Serialize multimedia_content
                multimedia_json = None
                if message.multimedia_content:
                    multimedia_json = _json.dumps(
                        [elem.to_dict() for elem in message.multimedia_content]
                    )

                # Serialize knowledge_references
                kr_json = _json.dumps(message.knowledge_references or [])

                msg_uuid = uuid.uuid4()

                session.execute(
                    text(
                        "INSERT INTO multimodal_librarian.messages "
                        "(id, thread_id, user_id, content, message_type, "
                        " multimedia_content, knowledge_references, created_at) "
                        "VALUES (:mid, :tid, :uid, :content, "
                        " CAST(:mtype AS multimodal_librarian.message_type), "
                        " CAST(:mm AS jsonb), CAST(:kr AS jsonb), :ts) "
                    ),
                    {
                        "mid": msg_uuid,
                        "tid": thread_uuid,
                        "uid": user_uuid,
                        "content": message.content,
                        "mtype": msg_type_str,
                        "mm": multimedia_json or "[]",
                        "kr": kr_json,
                        "ts": message.timestamp or datetime.utcnow(),
                    },
                )

                # Update last_message_at on the thread
                session.execute(
                    text(
                        "UPDATE multimodal_librarian.conversation_threads "
                        "SET last_message_at = :ts, updated_at = :ts "
                        "WHERE id = :tid"
                    ),
                    {"ts": message.timestamp or datetime.utcnow(), "tid": thread_uuid},
                )

                session.commit()

        except Exception as e:
            logger.error(f"Failed to persist message {message.message_id}: {e}")
    
    def _load_conversation(self, thread_id: str) -> Optional[ConversationThread]:
        """Load conversation from the real conversation_threads + messages tables."""
        try:
            with db_manager.get_session() as session:
                thread_uuid = uuid.UUID(thread_id)

                # Load thread row
                t_row = session.execute(
                    text(
                        "SELECT id, user_id::text, title, created_at, updated_at, is_archived "
                        "FROM multimodal_librarian.conversation_threads "
                        "WHERE id = :tid AND (is_archived IS NULL OR is_archived = false)"
                    ),
                    {"tid": thread_uuid},
                ).fetchone()

                if not t_row:
                    return None

                # Load messages ordered by created_at
                msg_rows = session.execute(
                    text(
                        "SELECT id, content, message_type::text, "
                        "       multimedia_content, knowledge_references, created_at "
                        "FROM multimodal_librarian.messages "
                        "WHERE thread_id = :tid "
                        "ORDER BY created_at ASC"
                    ),
                    {"tid": thread_uuid},
                ).fetchall()

                messages = []
                for mr in msg_rows:
                    # Map DB enum to MessageType
                    mt_str = (mr[2] or "USER").upper()
                    try:
                        mt = MessageType(mt_str.lower())
                    except (ValueError, KeyError):
                        mt = MessageType.USER

                    multimedia_content = []
                    if mr[3]:
                        raw_mm = mr[3] if isinstance(mr[3], list) else []
                        multimedia_content = [
                            MultimediaElement.from_dict(elem)
                            for elem in raw_mm
                        ]

                    kr = mr[4] if mr[4] else []
                    if isinstance(kr, dict):
                        kr = []

                    message = Message(
                        message_id=str(mr[0]),
                        content=mr[1],
                        multimedia_content=multimedia_content,
                        timestamp=mr[5],
                        message_type=mt,
                        knowledge_references=kr if isinstance(kr, list) else [],
                    )
                    messages.append(message)

                return ConversationThread(
                    thread_id=thread_id,
                    user_id=t_row[1] or "",
                    messages=messages,
                    created_at=t_row[3],
                    last_updated=t_row[4],
                    knowledge_summary="",
                )

        except Exception as e:
            logger.error(f"Failed to load conversation {thread_id}: {e}")
            return None
    
    def get_conversation_statistics(self) -> Dict[str, Any]:
        """Get conversation management statistics."""
        # Update average messages per conversation
        if self.conversation_stats['total_conversations'] > 0:
            self.conversation_stats['average_messages_per_conversation'] = (
                self.conversation_stats['total_messages'] / 
                self.conversation_stats['total_conversations']
            )
        
        return self.conversation_stats.copy()
    
    def reset_statistics(self):
        """Reset conversation statistics."""
        self.conversation_stats = {
            'total_conversations': 0,
            'total_messages': 0,
            'multimedia_messages': 0,
            'knowledge_chunks_created': 0,
            'average_messages_per_conversation': 0.0
        }
    
    def get_conversation_thread(self, thread_id: str) -> Optional[ConversationThread]:
        """
        Get conversation thread by ID (alias for get_conversation).
        
        Args:
            thread_id: Conversation thread identifier
            
        Returns:
            ConversationThread or None if not found
        """
        return self.get_conversation(thread_id)

    def update_conversation_title(self, thread_id: str, title: str) -> bool:
        """
        Update the title of a conversation's knowledge source.

        Updates both the conversation_threads row and the knowledge_sources
        row (looked up via UUID5 of thread_id).

        Args:
            thread_id: Conversation thread identifier
            title: New title string

        Returns:
            True if the title was updated successfully, False otherwise.
        """
        try:
            with db_manager.get_session() as session:
                thread_uuid = uuid.UUID(thread_id)

                # Update conversation_threads title
                session.execute(
                    text(
                        "UPDATE multimodal_librarian.conversation_threads "
                        "SET title = :title, updated_at = NOW() "
                        "WHERE id = :tid"
                    ),
                    {"title": title, "tid": thread_uuid},
                )

                # Update knowledge_sources title (UUID5 mapping)
                source_id = uuid.uuid5(
                    uuid.NAMESPACE_URL, thread_id
                )
                session.execute(
                    text(
                        "UPDATE multimodal_librarian.knowledge_sources "
                        "SET title = :title, updated_at = NOW() "
                        "WHERE id = :sid"
                    ),
                    {"title": title, "sid": source_id},
                )

                session.commit()
                logger.info(f"Updated title for conversation {thread_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to update title for conversation {thread_id}: {e}")
            return False

    def get_conversation_title(self, thread_id: str) -> Optional[str]:
        """
        Get the title of a conversation's knowledge source.

        Checks knowledge_sources (via UUID5 mapping) first, then
        falls back to conversation_threads.title.

        Args:
            thread_id: Conversation thread identifier

        Returns:
            The title string, or None if not found.
        """
        try:
            with db_manager.get_session() as session:
                # Try knowledge_sources first (has the user-facing title)
                source_id = uuid.uuid5(
                    uuid.NAMESPACE_URL, thread_id
                )
                row = session.execute(
                    text(
                        "SELECT title FROM multimodal_librarian.knowledge_sources "
                        "WHERE id = :sid"
                    ),
                    {"sid": source_id},
                ).fetchone()
                if row and row[0]:
                    return row[0]

                # Fallback to conversation_threads.title
                thread_uuid = uuid.UUID(thread_id)
                row = session.execute(
                    text(
                        "SELECT title FROM multimodal_librarian.conversation_threads "
                        "WHERE id = :tid"
                    ),
                    {"tid": thread_uuid},
                ).fetchone()
                return row[0] if row else None

        except Exception as e:
            logger.error(f"Failed to get title for conversation {thread_id}: {e}")
            return None

    
    def list_conversations(self, user_id: str, limit: int = 50, offset: int = 0) -> List[ConversationThread]:
        """
        List conversations for a user with pagination.
        
        Args:
            user_id: User identifier
            limit: Maximum number of conversations to return
            offset: Number of conversations to skip
            
        Returns:
            List of ConversationThread objects
        """
        try:
            with db_manager.get_session() as session:
                rows = session.execute(
                    text(
                        "SELECT id, user_id::text, title, created_at, updated_at "
                        "FROM multimodal_librarian.conversation_threads "
                        "WHERE (is_archived IS NULL OR is_archived = false) "
                        "ORDER BY COALESCE(last_message_at, updated_at) DESC "
                        "OFFSET :off LIMIT :lim"
                    ),
                    {"off": offset, "lim": limit},
                ).fetchall()

                conversations = []
                for r in rows:
                    conv = ConversationThread(
                        thread_id=str(r[0]),
                        user_id=r[1] or "",
                        messages=[],
                        created_at=r[3],
                        last_updated=r[4],
                        knowledge_summary="",
                    )
                    conversations.append(conv)

                return conversations

        except Exception as e:
            logger.error(f"Failed to list conversations for user {user_id}: {e}")
            return []
    
    def count_conversations(self, user_id: str) -> int:
        """
        Count total conversations for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Total number of conversations
        """
        try:
            with db_manager.get_session() as session:
                row = session.execute(
                    text(
                        "SELECT COUNT(*) FROM multimodal_librarian.conversation_threads "
                        "WHERE (is_archived IS NULL OR is_archived = false)"
                    )
                ).fetchone()
                return row[0] if row else 0

        except Exception as e:
            logger.error(f"Failed to count conversations for user {user_id}: {e}")
            return 0