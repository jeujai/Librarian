"""
Database package for the Multimodal Librarian system.

This package contains database connection management, models, and migrations
for PostgreSQL and vector database integration.
"""

from .connection import (
    DatabaseManager, Base, db_manager,
    get_database_session, init_database, create_tables, close_database
)

from .models import (
    # Core tables
    KnowledgeSource, KnowledgeChunkDB, MediaElementDB,
    ConversationDB, MessageDB,
    
    # Chunking framework tables
    ContentProfileDB, DomainConfigurationDB, ConfigPerformanceMetricDB,
    ConfigOptimizationDB, BridgeChunkDB, GapAnalysisDB, ValidationResultDB,
    
    # Citation and interaction tables
    CitationDB, InteractionFeedbackDB, TrainingSessionDB,
    
    # Knowledge graph tables
    ConceptExtractionDB, KGConfidenceScoreDB
)

from .migrations import (
    MigrationManager, create_initial_migration, upgrade_to_latest, check_database_status
)

__all__ = [
    # Connection management
    'DatabaseManager', 'Base', 'db_manager',
    'get_database_session', 'init_database', 'create_tables', 'close_database',
    
    # Database models
    'KnowledgeSource', 'KnowledgeChunkDB', 'MediaElementDB',
    'ConversationDB', 'MessageDB',
    'ContentProfileDB', 'DomainConfigurationDB', 'ConfigPerformanceMetricDB',
    'ConfigOptimizationDB', 'BridgeChunkDB', 'GapAnalysisDB', 'ValidationResultDB',
    'CitationDB', 'InteractionFeedbackDB', 'TrainingSessionDB',
    'ConceptExtractionDB', 'KGConfidenceScoreDB',
    
    # Migration management
    'MigrationManager', 'create_initial_migration', 'upgrade_to_latest', 'check_database_status'
]