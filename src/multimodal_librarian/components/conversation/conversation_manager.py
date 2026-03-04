"""
Conversation Management Component.

This module implements conversation thread creation and management,
message processing with multimedia support, and conversation-to-knowledge
conversion functionality.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass

from ...models.core import (
    ConversationThread, Message, MessageType, MultimediaElement,
    KnowledgeChunk, SourceType, ContentType, KnowledgeMetadata
)
from ...database.models import ConversationDB, MessageDB, KnowledgeSource
from ...database.connection import get_database_session

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
            with get_database_session() as session:
                # Query conversations for user
                db_conversations = session.query(ConversationDB).filter(
                    ConversationDB.user_id == user_id,
                    ConversationDB.is_active == True
                ).order_by(ConversationDB.last_updated.desc()).limit(limit).all()
                
                for db_conv in db_conversations:
                    # Load messages
                    messages = []
                    for db_msg in db_conv.messages:
                        multimedia_content = []
                        if db_msg.multimedia_content:
                            multimedia_content = [
                                MultimediaElement.from_dict(elem) 
                                for elem in db_msg.multimedia_content
                            ]
                        
                        message = Message(
                            message_id=db_msg.message_id,
                            content=db_msg.content,
                            multimedia_content=multimedia_content,
                            timestamp=db_msg.timestamp,
                            message_type=MessageType(db_msg.message_type),
                            knowledge_references=db_msg.knowledge_references or []
                        )
                        messages.append(message)
                    
                    conversation = ConversationThread(
                        thread_id=db_conv.thread_id,
                        user_id=db_conv.user_id,
                        messages=messages,
                        created_at=db_conv.created_at,
                        last_updated=db_conv.last_updated,
                        knowledge_summary=db_conv.knowledge_summary or ""
                    )
                    conversations.append(conversation)
        
        except Exception as e:
            logger.error(f"Failed to list conversations for user {user_id}: {e}")
        
        return conversations
    
    def process_message(self, thread_id: str, message_content: str,
                       multimedia_content: Optional[List[MultimediaElement]] = None,
                       message_type: MessageType = MessageType.USER) -> ConversationContext:
        """
        Process user message with conversation context.
        
        Args:
            thread_id: Conversation thread identifier
            message_content: Text content of the message
            multimedia_content: Optional multimedia elements
            message_type: Type of message (user, system, upload)
            
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
            knowledge_references=[]
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
    
    def convert_to_knowledge_chunks(self, conversation: ConversationThread) -> List[KnowledgeChunk]:
        """
        Convert conversation to searchable knowledge chunks.
        
        Args:
            conversation: Conversation thread to convert
            
        Returns:
            List of KnowledgeChunk objects
        """
        chunks = []
        
        try:
            # Group messages into meaningful chunks
            message_groups = self._group_messages_for_chunking(conversation.messages)
            
            for i, group in enumerate(message_groups):
                # Combine messages in group
                combined_content = self._combine_message_group(group)
                
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
                    total_chunks=len(message_groups)
                )
                
                # Create knowledge chunk
                chunk = KnowledgeChunk(
                    id=f"conv_{conversation.thread_id}_chunk_{i}",
                    content=combined_content,
                    source_type=SourceType.CONVERSATION,
                    source_id=conversation.thread_id,
                    location_reference=group[0].timestamp.isoformat(),  # Use first message timestamp
                    section=f"Messages {group[0].message_id} to {group[-1].message_id}",
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
            conversation = self.get_conversation(thread_id)
            if not conversation or conversation.user_id != user_id:
                return False
            
            # Remove from active conversations
            if thread_id in self.active_conversations:
                del self.active_conversations[thread_id]
            
            # Mark as inactive in database
            with get_database_session() as session:
                db_conversation = session.query(ConversationDB).filter(
                    ConversationDB.thread_id == thread_id
                ).first()
                
                if db_conversation:
                    db_conversation.is_active = False
                    session.commit()
            
            logger.info(f"Deleted conversation {thread_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to delete conversation {thread_id}: {e}")
            return False
    
    def _create_conversation_context(self, conversation: ConversationThread) -> ConversationContext:
        """Create conversation context for processing."""
        
        # Get recent messages (last 10)
        recent_messages = conversation.messages[-10:] if len(conversation.messages) > 10 else conversation.messages
        
        # Extract knowledge references
        knowledge_references = []
        for message in recent_messages:
            knowledge_references.extend(message.knowledge_references)
        
        # Extract multimedia elements
        multimedia_elements = []
        for message in recent_messages:
            multimedia_elements.extend(message.multimedia_content)
        
        # Create context summary
        context_summary = self._create_context_summary(recent_messages)
        
        return ConversationContext(
            thread=conversation,
            recent_messages=recent_messages,
            knowledge_references=list(set(knowledge_references)),  # Remove duplicates
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
    
    def _combine_message_group(self, messages: List[Message]) -> str:
        """Combine messages in a group into coherent content."""
        content_parts = []
        
        for message in messages:
            timestamp_str = message.timestamp.strftime("%Y-%m-%d %H:%M")
            message_type_str = message.message_type.value.upper()
            
            content_parts.append(f"[{timestamp_str}] {message_type_str}: {message.content}")
            
            # Add multimedia descriptions
            for elem in message.multimedia_content:
                content_parts.append(f"[MULTIMEDIA: {elem.element_type} - {elem.filename or 'unnamed'}]")
        
        return "\n".join(content_parts)
    
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
        """Persist conversation to database."""
        try:
            with get_database_session() as session:
                # Create knowledge source entry
                knowledge_source = KnowledgeSource(
                    source_type='conversation',
                    title=f"Conversation {conversation.thread_id[:8]}",
                    author=conversation.user_id,
                    created_at=conversation.created_at,
                    updated_at=conversation.last_updated
                )
                session.add(knowledge_source)
                session.flush()  # Get the ID
                
                # Create conversation entry
                db_conversation = ConversationDB(
                    thread_id=conversation.thread_id,
                    user_id=conversation.user_id,
                    source_id=knowledge_source.id,
                    knowledge_summary=conversation.knowledge_summary,
                    created_at=conversation.created_at,
                    last_updated=conversation.last_updated
                )
                session.add(db_conversation)
                session.commit()
        
        except Exception as e:
            logger.error(f"Failed to persist conversation {conversation.thread_id}: {e}")
    
    def _persist_message(self, conversation: ConversationThread, message: Message):
        """Persist message to database."""
        try:
            with get_database_session() as session:
                # Get conversation from database
                db_conversation = session.query(ConversationDB).filter(
                    ConversationDB.thread_id == conversation.thread_id
                ).first()
                
                if db_conversation:
                    # Convert multimedia content to JSON
                    multimedia_json = None
                    if message.multimedia_content:
                        multimedia_json = [elem.to_dict() for elem in message.multimedia_content]
                    
                    # Create message entry
                    db_message = MessageDB(
                        message_id=message.message_id,
                        conversation_id=db_conversation.id,
                        content=message.content,
                        message_type=message.message_type.value,
                        multimedia_content=multimedia_json,
                        knowledge_references=message.knowledge_references,
                        timestamp=message.timestamp
                    )
                    session.add(db_message)
                    
                    # Update conversation last_updated
                    db_conversation.last_updated = message.timestamp
                    
                    session.commit()
        
        except Exception as e:
            logger.error(f"Failed to persist message {message.message_id}: {e}")
    
    def _load_conversation(self, thread_id: str) -> Optional[ConversationThread]:
        """Load conversation from database."""
        try:
            with get_database_session() as session:
                db_conversation = session.query(ConversationDB).filter(
                    ConversationDB.thread_id == thread_id,
                    ConversationDB.is_active == True
                ).first()
                
                if not db_conversation:
                    return None
                
                # Load messages
                messages = []
                for db_msg in db_conversation.messages:
                    multimedia_content = []
                    if db_msg.multimedia_content:
                        multimedia_content = [
                            MultimediaElement.from_dict(elem) 
                            for elem in db_msg.multimedia_content
                        ]
                    
                    message = Message(
                        message_id=db_msg.message_id,
                        content=db_msg.content,
                        multimedia_content=multimedia_content,
                        timestamp=db_msg.timestamp,
                        message_type=MessageType(db_msg.message_type),
                        knowledge_references=db_msg.knowledge_references or []
                    )
                    messages.append(message)
                
                return ConversationThread(
                    thread_id=db_conversation.thread_id,
                    user_id=db_conversation.user_id,
                    messages=messages,
                    created_at=db_conversation.created_at,
                    last_updated=db_conversation.last_updated,
                    knowledge_summary=db_conversation.knowledge_summary or ""
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
            with get_database_session() as session:
                # Query conversations for user with pagination
                db_conversations = session.query(ConversationDB).filter(
                    ConversationDB.user_id == user_id,
                    ConversationDB.is_active == True
                ).order_by(ConversationDB.last_updated.desc()).offset(offset).limit(limit).all()
                
                conversations = []
                for db_conv in db_conversations:
                    # Load messages
                    messages = []
                    for db_msg in db_conv.messages:
                        multimedia_content = []
                        if db_msg.multimedia_content:
                            multimedia_content = [
                                MultimediaElement.from_dict(elem) 
                                for elem in db_msg.multimedia_content
                            ]
                        
                        message = Message(
                            message_id=db_msg.message_id,
                            content=db_msg.content,
                            multimedia_content=multimedia_content,
                            timestamp=db_msg.timestamp,
                            message_type=MessageType(db_msg.message_type),
                            knowledge_references=db_msg.knowledge_references or []
                        )
                        messages.append(message)
                    
                    conversation = ConversationThread(
                        thread_id=db_conv.thread_id,
                        user_id=db_conv.user_id,
                        messages=messages,
                        created_at=db_conv.created_at,
                        last_updated=db_conv.last_updated,
                        knowledge_summary=db_conv.knowledge_summary or ""
                    )
                    conversations.append(conversation)
                
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
            with get_database_session() as session:
                count = session.query(ConversationDB).filter(
                    ConversationDB.user_id == user_id,
                    ConversationDB.is_active == True
                ).count()
                return count
        
        except Exception as e:
            logger.error(f"Failed to count conversations for user {user_id}: {e}")
            return 0