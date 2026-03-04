"""
SQLAlchemy database models for the Multimodal Librarian system.

This module contains all database table definitions for PostgreSQL storage
of metadata, conversations, configurations, and system data.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from .connection import Base


class KnowledgeSource(Base):
    """Unified metadata for books and conversations."""
    __tablename__ = "knowledge_sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type = Column(String(20), nullable=False)  # 'book' or 'conversation'
    title = Column(String(500), nullable=False)
    author = Column(String(200))
    file_path = Column(String(1000))
    file_size = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    language = Column(String(10), default='en')
    subject = Column(String(200))
    keywords = Column(ARRAY(String))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    chunks = relationship("KnowledgeChunkDB", back_populates="source", cascade="all, delete-orphan")
    conversations = relationship("ConversationDB", back_populates="source")
    
    __table_args__ = (
        Index('idx_knowledge_sources_type', 'source_type'),
        Index('idx_knowledge_sources_title', 'title'),
        Index('idx_knowledge_sources_created', 'created_at'),
        CheckConstraint("source_type IN ('book', 'conversation')", name='check_source_type'),
    )


class KnowledgeChunkDB(Base):
    """Chunk metadata with source type and references."""
    __tablename__ = "knowledge_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(String(100), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey('knowledge_sources.id'), nullable=False)
    location_reference = Column(String(100))  # page number or timestamp
    section = Column(String(200))
    content_type = Column(String(20), default='general')
    complexity_score = Column(Float, default=0.0)
    extraction_confidence = Column(Float, default=1.0)
    processing_timestamp = Column(DateTime, default=datetime.utcnow)
    chunk_index = Column(Integer, default=0)
    total_chunks = Column(Integer, default=1)
    
    # Relationships
    source = relationship("KnowledgeSource", back_populates="chunks")
    media_elements = relationship("MediaElementDB", back_populates="chunk", cascade="all, delete-orphan")
    bridge_chunks = relationship("BridgeChunkDB", back_populates="source_chunk")
    
    __table_args__ = (
        Index('idx_knowledge_chunks_source', 'source_id'),
        Index('idx_knowledge_chunks_content_type', 'content_type'),
        Index('idx_knowledge_chunks_complexity', 'complexity_score'),
        Index('idx_knowledge_chunks_timestamp', 'processing_timestamp'),
        CheckConstraint("complexity_score >= 0.0 AND complexity_score <= 1.0", name='check_complexity_score'),
        CheckConstraint("extraction_confidence >= 0.0 AND extraction_confidence <= 1.0", name='check_extraction_confidence'),
    )


class MediaElementDB(Base):
    """Associated images, charts, and media files."""
    __tablename__ = "media_elements"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    element_id = Column(String(100), unique=True, nullable=False)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey('knowledge_chunks.id'), nullable=False)
    element_type = Column(String(50), nullable=False)  # image, chart, table, graph
    file_path = Column(String(1000))
    caption = Column(Text)
    alt_text = Column(Text)
    element_metadata = Column(JSON)  # Renamed from 'metadata' to avoid conflict
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    chunk = relationship("KnowledgeChunkDB", back_populates="media_elements")
    
    __table_args__ = (
        Index('idx_media_elements_chunk', 'chunk_id'),
        Index('idx_media_elements_type', 'element_type'),
    )


class ConversationDB(Base):
    """Conversation threads treated as knowledge sources."""
    __tablename__ = "conversations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(String(100), unique=True, nullable=False)
    user_id = Column(String(100), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey('knowledge_sources.id'), nullable=False)
    knowledge_summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    source = relationship("KnowledgeSource", back_populates="conversations")
    messages = relationship("MessageDB", back_populates="conversation", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_conversations_user', 'user_id'),
        Index('idx_conversations_created', 'created_at'),
        Index('idx_conversations_updated', 'last_updated'),
    )


class MessageDB(Base):
    """Individual messages within conversations."""
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(String(100), unique=True, nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey('conversations.id'), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(20), default='user')  # user, system, upload
    multimedia_content = Column(JSON)  # Store multimedia elements as JSON
    knowledge_references = Column(ARRAY(String))
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    conversation = relationship("ConversationDB", back_populates="messages")
    
    __table_args__ = (
        Index('idx_messages_conversation', 'conversation_id'),
        Index('idx_messages_timestamp', 'timestamp'),
        Index('idx_messages_type', 'message_type'),
        CheckConstraint("message_type IN ('user', 'system', 'upload')", name='check_message_type'),
    )


class ContentProfileDB(Base):
    """Automatically generated document profiles with YAGO/ConceptNet analysis."""
    __tablename__ = "content_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey('knowledge_sources.id'), nullable=False)
    content_type = Column(String(20), nullable=False)
    domain_categories = Column(ARRAY(String))
    complexity_score = Column(Float, default=0.0)
    structure_hierarchy = Column(JSON)
    domain_patterns = Column(JSON)
    cross_reference_density = Column(Float, default=0.0)
    conceptual_density = Column(Float, default=0.0)
    chunking_requirements = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_content_profiles_source', 'source_id'),
        Index('idx_content_profiles_type', 'content_type'),
        Index('idx_content_profiles_complexity', 'complexity_score'),
        CheckConstraint("complexity_score >= 0.0 AND complexity_score <= 1.0", name='check_profile_complexity'),
        CheckConstraint("cross_reference_density >= 0.0", name='check_cross_ref_density'),
        CheckConstraint("conceptual_density >= 0.0", name='check_conceptual_density'),
    )


class DomainConfigurationDB(Base):
    """Versioned domain configurations with generation metadata and performance baselines."""
    __tablename__ = "domain_configurations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_name = Column(String(100), nullable=False)
    version = Column(Integer, default=1)
    config_data = Column(JSON, nullable=False)  # Stores DomainConfig as JSON
    generation_method = Column(String(50), default='hybrid')
    source_documents = Column(ARRAY(String))
    performance_score = Column(Float)
    confidence_score = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    performance_metrics = relationship("ConfigPerformanceMetricDB", back_populates="config", cascade="all, delete-orphan")
    optimizations = relationship("ConfigOptimizationDB", back_populates="config", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_domain_configs_name', 'domain_name'),
        Index('idx_domain_configs_version', 'domain_name', 'version'),
        Index('idx_domain_configs_active', 'is_active'),
        Index('idx_domain_configs_performance', 'performance_score'),
        UniqueConstraint('domain_name', 'version', name='uq_domain_version'),
        CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name='check_config_confidence'),
        CheckConstraint("version >= 1", name='check_version_positive'),
    )


class ConfigPerformanceMetricDB(Base):
    """Real-time performance tracking for domain configurations."""
    __tablename__ = "config_performance_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(UUID(as_uuid=True), ForeignKey('domain_configurations.id'), nullable=False)
    chunk_quality_score = Column(Float, default=0.0)
    bridge_success_rate = Column(Float, default=0.0)
    retrieval_effectiveness = Column(Float, default=0.0)
    user_satisfaction_score = Column(Float, default=0.0)
    processing_efficiency = Column(Float, default=0.0)
    boundary_quality = Column(Float, default=0.0)
    document_count = Column(Integer, default=0)
    measurement_date = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    config = relationship("DomainConfigurationDB", back_populates="performance_metrics")
    
    __table_args__ = (
        Index('idx_performance_metrics_config', 'config_id'),
        Index('idx_performance_metrics_date', 'measurement_date'),
        CheckConstraint("chunk_quality_score >= 0.0 AND chunk_quality_score <= 1.0", name='check_chunk_quality'),
        CheckConstraint("bridge_success_rate >= 0.0 AND bridge_success_rate <= 1.0", name='check_bridge_success'),
        CheckConstraint("document_count >= 0", name='check_document_count'),
    )


class ConfigOptimizationDB(Base):
    """Configuration optimization history and improvement tracking."""
    __tablename__ = "config_optimizations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(UUID(as_uuid=True), ForeignKey('domain_configurations.id'), nullable=False)
    optimization_id = Column(String(100), unique=True, nullable=False)
    optimization_type = Column(String(100), nullable=False)
    changes_made = Column(JSON)
    performance_before = Column(JSON)
    performance_after = Column(JSON)
    improvement_score = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    config = relationship("DomainConfigurationDB", back_populates="optimizations")
    
    __table_args__ = (
        Index('idx_optimizations_config', 'config_id'),
        Index('idx_optimizations_type', 'optimization_type'),
        Index('idx_optimizations_timestamp', 'timestamp'),
        Index('idx_optimizations_improvement', 'improvement_score'),
    )


class BridgeChunkDB(Base):
    """LLM-generated bridge chunks with validation scores and performance tracking."""
    __tablename__ = "bridge_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bridge_id = Column(String(100), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    source_chunk_id = Column(UUID(as_uuid=True), ForeignKey('knowledge_chunks.id'), nullable=False)
    target_chunk_id = Column(String(100))  # Reference to another chunk
    generation_method = Column(String(50), default='gemini_25_flash')
    gap_analysis = Column(JSON)
    validation_result = Column(JSON)
    confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    source_chunk = relationship("KnowledgeChunkDB", back_populates="bridge_chunks")
    
    __table_args__ = (
        Index('idx_bridge_chunks_source', 'source_chunk_id'),
        Index('idx_bridge_chunks_method', 'generation_method'),
        Index('idx_bridge_chunks_confidence', 'confidence_score'),
        Index('idx_bridge_chunks_created', 'created_at'),
        CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name='check_bridge_confidence'),
    )


class GapAnalysisDB(Base):
    """Conceptual gap analysis results for bridge generation decisions."""
    __tablename__ = "gap_analyses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id = Column(String(100), unique=True, nullable=False)
    chunk1_id = Column(String(100), nullable=False)
    chunk2_id = Column(String(100), nullable=False)
    necessity_score = Column(Float, nullable=False)
    gap_type = Column(String(50), nullable=False)
    bridge_strategy = Column(String(50), nullable=False)
    semantic_distance = Column(Float, default=0.0)
    concept_overlap = Column(Float, default=0.0)
    cross_reference_density = Column(Float, default=0.0)
    structural_continuity = Column(Float, default=0.0)
    domain_specific_gaps = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_gap_analyses_chunks', 'chunk1_id', 'chunk2_id'),
        Index('idx_gap_analyses_necessity', 'necessity_score'),
        Index('idx_gap_analyses_type', 'gap_type'),
        Index('idx_gap_analyses_strategy', 'bridge_strategy'),
        CheckConstraint("necessity_score >= 0.0 AND necessity_score <= 1.0", name='check_necessity_score'),
        CheckConstraint("semantic_distance >= 0.0", name='check_semantic_distance'),
        CheckConstraint("concept_overlap >= 0.0 AND concept_overlap <= 1.0", name='check_concept_overlap'),
    )


class ValidationResultDB(Base):
    """Cross-encoding validation results for bridge quality assessment."""
    __tablename__ = "validation_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    validation_id = Column(String(100), unique=True, nullable=False)
    bridge_id = Column(String(100), nullable=False)
    individual_scores = Column(JSON)
    composite_score = Column(Float, default=0.0)
    validation_details = Column(JSON)
    passed_validation = Column(Boolean, default=False)
    content_type_thresholds = Column(JSON)
    validation_timestamp = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_validation_results_bridge', 'bridge_id'),
        Index('idx_validation_results_score', 'composite_score'),
        Index('idx_validation_results_passed', 'passed_validation'),
        Index('idx_validation_results_timestamp', 'validation_timestamp'),
        CheckConstraint("composite_score >= 0.0 AND composite_score <= 1.0", name='check_composite_score'),
    )


class CitationDB(Base):
    """Unified citation tracking for all knowledge sources."""
    __tablename__ = "citations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    citation_id = Column(String(100), unique=True, nullable=False)
    source_type = Column(String(20), nullable=False)
    source_title = Column(String(500), nullable=False)
    location_reference = Column(String(100))
    chunk_id = Column(String(100), nullable=False)
    relevance_score = Column(Float, default=0.0)
    query_context = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_citations_source_type', 'source_type'),
        Index('idx_citations_chunk', 'chunk_id'),
        Index('idx_citations_relevance', 'relevance_score'),
        Index('idx_citations_created', 'created_at'),
        CheckConstraint("source_type IN ('book', 'conversation')", name='check_citation_source_type'),
        CheckConstraint("relevance_score >= 0.0 AND relevance_score <= 1.0", name='check_relevance_score'),
    )


class InteractionFeedbackDB(Base):
    """User interaction data for reward signal generation."""
    __tablename__ = "interaction_feedback"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_id = Column(String(100), unique=True, nullable=False)
    chunk_id = Column(String(100), nullable=False)
    user_id = Column(String(100), nullable=False)
    interaction_type = Column(String(20), nullable=False)  # view, cite, export, rate
    feedback_score = Column(Float, nullable=False)  # -1.0 to 1.0
    context_query = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_interaction_feedback_chunk', 'chunk_id'),
        Index('idx_interaction_feedback_user', 'user_id'),
        Index('idx_interaction_feedback_type', 'interaction_type'),
        Index('idx_interaction_feedback_score', 'feedback_score'),
        Index('idx_interaction_feedback_timestamp', 'timestamp'),
        CheckConstraint("interaction_type IN ('view', 'cite', 'export', 'rate')", name='check_interaction_type'),
        CheckConstraint("feedback_score >= -1.0 AND feedback_score <= 1.0", name='check_feedback_score'),
    )


class TrainingSessionDB(Base):
    """ML training session metadata and performance metrics."""
    __tablename__ = "training_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), unique=True, nullable=False)
    session_type = Column(String(50), nullable=False)  # batch, streaming, sequence
    batch_size = Column(Integer)
    total_chunks = Column(Integer, default=0)
    total_sequences = Column(Integer, default=0)
    content_types = Column(ARRAY(String))
    source_types = Column(ARRAY(String))
    reward_distribution = Column(JSON)
    performance_metrics = Column(JSON)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String(20), default='active')  # active, completed, failed
    
    __table_args__ = (
        Index('idx_training_sessions_type', 'session_type'),
        Index('idx_training_sessions_status', 'status'),
        Index('idx_training_sessions_started', 'started_at'),
        Index('idx_training_sessions_completed', 'completed_at'),
        CheckConstraint("status IN ('active', 'completed', 'failed')", name='check_session_status'),
        CheckConstraint("batch_size > 0", name='check_batch_size_positive'),
    )


# Knowledge Graph Tables

class ConceptExtractionDB(Base):
    """Tracking of concept extraction from chunks."""
    __tablename__ = "concept_extractions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    extraction_id = Column(String(100), unique=True, nullable=False)
    chunk_id = Column(String(100), nullable=False)
    extraction_method = Column(String(50), default='LLM')
    confidence_score = Column(Float, default=0.0)
    extracted_concepts = Column(JSON)  # List of concept data
    extracted_relationships = Column(JSON)  # List of relationship data
    extraction_timestamp = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_concept_extractions_chunk', 'chunk_id'),
        Index('idx_concept_extractions_method', 'extraction_method'),
        Index('idx_concept_extractions_confidence', 'confidence_score'),
        Index('idx_concept_extractions_timestamp', 'extraction_timestamp'),
        CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name='check_extraction_confidence'),
    )


class KGConfidenceScoreDB(Base):
    """Confidence tracking for knowledge graph elements."""
    __tablename__ = "kg_confidence_scores"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    element_id = Column(String(100), nullable=False)
    element_type = Column(String(20), nullable=False)  # concept, relationship, triple
    confidence_score = Column(Float, nullable=False)
    evidence_count = Column(Integer, default=1)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    source_extractions = Column(ARRAY(String))  # List of extraction IDs
    
    __table_args__ = (
        Index('idx_kg_confidence_element', 'element_id'),
        Index('idx_kg_confidence_type', 'element_type'),
        Index('idx_kg_confidence_score', 'confidence_score'),
        Index('idx_kg_confidence_updated', 'last_updated'),
        UniqueConstraint('element_id', 'element_type', name='uq_kg_element'),
        CheckConstraint("element_type IN ('concept', 'relationship', 'triple')", name='check_kg_element_type'),
        CheckConstraint("confidence_score >= 0.0 AND confidence_score <= 1.0", name='check_kg_confidence'),
        CheckConstraint("evidence_count >= 1", name='check_evidence_count'),
    )


# Security and Audit Tables

class UserDB(Base):
    """User accounts and authentication data."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(255), nullable=False)
    role = Column(String(50), default='user')
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    
    # Relationships
    api_keys = relationship("APIKeyDB", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLogDB", back_populates="user")
    
    __table_args__ = (
        Index('idx_users_username', 'username'),
        Index('idx_users_email', 'email'),
        Index('idx_users_role', 'role'),
        Index('idx_users_active', 'is_active'),
        Index('idx_users_created', 'created_at'),
        CheckConstraint("role IN ('admin', 'user', 'ml_researcher', 'read_only')", name='check_user_role'),
    )


class APIKeyDB(Base):
    """API keys for programmatic access."""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_id = Column(String(100), unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    name = Column(String(200), nullable=False)
    key_hash = Column(String(255), nullable=False)  # Hashed API key
    permissions = Column(ARRAY(String))  # List of permissions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    last_used = Column(DateTime)
    usage_count = Column(Integer, default=0)
    
    # Relationships
    user = relationship("UserDB", back_populates="api_keys")
    
    __table_args__ = (
        Index('idx_api_keys_user', 'user_id'),
        Index('idx_api_keys_active', 'is_active'),
        Index('idx_api_keys_expires', 'expires_at'),
        Index('idx_api_keys_created', 'created_at'),
    )


class AuditLogDB(Base):
    """Comprehensive audit logging for all system operations."""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(100), unique=True, nullable=False)
    event_type = Column(String(50), nullable=False)
    level = Column(String(20), default='info')
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    session_id = Column(String(100))
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(Text)
    resource_type = Column(String(50))
    resource_id = Column(String(100))
    action = Column(String(100), nullable=False)
    result = Column(String(20), nullable=False)
    details = Column(JSON)
    sensitive_data_hash = Column(String(64))  # SHA-256 hash
    
    # Relationships
    user = relationship("UserDB", back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_audit_logs_event_type', 'event_type'),
        Index('idx_audit_logs_timestamp', 'timestamp'),
        Index('idx_audit_logs_user', 'user_id'),
        Index('idx_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_logs_action', 'action'),
        Index('idx_audit_logs_result', 'result'),
        Index('idx_audit_logs_level', 'level'),
        CheckConstraint("level IN ('info', 'warning', 'error', 'critical')", name='check_audit_level'),
        CheckConstraint("result IN ('success', 'failure', 'error', 'security_event')", name='check_audit_result'),
    )


class DataDeletionLogDB(Base):
    """Log of all data deletion operations for compliance."""
    __tablename__ = "data_deletion_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deletion_id = Column(String(100), unique=True, nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(100), nullable=False)
    requested_by = Column(String(100), nullable=False)
    deletion_reason = Column(String(200))
    deletion_status = Column(String(20), default='pending')
    deleted_components = Column(JSON)  # List of deleted components
    errors = Column(JSON)  # List of errors encountered
    requested_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    verification_hash = Column(String(64))  # Hash of deleted data for verification
    
    __table_args__ = (
        Index('idx_deletion_logs_resource', 'resource_type', 'resource_id'),
        Index('idx_deletion_logs_requested_by', 'requested_by'),
        Index('idx_deletion_logs_status', 'deletion_status'),
        Index('idx_deletion_logs_requested', 'requested_at'),
        Index('idx_deletion_logs_completed', 'completed_at'),
        CheckConstraint("deletion_status IN ('pending', 'in_progress', 'completed', 'failed', 'partial')", name='check_deletion_status'),
        CheckConstraint("resource_type IN ('book', 'conversation', 'user_data', 'all')", name='check_deletion_resource_type'),
    )


class PrivacyRequestDB(Base):
    """Privacy requests for GDPR compliance and data subject rights."""
    __tablename__ = "privacy_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(100), unique=True, nullable=False)
    request_type = Column(String(50), nullable=False)  # export, delete, anonymize, rectify
    user_id = Column(String(100), nullable=False)
    requested_by = Column(String(100), nullable=False)
    request_details = Column(JSON)
    status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    completed_at = Column(DateTime)
    result_data = Column(JSON)
    notes = Column(Text)
    
    __table_args__ = (
        Index('idx_privacy_requests_type', 'request_type'),
        Index('idx_privacy_requests_user', 'user_id'),
        Index('idx_privacy_requests_status', 'status'),
        Index('idx_privacy_requests_created', 'created_at'),
        CheckConstraint("request_type IN ('export', 'delete', 'anonymize', 'rectify', 'access')", name='check_privacy_request_type'),
        CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')", name='check_privacy_status'),
    )


class SecurityIncidentDB(Base):
    """Security incidents and violations tracking."""
    __tablename__ = "security_incidents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(String(100), unique=True, nullable=False)
    incident_type = Column(String(50), nullable=False)
    severity = Column(String(20), default='medium')
    status = Column(String(20), default='open')
    detected_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    source_ip = Column(String(45))
    user_id = Column(String(100))
    description = Column(Text, nullable=False)
    indicators = Column(JSON)  # IOCs and other indicators
    response_actions = Column(JSON)  # Actions taken
    false_positive = Column(Boolean, default=False)
    
    __table_args__ = (
        Index('idx_security_incidents_type', 'incident_type'),
        Index('idx_security_incidents_severity', 'severity'),
        Index('idx_security_incidents_status', 'status'),
        Index('idx_security_incidents_detected', 'detected_at'),
        Index('idx_security_incidents_source_ip', 'source_ip'),
        CheckConstraint("incident_type IN ('unauthorized_access', 'brute_force', 'data_breach', 'malware', 'dos', 'other')", name='check_incident_type'),
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name='check_incident_severity'),
        CheckConstraint("status IN ('open', 'investigating', 'resolved', 'closed')", name='check_incident_status'),
    )


class EncryptionKeyDB(Base):
    """Encryption key management and rotation."""
    __tablename__ = "encryption_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key_id = Column(String(100), unique=True, nullable=False)
    key_type = Column(String(50), nullable=False)  # data, backup, transport
    key_hash = Column(String(64), nullable=False)  # Hash of the key for identification
    algorithm = Column(String(50), default='AES-256')
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    rotated_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    usage_count = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_encryption_keys_type', 'key_type'),
        Index('idx_encryption_keys_active', 'is_active'),
        Index('idx_encryption_keys_expires', 'expires_at'),
        Index('idx_encryption_keys_created', 'created_at'),
        CheckConstraint("key_type IN ('data', 'backup', 'transport', 'signing')", name='check_key_type'),
    )


# Chat and Messaging Models

class ChatMessage(Base):
    """Chat message model for conversation history."""
    __tablename__ = "chat_messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(20), nullable=False, default='user')
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    sources = Column(ARRAY(String), default=[])
    message_metadata = Column(JSON, default={})  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    
    __table_args__ = (
        Index('idx_chat_messages_user_id', 'user_id'),
        Index('idx_chat_messages_timestamp', 'timestamp'),
        Index('idx_chat_messages_type', 'message_type'),
        CheckConstraint("message_type IN ('user', 'assistant', 'system')", name='check_chat_message_type'),
    )


# Bridge Chunk Models
# LLM-generated bridge chunks connecting adjacent knowledge chunks