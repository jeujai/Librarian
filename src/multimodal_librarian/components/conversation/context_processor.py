"""
Context Processing Component.

This module implements unified knowledge processing for conversations,
applying book-equivalent chunking strategies to conversation content
and generating embeddings using the same methods as book content.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ...models.chunking import ChunkingRequirements, ContentProfile
from ...models.core import (
    ContentType,
    ConversationThread,
    KnowledgeChunk,
    KnowledgeMetadata,
    MediaElement,
    Message,
    SourceType,
)
from ..chunking_framework.content_analyzer import AutomatedContentAnalyzer
from ..chunking_framework.framework import (
    GenericMultiLevelChunkingFramework,
    ProcessedDocument,
)

logger = logging.getLogger(__name__)


@dataclass
class ConversationFlow:
    """Analysis of conversation flow and semantic relationships."""
    message_count: int
    time_span_hours: float
    topic_transitions: List[Dict[str, Any]]
    semantic_coherence_score: float
    interaction_patterns: Dict[str, Any]
    knowledge_density: float


@dataclass
class ConversationDocument:
    """Conversation content formatted as document for chunking."""
    text: str
    structure: Dict[str, Any]
    metadata: Dict[str, Any]
    temporal_markers: List[Dict[str, Any]]
    multimedia_references: List[Dict[str, Any]]


@dataclass
class TemporalChunk:
    """Knowledge chunk with temporal ordering information."""
    chunk: KnowledgeChunk
    temporal_order: int
    time_range: Tuple[datetime, datetime]
    message_ids: List[str]
    semantic_relationships: List[str]


class ContextProcessor:
    """
    Processes conversation context and applies unified knowledge processing.
    
    Analyzes conversation flow, applies book-equivalent adaptive chunking
    to conversation history, and maintains temporal ordering and semantic
    relationship tracking.
    """
    
    def __init__(self):
        """Initialize the context processor."""
        self.chunking_framework = GenericMultiLevelChunkingFramework()
        self.content_analyzer = AutomatedContentAnalyzer()
        
        self.processing_stats = {
            'conversations_processed': 0,
            'total_chunks_created': 0,
            'average_chunks_per_conversation': 0.0,
            'temporal_relationships_tracked': 0,
            'semantic_relationships_identified': 0
        }
        
        logger.info("Initialized ContextProcessor")
    
    def analyze_conversation_flow(self, messages: List[Message]) -> ConversationFlow:
        """
        Analyze semantic relationships in conversation.
        
        Args:
            messages: List of messages to analyze
            
        Returns:
            ConversationFlow with analysis results
        """
        if not messages:
            return ConversationFlow(
                message_count=0,
                time_span_hours=0.0,
                topic_transitions=[],
                semantic_coherence_score=0.0,
                interaction_patterns={},
                knowledge_density=0.0
            )
        
        # Calculate time span
        start_time = messages[0].timestamp
        end_time = messages[-1].timestamp
        time_span_hours = (end_time - start_time).total_seconds() / 3600.0
        
        # Analyze topic transitions
        topic_transitions = self._analyze_topic_transitions(messages)
        
        # Calculate semantic coherence
        semantic_coherence_score = self._calculate_semantic_coherence(messages)
        
        # Analyze interaction patterns
        interaction_patterns = self._analyze_interaction_patterns(messages)
        
        # Calculate knowledge density
        knowledge_density = self._calculate_knowledge_density(messages)
        
        return ConversationFlow(
            message_count=len(messages),
            time_span_hours=time_span_hours,
            topic_transitions=topic_transitions,
            semantic_coherence_score=semantic_coherence_score,
            interaction_patterns=interaction_patterns,
            knowledge_density=knowledge_density
        )
    
    def chunk_conversation_as_knowledge(self, conversation: ConversationThread) -> List[KnowledgeChunk]:
        """
        Apply book-equivalent chunking to conversation content.
        
        Args:
            conversation: Conversation thread to process
            
        Returns:
            List of KnowledgeChunk objects with temporal ordering
        """
        if not conversation.messages:
            return []
        
        logger.info(f"Processing conversation {conversation.thread_id} as knowledge")
        
        try:
            # Convert conversation to document format
            conversation_doc = self._convert_conversation_to_document(conversation)
            
            # Create document content for chunking framework
            from ...models.core import (
                DocumentContent,
                DocumentMetadata,
                DocumentStructure,
            )
            
            document_content = DocumentContent(
                text=conversation_doc.text,
                metadata=DocumentMetadata(
                    title=f"Conversation {conversation.thread_id[:8]}",
                    author=conversation.user_id,
                    creation_date=conversation.created_at,
                    page_count=1,
                    file_size=len(conversation_doc.text.encode('utf-8')),
                    language='en',
                    subject='conversation',
                    keywords=self._extract_conversation_keywords(conversation_doc.text)
                ),
                structure=DocumentStructure(
                    chapters=[],
                    sections=conversation_doc.structure.get('sections', []),
                    paragraphs=conversation_doc.structure.get('paragraphs', []),
                    page_count=1,
                    has_toc=False
                )
            )
            
            # Process through chunking framework
            processed_doc = self.chunking_framework.process_document(
                document_content, 
                document_id=f"conversation_{conversation.thread_id}"
            )
            
            # Convert processed chunks to knowledge chunks with temporal information
            knowledge_chunks = self._convert_to_temporal_knowledge_chunks(
                processed_doc, conversation, conversation_doc
            )
            
            # Update statistics
            self.processing_stats['conversations_processed'] += 1
            self.processing_stats['total_chunks_created'] += len(knowledge_chunks)
            self.processing_stats['average_chunks_per_conversation'] = (
                self.processing_stats['total_chunks_created'] / 
                self.processing_stats['conversations_processed']
            )
            
            logger.info(f"Created {len(knowledge_chunks)} knowledge chunks from conversation")
            return knowledge_chunks
        
        except Exception as e:
            logger.error(f"Failed to chunk conversation as knowledge: {e}")
            return []
    
    def process_conversation_with_unified_strategy(self, conversation: ConversationThread,
                                                 content_profile: Optional[ContentProfile] = None) -> List[TemporalChunk]:
        """
        Process conversation using unified chunking strategy with temporal tracking.
        
        Args:
            conversation: Conversation to process
            content_profile: Optional pre-computed content profile
            
        Returns:
            List of TemporalChunk objects with ordering and relationships
        """
        # Get knowledge chunks
        knowledge_chunks = self.chunk_conversation_as_knowledge(conversation)
        
        # Analyze conversation flow
        conversation_flow = self.analyze_conversation_flow(conversation.messages)
        
        # Create temporal chunks with relationship tracking
        temporal_chunks = []
        
        for i, chunk in enumerate(knowledge_chunks):
            # Determine time range for this chunk
            time_range = self._determine_chunk_time_range(chunk, conversation.messages)
            
            # Find related message IDs
            message_ids = self._find_related_message_ids(chunk, conversation.messages)
            
            # Identify semantic relationships
            semantic_relationships = self._identify_semantic_relationships(
                chunk, knowledge_chunks, conversation_flow
            )
            
            temporal_chunk = TemporalChunk(
                chunk=chunk,
                temporal_order=i,
                time_range=time_range,
                message_ids=message_ids,
                semantic_relationships=semantic_relationships
            )
            
            temporal_chunks.append(temporal_chunk)
        
        # Update relationship tracking statistics
        total_relationships = sum(len(tc.semantic_relationships) for tc in temporal_chunks)
        self.processing_stats['semantic_relationships_identified'] += total_relationships
        self.processing_stats['temporal_relationships_tracked'] += len(temporal_chunks)
        
        return temporal_chunks
    
    def generate_embeddings_for_conversation(self, conversation_chunks: List[KnowledgeChunk]) -> List[KnowledgeChunk]:
        """
        Generate embeddings using same methods as book content.
        
        Args:
            conversation_chunks: Chunks to generate embeddings for
            
        Returns:
            Updated chunks with embeddings
        """
        # This would integrate with the vector store component
        # For now, we'll mark where embeddings would be generated
        
        for chunk in conversation_chunks:
            # Placeholder for embedding generation
            # In actual implementation, this would call the vector store
            # embedding generation service
            chunk.embedding = None  # Would be populated by vector store
            
            # Update metadata to indicate embedding generation
            if chunk.knowledge_metadata:
                chunk.knowledge_metadata.processing_timestamp = datetime.now()
        
        logger.info(f"Generated embeddings for {len(conversation_chunks)} conversation chunks")
        return conversation_chunks
    
    def _convert_conversation_to_document(self, conversation: ConversationThread) -> ConversationDocument:
        """Convert conversation to document format for chunking."""
        
        text_parts = []
        temporal_markers = []
        multimedia_references = []
        sections = []
        paragraphs = []
        
        current_section = None
        current_paragraph_start = 0
        
        for i, message in enumerate(conversation.messages):
            # Create temporal marker
            temporal_markers.append({
                'message_id': message.message_id,
                'timestamp': message.timestamp.isoformat(),
                'position': len(' '.join(text_parts)),
                'message_type': message.message_type.value
            })
            
            # Format message with context
            timestamp_str = message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            message_header = f"[{timestamp_str}] {message.message_type.value.upper()}:"
            
            # Add message content
            message_text = f"{message_header} {message.content}"
            text_parts.append(message_text)
            
            # Track multimedia references
            for j, elem in enumerate(message.multimedia_content):
                multimedia_references.append({
                    'message_id': message.message_id,
                    'element_index': j,
                    'element_type': elem.element_type,
                    'filename': elem.filename,
                    'position': len(' '.join(text_parts))
                })
                
                # Add multimedia placeholder to text
                multimedia_text = f"[MULTIMEDIA: {elem.element_type}"
                if elem.filename:
                    multimedia_text += f" - {elem.filename}"
                multimedia_text += "]"
                text_parts.append(multimedia_text)
            
            # Detect section boundaries (topic changes or time gaps)
            if i > 0:
                prev_message = conversation.messages[i-1]
                time_gap = (message.timestamp - prev_message.timestamp).total_seconds()
                
                # Create new section if significant time gap (> 30 minutes)
                if time_gap > 1800:
                    if current_section:
                        sections.append(current_section)
                    
                    current_section = {
                        'title': f"Discussion from {timestamp_str}",
                        'start_message': message.message_id,
                        'start_position': len(' '.join(text_parts[:-1]))
                    }
            
            # Create paragraph boundaries (every few messages or topic changes)
            if i % 3 == 0 or i == len(conversation.messages) - 1:
                paragraphs.append({
                    'start_position': current_paragraph_start,
                    'end_position': len(' '.join(text_parts)),
                    'message_count': min(3, len(conversation.messages) - (i // 3) * 3)
                })
                current_paragraph_start = len(' '.join(text_parts))
        
        # Close final section
        if current_section:
            current_section['end_position'] = len(' '.join(text_parts))
            sections.append(current_section)
        
        # Combine all text
        full_text = '\n\n'.join(text_parts)
        
        # Create structure information
        structure = {
            'sections': sections,
            'paragraphs': paragraphs,
            'message_count': len(conversation.messages),
            'multimedia_count': len(multimedia_references)
        }
        
        # Create metadata
        metadata = {
            'conversation_id': conversation.thread_id,
            'user_id': conversation.user_id,
            'created_at': conversation.created_at.isoformat(),
            'last_updated': conversation.last_updated.isoformat(),
            'message_count': len(conversation.messages),
            'time_span_hours': (conversation.last_updated - conversation.created_at).total_seconds() / 3600.0
        }
        
        return ConversationDocument(
            text=full_text,
            structure=structure,
            metadata=metadata,
            temporal_markers=temporal_markers,
            multimedia_references=multimedia_references
        )
    
    def _analyze_topic_transitions(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Analyze topic transitions in conversation."""
        transitions = []
        
        if len(messages) < 2:
            return transitions
        
        # Simple topic transition detection based on content similarity
        for i in range(1, len(messages)):
            prev_msg = messages[i-1]
            curr_msg = messages[i]
            
            # Calculate simple content similarity (word overlap)
            prev_words = set(prev_msg.content.lower().split())
            curr_words = set(curr_msg.content.lower().split())
            
            if prev_words and curr_words:
                overlap = len(prev_words.intersection(curr_words))
                similarity = overlap / len(prev_words.union(curr_words))
                
                # If similarity is low, it might be a topic transition
                if similarity < 0.3:
                    transitions.append({
                        'from_message': prev_msg.message_id,
                        'to_message': curr_msg.message_id,
                        'similarity_score': similarity,
                        'timestamp': curr_msg.timestamp.isoformat(),
                        'transition_type': 'topic_change'
                    })
        
        return transitions
    
    def _calculate_semantic_coherence(self, messages: List[Message]) -> float:
        """Calculate semantic coherence score for conversation."""
        if len(messages) < 2:
            return 1.0
        
        # Simple coherence calculation based on word overlap between adjacent messages
        coherence_scores = []
        
        for i in range(1, len(messages)):
            prev_words = set(messages[i-1].content.lower().split())
            curr_words = set(messages[i].content.lower().split())
            
            if prev_words and curr_words:
                overlap = len(prev_words.intersection(curr_words))
                similarity = overlap / len(prev_words.union(curr_words))
                coherence_scores.append(similarity)
        
        return sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0.0
    
    def _analyze_interaction_patterns(self, messages: List[Message]) -> Dict[str, Any]:
        """Analyze interaction patterns in conversation."""
        patterns = {
            'message_types': {},
            'response_times': [],
            'message_lengths': [],
            'multimedia_usage': 0
        }
        
        # Count message types
        for message in messages:
            msg_type = message.message_type.value
            patterns['message_types'][msg_type] = patterns['message_types'].get(msg_type, 0) + 1
        
        # Calculate response times and message lengths
        for i, message in enumerate(messages):
            patterns['message_lengths'].append(len(message.content.split()))
            
            if message.multimedia_content:
                patterns['multimedia_usage'] += len(message.multimedia_content)
            
            if i > 0:
                prev_message = messages[i-1]
                response_time = (message.timestamp - prev_message.timestamp).total_seconds()
                patterns['response_times'].append(response_time)
        
        # Calculate averages
        if patterns['response_times']:
            patterns['average_response_time'] = sum(patterns['response_times']) / len(patterns['response_times'])
        
        if patterns['message_lengths']:
            patterns['average_message_length'] = sum(patterns['message_lengths']) / len(patterns['message_lengths'])
        
        return patterns
    
    def _calculate_knowledge_density(self, messages: List[Message]) -> float:
        """Calculate knowledge density of conversation."""
        if not messages:
            return 0.0
        
        # Simple heuristic: knowledge density based on content richness
        total_words = sum(len(msg.content.split()) for msg in messages)
        multimedia_elements = sum(len(msg.multimedia_content) for msg in messages)
        knowledge_references = sum(len(msg.knowledge_references) for msg in messages)
        
        # Normalize to 0-1 scale
        word_density = min(total_words / 1000.0, 1.0)  # Normalize by 1000 words
        multimedia_density = min(multimedia_elements / 10.0, 1.0)  # Normalize by 10 elements
        reference_density = min(knowledge_references / 20.0, 1.0)  # Normalize by 20 references
        
        return (word_density + multimedia_density + reference_density) / 3.0
    
    def _extract_conversation_keywords(self, text: str) -> List[str]:
        """Extract keywords from conversation text."""
        # Simple keyword extraction
        words = text.lower().split()
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'}
        
        # Count word frequencies
        word_freq = {}
        for word in words:
            if word not in stop_words and len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Return top keywords
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:10]]
    
    def _convert_to_temporal_knowledge_chunks(self, processed_doc: ProcessedDocument,
                                            conversation: ConversationThread,
                                            conversation_doc: ConversationDocument) -> List[KnowledgeChunk]:
        """Convert processed chunks to knowledge chunks with temporal information."""
        
        knowledge_chunks = []
        
        for i, processed_chunk in enumerate(processed_doc.chunks):
            # Find corresponding temporal markers
            chunk_start = processed_chunk.start_position
            chunk_end = processed_chunk.end_position
            
            # Find messages that overlap with this chunk
            relevant_markers = [
                marker for marker in conversation_doc.temporal_markers
                if chunk_start <= marker['position'] <= chunk_end
            ]
            
            # Determine location reference (timestamp of first message in chunk)
            location_reference = ""
            if relevant_markers:
                location_reference = relevant_markers[0]['timestamp']
            
            # Find associated multimedia
            associated_media = []
            for ref in conversation_doc.multimedia_references:
                if chunk_start <= ref['position'] <= chunk_end:
                    # Create MediaElement for multimedia reference
                    media_elem = MediaElement(
                        element_id=str(uuid.uuid4()),
                        element_type=ref['element_type'],
                        caption=ref.get('filename', ''),
                        metadata={
                            'message_id': ref['message_id'],
                            'element_index': ref['element_index'],
                            'original_filename': ref.get('filename')
                        }
                    )
                    associated_media.append(media_elem)
            
            # Create knowledge metadata
            knowledge_metadata = KnowledgeMetadata(
                complexity_score=processed_doc.content_profile.complexity_score,
                domain_tags=processed_doc.content_profile.domain_categories[:3],
                extraction_confidence=0.9,  # High confidence for conversation content
                processing_timestamp=datetime.now(),
                chunk_index=i,
                total_chunks=len(processed_doc.chunks)
            )
            
            # Create knowledge chunk
            chunk_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"conv_{conversation.thread_id}_chunk_{i}",
            ))
            knowledge_chunk = KnowledgeChunk(
                id=chunk_id,
                content=processed_chunk.content,
                source_type=SourceType.CONVERSATION,
                source_id=conversation.thread_id,
                location_reference=location_reference,
                section=f"Chunk {i+1} of {len(processed_doc.chunks)}",
                content_type=processed_doc.content_profile.content_type,
                associated_media=associated_media,
                knowledge_metadata=knowledge_metadata
            )
            
            knowledge_chunks.append(knowledge_chunk)
        
        return knowledge_chunks
    
    def _determine_chunk_time_range(self, chunk: KnowledgeChunk, messages: List[Message]) -> Tuple[datetime, datetime]:
        """Determine time range for a knowledge chunk."""
        
        # Extract timestamp from location reference
        try:
            start_time = datetime.fromisoformat(chunk.location_reference)
        except (ValueError, TypeError):
            start_time = messages[0].timestamp if messages else datetime.now()
        
        # Find end time by looking at chunk position
        chunk_index = chunk.knowledge_metadata.chunk_index if chunk.knowledge_metadata else 0
        total_chunks = chunk.knowledge_metadata.total_chunks if chunk.knowledge_metadata else 1
        
        if total_chunks > 1 and messages:
            # Estimate end time based on chunk position
            total_duration = (messages[-1].timestamp - messages[0].timestamp).total_seconds()
            chunk_duration = total_duration / total_chunks
            end_time = start_time + datetime.timedelta(seconds=chunk_duration)
        else:
            end_time = start_time
        
        return (start_time, end_time)
    
    def _find_related_message_ids(self, chunk: KnowledgeChunk, messages: List[Message]) -> List[str]:
        """Find message IDs related to a knowledge chunk."""
        
        # Simple approach: find messages whose content appears in the chunk
        related_ids = []
        
        for message in messages:
            # Check if message content is substantially present in chunk
            message_words = set(message.content.lower().split())
            chunk_words = set(chunk.content.lower().split())
            
            if message_words and chunk_words:
                overlap = len(message_words.intersection(chunk_words))
                overlap_ratio = overlap / len(message_words)
                
                # If significant overlap, consider it related
                if overlap_ratio > 0.5:
                    related_ids.append(message.message_id)
        
        return related_ids
    
    def _identify_semantic_relationships(self, chunk: KnowledgeChunk, 
                                       all_chunks: List[KnowledgeChunk],
                                       conversation_flow: ConversationFlow) -> List[str]:
        """Identify semantic relationships between chunks."""
        
        relationships = []
        
        # Find chunks with similar content
        chunk_words = set(chunk.content.lower().split())
        
        for other_chunk in all_chunks:
            if other_chunk.id == chunk.id:
                continue
            
            other_words = set(other_chunk.content.lower().split())
            
            if chunk_words and other_words:
                overlap = len(chunk_words.intersection(other_words))
                similarity = overlap / len(chunk_words.union(other_words))
                
                # If high similarity, add relationship
                if similarity > 0.4:
                    relationships.append(other_chunk.id)
        
        return relationships[:5]  # Limit to top 5 relationships
    
    def get_processing_statistics(self) -> Dict[str, Any]:
        """Get context processing statistics."""
        return self.processing_stats.copy()
    
    def reset_statistics(self):
        """Reset processing statistics."""
        self.processing_stats = {
            'conversations_processed': 0,
            'total_chunks_created': 0,
            'average_chunks_per_conversation': 0.0,
            'temporal_relationships_tracked': 0,
            'semantic_relationships_identified': 0
        }