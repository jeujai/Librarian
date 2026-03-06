"""
Generic Multi-Level Chunking Framework.

This module implements the main framework that coordinates all components:
automated content analysis, domain configuration management, multi-level chunking,
gap analysis, bridge generation, validation, and fallback systems.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ...config import get_settings
from ...models.chunking import (
    BridgeChunk,
    ChunkingRequirements,
    ContentProfile,
    DomainConfig,
    GapAnalysis,
    ValidationResult,
)
from ...models.core import BridgeStrategy, ContentType, DocumentContent, GapType
from .bridge_generator import SmartBridgeGenerator
from .config_manager import DomainConfigurationManager
from .content_analyzer import AutomatedContentAnalyzer
from .fallback_system import FallbackConfig, IntelligentFallbackSystem
from .gap_analyzer import ConceptualGapAnalyzer
from .validator import MultiStageValidator, ValidationConfig

logger = logging.getLogger(__name__)


@dataclass
class ProcessedChunk:
    """A processed chunk with metadata.
    
    The chunk ID must be a valid UUID string to ensure consistency
    across PostgreSQL and Milvus storage systems.
    """
    id: str
    content: str
    start_position: int
    end_position: int
    chunk_type: str = "content"  # content, bridge, fallback
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        # Validate that id is a valid UUID for storage consistency
        try:
            uuid.UUID(self.id)
        except (ValueError, TypeError):
            raise ValueError(f"ProcessedChunk id must be a valid UUID, got: {self.id}")


@dataclass
class ChunkChangeMapping:
    """Mapping of chunk ID changes during document re-processing."""
    added: List[str]      # new chunk IDs not in previous set
    removed: List[str]    # previous IDs not in new set
    unchanged: List[str]  # IDs present in both sets


@dataclass
class UnresolvedBisection:
    """Records a concept that could not be kept whole by boundary adjustment."""
    concept_name: str
    concept_confidence: float
    boundary_index: int  # word index of the boundary in the original text
    chunk_before_id: str  # ID of the chunk before the boundary
    chunk_after_id: str   # ID of the chunk after the boundary


@dataclass
class ProcessedDocument:
    """Result of document processing through the framework."""
    document_id: str
    content_profile: ContentProfile
    domain_config: DomainConfig
    chunks: List[ProcessedChunk]
    bridges: List[BridgeChunk]
    processing_stats: Dict[str, Any]
    processing_time: float
    chunk_change_mapping: Optional[ChunkChangeMapping] = None

    def get_total_chunks(self) -> int:
        """Get total number of chunks including bridges."""
        return len(self.chunks) + len(self.bridges)
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[ProcessedChunk]:
        """Get chunk by ID."""
        for chunk in self.chunks:
            if chunk.id == chunk_id:
                return chunk
        return None


@dataclass
class ChunkingResult:
    """Result of chunking operation."""
    chunks: List[ProcessedChunk]
    bridges: List[BridgeChunk]
    gaps_analyzed: int
    bridges_generated: int
    bridges_validated: int
    fallbacks_created: int
    processing_notes: List[str]


@dataclass
class SectionClassification:
    """Classification result for a document section.

    Requirements: 6.1
    """
    section_text: str
    content_type: ContentType
    chunking_requirements: ChunkingRequirements
    start_offset: int
    end_offset: int


class GenericMultiLevelChunkingFramework:
    """
    Generic multi-level chunking framework with automated content profiling
    and smart bridge generation.
    
    Coordinates all components to provide adaptive chunking strategies with
    continuous optimization based on performance metrics and user feedback.
    """
    
    def __init__(self, validation_config: Optional[ValidationConfig] = None,
                 fallback_config: Optional[FallbackConfig] = None):
        """Initialize the chunking framework."""
        
        # Initialize all components
        self.content_analyzer = AutomatedContentAnalyzer()
        self.config_manager = DomainConfigurationManager()
        self.gap_analyzer = ConceptualGapAnalyzer()
        self.bridge_generator = SmartBridgeGenerator()
        self.validator = MultiStageValidator(validation_config)
        self.fallback_system = IntelligentFallbackSystem(fallback_config)
        
        # Framework statistics
        self.framework_stats = {
            'documents_processed': 0,
            'total_chunks_created': 0,
            'total_bridges_generated': 0,
            'total_fallbacks_created': 0,
            'average_processing_time': 0.0,
            'success_rate': 0.0
        }
        
        logger.info("Initialized Generic Multi-Level Chunking Framework")
    
    def process_document_chunks_only(self, document: DocumentContent,
                                    document_id: Optional[str] = None,
                                    previous_chunk_ids: Optional[Set[str]] = None) -> ProcessedDocument:
        """Process document and return chunks WITHOUT bridge generation.
        
        This is the fast path (~5s) that produces chunks ready for embedding
        and KG extraction. Bridge generation is deferred to
        generate_bridges_for_document() which can run in parallel.
        
        The returned ProcessedDocument has empty bridges list but includes
        bridge_generation_data in processing_stats for later use.
        """
        start_time = datetime.now()
        
        if document_id is None:
            document_id = str(uuid.uuid4())
        
        logger.info(f"Processing document {document_id} (chunks only, no bridges)")
        
        try:
            # Step 1: Generate content profile
            content_profile = self.generate_content_profile(document)
            
            # Step 2: Get or create domain configuration
            domain_config = self.get_or_create_domain_config(content_profile)
            
            # Step 3: Perform chunking WITHOUT bridges
            chunking_result = self._chunk_without_bridges(
                document, content_profile, domain_config,
                document_id=document_id
            )
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            processing_stats = {
                'content_type': content_profile.content_type.value,
                'complexity_score': content_profile.complexity_score,
                'domain_categories': len(content_profile.domain_categories),
                'chunks_created': len(chunking_result['chunks']),
                'bridges_generated': 0,
                'bridges_validated': 0,
                'fallbacks_created': 0,
                'gaps_analyzed': chunking_result['gaps_analyzed'],
                'processing_time': processing_time,
                'processing_notes': chunking_result['processing_notes'],
                # Stash data needed for deferred bridge generation
                'bridge_generation_data': {
                    'bridge_needed': chunking_result['bridge_needed_serialized'],
                    'all_unresolved_bisections': chunking_result['unresolved_bisections_serialized'],
                    'content_type': content_profile.content_type.value,
                    'domain_config_dict': {
                        'domain_name': domain_config.domain_name,
                        'bridge_thresholds': domain_config.bridge_thresholds,
                        'preservation_patterns': domain_config.preservation_patterns,
                    },
                },
            }
            
            self._update_framework_stats(processing_stats, True)
            
            chunk_change_mapping = None
            if previous_chunk_ids is not None:
                new_ids = {chunk.id for chunk in chunking_result['chunks']}
                chunk_change_mapping = ChunkChangeMapping(
                    added=list(new_ids - previous_chunk_ids),
                    removed=list(previous_chunk_ids - new_ids),
                    unchanged=list(new_ids & previous_chunk_ids),
                )
            
            return ProcessedDocument(
                document_id=document_id,
                content_profile=content_profile,
                domain_config=domain_config,
                chunks=chunking_result['chunks'],
                bridges=[],  # Deferred
                processing_stats=processing_stats,
                processing_time=processing_time,
                chunk_change_mapping=chunk_change_mapping
            )
        
        except Exception as e:
            logger.error(f"Failed to process document chunks {document_id}: {e}")
            processing_time = (datetime.now() - start_time).total_seconds()
            self._update_framework_stats({'processing_time': processing_time}, False)
            raise
    
    def _chunk_without_bridges(self, document: DocumentContent,
                               content_profile: ContentProfile,
                               domain_config: DomainConfig,
                               document_id: Optional[str] = None) -> Dict[str, Any]:
        """Perform chunking and gap analysis but skip bridge generation.
        
        Returns a dict with chunks, gap analysis results, and serialized
        data needed for deferred bridge generation.
        """
        processing_notes = []
        
        # Step 1: Primary chunking
        section_classifications = self.content_analyzer.classify_sections(document)
        all_unresolved_bisections: Dict[int, List[UnresolvedBisection]] = {}
        
        if len(section_classifications) > 1:
            primary_chunks = []
            chunk_offset = 0
            for section_text, section_type, section_reqs in section_classifications:
                section_profile = ContentProfile(
                    content_type=section_type,
                    chunking_requirements=section_reqs,
                    complexity_score=content_profile.complexity_score,
                    conceptual_density=content_profile.conceptual_density,
                    cross_reference_density=content_profile.cross_reference_density,
                    domain_categories=content_profile.domain_categories,
                    structure_hierarchy=content_profile.structure_hierarchy,
                    domain_patterns=content_profile.domain_patterns,
                )
                section_domain_config = self.config_manager.get_or_generate_config(section_profile)
                section_chunks, section_bisections = self._perform_primary_chunking(
                    section_text, section_profile, section_domain_config,
                    document_id=document_id or ""
                )
                for boundary_idx, bisections in section_bisections.items():
                    all_unresolved_bisections[boundary_idx + chunk_offset] = bisections
                chunk_offset += len(section_chunks)
                primary_chunks.extend(section_chunks)
        else:
            primary_chunks, all_unresolved_bisections = self._perform_primary_chunking(
                document.text, content_profile, domain_config,
                document_id=document_id or ""
            )
        processing_notes.append(f"Created {len(primary_chunks)} primary chunks")
        
        # Step 2: Secondary chunking
        final_chunks = self._perform_secondary_chunking(
            primary_chunks, content_profile, domain_config,
            document_id=document_id or ""
        )
        processing_notes.append(f"Refined to {len(final_chunks)} final chunks")
        
        # Step 3: Gap analysis (fast, no LLM)
        bridge_threshold = domain_config.bridge_thresholds.get('default', 0.7)
        gap_analyses = []
        bridge_needed = []
        
        for i in range(len(final_chunks) - 1):
            chunk1 = final_chunks[i]
            chunk2 = final_chunks[i + 1]
            gap_analysis = self.gap_analyzer.analyze_boundary_gap(
                chunk1.content, chunk2.content,
                content_profile.content_type, domain_config
            )
            gap_analyses.append((i, chunk1, chunk2, gap_analysis))
            if gap_analysis.necessity_score >= bridge_threshold:
                bridge_needed.append((i, chunk1, chunk2, gap_analysis))
        
        # Serialize bridge_needed for deferred generation
        # We store chunk IDs + content + gap analysis so the bridge task
        # can reconstruct everything without re-running gap analysis
        bridge_needed_serialized = []
        for idx, chunk1, chunk2, gap_analysis in bridge_needed:
            bridge_needed_serialized.append({
                'boundary_index': idx,
                'chunk1_id': chunk1.id,
                'chunk1_content': chunk1.content,
                'chunk2_id': chunk2.id,
                'chunk2_content': chunk2.content,
                'gap_type': gap_analysis.gap_type.value,
                'bridge_strategy': gap_analysis.bridge_strategy.value,
                'necessity_score': gap_analysis.necessity_score,
                'semantic_distance': gap_analysis.semantic_distance,
                'concept_overlap': gap_analysis.concept_overlap,
                'cross_reference_density': gap_analysis.cross_reference_density,
                'domain_specific_gaps': gap_analysis.domain_specific_gaps,
            })
        
        # Serialize unresolved bisections
        unresolved_serialized = {}
        for boundary_idx, bisections in all_unresolved_bisections.items():
            unresolved_serialized[str(boundary_idx)] = [
                {
                    'concept_name': b.concept_name,
                    'concept_confidence': b.concept_confidence,
                    'boundary_index': b.boundary_index,
                    'chunk_before_id': b.chunk_before_id,
                    'chunk_after_id': b.chunk_after_id,
                }
                for b in bisections
            ]
        
        return {
            'chunks': final_chunks,
            'gaps_analyzed': len(gap_analyses),
            'bridge_needed_serialized': bridge_needed_serialized,
            'unresolved_bisections_serialized': unresolved_serialized,
            'processing_notes': processing_notes,
        }
    
    def generate_bridges_for_document(self, bridge_generation_data: Dict[str, Any],
                                     progress_callback: callable = None) -> List[BridgeChunk]:
        """Generate bridges from previously serialized bridge data.
        
        This is the slow path (~550s) that can run in parallel with
        embedding storage and KG extraction.
        
        Args:
            bridge_generation_data: Dict from processing_stats['bridge_generation_data']
            
        Returns:
            List of BridgeChunk objects
        """
        from ...models.core import BridgeStrategy, GapType
        
        bridge_needed_data = bridge_generation_data['bridge_needed']
        unresolved_data = bridge_generation_data.get('all_unresolved_bisections', {})
        content_type_str = bridge_generation_data.get('content_type', 'general')
        
        try:
            content_type = ContentType(content_type_str)
        except ValueError:
            content_type = ContentType.GENERAL
        
        # Reconstruct domain config for bridge generator
        domain_config_dict = bridge_generation_data.get('domain_config_dict', {})
        domain_config = DomainConfig(
            domain_name=domain_config_dict.get('domain_name', 'unknown'),
            bridge_thresholds=domain_config_dict.get('bridge_thresholds', {}),
            preservation_patterns=domain_config_dict.get('preservation_patterns', []),
        )
        
        if not bridge_needed_data:
            logger.info("No bridges needed")
            return []
        
        # Reconstruct boundary pairs and gap analyses
        boundary_pairs = []
        for item in bridge_needed_data:
            gap_analysis = GapAnalysis(
                gap_type=GapType(item['gap_type']),
                bridge_strategy=BridgeStrategy(item.get('bridge_strategy', 'semantic_overlap')),
                necessity_score=item['necessity_score'],
                semantic_distance=item.get('semantic_distance', 0.0),
                concept_overlap=item.get('concept_overlap', 0.0),
                cross_reference_density=item.get('cross_reference_density', 0.0),
                domain_specific_gaps=item.get('domain_specific_gaps', {}),
            )
            boundary_pairs.append((
                item['chunk1_content'],
                item['chunk2_content'],
                gap_analysis
            ))
        
        # Reconstruct bisected concepts mapping
        bisected_concepts_per_boundary = None
        if unresolved_data:
            bisected_concepts_per_boundary = {}
            # Map from bridge_needed index to concept names
            for batch_idx, item in enumerate(bridge_needed_data):
                boundary_idx = item['boundary_index']
                bisections = unresolved_data.get(str(boundary_idx), [])
                if bisections:
                    concept_names = [b['concept_name'] for b in bisections]
                    bisected_concepts_per_boundary[batch_idx] = concept_names
        
        logger.info(f"Generating {len(boundary_pairs)} bridges (deferred)")
        
        raw_bridges = self.bridge_generator.batch_generate_bridges(
            boundary_pairs,
            content_type=content_type,
            domain_config=domain_config,
            bisected_concepts_per_boundary=bisected_concepts_per_boundary,
            progress_callback=progress_callback,
        )
        
        # Validate and apply fallbacks
        bridges = []
        for i, (item, raw_bridge) in enumerate(zip(bridge_needed_data, raw_bridges)):
            chunk1_content = item['chunk1_content']
            chunk2_content = item['chunk2_content']
            
            validation_result = self.validator.validate_bridge(
                raw_bridge, chunk1_content, chunk2_content, content_type
            )
            raw_bridge.validation_result = validation_result
            raw_bridge.source_chunks = [item['chunk1_id'], item['chunk2_id']]
            
            if not validation_result.passed_validation:
                gap_analysis = GapAnalysis(
                    gap_type=GapType(item['gap_type']),
                    bridge_strategy=BridgeStrategy(item.get('bridge_strategy', 'semantic_overlap')),
                    necessity_score=item['necessity_score'],
                )
                fallback_result = self.fallback_system.create_fallback(
                    chunk1_content, chunk2_content, gap_analysis,
                    content_type, raw_bridge.content
                )
                fallback_bridge = BridgeChunk(
                    content=fallback_result.fallback_content,
                    source_chunks=[item['chunk1_id'], item['chunk2_id']],
                    generation_method=fallback_result.strategy_used.value,
                    gap_analysis=gap_analysis,
                    confidence_score=fallback_result.quality_score,
                    created_at=datetime.now()
                )
                bridges.append(fallback_bridge)
            else:
                bridges.append(raw_bridge)
        
        # Concept-recovery bridges
        settings = get_settings()
        enable_recovery = getattr(settings, 'enable_concept_recovery_bridges', True)
        
        if enable_recovery and unresolved_data:
            # Build a lookup of chunk content by ID from bridge_needed_data
            chunk_content_by_id = {}
            for item in bridge_needed_data:
                chunk_content_by_id[item['chunk1_id']] = item['chunk1_content']
                chunk_content_by_id[item['chunk2_id']] = item['chunk2_content']
            
            for boundary_idx_str, bisections in unresolved_data.items():
                if not bisections:
                    continue
                
                bisected_names = [b['concept_name'] for b in bisections]
                chunk_before_id = bisections[0]['chunk_before_id']
                chunk_after_id = bisections[0]['chunk_after_id']
                
                chunk1_content = chunk_content_by_id.get(chunk_before_id)
                chunk2_content = chunk_content_by_id.get(chunk_after_id)
                if not chunk1_content or not chunk2_content:
                    continue
                
                # Check if existing bridge covers these concepts
                existing_bridge = None
                for bridge in bridges:
                    if bridge.source_chunks == [chunk_before_id, chunk_after_id]:
                        existing_bridge = bridge
                        break
                
                if existing_bridge is not None:
                    missing = [
                        name for name in bisected_names
                        if name.lower() not in existing_bridge.content.lower()
                    ]
                    if not missing:
                        continue
                    bisected_names = missing
                
                recovery_gap = GapAnalysis(
                    necessity_score=0.0,
                    gap_type=GapType.CONCEPTUAL,
                    bridge_strategy=BridgeStrategy.SEMANTIC_OVERLAP,
                )
                
                try:
                    recovery_bridge = self.bridge_generator.generate_bridge(
                        chunk1_content, chunk2_content, recovery_gap,
                        content_type=content_type,
                        domain_config=domain_config,
                        bisected_concepts=bisected_names,
                    )
                    recovery_bridge.source_chunks = [chunk_before_id, chunk_after_id]
                    if recovery_bridge.metadata is None:
                        recovery_bridge.metadata = {}
                    recovery_bridge.metadata['is_recovery_bridge'] = True
                    recovery_bridge.metadata['target_bisected_concepts'] = bisected_names
                    bridges.append(recovery_bridge)
                except Exception as e:
                    logger.warning(f"Recovery bridge generation failed for boundary {boundary_idx_str}: {e}")
        
        # Extract concepts from bridges for KG indexing
        concept_extractor = self._get_concept_extractor()
        for bridge in bridges:
            try:
                bridge_concepts = concept_extractor.extract_concepts_regex(bridge.content)
                if bridge.metadata is None:
                    bridge.metadata = {}
                bridge.metadata['extracted_concepts'] = [c.concept_id for c in bridge_concepts]
                bridge.metadata['adjacent_chunk_ids'] = bridge.source_chunks
            except Exception as e:
                logger.warning(f"Bridge concept extraction failed: {e}")
                if bridge.metadata is None:
                    bridge.metadata = {}
                bridge.metadata['extracted_concepts'] = []
                bridge.metadata['adjacent_chunk_ids'] = bridge.source_chunks
        
        logger.info(f"Generated {len(bridges)} bridges (deferred)")
        return bridges

    def process_document(self, document: DocumentContent, 
                        document_id: Optional[str] = None,
                        previous_chunk_ids: Optional[Set[str]] = None) -> ProcessedDocument:
        """
        Process document with automated profiling and adaptive chunking.
        
        Args:
            document: Document content to process
            document_id: Optional document identifier
            
        Returns:
            ProcessedDocument with chunks, bridges, and metadata
        """
        start_time = datetime.now()
        
        if document_id is None:
            document_id = str(uuid.uuid4())
        
        logger.info(f"Processing document {document_id}")
        
        try:
            # Step 1: Generate content profile
            content_profile = self.generate_content_profile(document)
            
            # Step 2: Get or create domain configuration
            domain_config = self.get_or_create_domain_config(content_profile)
            
            # Step 3: Perform multi-level chunking with bridges
            chunking_result = self.chunk_with_smart_bridges(
                document, content_profile, domain_config,
                document_id=document_id
            )
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Compile processing statistics
            processing_stats = {
                'content_type': content_profile.content_type.value,
                'complexity_score': content_profile.complexity_score,
                'domain_categories': len(content_profile.domain_categories),
                'chunks_created': len(chunking_result.chunks),
                'bridges_generated': chunking_result.bridges_generated,
                'bridges_validated': chunking_result.bridges_validated,
                'fallbacks_created': chunking_result.fallbacks_created,
                'gaps_analyzed': chunking_result.gaps_analyzed,
                'processing_time': processing_time,
                'processing_notes': chunking_result.processing_notes
            }
            
            # Update framework statistics
            self._update_framework_stats(processing_stats, True)
            
            # Compute chunk change mapping if previous IDs provided
            chunk_change_mapping = None
            if previous_chunk_ids is not None:
                new_ids = {chunk.id for chunk in chunking_result.chunks}
                chunk_change_mapping = ChunkChangeMapping(
                    added=list(new_ids - previous_chunk_ids),
                    removed=list(previous_chunk_ids - new_ids),
                    unchanged=list(new_ids & previous_chunk_ids),
                )
            
            return ProcessedDocument(
                document_id=document_id,
                content_profile=content_profile,
                domain_config=domain_config,
                chunks=chunking_result.chunks,
                bridges=chunking_result.bridges,
                processing_stats=processing_stats,
                processing_time=processing_time,
                chunk_change_mapping=chunk_change_mapping
            )
        
        except Exception as e:
            logger.error(f"Failed to process document {document_id}: {e}")
            
            # Update statistics for failure
            processing_time = (datetime.now() - start_time).total_seconds()
            self._update_framework_stats({'processing_time': processing_time}, False)
            
            raise
    
    def generate_content_profile(self, document: DocumentContent) -> ContentProfile:
        """
        Automatically generate content profile using knowledge graphs.
        
        Args:
            document: Document to analyze
            
        Returns:
            ContentProfile with automated analysis results
        """
        logger.debug("Generating content profile")
        return self.content_analyzer.analyze_document(document)
    
    def get_or_create_domain_config(self, content_profile: ContentProfile) -> DomainConfig:
        """
        Get existing or automatically generate domain configuration.
        
        Args:
            content_profile: Content profile from analysis
            
        Returns:
            DomainConfig for the content domain
        """
        logger.debug(f"Getting domain configuration for {content_profile.content_type.value}")
        return self.config_manager.get_or_generate_config(content_profile)
    
    def chunk_with_smart_bridges(self, document: DocumentContent, 
                               content_profile: ContentProfile,
                               domain_config: DomainConfig,
                               document_id: Optional[str] = None) -> ChunkingResult:
        """
        Apply multi-level chunking with smart bridge generation.
        
        Args:
            document: Document to chunk
            content_profile: Content profile
            domain_config: Domain configuration
            
        Returns:
            ChunkingResult with chunks and bridges
        """
        logger.debug("Starting multi-level chunking with smart bridges")
        
        processing_notes = []
        
        # Step 1: Primary chunking based on content profile
        # Try per-section classification for mixed-domain documents
        section_classifications = self.content_analyzer.classify_sections(document)

        # Accumulate unresolved bisections across all sections.
        all_unresolved_bisections: Dict[int, List[UnresolvedBisection]] = {}

        if len(section_classifications) > 1:
            # Per-section chunking: each section gets its own domain config
            primary_chunks = []
            chunk_offset = 0
            for section_text, section_type, section_reqs in section_classifications:
                section_profile = ContentProfile(
                    content_type=section_type,
                    chunking_requirements=section_reqs,
                    complexity_score=content_profile.complexity_score,
                    conceptual_density=content_profile.conceptual_density,
                    cross_reference_density=content_profile.cross_reference_density,
                    domain_categories=content_profile.domain_categories,
                    structure_hierarchy=content_profile.structure_hierarchy,
                    domain_patterns=content_profile.domain_patterns,
                )
                section_domain_config = self.config_manager.get_or_generate_config(section_profile)
                section_chunks, section_bisections = self._perform_primary_chunking(
                    section_text, section_profile, section_domain_config,
                    document_id=document_id or ""
                )
                # Re-key bisection indices relative to the combined chunk list.
                for boundary_idx, bisections in section_bisections.items():
                    all_unresolved_bisections[boundary_idx + chunk_offset] = bisections
                chunk_offset += len(section_chunks)
                primary_chunks.extend(section_chunks)
        else:
            # Single-section document — use document-level profile (existing behavior)
            primary_chunks, all_unresolved_bisections = self._perform_primary_chunking(
                document.text, content_profile, domain_config,
                document_id=document_id or ""
            )
        processing_notes.append(f"Created {len(primary_chunks)} primary chunks")
        
        # Step 2: Secondary chunking if needed
        final_chunks = self._perform_secondary_chunking(
            primary_chunks, content_profile, domain_config,
            document_id=document_id or ""
        )
        processing_notes.append(f"Refined to {len(final_chunks)} final chunks")
        
        # Step 3: Gap analysis (fast, no LLM calls)
        bridge_threshold = domain_config.bridge_thresholds.get('default', 0.7)
        gap_analyses = []  # (index, chunk1, chunk2, gap_analysis)
        bridge_needed = []  # subset that needs LLM bridge generation
        
        for i in range(len(final_chunks) - 1):
            chunk1 = final_chunks[i]
            chunk2 = final_chunks[i + 1]
            gap_analysis = self.gap_analyzer.analyze_boundary_gap(
                chunk1.content, chunk2.content,
                content_profile.content_type, domain_config
            )
            gap_analyses.append((i, chunk1, chunk2, gap_analysis))
            if gap_analysis.necessity_score >= bridge_threshold:
                bridge_needed.append((i, chunk1, chunk2, gap_analysis))
        
        gaps_analyzed = len(gap_analyses)
        bridges_generated = 0
        bridges_validated = 0
        fallbacks_created = 0
        bridges = []
        
        # Step 4: Batch bridge generation (concurrent LLM calls)
        if bridge_needed:
            boundary_pairs = [
                (chunk1.content, chunk2.content, gap_analysis)
                for _, chunk1, chunk2, gap_analysis in bridge_needed
            ]

            # Build bisected concepts mapping for standard bridge augmentation.
            # Maps from position in bridge_needed list to concept names.
            bisected_concepts_per_boundary: Optional[Dict[int, List[str]]] = None
            if all_unresolved_bisections:
                bisected_concepts_per_boundary = {}
                for batch_idx, (boundary_idx, _, _, _) in enumerate(bridge_needed):
                    if boundary_idx in all_unresolved_bisections:
                        concept_names = [
                            b.concept_name
                            for b in all_unresolved_bisections[boundary_idx]
                        ]
                        if concept_names:
                            bisected_concepts_per_boundary[batch_idx] = concept_names

            logger.info(f"Batch generating {len(boundary_pairs)} bridges (batch_size={self.bridge_generator.batch_size})")
            
            raw_bridges = self.bridge_generator.batch_generate_bridges(
                boundary_pairs,
                content_type=content_profile.content_type,
                domain_config=domain_config,
                bisected_concepts_per_boundary=bisected_concepts_per_boundary
            )
            
            # Step 5: Validate each bridge, apply fallback if needed
            for (idx, chunk1, chunk2, gap_analysis), raw_bridge in zip(bridge_needed, raw_bridges):
                validation_result = self.validator.validate_bridge(
                    raw_bridge, chunk1.content, chunk2.content, content_profile.content_type
                )
                raw_bridge.validation_result = validation_result
                raw_bridge.source_chunks = [chunk1.id, chunk2.id]
                
                if not validation_result.passed_validation:
                    logger.debug(f"Bridge validation failed (score: {validation_result.composite_score:.2f}), trying fallback")
                    fallback_result = self.fallback_system.create_fallback(
                        chunk1.content, chunk2.content, gap_analysis,
                        content_profile.content_type, raw_bridge.content
                    )
                    fallback_bridge = BridgeChunk(
                        content=fallback_result.fallback_content,
                        source_chunks=[chunk1.id, chunk2.id],
                        generation_method=fallback_result.strategy_used.value,
                        gap_analysis=gap_analysis,
                        confidence_score=fallback_result.quality_score,
                        created_at=datetime.now()
                    )
                    if self.fallback_system.detect_upgrade_opportunity(fallback_result):
                        fallback_bridge.metadata = {'upgrade_candidate': True}
                    bridges.append(fallback_bridge)
                    fallbacks_created += 1
                else:
                    bridges.append(raw_bridge)
                    bridges_generated += 1
                    bridges_validated += 1
        
        processing_notes.append(f"Analyzed {gaps_analyzed} gaps, generated {bridges_generated} bridges, created {fallbacks_created} fallbacks")
        
        # Step 5.5: Concept-recovery bridge generation
        settings = get_settings()
        enable_recovery = getattr(
            settings, 'enable_concept_recovery_bridges', True
        )

        if enable_recovery and all_unresolved_bisections:
            recovery_bridges = []

            for boundary_idx, bisections in (
                all_unresolved_bisections.items()
            ):
                if boundary_idx >= len(final_chunks) - 1:
                    continue

                chunk1 = final_chunks[boundary_idx]
                chunk2 = final_chunks[boundary_idx + 1]
                bisected_names = [
                    b.concept_name for b in bisections
                ]

                # Check if a standard bridge covers these concepts
                existing_bridge = None
                for bridge in bridges:
                    if bridge.source_chunks == [
                        chunk1.id, chunk2.id
                    ]:
                        existing_bridge = bridge
                        break

                if existing_bridge is not None:
                    # Find concepts missing from the bridge
                    missing = [
                        name for name in bisected_names
                        if name.lower()
                        not in existing_bridge.content.lower()
                    ]
                    if not missing:
                        continue  # all concepts covered
                    bisected_names = missing

                # Find gap analysis for this boundary
                recovery_gap = None
                for idx, c1, c2, ga in gap_analyses:
                    if idx == boundary_idx:
                        recovery_gap = ga
                        break

                if recovery_gap is None:
                    recovery_gap = GapAnalysis(
                        necessity_score=0.0,
                        gap_type=GapType.CONCEPTUAL,
                        bridge_strategy=(
                            BridgeStrategy.SEMANTIC_OVERLAP
                        ),
                    )

                try:
                    recovery_bridge = (
                        self.bridge_generator.generate_bridge(
                            chunk1.content,
                            chunk2.content,
                            recovery_gap,
                            content_type=(
                                content_profile.content_type
                            ),
                            domain_config=domain_config,
                            bisected_concepts=bisected_names,
                        )
                    )
                    recovery_bridge.source_chunks = [
                        chunk1.id, chunk2.id
                    ]
                    if recovery_bridge.metadata is None:
                        recovery_bridge.metadata = {}
                    recovery_bridge.metadata[
                        'is_recovery_bridge'
                    ] = True
                    recovery_bridge.metadata[
                        'target_bisected_concepts'
                    ] = bisected_names
                    recovery_bridge.metadata[
                        'adjacent_chunk_ids'
                    ] = [chunk1.id, chunk2.id]
                    recovery_bridges.append(recovery_bridge)
                except Exception as e:
                    logger.warning(
                        f"Recovery bridge generation failed "
                        f"for boundary {boundary_idx}: {e}"
                    )

            bridges.extend(recovery_bridges)
            if recovery_bridges:
                processing_notes.append(
                    f"Generated {len(recovery_bridges)} "
                    f"concept-recovery bridges"
                )

        # Step 6: Extract concepts from bridge chunks for KG indexing
        concept_extractor = self._get_concept_extractor()
        for bridge in bridges:
            try:
                bridge_concepts = concept_extractor.extract_concepts_regex(bridge.content)
                if bridge.metadata is None:
                    bridge.metadata = {}
                bridge.metadata['extracted_concepts'] = [
                    c.concept_id for c in bridge_concepts
                ]
                bridge.metadata['adjacent_chunk_ids'] = bridge.source_chunks
            except Exception as e:
                logger.warning(f"Bridge concept extraction failed: {e}")
                if bridge.metadata is None:
                    bridge.metadata = {}
                bridge.metadata['extracted_concepts'] = []
                bridge.metadata['adjacent_chunk_ids'] = bridge.source_chunks
        
        return ChunkingResult(
            chunks=final_chunks,
            bridges=bridges,
            gaps_analyzed=gaps_analyzed,
            bridges_generated=bridges_generated,
            bridges_validated=bridges_validated,
            fallbacks_created=fallbacks_created,
            processing_notes=processing_notes
        )
    
    def _perform_primary_chunking(self, text: str, content_profile: ContentProfile,
                                domain_config: DomainConfig,
                                document_id: str = "") -> Tuple[List[ProcessedChunk], Dict[int, List[UnresolvedBisection]]]:
        """Perform primary chunking based on semantic boundaries.

        Returns:
            A tuple of (chunks, unresolved_bisections_by_boundary) where
            the second element maps chunk-pair index to the list of
            ``UnresolvedBisection`` records for that boundary.
        """

        # Get chunking requirements
        chunking_reqs = content_profile.chunking_requirements
        if not chunking_reqs:
            chunking_reqs = ChunkingRequirements()

        # Split text into initial chunks based on size
        words = text.split()
        chunks = []
        current_chunk = []
        current_size = 0
        chunk_index = 0  # Track chunk index for metadata

        # Accumulate unresolved bisections per boundary.
        # Key = chunk-pair index (boundary between chunk i and chunk i+1).
        unresolved_bisections_by_boundary: Dict[int, List[UnresolvedBisection]] = {}
        # Temporary list for the current boundary call.
        pending_bisections: List[UnresolvedBisection] = []

        for word in words:
            current_chunk.append(word)
            current_size += 1

            # Check if we should create a chunk
            if current_size >= chunking_reqs.preferred_chunk_size:
                # Try to find a good boundary
                chunk_text = ' '.join(current_chunk)
                boundary_pos = self._find_semantic_boundary(
                    chunk_text, content_profile.content_type, domain_config
                )

                if boundary_pos > 0:
                    # Check for concept bisection at the
                    # proposed boundary and adjust if needed.
                    pre_text = ' '.join(
                        current_chunk[:boundary_pos]
                    )
                    post_text = ' '.join(
                        current_chunk[boundary_pos:]
                    )
                    settings = get_settings()
                    ov_window = getattr(
                        settings, 'overlap_window', 20
                    )
                    max_size = getattr(
                        chunking_reqs,
                        'max_chunk_size',
                        chunking_reqs.preferred_chunk_size * 2,
                    )
                    pending_bisections = []
                    boundary_pos = (
                        self
                        ._adjust_boundary_for_concept_contiguity(
                            pre_boundary_text=pre_text,
                            post_boundary_text=post_text,
                            boundary_word_index=boundary_pos,
                            max_chunk_size=max_size,
                            current_chunk_size=boundary_pos,
                            overlap_window=ov_window,
                            unresolved_bisections=pending_bisections,
                        )
                    )

                    # Split at (possibly adjusted) boundary
                    chunk_words = current_chunk[:boundary_pos]
                    remaining_words = current_chunk[boundary_pos:]

                    chunk = ProcessedChunk(
                        id=self._generate_chunk_id(document_id, ' '.join(chunk_words)),
                        content=' '.join(chunk_words),
                        start_position=len(chunks) * chunking_reqs.preferred_chunk_size,
                        end_position=len(chunks) * chunking_reqs.preferred_chunk_size + len(chunk_words),
                        metadata={'chunk_type': 'primary', 'word_count': len(chunk_words), 'chunk_index': chunk_index}
                    )
                    chunks.append(chunk)

                    # Back-fill chunk IDs on pending bisection records.
                    # The boundary is between this chunk (before) and the
                    # next chunk (after).  chunk_after_id will be filled
                    # once the next chunk is created.
                    boundary_pair_idx = len(chunks) - 1  # index of chunk pair
                    if pending_bisections:
                        for bisection in pending_bisections:
                            bisection.chunk_before_id = chunk.id
                        unresolved_bisections_by_boundary[boundary_pair_idx] = pending_bisections
                        pending_bisections = []

                    chunk_index += 1

                    # Start new chunk with remaining words
                    current_chunk = remaining_words
                    current_size = len(remaining_words)
                else:
                    # No good boundary found, split at current position
                    chunk = ProcessedChunk(
                        id=self._generate_chunk_id(document_id, ' '.join(current_chunk)),
                        content=' '.join(current_chunk),
                        start_position=len(chunks) * chunking_reqs.preferred_chunk_size,
                        end_position=len(chunks) * chunking_reqs.preferred_chunk_size + len(current_chunk),
                        metadata={'chunk_type': 'primary', 'word_count': len(current_chunk), 'chunk_index': chunk_index}
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                    current_chunk = []
                    current_size = 0

        # Handle remaining words
        if current_chunk:
            chunk = ProcessedChunk(
                id=self._generate_chunk_id(document_id, ' '.join(current_chunk)),
                content=' '.join(current_chunk),
                start_position=len(chunks) * chunking_reqs.preferred_chunk_size,
                end_position=len(chunks) * chunking_reqs.preferred_chunk_size + len(current_chunk),
                metadata={'chunk_type': 'primary', 'word_count': len(current_chunk), 'chunk_index': chunk_index}
            )
            chunks.append(chunk)

        # Back-fill chunk_after_id on all bisection records.
        for boundary_idx, bisections in unresolved_bisections_by_boundary.items():
            if boundary_idx < len(chunks) - 1:
                after_id = chunks[boundary_idx + 1].id
                for bisection in bisections:
                    bisection.chunk_after_id = after_id

        return chunks, unresolved_bisections_by_boundary
    
    def _find_semantic_boundary(self, text: str, content_type: ContentType,
                              domain_config: DomainConfig) -> int:
        """Find semantic boundary within text for chunking."""
        
        # Get delimiters for this domain
        delimiters = domain_config.delimiters
        
        # Try delimiters in priority order
        for delimiter in sorted(delimiters, key=lambda x: x.priority, reverse=True):
            import re
            matches = list(re.finditer(delimiter.pattern, text))
            
            if matches:
                # Find the match closest to the middle of the text
                target_pos = len(text) // 2
                best_match = min(matches, key=lambda m: abs(m.start() - target_pos))
                
                # Convert character position to word position
                words_before = len(text[:best_match.start()].split())
                return words_before
        
        # Fallback to sentence boundaries
        sentences = text.split('.')
        if len(sentences) > 1:
            # Split at middle sentence
            middle_sentence = len(sentences) // 2
            text_to_middle = '.'.join(sentences[:middle_sentence]) + '.'
            return len(text_to_middle.split())
        
        # No good boundary found
        return 0

    def _get_concept_extractor(self):
        """Lazily initialize and return a ConceptExtractor instance.

        Follows DI principles — the extractor is not created in ``__init__``
        to avoid import-time side effects.  It is cached on first use.
        """
        if not hasattr(self, '_concept_extractor') or self._concept_extractor is None:
            from ..knowledge_graph.kg_builder import ConceptExtractor
            self._concept_extractor = ConceptExtractor()
        return self._concept_extractor
    def _generate_chunk_id(self, document_id: str, content: str) -> str:
        """Generate a deterministic UUID from document ID and content hash.

        Uses SHA-256 hash of '{document_id}:{content}' to produce a
        deterministic UUID. Sets UUID version 4 bits for format compatibility.

        Raises ValueError if content is empty.

        Requirements: 7.1
        """
        if not content:
            raise ValueError("Cannot generate chunk ID from empty content")

        hash_input = f"{document_id}:{content}".encode('utf-8')
        hash_bytes = hashlib.sha256(hash_input).digest()[:16]
        hash_bytes = bytearray(hash_bytes)
        hash_bytes[6] = (hash_bytes[6] & 0x0F) | 0x40  # version 4
        hash_bytes[8] = (hash_bytes[8] & 0x3F) | 0x80  # variant 1
        return str(uuid.UUID(bytes=bytes(hash_bytes)))

    def _adjust_boundary_for_concept_contiguity(
        self,
        pre_boundary_text: str,
        post_boundary_text: str,
        boundary_word_index: int,
        max_chunk_size: int,
        current_chunk_size: int,
        overlap_window: int = 20,
        unresolved_bisections: Optional[List[UnresolvedBisection]] = None,
    ) -> int:
        """Check if a multi-word concept spans the proposed boundary.

        Returns an adjusted boundary word index that keeps the highest-
        confidence spanning concept in a single chunk.

        Algorithm:
        1. Extract last *overlap_window* tokens before boundary + first
           *overlap_window* after.
        2. Run concept extraction on the combined overlap zone.
        3. For each extracted concept, check if it spans the boundary
           position.
        4. If a spanning concept is found, shift boundary past it (or
           before it if that would exceed *max_chunk_size*).
        5. If multiple spanning concepts: prioritise highest confidence.
        6. If no spanning concepts: return boundary unchanged.

        When *unresolved_bisections* is provided, any spanning concept
        that cannot be resolved by boundary shifting is appended to the
        list as an ``UnresolvedBisection`` record.

        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 1.1, 1.2, 1.4
        """
        try:
            concept_extractor = self._get_concept_extractor()

            # Build overlap zone
            pre_words = pre_boundary_text.split()
            post_words = post_boundary_text.split()
            overlap_pre = pre_words[-overlap_window:] if len(pre_words) >= overlap_window else pre_words
            overlap_post = post_words[:overlap_window] if len(post_words) >= overlap_window else post_words
            overlap_text = ' '.join(overlap_pre + overlap_post)

            # Extract concepts from overlap zone
            overlap_concepts = concept_extractor.extract_concepts_regex(overlap_text)

            if not overlap_concepts:
                return boundary_word_index  # no concepts in overlap zone

            # Check each concept for boundary spanning
            boundary_in_overlap = len(overlap_pre)  # word index of boundary within overlap text
            overlap_words_list = overlap_pre + overlap_post
            spanning_concepts = []

            for concept in overlap_concepts:
                concept_tokens = concept.concept_name.lower().split()
                if len(concept_tokens) < 2:
                    continue  # only multi-word concepts can be bisected
                # Find concept position in overlap text (case-insensitive)
                overlap_lower = [w.lower() for w in overlap_words_list]
                for i in range(len(overlap_lower) - len(concept_tokens) + 1):
                    if overlap_lower[i:i + len(concept_tokens)] == concept_tokens:
                        concept_start = i
                        concept_end = i + len(concept_tokens)
                        if concept_start < boundary_in_overlap < concept_end:
                            spanning_concepts.append((concept, concept_start, concept_end))

            if not spanning_concepts:
                return boundary_word_index  # no concepts span the boundary

            # Pick highest-confidence spanning concept
            best = max(spanning_concepts, key=lambda x: x[0].confidence)
            concept, start_in_overlap, end_in_overlap = best

            # Record all OTHER spanning concepts as unresolved
            if unresolved_bisections is not None:
                for other_concept, _, _ in spanning_concepts:
                    if other_concept is not best[0]:
                        unresolved_bisections.append(UnresolvedBisection(
                            concept_name=other_concept.concept_name,
                            concept_confidence=other_concept.confidence,
                            boundary_index=boundary_word_index,
                            chunk_before_id="",
                            chunk_after_id="",
                        ))

            # Shift boundary past the concept (keep concept in current chunk)
            shift_forward = end_in_overlap - boundary_in_overlap
            new_boundary_forward = boundary_word_index + shift_forward
            if current_chunk_size + shift_forward <= max_chunk_size:
                return new_boundary_forward

            # Can't shift forward — shift backward (put concept in next chunk)
            shift_backward = boundary_in_overlap - start_in_overlap
            new_boundary_backward = boundary_word_index - shift_backward
            # Guard: don't produce a negative or zero-size chunk
            if new_boundary_backward > 0:
                return new_boundary_backward

            # Fallback: record the BEST concept as unresolved too
            if unresolved_bisections is not None:
                unresolved_bisections.append(UnresolvedBisection(
                    concept_name=concept.concept_name,
                    concept_confidence=concept.confidence,
                    boundary_index=boundary_word_index,
                    chunk_before_id="",
                    chunk_after_id="",
                ))
            return boundary_word_index

        except Exception:
            # If concept extraction fails for any reason, return original
            # boundary unchanged to maintain backward compatibility.
            logger.debug(
                "Concept bisection check failed; keeping original boundary",
                exc_info=True,
            )
            return boundary_word_index

    
    def _perform_secondary_chunking(self, chunks: List[ProcessedChunk],
                                  content_profile: ContentProfile,
                                  domain_config: DomainConfig,
                                  document_id: str = "") -> List[ProcessedChunk]:
        """Perform secondary chunking to refine chunk boundaries."""
        
        refined_chunks = []
        
        for chunk in chunks:
            # Check if chunk needs further splitting
            chunking_reqs = content_profile.chunking_requirements
            if not chunking_reqs:
                chunking_reqs = ChunkingRequirements()
            
            word_count = len(chunk.content.split())
            
            if word_count > chunking_reqs.max_chunk_size:
                # Split large chunk
                sub_chunks = self._split_large_chunk(chunk, chunking_reqs, domain_config, document_id=document_id)
                refined_chunks.extend(sub_chunks)
            elif word_count < chunking_reqs.min_chunk_size and refined_chunks:
                # Merge small chunk with previous chunk ONLY if result won't exceed max
                previous_chunk = refined_chunks[-1]
                previous_word_count = len(previous_chunk.content.split())
                merged_word_count = previous_word_count + word_count
                
                # Only merge if combined size is within max_chunk_size limit
                if merged_word_count <= chunking_reqs.max_chunk_size:
                    merged_content = previous_chunk.content + " " + chunk.content
                    
                    merged_chunk = ProcessedChunk(
                        id=previous_chunk.id,
                        content=merged_content,
                        start_position=previous_chunk.start_position,
                        end_position=chunk.end_position,
                        metadata={
                            'chunk_type': 'merged',
                            'word_count': merged_word_count,
                            'merged_from': [previous_chunk.id, chunk.id]
                        }
                    )
                    refined_chunks[-1] = merged_chunk
                else:
                    # Don't merge - keep chunk separate even if small
                    refined_chunks.append(chunk)
            else:
                refined_chunks.append(chunk)
        
        return refined_chunks
    
    def _split_large_chunk(self, chunk: ProcessedChunk, chunking_reqs: ChunkingRequirements,
                         domain_config: DomainConfig,
                         document_id: str = "") -> List[ProcessedChunk]:
        """Split a large chunk into smaller chunks."""
        
        words = chunk.content.split()
        target_size = chunking_reqs.preferred_chunk_size
        
        sub_chunks = []
        current_words = []
        sub_chunk_index = 0
        
        for word in words:
            current_words.append(word)
            
            if len(current_words) >= target_size:
                sub_chunk = ProcessedChunk(
                    id=self._generate_chunk_id(document_id, ' '.join(current_words)),
                    content=' '.join(current_words),
                    start_position=chunk.start_position + sub_chunk_index * target_size,
                    end_position=chunk.start_position + (sub_chunk_index + 1) * target_size,
                    metadata={
                        'chunk_type': 'secondary',
                        'parent_chunk_id': chunk.id,  # Reference parent by ID
                        'sub_chunk_index': sub_chunk_index,
                        'word_count': len(current_words)
                    }
                )
                sub_chunks.append(sub_chunk)
                sub_chunk_index += 1
                current_words = []
        
        # Handle remaining words
        if current_words:
            sub_chunk = ProcessedChunk(
                id=self._generate_chunk_id(document_id, ' '.join(current_words)),
                content=' '.join(current_words),
                start_position=chunk.start_position + sub_chunk_index * target_size,
                end_position=chunk.end_position,
                metadata={
                    'chunk_type': 'secondary',
                    'parent_chunk_id': chunk.id,  # Reference parent by ID
                    'sub_chunk_index': sub_chunk_index,
                    'word_count': len(current_words)
                }
            )
            sub_chunks.append(sub_chunk)
        
        return sub_chunks
    
    def _generate_and_validate_bridge(self, chunk1: ProcessedChunk, chunk2: ProcessedChunk,
                                    gap_analysis: GapAnalysis, content_profile: ContentProfile,
                                    domain_config: DomainConfig) -> Optional[BridgeChunk]:
        """Generate and validate a bridge between two chunks."""
        
        try:
            # Generate bridge
            bridge = self.bridge_generator.generate_bridge(
                chunk1.content, chunk2.content, gap_analysis,
                content_profile.content_type, domain_config
            )
            
            # Validate bridge
            validation_result = self.validator.validate_bridge(
                bridge, chunk1.content, chunk2.content, content_profile.content_type
            )
            
            bridge.validation_result = validation_result
            
            # If validation fails, try fallback
            if not validation_result.passed_validation:
                logger.debug(f"Bridge validation failed (score: {validation_result.composite_score:.2f}), trying fallback")
                
                fallback_result = self.fallback_system.create_fallback(
                    chunk1.content, chunk2.content, gap_analysis,
                    content_profile.content_type, bridge.content
                )
                
                # Create fallback bridge
                fallback_bridge = BridgeChunk(
                    content=fallback_result.fallback_content,
                    source_chunks=[chunk1.id, chunk2.id],
                    generation_method=fallback_result.strategy_used.value,
                    gap_analysis=gap_analysis,
                    confidence_score=fallback_result.quality_score,
                    created_at=datetime.now()
                )
                
                # Check if fallback should be upgraded
                if self.fallback_system.detect_upgrade_opportunity(fallback_result):
                    logger.info("Fallback marked for potential upgrade to bridge")
                    fallback_bridge.metadata = {'upgrade_candidate': True}
                
                return fallback_bridge
            
            return bridge
        
        except Exception as e:
            logger.warning(f"Bridge generation failed: {e}")
            
            # Create fallback
            fallback_result = self.fallback_system.create_fallback(
                chunk1.content, chunk2.content, gap_analysis, content_profile.content_type
            )
            
            return BridgeChunk(
                content=fallback_result.fallback_content,
                source_chunks=[chunk1.id, chunk2.id],
                generation_method=fallback_result.strategy_used.value,
                gap_analysis=gap_analysis,
                confidence_score=fallback_result.quality_score,
                created_at=datetime.now()
            )
    
    def optimize_configuration(self, domain_name: str, 
                             performance_data: Dict[str, Any]) -> DomainConfig:
        """
        Continuously optimize domain configuration based on usage.
        
        Args:
            domain_name: Name of the domain to optimize
            performance_data: Performance metrics for optimization
            
        Returns:
            Optimized DomainConfig
        """
        logger.info(f"Optimizing configuration for domain: {domain_name}")
        
        # Convert performance data to PerformanceMetrics
        from ...models.chunking import PerformanceMetrics
        
        performance_metrics = PerformanceMetrics(
            chunk_quality_score=performance_data.get('chunk_quality_score', 0.0),
            bridge_success_rate=performance_data.get('bridge_success_rate', 0.0),
            retrieval_effectiveness=performance_data.get('retrieval_effectiveness', 0.0),
            user_satisfaction_score=performance_data.get('user_satisfaction_score', 0.0),
            processing_efficiency=performance_data.get('processing_efficiency', 0.0),
            boundary_quality=performance_data.get('boundary_quality', 0.0),
            document_count=performance_data.get('document_count', 0)
        )
        
        return self.config_manager.optimize_configuration(domain_name, performance_metrics)
    
    def _update_framework_stats(self, processing_stats: Dict[str, Any], success: bool):
        """Update framework statistics."""
        self.framework_stats['documents_processed'] += 1
        
        if success:
            self.framework_stats['total_chunks_created'] += processing_stats.get('chunks_created', 0)
            self.framework_stats['total_bridges_generated'] += processing_stats.get('bridges_generated', 0)
            self.framework_stats['total_fallbacks_created'] += processing_stats.get('fallbacks_created', 0)
        
        # Update average processing time
        total_docs = self.framework_stats['documents_processed']
        current_avg = self.framework_stats['average_processing_time']
        new_time = processing_stats.get('processing_time', 0.0)
        
        self.framework_stats['average_processing_time'] = (
            (current_avg * (total_docs - 1) + new_time) / total_docs
        )
        
        # Update success rate
        if success:
            successful_docs = sum(1 for _ in range(total_docs) if success)  # Simplified
            self.framework_stats['success_rate'] = successful_docs / total_docs
    
    def get_framework_statistics(self) -> Dict[str, Any]:
        """Get comprehensive framework statistics."""
        stats = self.framework_stats.copy()
        
        # Add component statistics
        stats['content_analyzer'] = {}  # Content analyzer doesn't have stats yet
        stats['config_manager'] = {}    # Config manager doesn't have stats yet
        stats['gap_analyzer'] = {}      # Gap analyzer doesn't have stats yet
        stats['bridge_generator'] = self.bridge_generator.get_generation_statistics()
        stats['validator'] = self.validator.get_validation_statistics()
        stats['fallback_system'] = self.fallback_system.get_fallback_statistics()
        
        return stats
    
    def reset_statistics(self):
        """Reset all framework statistics."""
        self.framework_stats = {
            'documents_processed': 0,
            'total_chunks_created': 0,
            'total_bridges_generated': 0,
            'total_fallbacks_created': 0,
            'average_processing_time': 0.0,
            'success_rate': 0.0
        }
        
        # Reset component statistics
        self.bridge_generator.reset_statistics()
        self.validator.reset_statistics()
        self.fallback_system.reset_statistics()