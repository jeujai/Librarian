"""
Core data models for the Multimodal Librarian system.

This module contains the fundamental data structures used throughout the application,
including document content, chunks, multimedia responses, and conversation models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Any, Union
import json
import numpy as np
from pathlib import Path


class SourceType(Enum):
    """Type of knowledge source."""
    BOOK = "book"
    CONVERSATION = "conversation"


class ContentType(Enum):
    """Type of content for adaptive processing."""
    TECHNICAL = "technical"
    LEGAL = "legal"
    MEDICAL = "medical"
    NARRATIVE = "narrative"
    ACADEMIC = "academic"
    GENERAL = "general"


class MessageType(Enum):
    """Type of message in conversation."""
    USER = "user"
    SYSTEM = "system"
    UPLOAD = "upload"


class GapType(Enum):
    """Type of conceptual gap between chunks."""
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    CROSS_REFERENCE = "cross_reference"


class BridgeStrategy(Enum):
    """Strategy for bridge generation."""
    GEMINI_FLASH = "gemini_flash"
    MECHANICAL_FALLBACK = "mechanical_fallback"
    SEMANTIC_OVERLAP = "semantic_overlap"


class SequenceType(Enum):
    """Type of chunk sequence for ML training."""
    TEMPORAL = "temporal"
    SEMANTIC = "semantic"
    CAUSAL = "causal"


class InteractionType(Enum):
    """Type of user interaction for feedback."""
    VIEW = "view"
    CITE = "cite"
    EXPORT = "export"
    RATE = "rate"


class RelationshipType(Enum):
    """Type of knowledge graph relationship."""
    CAUSAL = "causal"
    HIERARCHICAL = "hierarchical"
    ASSOCIATIVE = "associative"


@dataclass
class MediaElement:
    """Represents a media element (image, chart, etc.) in content."""
    element_id: str
    element_type: str  # image, chart, table, graph
    file_path: Optional[str] = None
    content_data: Optional[bytes] = None
    caption: Optional[str] = None
    alt_text: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'element_id': self.element_id,
            'element_type': self.element_type,
            'file_path': str(self.file_path) if self.file_path else None,
            'content_data': self.content_data.hex() if self.content_data else None,
            'caption': self.caption,
            'alt_text': self.alt_text,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MediaElement':
        """Create from dictionary for JSON deserialization."""
        return cls(
            element_id=data['element_id'],
            element_type=data['element_type'],
            file_path=Path(data['file_path']) if data.get('file_path') else None,
            content_data=bytes.fromhex(data['content_data']) if data.get('content_data') else None,
            caption=data.get('caption'),
            alt_text=data.get('alt_text'),
            metadata=data.get('metadata', {})
        )
    
    def validate(self) -> bool:
        """Validate media element data integrity."""
        if not self.element_id or not self.element_type:
            return False
        if not self.file_path and not self.content_data:
            return False
        return True


@dataclass
class DocumentStructure:
    """Represents the hierarchical structure of a document."""
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    sections: List[Dict[str, Any]] = field(default_factory=list)
    paragraphs: List[Dict[str, Any]] = field(default_factory=list)
    page_count: int = 0
    has_toc: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'chapters': self.chapters,
            'sections': self.sections,
            'paragraphs': self.paragraphs,
            'page_count': self.page_count,
            'has_toc': self.has_toc
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentStructure':
        """Create from dictionary for JSON deserialization."""
        return cls(
            chapters=data.get('chapters', []),
            sections=data.get('sections', []),
            paragraphs=data.get('paragraphs', []),
            page_count=data.get('page_count', 0),
            has_toc=data.get('has_toc', False)
        )


@dataclass
class DocumentMetadata:
    """Metadata for document content."""
    title: str
    author: Optional[str] = None
    creation_date: Optional[datetime] = None
    page_count: int = 0
    file_size: int = 0
    language: str = "en"
    subject: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'title': self.title,
            'author': self.author,
            'creation_date': self.creation_date.isoformat() if self.creation_date else None,
            'page_count': self.page_count,
            'file_size': self.file_size,
            'language': self.language,
            'subject': self.subject,
            'keywords': self.keywords
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentMetadata':
        """Create from dictionary for JSON deserialization."""
        creation_date = None
        if data.get('creation_date'):
            creation_date = datetime.fromisoformat(data['creation_date'])
        
        return cls(
            title=data['title'],
            author=data.get('author'),
            creation_date=creation_date,
            page_count=data.get('page_count', 0),
            file_size=data.get('file_size', 0),
            language=data.get('language', 'en'),
            subject=data.get('subject'),
            keywords=data.get('keywords', [])
        )
    
    def validate(self) -> bool:
        """Validate document metadata."""
        if not self.title:
            return False
        if self.file_size < 0 or self.page_count < 0:
            return False
        return True


@dataclass
class DocumentContent:
    """Represents extracted content from a document."""
    text: str
    images: List[MediaElement] = field(default_factory=list)
    tables: List[MediaElement] = field(default_factory=list)
    charts: List[MediaElement] = field(default_factory=list)
    metadata: Optional[DocumentMetadata] = None
    structure: Optional[DocumentStructure] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'text': self.text,
            'images': [img.to_dict() for img in self.images],
            'tables': [table.to_dict() for table in self.tables],
            'charts': [chart.to_dict() for chart in self.charts],
            'metadata': self.metadata.to_dict() if self.metadata else None,
            'structure': self.structure.to_dict() if self.structure else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentContent':
        """Create from dictionary for JSON deserialization."""
        return cls(
            text=data['text'],
            images=[MediaElement.from_dict(img) for img in data.get('images', [])],
            tables=[MediaElement.from_dict(table) for table in data.get('tables', [])],
            charts=[MediaElement.from_dict(chart) for chart in data.get('charts', [])],
            metadata=DocumentMetadata.from_dict(data['metadata']) if data.get('metadata') else None,
            structure=DocumentStructure.from_dict(data['structure']) if data.get('structure') else None
        )
    
    def validate(self) -> bool:
        """Validate document content integrity."""
        if not self.text and not self.images and not self.tables and not self.charts:
            return False
        
        # Validate all media elements
        for media_list in [self.images, self.tables, self.charts]:
            for media in media_list:
                if not media.validate():
                    return False
        
        # Validate metadata if present
        if self.metadata and not self.metadata.validate():
            return False
        
        return True
    
    def get_all_media(self) -> List[MediaElement]:
        """Get all media elements from the document."""
        return self.images + self.tables + self.charts
    
    def has_multimodal_content(self) -> bool:
        """Check if document contains multimedia content."""
        return len(self.get_all_media()) > 0


@dataclass
class KnowledgeMetadata:
    """Metadata for knowledge chunks."""
    complexity_score: float = 0.0
    domain_tags: List[str] = field(default_factory=list)
    extraction_confidence: float = 1.0
    processing_timestamp: datetime = field(default_factory=datetime.now)
    chunk_index: int = 0
    total_chunks: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'complexity_score': self.complexity_score,
            'domain_tags': self.domain_tags,
            'extraction_confidence': self.extraction_confidence,
            'processing_timestamp': self.processing_timestamp.isoformat(),
            'chunk_index': self.chunk_index,
            'total_chunks': self.total_chunks
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeMetadata':
        """Create from dictionary for JSON deserialization."""
        return cls(
            complexity_score=data.get('complexity_score', 0.0),
            domain_tags=data.get('domain_tags', []),
            extraction_confidence=data.get('extraction_confidence', 1.0),
            processing_timestamp=datetime.fromisoformat(data.get('processing_timestamp', datetime.now().isoformat())),
            chunk_index=data.get('chunk_index', 0),
            total_chunks=data.get('total_chunks', 1)
        )


@dataclass
class KnowledgeChunk:
    """Represents a chunk of knowledge from any source."""
    id: str
    content: str
    embedding: Optional[np.ndarray] = None
    source_type: SourceType = SourceType.BOOK
    source_id: str = ""
    location_reference: str = ""  # page_number for books, timestamp for conversations
    section: str = ""
    content_type: ContentType = ContentType.GENERAL
    associated_media: List[MediaElement] = field(default_factory=list)
    knowledge_metadata: Optional[KnowledgeMetadata] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'content': self.content,
            'embedding': self.embedding.tolist() if self.embedding is not None else None,
            'source_type': self.source_type.value,
            'source_id': self.source_id,
            'location_reference': self.location_reference,
            'section': self.section,
            'content_type': self.content_type.value,
            'associated_media': [media.to_dict() for media in self.associated_media],
            'knowledge_metadata': self.knowledge_metadata.to_dict() if self.knowledge_metadata else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeChunk':
        """Create from dictionary for JSON deserialization."""
        embedding = None
        if data.get('embedding'):
            embedding = np.array(data['embedding'])
        
        return cls(
            id=data['id'],
            content=data['content'],
            embedding=embedding,
            source_type=SourceType(data.get('source_type', 'book')),
            source_id=data.get('source_id', ''),
            location_reference=data.get('location_reference', ''),
            section=data.get('section', ''),
            content_type=ContentType(data.get('content_type', 'general')),
            associated_media=[MediaElement.from_dict(media) for media in data.get('associated_media', [])],
            knowledge_metadata=KnowledgeMetadata.from_dict(data['knowledge_metadata']) if data.get('knowledge_metadata') else None
        )
    
    def validate(self) -> bool:
        """Validate knowledge chunk data integrity."""
        if not self.id or not self.content:
            return False
        
        # Validate associated media
        for media in self.associated_media:
            if not media.validate():
                return False
        
        return True
    
    def get_word_count(self) -> int:
        """Get word count of the chunk content."""
        return len(self.content.split())
    
    def has_media(self) -> bool:
        """Check if chunk has associated media."""
        return len(self.associated_media) > 0


# Alias for backward compatibility
Chunk = KnowledgeChunk


@dataclass
class MultimediaElement:
    """Represents multimedia content in messages."""
    element_type: str  # text, image, document, data
    content: Union[str, bytes]
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        content_data = self.content
        if isinstance(self.content, bytes):
            content_data = self.content.hex()
        
        return {
            'element_type': self.element_type,
            'content': content_data,
            'filename': self.filename,
            'mime_type': self.mime_type,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MultimediaElement':
        """Create from dictionary for JSON deserialization."""
        content = data['content']
        if data.get('element_type') in ['image', 'document'] and isinstance(content, str):
            try:
                content = bytes.fromhex(content)
            except ValueError:
                pass  # Keep as string if not hex
        
        return cls(
            element_type=data['element_type'],
            content=content,
            filename=data.get('filename'),
            mime_type=data.get('mime_type'),
            metadata=data.get('metadata', {})
        )


@dataclass
class Message:
    """Represents a message in a conversation."""
    message_id: str
    content: str
    multimedia_content: List[MultimediaElement] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    message_type: MessageType = MessageType.USER
    knowledge_references: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'message_id': self.message_id,
            'content': self.content,
            'multimedia_content': [elem.to_dict() for elem in self.multimedia_content],
            'timestamp': self.timestamp.isoformat(),
            'message_type': self.message_type.value,
            'knowledge_references': self.knowledge_references
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create from dictionary for JSON deserialization."""
        return cls(
            message_id=data['message_id'],
            content=data['content'],
            multimedia_content=[MultimediaElement.from_dict(elem) for elem in data.get('multimedia_content', [])],
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())),
            message_type=MessageType(data.get('message_type', 'user')),
            knowledge_references=data.get('knowledge_references', [])
        )
    
    def validate(self) -> bool:
        """Validate message data integrity."""
        if not self.message_id or not self.content:
            return False
        return True
    
    def has_multimedia(self) -> bool:
        """Check if message contains multimedia content."""
        return len(self.multimedia_content) > 0


@dataclass
class ConversationThread:
    """Represents a conversation thread."""
    thread_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    knowledge_summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'thread_id': self.thread_id,
            'user_id': self.user_id,
            'messages': [msg.to_dict() for msg in self.messages],
            'created_at': self.created_at.isoformat(),
            'last_updated': self.last_updated.isoformat(),
            'knowledge_summary': self.knowledge_summary
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationThread':
        """Create from dictionary for JSON deserialization."""
        return cls(
            thread_id=data['thread_id'],
            user_id=data['user_id'],
            messages=[Message.from_dict(msg) for msg in data.get('messages', [])],
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            last_updated=datetime.fromisoformat(data.get('last_updated', datetime.now().isoformat())),
            knowledge_summary=data.get('knowledge_summary', '')
        )
    
    def validate(self) -> bool:
        """Validate conversation thread data integrity."""
        if not self.thread_id or not self.user_id:
            return False
        
        # Validate all messages
        for message in self.messages:
            if not message.validate():
                return False
        
        return True
    
    def add_message(self, message: Message) -> None:
        """Add a message to the conversation."""
        self.messages.append(message)
        self.last_updated = datetime.now()
    
    def get_message_count(self) -> int:
        """Get total number of messages in conversation."""
        return len(self.messages)
    
    def get_latest_message(self) -> Optional[Message]:
        """Get the most recent message."""
        return self.messages[-1] if self.messages else None


# Alias for backward compatibility
ConversationChunk = KnowledgeChunk


@dataclass
class Visualization:
    """Represents a generated visualization."""
    viz_id: str
    viz_type: str  # chart, graph, diagram, image
    content_data: bytes
    caption: str = ""
    alt_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'viz_id': self.viz_id,
            'viz_type': self.viz_type,
            'content_data': self.content_data.hex(),
            'caption': self.caption,
            'alt_text': self.alt_text,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Visualization':
        """Create from dictionary for JSON deserialization."""
        return cls(
            viz_id=data['viz_id'],
            viz_type=data['viz_type'],
            content_data=bytes.fromhex(data['content_data']),
            caption=data.get('caption', ''),
            alt_text=data.get('alt_text', ''),
            metadata=data.get('metadata', {})
        )


@dataclass
class AudioFile:
    """Represents generated audio content."""
    audio_id: str
    content_data: bytes
    duration_seconds: float = 0.0
    format: str = "mp3"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'audio_id': self.audio_id,
            'content_data': self.content_data.hex(),
            'duration_seconds': self.duration_seconds,
            'format': self.format,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AudioFile':
        """Create from dictionary for JSON deserialization."""
        return cls(
            audio_id=data['audio_id'],
            content_data=bytes.fromhex(data['content_data']),
            duration_seconds=data.get('duration_seconds', 0.0),
            format=data.get('format', 'mp3'),
            metadata=data.get('metadata', {})
        )


@dataclass
class VideoFile:
    """Represents generated video content."""
    video_id: str
    content_data: bytes
    duration_seconds: float = 0.0
    format: str = "mp4"
    resolution: str = "1920x1080"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'video_id': self.video_id,
            'content_data': self.content_data.hex(),
            'duration_seconds': self.duration_seconds,
            'format': self.format,
            'resolution': self.resolution,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VideoFile':
        """Create from dictionary for JSON deserialization."""
        return cls(
            video_id=data['video_id'],
            content_data=bytes.fromhex(data['content_data']),
            duration_seconds=data.get('duration_seconds', 0.0),
            format=data.get('format', 'mp4'),
            resolution=data.get('resolution', '1920x1080'),
            metadata=data.get('metadata', {})
        )


@dataclass
class KnowledgeCitation:
    """Represents a citation to a knowledge source."""
    source_type: SourceType
    source_title: str
    location_reference: str
    chunk_id: str
    relevance_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'source_type': self.source_type.value,
            'source_title': self.source_title,
            'location_reference': self.location_reference,
            'chunk_id': self.chunk_id,
            'relevance_score': self.relevance_score
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeCitation':
        """Create from dictionary for JSON deserialization."""
        return cls(
            source_type=SourceType(data['source_type']),
            source_title=data['source_title'],
            location_reference=data['location_reference'],
            chunk_id=data['chunk_id'],
            relevance_score=data.get('relevance_score', 0.0)
        )


@dataclass
class ExportMetadata:
    """Metadata for export operations."""
    export_format: str
    created_at: datetime = field(default_factory=datetime.now)
    file_size: int = 0
    page_count: int = 0
    includes_media: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'export_format': self.export_format,
            'created_at': self.created_at.isoformat(),
            'file_size': self.file_size,
            'page_count': self.page_count,
            'includes_media': self.includes_media
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExportMetadata':
        """Create from dictionary for JSON deserialization."""
        return cls(
            export_format=data['export_format'],
            created_at=datetime.fromisoformat(data.get('created_at', datetime.now().isoformat())),
            file_size=data.get('file_size', 0),
            page_count=data.get('page_count', 0),
            includes_media=data.get('includes_media', False)
        )


@dataclass
class MultimediaResponse:
    """Represents a complete multimedia response."""
    text_content: str
    visualizations: List[Visualization] = field(default_factory=list)
    audio_content: Optional[AudioFile] = None
    video_content: Optional[VideoFile] = None
    knowledge_citations: List[KnowledgeCitation] = field(default_factory=list)
    export_metadata: Optional[ExportMetadata] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'text_content': self.text_content,
            'visualizations': [viz.to_dict() for viz in self.visualizations],
            'audio_content': self.audio_content.to_dict() if self.audio_content else None,
            'video_content': self.video_content.to_dict() if self.video_content else None,
            'knowledge_citations': [citation.to_dict() for citation in self.knowledge_citations],
            'export_metadata': self.export_metadata.to_dict() if self.export_metadata else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MultimediaResponse':
        """Create from dictionary for JSON deserialization."""
        return cls(
            text_content=data['text_content'],
            visualizations=[Visualization.from_dict(viz) for viz in data.get('visualizations', [])],
            audio_content=AudioFile.from_dict(data['audio_content']) if data.get('audio_content') else None,
            video_content=VideoFile.from_dict(data['video_content']) if data.get('video_content') else None,
            knowledge_citations=[KnowledgeCitation.from_dict(citation) for citation in data.get('knowledge_citations', [])],
            export_metadata=ExportMetadata.from_dict(data['export_metadata']) if data.get('export_metadata') else None
        )
    
    def validate(self) -> bool:
        """Validate multimedia response data integrity."""
        if not self.text_content:
            return False
        return True
    
    def has_multimedia(self) -> bool:
        """Check if response contains multimedia content."""
        return (len(self.visualizations) > 0 or 
                self.audio_content is not None or 
                self.video_content is not None)
    
    def get_total_citations(self) -> int:
        """Get total number of citations."""
        return len(self.knowledge_citations)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MultimediaResponse':
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)