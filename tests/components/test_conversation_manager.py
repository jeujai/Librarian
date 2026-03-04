"""
Tests for the Conversation Management Component.

This module contains tests for conversation thread management,
message processing, and conversation-to-knowledge conversion.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
import uuid

from src.multimodal_librarian.components.conversation import (
    ConversationManager, ContextProcessor, MultimediaInput, ProcessedInput
)
from src.multimodal_librarian.models.core import (
    ConversationThread, Message, MessageType, MultimediaElement,
    KnowledgeChunk, SourceType, ContentType
)


class TestConversationManager:
    """Test cases for ConversationManager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = ConversationManager()
        self.test_user_id = "test_user_123"
    
    def test_start_conversation(self):
        """Test starting a new conversation."""
        # Test without initial message
        conversation = self.manager.start_conversation(self.test_user_id)
        
        assert conversation.user_id == self.test_user_id
        assert conversation.thread_id is not None
        assert len(conversation.messages) == 0
        assert conversation.thread_id in self.manager.active_conversations
    
    def test_start_conversation_with_initial_message(self):
        """Test starting a conversation with initial message."""
        initial_message = "Hello, I need help with something."
        
        conversation = self.manager.start_conversation(
            self.test_user_id, initial_message
        )
        
        assert len(conversation.messages) == 1
        assert conversation.messages[0].content == initial_message
        assert conversation.messages[0].message_type == MessageType.USER
    
    def test_process_message(self):
        """Test processing a message in conversation."""
        # Start conversation
        conversation = self.manager.start_conversation(self.test_user_id)
        
        # Process message
        message_content = "What is machine learning?"
        context = self.manager.process_message(
            conversation.thread_id, message_content
        )
        
        assert context.thread.thread_id == conversation.thread_id
        assert len(context.recent_messages) == 1
        assert context.recent_messages[0].content == message_content
        assert message_content in context.context_summary
    
    def test_accept_multimedia_input_text(self):
        """Test accepting text input."""
        input_data = MultimediaInput(
            input_type="text",
            content="This is a text message"
        )
        
        result = self.manager.accept_multimedia_input(input_data)
        
        assert result.text_content == "This is a text message"
        assert len(result.multimedia_elements) == 0
        assert "Processed text input" in result.processing_notes
    
    def test_accept_multimedia_input_image(self):
        """Test accepting image input."""
        input_data = MultimediaInput(
            input_type="image",
            content=b"fake_image_data",
            filename="test.jpg",
            mime_type="image/jpeg"
        )
        
        result = self.manager.accept_multimedia_input(input_data)
        
        assert "[Image uploaded: test.jpg]" in result.text_content
        assert len(result.multimedia_elements) == 1
        assert result.multimedia_elements[0].element_type == "image"
        assert result.multimedia_elements[0].filename == "test.jpg"
    
    def test_convert_to_knowledge_chunks(self):
        """Test converting conversation to knowledge chunks."""
        # Create conversation with messages
        conversation = ConversationThread(
            thread_id=str(uuid.uuid4()),
            user_id=self.test_user_id,
            messages=[
                Message(
                    message_id=str(uuid.uuid4()),
                    content="What is artificial intelligence?",
                    timestamp=datetime.now(),
                    message_type=MessageType.USER
                ),
                Message(
                    message_id=str(uuid.uuid4()),
                    content="AI is a field of computer science focused on creating intelligent machines.",
                    timestamp=datetime.now(),
                    message_type=MessageType.SYSTEM
                )
            ]
        )
        
        chunks = self.manager.convert_to_knowledge_chunks(conversation)
        
        assert len(chunks) > 0
        assert all(isinstance(chunk, KnowledgeChunk) for chunk in chunks)
        assert all(chunk.source_type == SourceType.CONVERSATION for chunk in chunks)
        assert all(chunk.source_id == conversation.thread_id for chunk in chunks)
    
    def test_get_conversation_statistics(self):
        """Test getting conversation statistics."""
        stats = self.manager.get_conversation_statistics()
        
        assert 'total_conversations' in stats
        assert 'total_messages' in stats
        assert 'multimedia_messages' in stats
        assert 'knowledge_chunks_created' in stats
        assert 'average_messages_per_conversation' in stats


class TestContextProcessor:
    """Test cases for ContextProcessor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = ContextProcessor()
    
    def test_analyze_conversation_flow_empty(self):
        """Test analyzing empty conversation flow."""
        flow = self.processor.analyze_conversation_flow([])
        
        assert flow.message_count == 0
        assert flow.time_span_hours == 0.0
        assert len(flow.topic_transitions) == 0
        assert flow.semantic_coherence_score == 0.0
    
    def test_analyze_conversation_flow_with_messages(self):
        """Test analyzing conversation flow with messages."""
        messages = [
            Message(
                message_id=str(uuid.uuid4()),
                content="Tell me about machine learning",
                timestamp=datetime(2024, 1, 1, 10, 0, 0),
                message_type=MessageType.USER
            ),
            Message(
                message_id=str(uuid.uuid4()),
                content="Machine learning is a subset of AI that focuses on algorithms",
                timestamp=datetime(2024, 1, 1, 10, 1, 0),
                message_type=MessageType.SYSTEM
            ),
            Message(
                message_id=str(uuid.uuid4()),
                content="What about deep learning?",
                timestamp=datetime(2024, 1, 1, 10, 2, 0),
                message_type=MessageType.USER
            )
        ]
        
        flow = self.processor.analyze_conversation_flow(messages)
        
        assert flow.message_count == 3
        assert flow.time_span_hours == pytest.approx(0.033, abs=0.01)  # ~2 minutes
        assert 'user' in flow.interaction_patterns['message_types']
        assert 'system' in flow.interaction_patterns['message_types']
        assert flow.semantic_coherence_score > 0.0
    
    @patch('src.multimodal_librarian.components.conversation.context_processor.GenericMultiLevelChunkingFramework')
    def test_chunk_conversation_as_knowledge(self, mock_framework_class):
        """Test chunking conversation as knowledge."""
        # Mock the chunking framework
        mock_framework = Mock()
        mock_framework_class.return_value = mock_framework
        
        # Mock processed document
        from src.multimodal_librarian.components.chunking_framework.framework import ProcessedDocument, ProcessedChunk
        from src.multimodal_librarian.models.chunking import ContentProfile
        
        mock_processed_doc = ProcessedDocument(
            document_id="test_doc",
            content_profile=ContentProfile(
                content_type=ContentType.GENERAL,
                domain_categories=["general"],
                complexity_score=0.5,
                structure_hierarchy={},
                domain_patterns={},
                cross_reference_density=0.0,
                conceptual_density=0.0,
                chunking_requirements=None
            ),
            domain_config=Mock(),
            chunks=[
                ProcessedChunk(
                    id="chunk_0",
                    content="Test chunk content",
                    start_position=0,
                    end_position=100
                )
            ],
            bridges=[],
            processing_stats={},
            processing_time=1.0
        )
        
        mock_framework.process_document.return_value = mock_processed_doc
        
        # Create test conversation
        conversation = ConversationThread(
            thread_id=str(uuid.uuid4()),
            user_id="test_user",
            messages=[
                Message(
                    message_id=str(uuid.uuid4()),
                    content="Test message",
                    timestamp=datetime.now(),
                    message_type=MessageType.USER
                )
            ]
        )
        
        # Test chunking
        chunks = self.processor.chunk_conversation_as_knowledge(conversation)
        
        assert len(chunks) > 0
        assert all(isinstance(chunk, KnowledgeChunk) for chunk in chunks)
        assert all(chunk.source_type == SourceType.CONVERSATION for chunk in chunks)
    
    def test_get_processing_statistics(self):
        """Test getting processing statistics."""
        stats = self.processor.get_processing_statistics()
        
        assert 'conversations_processed' in stats
        assert 'total_chunks_created' in stats
        assert 'average_chunks_per_conversation' in stats
        assert 'temporal_relationships_tracked' in stats
        assert 'semantic_relationships_identified' in stats


if __name__ == "__main__":
    pytest.main([__file__])