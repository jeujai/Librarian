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
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

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
from .bridge_generator import BatchGenerationStats, SmartBridgeGenerator
from .config_manager import DomainConfigurationManager
from .content_analyzer import AutomatedContentAnalyzer
from .fallback_system import FallbackConfig, IntelligentFallbackSystem
from .gap_analyzer import ConceptualGapAnalyzer
from .validator import MultiStageValidator, ValidationConfig

logger = logging.getLogger(__name__)


# Module-level cache for the bundled English word list used to tell a
# hyphenated soft-wrap ("trans-\nmission") from a true hyphenated compound that
# wrapped at its own hyphen ("exposure-\nprone").  Loaded lazily once.
_ENGLISH_WORDS: Optional[frozenset] = None


def _load_english_words() -> frozenset:
    """Load (and cache) the bundled lowercase English word list."""
    global _ENGLISH_WORDS
    if _ENGLISH_WORDS is None:
        import gzip
        import os

        path = os.path.join(os.path.dirname(__file__), "english_words.txt.gz")
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                _ENGLISH_WORDS = frozenset(f.read().splitlines())
        except Exception as e:  # noqa: BLE001 — degrade gracefully
            logger.warning(
                "Could not load English word list (%s); de-hyphenation will "
                "merge all soft-wrap candidates",
                e,
            )
            _ENGLISH_WORDS = frozenset()
    return _ENGLISH_WORDS


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

        # Vetted multi-word concept vocabulary (lowercased names), prefetched by
        # the caller (celery) before chunking.  Empty by default, so the
        # boundary-contiguity check falls back to its regex + spaCy sources.
        self.known_concept_names: Set[str] = set()

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

        # Step 4: Append table chunks (discrete units, excluded from gap analysis)
        table_chunks = self._chunk_tables(document, document_id or "")
        if table_chunks:
            final_chunks = final_chunks + table_chunks
            processing_notes.append(f"Appended {len(table_chunks)} table chunks")

        return {
            'chunks': final_chunks,
            'gaps_analyzed': len(gap_analyses),
            'bridge_needed_serialized': bridge_needed_serialized,
            'unresolved_bisections_serialized': unresolved_serialized,
            'processing_notes': processing_notes,
        }

    def _chunk_tables(self, document: DocumentContent,
                      document_id: str) -> List[ProcessedChunk]:
        """Render extracted tables into dedicated retrievable chunks.

        Each table's structured cell data (headers + rows) is decoded from
        ``MediaElement.content_data`` (JSON bytes) and rendered as a stable
        pipe-delimited text block, so downstream retrieval/citation can surface
        tabular facts (e.g. drug-dose rows) that the main text stream omits.

        Returns one ``ProcessedChunk`` per table with ``chunk_type="table"``.
        """
        import json as _json

        chunks: List[ProcessedChunk] = []
        for table in document.tables:
            if table.element_type != "table" or not table.content_data:
                continue
            try:
                table_dict = _json.loads(table.content_data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                logger.warning(
                    "Skipping table %s: bad content_data (%s)", table.element_id, e
                )
                continue

            headers = table_dict.get("headers") or []
            rows = table_dict.get("rows") or []
            if not rows:
                continue

            def _cells(row):
                return [
                    ("" if c is None else str(c)).replace("\n", " ")
                    for c in row
                ]

            lines = []
            if headers:
                lines.append(" | ".join(_cells(headers)))
            for row in rows:
                lines.append(" | ".join(_cells(row)))

            content = "\n".join(lines).strip()
            if not content:
                continue

            table_meta = table.metadata or {}
            chunks.append(ProcessedChunk(
                id=str(uuid.uuid4()),
                content=content,
                start_position=0,
                end_position=0,
                chunk_type="table",
                metadata={
                    "page_number": table_meta.get("page_number"),
                    "table_index": table_meta.get("table_index"),
                    "row_count": table_dict.get("row_count", len(rows)),
                    "col_count": table_dict.get("col_count", len(headers)),
                    "element_id": table.element_id,
                    "caption": table.caption,
                },
            ))

        return chunks

    def generate_bridges_for_document(self, bridge_generation_data: Dict[str, Any],
                                     progress_callback: callable = None,
                                     storage_callback: callable = None) -> Tuple[List[BridgeChunk], BatchGenerationStats]:
        """Generate bridges from previously serialized bridge data.
        
        This is the slow path (~550s) that can run in parallel with
        embedding storage and KG extraction.
        
        Args:
            bridge_generation_data: Dict from processing_stats['bridge_generation_data']
            progress_callback: Optional callback for progress reporting
            storage_callback: Optional async callback for incremental storage.
                Called after each batch of bridges is generated and validated.
                Signature: async def callback(bridges: List[BridgeChunk]) -> None
                This enables incremental storage to preserve progress on failure.
            
        Returns:
            Tuple of (List of BridgeChunk objects, BatchGenerationStats)
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
            empty_stats = BatchGenerationStats(
                total_requests=0,
                successful_generations=0,
                failed_generations=0,
                total_tokens_used=0,
                total_cost_estimate=0.0,
                average_generation_time=0.0,
                batch_processing_time=0.0,
            )
            return ([], empty_stats)
        
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
        
        raw_bridges, batch_stats = self.bridge_generator.batch_generate_bridges(
            boundary_pairs,
            content_type=content_type,
            domain_config=domain_config,
            bisected_concepts_per_boundary=bisected_concepts_per_boundary,
            progress_callback=progress_callback,
            storage_callback=storage_callback,
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
        return (bridges, batch_stats)

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
            
            raw_bridges, _batch_stats = self.bridge_generator.batch_generate_bridges(
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
    
    @staticmethod
    def _dehyphenate_soft_wraps(text: str) -> str:
        """Merge hyphenated line-breaks introduced by PDF justification.

        Justified PDFs break long words with a typesetter hyphen at the line
        end, so extracted text carries "trans-\\nmission".  After the
        whitespace collapse this becomes the broken token "trans- mission",
        which a query for "transmission" never matches.  This folds those
        back together.  A true hyphenated compound that happens to wrap at its
        own hyphen ("exposure-\\nprone") is instead re-joined with the hyphen
        kept ("exposure-prone").

        Disambiguation uses the bundled English word list:

        * merged form is a known word   -> soft-wrap, drop the hyphen
        * both fragments are known words -> true compound, keep the hyphen
        * either fragment is unknown    -> soft-wrap, drop the hyphen

        Acronym/camelCase compounds ("HCP-\\nto") are recognised by internal
        capitals in the left fragment and always keep the hyphen.
        """
        import re

        pattern = re.compile(r"([A-Za-z]+)-(\n[ \t]*)([a-z][A-Za-z]*)")
        words = _load_english_words()

        def _known(word: str) -> bool:
            return word in words

        def _repl(match: "re.Match") -> str:
            left = match.group(1)
            right = match.group(3)
            # Internal capitals -> acronym/camelCase compound ("HCP-to").
            if sum(1 for c in left if c.isupper()) >= 2:
                return left + "-" + right
            left_lower = left.lower()
            right_lower = right.lower()
            if _known(left_lower + right_lower):
                return left + right  # soft-wrap
            if _known(left_lower) and _known(right_lower):
                return left + "-" + right  # true compound
            return left + right  # default: soft-wrap

        return pattern.sub(_repl, text)

    # Function words never terminate a soft-wrap ("pre- and post-operative"):
    # a hyphen directly followed by one of these is a dash, not a line-break.
    _FUNCTION_WORDS = frozenset({
        "and", "or", "the", "a", "an", "of", "to", "in", "on", "with",
        "for", "by", "from", "as", "at", "is", "are", "was", "were", "be",
        "been", "that", "this", "these", "those", "it", "its", "not",
    })

    # Common English inflections tried when deciding whether a merged soft-wrap
    # candidate is a real word ("recommendations" -> "recommendation" -> word).
    # Longer suffixes first so "boxes" strips "es" (not "s" -> "boxe").
    _INFLECTIONS = (
        ("ies", "y"), ("es", ""), ("s", ""), ("ed", ""),
        ("ing", ""), ("ing", "e"), ("d", ""),
    )

    @staticmethod
    def _dehyphenate_space_wraps(
        text: str,
        extra_words: Optional[Iterable[str]] = None,
    ) -> str:
        """Fold already-whitespace-collapsed soft-wrap hyphens ("andro- gen").

        The newline-form counterpart (:meth:`_dehyphenate_soft_wraps`) runs
        *during* chunking, before the whitespace collapse, so it sees the raw
        "trans-\\nmission".  Chunks stored before that fix carry the collapsed
        artifact "trans- mission" — a hyphen directly followed by a space.  This
        folds those in place, so a re-chunk of the whole document is not needed.

        The space-collapsed form has lost the line-break signal, so a soft-wrap
        ("gyneco- mastia") is indistinguishable from a true compound ("B- cell")
        on the surface.  The word list is the only cheap discriminator, so this
        method is deliberately conservative: it only *joins* when the merged
        form is a known word (or a known word plus a common inflection —
        "recommen- dations" -> "recommendations" -> "recommendation").  Every
        other case keeps the hyphen and only drops the spurious space, which
        restores true compounds ("B- cell" -> "B-cell", "enzyme- inducing" ->
        "enzyme-inducing") without corrupting them.

        ``extra_words`` supplements the bundled English word list with a
        domain vocabulary (e.g. UMLS / concept names), so medical soft-wraps
        ("thromboem- bolism" -> "thromboembolism") are also joined.  For bulk
        use, pass a pre-built :class:`set`/``frozenset`` (building it once
        rather than per-call).
        """
        import re

        pattern = re.compile(r"([A-Za-z]+)-([ \t]+)([A-Za-z][A-Za-z]*)")
        words = _load_english_words()
        extra = extra_words
        function_words = GenericMultiLevelChunkingFramework._FUNCTION_WORDS
        inflections = GenericMultiLevelChunkingFramework._INFLECTIONS

        def _known(word: str) -> bool:
            """True if ``word`` is a known word, possibly with a common English
            inflection stripped ("recommendations" -> "recommendation").
            """
            if word in words or (extra is not None and word in extra):
                return True
            for suffix, replacement in inflections:
                if word.endswith(suffix) and len(word) > len(suffix) + 1:
                    stem = word[: -len(suffix)] + replacement
                    if stem in words or (extra is not None and stem in extra):
                        return True
            return False

        def _repl(match: "re.Match") -> str:
            left = match.group(1)
            right = match.group(3)
            right_lower = right.lower()
            if right_lower in function_words:
                return match.group(0)  # dash + conjunction, not a soft-wrap
            if _known(left.lower() + right_lower):
                return left + right  # soft-wrap -> join
            return left + "-" + right  # compound -> drop space, keep hyphen

        return pattern.sub(_repl, text)

    @staticmethod
    def _split_words_preserving_whitespace(text: str) -> Tuple[List[str], List[str]]:
        """Split *text* into ``(words, separators)``.

        ``words`` is identical to ``text.split()`` (same tokenization, so chunk
        IDs stay stable).  ``separators[i]`` is the whitespace run — including
        any newlines — immediately before ``words[i]``, which lets
        ``\\n``-anchored domain delimiters match even after the buffer is
        reconstructed for boundary detection.
        """
        import re
        words = text.split()
        separators = [''] * len(words)
        pos = 0
        for i, match in enumerate(re.finditer(r'\S+', text)):
            if i >= len(words):
                break
            separators[i] = text[pos:match.start()]
            pos = match.end()
        return words, separators

    @staticmethod
    def _reconstruct_with_whitespace(words: List[str], separators: List[str]) -> str:
        """Rejoin *words* with their original inter-word whitespace.

        The first separator (whitespace before the first word) is dropped so
        the result has no leading whitespace, keeping the word count identical
        to the flat ``words`` list used for chunk content.
        """
        parts = []
        for i, word in enumerate(words):
            if i > 0:
                parts.append(separators[i])
            parts.append(word)
        return ''.join(parts)

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

        # Fold hyphenated soft-wraps ("trans-\nmission" -> "transmission")
        # before tokenising so chunk content (and hence chunk IDs) are clean.
        text = self._dehyphenate_soft_wraps(text)

        # Split text into initial chunks based on size.  Keep the original
        # whitespace (newlines included) alongside each word so that
        # newline-anchored domain delimiters can still match during boundary
        # detection.
        words, word_separators = self._split_words_preserving_whitespace(text)
        chunks = []
        current_chunk = []
        current_separators = []
        current_size = 0
        chunk_index = 0  # Track chunk index for metadata

        # Accumulate unresolved bisections per boundary.
        # Key = chunk-pair index (boundary between chunk i and chunk i+1).
        unresolved_bisections_by_boundary: Dict[int, List[UnresolvedBisection]] = {}
        # Temporary list for the current boundary call.
        pending_bisections: List[UnresolvedBisection] = []

        i = 0
        n_words = len(words)
        while i < n_words:
            word = words[i]
            separator = word_separators[i]
            i += 1
            current_chunk.append(word)
            current_separators.append(separator)
            current_size += 1

            # Check if we should create a chunk
            if current_size >= chunking_reqs.preferred_chunk_size:
                # Try to find a good boundary.  Reconstruct the buffer with
                # its original whitespace so newline-anchored delimiters
                # (section headers, numbered subsections) can match.
                chunk_text = self._reconstruct_with_whitespace(
                    current_chunk, current_separators
                )
                boundary_pos = self._find_semantic_boundary(
                    chunk_text, content_profile.content_type, domain_config
                )

                if boundary_pos > 0:
                    # Check for concept bisection at the
                    # proposed boundary and adjust if needed.
                    # Preserve the buffer's original whitespace (newlines) so
                    # the concept-contiguity snap-back can re-anchor to
                    # newline/list-item boundaries, not just period-based
                    # sentence ends.
                    pre_text = self._reconstruct_with_whitespace(
                        current_chunk[:boundary_pos],
                        current_separators[:boundary_pos],
                    )
                    post_text = self._reconstruct_with_whitespace(
                        current_chunk[boundary_pos:],
                        current_separators[boundary_pos:],
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
                    remaining_separators = current_separators[boundary_pos:]

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
                    current_separators = remaining_separators
                    current_size = len(remaining_words)
                else:
                    # No sentence boundary exists anywhere in this buffer (the
                    # search already ran inside _find_semantic_boundary), so a
                    # hard split at the buffer end is required.  Still run the
                    # concept-contiguity check against the following lookahead
                    # words so a multi-word concept spanning into the next
                    # buffer is kept whole instead of silently bisected.
                    settings = get_settings()
                    ov_window = getattr(settings, 'overlap_window', 20)
                    max_size = getattr(
                        chunking_reqs,
                        'max_chunk_size',
                        chunking_reqs.preferred_chunk_size * 2,
                    )
                    pre_text = self._reconstruct_with_whitespace(
                        current_chunk, current_separators
                    )
                    post_text = self._reconstruct_with_whitespace(
                        words[i:i + ov_window],
                        word_separators[i:i + ov_window],
                    )
                    pending_bisections = []
                    boundary_pos = (
                        self
                        ._adjust_boundary_for_concept_contiguity(
                            pre_boundary_text=pre_text,
                            post_boundary_text=post_text,
                            boundary_word_index=len(current_chunk),
                            max_chunk_size=max_size,
                            current_chunk_size=len(current_chunk),
                            overlap_window=ov_window,
                            unresolved_bisections=pending_bisections,
                        )
                    )

                    # A forward shift (keep the concept in this chunk) moves
                    # the boundary past the buffer end — pull those words in
                    # from the input stream so the concept stays whole.
                    if boundary_pos > len(current_chunk):
                        extra = boundary_pos - len(current_chunk)
                        for _ in range(min(extra, n_words - i)):
                            current_chunk.append(words[i])
                            current_separators.append(word_separators[i])
                            i += 1
                        boundary_pos = len(current_chunk)

                    chunk_words = current_chunk[:boundary_pos]
                    remaining_words = current_chunk[boundary_pos:]
                    remaining_separators = current_separators[boundary_pos:]

                    chunk = ProcessedChunk(
                        id=self._generate_chunk_id(document_id, ' '.join(chunk_words)),
                        content=' '.join(chunk_words),
                        start_position=len(chunks) * chunking_reqs.preferred_chunk_size,
                        end_position=len(chunks) * chunking_reqs.preferred_chunk_size + len(chunk_words),
                        metadata={'chunk_type': 'primary', 'word_count': len(chunk_words), 'chunk_index': chunk_index}
                    )
                    chunks.append(chunk)

                    boundary_pair_idx = len(chunks) - 1
                    if pending_bisections:
                        for bisection in pending_bisections:
                            bisection.chunk_before_id = chunk.id
                        unresolved_bisections_by_boundary[boundary_pair_idx] = pending_bisections
                        pending_bisections = []

                    chunk_index += 1
                    current_chunk = remaining_words
                    current_separators = remaining_separators
                    current_size = len(remaining_words)

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
        
        # Fallback to sentence boundaries.  The naive ``text.split('.')`` this
        # replaces treated every period as a sentence end, so it split a nested
        # list at "iii." and orphaned the marker from its content ("iii." at the
        # end of one chunk, "Is followed by ..." at the start of the next).  The
        # sentence-aware splitter below avoids that and honours concept/sentence
        # contiguity.
        boundaries = self._find_sentence_boundaries(text)
        if boundaries:
            target_pos = len(text.split()) // 2
            return min(boundaries, key=lambda b: abs(b - target_pos))

        # No good boundary found
        return 0

    def _find_sentence_boundaries(self, text: str) -> List[int]:
        """Return word counts at clean split points in *text*.

        Two kinds of boundary are detected:

        1. Real sentence ends — a ``.``/``!``/``?`` followed by whitespace (or
           end-of-string), where the preceding token is a genuine word (not a
           list marker, initial, or abbreviation).  The split lands AFTER the
           terminating punctuation, including any closing quote/bracket that
           immediately follows it ('".', '.)', '.]').
        2. List-item starts — an inline roman numeral ("iii."), single letter
           ("a."), or short number ("5.") marker.  The split lands BEFORE the
           marker so the marker stays attached to its content.

        Decimals ("3.14") and dot-prefixed abbreviations are ruled out by the
        whitespace requirement (no whitespace follows the period in "3.14").
        """
        import re

        abbreviations = {
            'dr', 'mr', 'mrs', 'ms', 'prof', 'sr', 'jr', 'st', 'inc', 'ltd',
            'corp', 'co', 'etc', 'vs', 'eg', 'ie', 'cf', 'al', 'vol',
            'ed', 'eds', 'pp', 'resp', 'min', 'max', 'approx', 'dept',
            'assoc', 'ca', 'ch', 'sec', 'rev',
            # Medical/clinical shorthand commonly written with a trailing
            # period.  Dot-stripped forms so "p.o." and "q.d." match too.
            'pt', 'pts', 'neg', 'pos', 'ref', 'refs', 'incl', 'excl', 'esp',
            'wks', 'hrs', 'mo', 'mos', 'yr', 'yrs',
            'bid', 'tid', 'qid', 'qd', 'po', 'prn', 'npo', 'qam', 'qpm',
            'qh', 'qhs', 'im', 'sc', 'subq', 'md', 'phd', 'rn', 'dds',
            'mph', 'od', 'wrt', 'spp', 'var',
            # Additional clinical/time shorthand ("i.v.", "b.p.", "8 a.m.").
            # Dot-stripped forms, except where stripping yields a common
            # English word ("am"/"pm"): those keep their internal dot so a
            # sentence-final "I am." or "at 8 pm." is not misread as the
            # dotted abbreviation.
            'hr', 'wk', 'iv', 'bp', 'est', 'avg', 'std', 'wt',
            'a.m', 'p.m', 'viz',
        }
        roman_numeral = re.compile(r'^[ivxlcdm]+$')
        closing_punct = set("\"')]}»”’")

        total_words = len(text.split())
        boundaries: List[int] = []

        def _starts_sentence(word: str) -> bool:
            """True if *word* begins a new sentence (or is end-of-text)."""
            if not word:
                return True
            c = word[0]
            return c.isupper() or c.isdigit() or c in "\"'([{«“‘"

        for match in re.finditer(r'[.!?]', text):
            pos = match.start()

            # The period may be followed by a closing quote/bracket before the
            # whitespace that ends the sentence ('".', '.)', '.]').  Skip those
            # so such sentence ends are recognised; the split lands after the
            # closing punctuation.
            end_pos = pos + 1
            while end_pos < len(text) and text[end_pos] in closing_punct:
                end_pos += 1
            before = text[:pos].rstrip()
            token = before.rsplit(None, 1)[-1] if before else ''
            token_clean = token.rstrip('.,;:()[]"\'')
            token_lower = token_clean.lower()

            nxt = text[end_pos:end_pos + 1]
            if nxt and not nxt.isspace():
                # A period/!? fused directly to an uppercase letter is a
                # dropped-space PDF artifact ("...tested.Next, the HCP").
                # Split it as a sentence end, unless the punctuation closes a
                # known abbreviation ("Dr.Smith" keeps the title fused).
                fused_is_abbrev = (
                    token_lower in abbreviations
                    or token_lower.replace('.', '') in abbreviations
                )
                if nxt.isupper() and not fused_is_abbrev:
                    boundary = len(text[:end_pos].split())
                    if 0 < boundary < total_words:
                        boundaries.append(boundary)
                continue

            # List marker — split BEFORE it so it stays with its content.
            # Multi-char roman numerals ("iii.") and short numbers ("5.") are
            # unambiguous markers; a lowercase single letter ("a.", "b.") is a
            # lettered list item.
            is_roman = bool(roman_numeral.match(token_lower)) and 2 <= len(token_lower) <= 4
            is_lower_letter = len(token_lower) == 1 and token_clean.islower()
            is_short_number = token_lower.isdigit() and len(token_lower) <= 2
            if is_roman or is_lower_letter or is_short_number:
                marker_start = pos - len(token)
                boundary = len(text[:marker_start].rstrip().split())
                if 0 < boundary < total_words:
                    boundaries.append(boundary)
                continue

            # Uppercase single letter ("K.", "I.") is a name initial, not a
            # boundary at all — neither a list marker nor a sentence end.
            is_initial = len(token_lower) == 1 and token_clean.isupper()
            if is_initial:
                continue

            is_abbrev = (
                token_lower in abbreviations
                or token_lower.replace('.', '') in abbreviations
            )

            # A period is a sentence end only if the next word starts a new
            # sentence (capitalised, a digit, an opening quote/bracket, or
            # end-of-text).  A lowercase continuation means the period was an
            # abbreviation or decimal ("p.o. twice daily", "neg. for hepatitis",
            # "3.14"), so it is NOT a boundary.  This one rule removes most
            # spurious splits on medical shorthand without enumerating every
            # abbreviation.
            after_text = text[end_pos:]
            next_word = after_text.split()[0] if after_text.strip() else ''
            if not _starts_sentence(next_word):
                continue

            # A known abbreviation before a capitalised word is still not a
            # sentence end ("Dr. Smith", "resp. HBV infection"), so the
            # abbreviation list suppresses that case.
            if is_abbrev:
                continue

            # "No.", "Fig.", "Temp." are abbreviations only when a numeral
            # follows ("No. 5", "Fig. 3", "Temp. 98.6"); before a capitalised
            # word the lowercase form is the English word ("no", "fig",
            # "temp") and ends the sentence.  They are deliberately absent
            # from the abbreviation set above so the bare word is not
            # blanket-suppressed.
            if token_lower in ('no', 'fig', 'temp') and next_word[:1].isdigit():
                continue

            # Real sentence end — split AFTER the terminating punctuation
            # (and any closing quote/bracket).
            boundary = len(text[:end_pos].split())
            if 0 < boundary < total_words:
                boundaries.append(boundary)

        # Newline-signalled list items and paragraph breaks.  The period-based
        # scan above cannot see bullet markers ("-", "•") or parenthesised
        # list markers ("a)", "(1)", "1)") because they carry no terminal
        # punctuation, so a bulleted/numbered list produced zero boundaries
        # and its items were bisected mid-phrase.  Detect a boundary when a
        # newline is followed (after indentation) by a list marker or by a
        # blank line.
        bullet_chars = set("-*•·▪◦○∙‣⁃–—")
        list_marker = re.compile(r'(?:[0-9]+|[a-zA-Z]|[ivxlcdm]{2,4})[.)]\s+')
        paren_marker = re.compile(r'\([0-9a-zA-Z]{1,3}\)\s+')

        for m in re.finditer(r'\n', text):
            after = text[m.end():]

            # Blank line (paragraph break): newline then optional indentation
            # then another newline.
            if re.match(r'[ \t]*\n', after):
                boundary = len(text[:m.end()].rstrip().split())
                if 0 < boundary < total_words:
                    boundaries.append(boundary)
                continue

            # Strip indentation on the following line.
            rest = re.sub(r'^[ \t]*', '', after)

            # Bullet marker at the start of the line ("- item", "• item").
            if rest and rest[0] in bullet_chars and (len(rest) == 1 or rest[1].isspace()):
                boundary = len(text[:m.end()].rstrip().split())
                if 0 < boundary < total_words:
                    boundaries.append(boundary)
                continue

            # Number/letter/roman + "." or ")", or a "(x)" marker.
            if list_marker.match(rest) or paren_marker.match(rest):
                boundary = len(text[:m.end()].rstrip().split())
                if 0 < boundary < total_words:
                    boundaries.append(boundary)
                continue

        # Bare capitalised phrase LISTS — two or more consecutive short
        # Title-Case / ALL-CAPS lines with no marker and no terminal
        # punctuation ("Healthcare Personnel" / "Post-Exposure Prophylaxis").
        # A single isolated capitalised line is ambiguous with wrapped prose
        # ("Hepatitis B Virus" landing on its own line mid-sentence), so it is
        # deliberately NOT split; only runs of >=2 such lines are list items.
        lines = text.split('\n')
        cap_flags = [self._is_standalone_capitalized_phrase(ln) for ln in lines]
        i = 0
        while i < len(lines):
            if cap_flags[i]:
                j = i
                while j < len(lines) and cap_flags[j]:
                    j += 1
                if j - i >= 2:
                    for k in range(i, j):
                        boundary = len(' '.join(lines[:k]).split())
                        if 0 < boundary < total_words:
                            boundaries.append(boundary)
                i = j
            else:
                i += 1

        return sorted(set(boundaries))

    @staticmethod
    def _is_standalone_capitalized_phrase(line: str) -> bool:
        """True if *line* is a short bare Title-Case / ALL-CAPS phrase.

        Detects list-item labels that carry no bullet/number/parenthesis
        marker and no terminal punctuation ("Healthcare Personnel",
        "Post-Exposure Prophylaxis").  A high ratio of capitalised words
        (>= 0.8, over alphabetic words only) discriminates such labels from
        wrapped prose, where at most the first word of a line is capitalised.
        """
        line = line.strip()
        if not line or not line[-1].isalnum():
            return False
        words = line.split()
        if not (2 <= len(words) <= 10):
            return False
        alpha = [w for w in words if w[0].isalpha()]
        if len(alpha) < 2:
            return False
        caps = sum(1 for w in alpha if w[0].isupper())
        return caps / len(alpha) >= 0.8

    def _get_concept_extractor(self):
        """Lazily initialize and return a ConceptExtractor instance.

        Follows DI principles — the extractor is not created in ``__init__``
        to avoid import-time side effects.  It is cached on first use.
        """
        if not hasattr(self, '_concept_extractor') or self._concept_extractor is None:
            from ..knowledge_graph.kg_builder import ConceptExtractor
            self._concept_extractor = ConceptExtractor()
        return self._concept_extractor

    def _get_spacy_nlp(self):
        """Lazily load a spaCy model for domain-aware noun-chunk extraction.

        Prefers ``en_core_sci_sm`` (biomedical multi-word phrases) and falls
        back to ``en_core_web_sm``.  Returns ``None`` when spaCy or its models
        are unavailable so callers can fall back to the regex concept source.
        """
        if getattr(self, '_spacy_nlp', None) is not None:
            return self._spacy_nlp
        try:
            import spacy
        except Exception:
            self._spacy_nlp = None
            return None
        for model_name in ("en_core_sci_sm", "en_core_web_sm"):
            try:
                nlp = spacy.load(model_name)
                self._spacy_nlp = nlp
                return nlp
            except Exception:
                continue
        self._spacy_nlp = None
        return None

    def _extract_domain_concepts(self, text: str) -> List["ConceptNode"]:
        """Extract multi-word domain spans as lightweight concept records.

        The regex concept source uses a software/ML seed vocabulary, so it
        misses domain phrases like "category III exposure-prone procedures".
        scispacy's ``doc.ents`` yields those biomedical phrases directly, and
        ``doc.noun_chunks`` adds general noun phrases ("management guidelines")
        when a non-biomedical model is loaded.  Returns ``[]`` when spaCy is
        unavailable.
        """
        nlp = self._get_spacy_nlp()
        if nlp is None:
            return []
        try:
            doc = nlp(text)
        except Exception:
            return []
        from ...models.knowledge_graph import ConceptNode

        concepts = []
        seen = set()
        for span in list(doc.ents) + list(doc.noun_chunks):
            cleaned = [t.text for t in span if any(c.isalnum() for c in t.text)]
            if len(cleaned) < 2:
                continue
            name = ' '.join(cleaned).strip()
            key = name.lower()
            if len(key) < 3 or key in seen:
                continue
            seen.add(key)
            concepts.append(ConceptNode(
                concept_id=f"public:{key}",
                concept_name=name,
                concept_type="NOUN_CHUNK",
                confidence=0.75,
            ))
        return concepts

    def _match_known_concepts(self, text: str) -> List["ConceptNode"]:
        """Return vetted multi-word concepts present in *text*.

        ``self.known_concept_names`` is the prefetched vocabulary (UMLS +
        seed/canonical/frozen librarian concepts, plus their surface forms).
        Scans *text*'s clean tokens for n-grams (n >= 2, up to the full text
        length) that match a known name, yielding high-confidence
        ``KNOWN_CONCEPT`` records so the boundary-contiguity check keeps them
        whole.  *text* is always the short overlap window, so the O(n^2) n-gram
        scan stays cheap; it never iterates the full vocabulary, only the
        n-grams actually present in the text.

        Matching is pluralisation- and hyphenation-robust: both the vocabulary
        and the text n-grams are run through ``_canonicalize_phrase`` so
        "exposure prone procedures", "exposure-prone procedures", and an
        "exposure prone procedure" surface form all match one another.
        """
        known = getattr(self, 'known_concept_names', None)
        if not known:
            return []

        # Canonicalize the vocabulary once and cache it (keyed on the set's
        # identity so a fresh prefetch invalidates the cache).
        known_key = id(known)
        if (getattr(self, '_known_canonical', None) is None
                or getattr(self, '_known_canonical_key', None) != known_key):
            self._known_canonical = {
                self._canonicalize_phrase(term) for term in known
            }
            self._known_canonical_key = known_key
        known_canonical = self._known_canonical

        tokens = self._clean_tokens(text)
        max_n = len(tokens)
        from ...models.knowledge_graph import ConceptNode

        concepts = []
        seen = set()
        for n in range(2, max_n + 1):
            for i in range(len(tokens) - n + 1):
                phrase = ' '.join(tokens[i:i + n])
                canonical = self._canonicalize_phrase(phrase)
                if canonical not in known_canonical or canonical in seen:
                    continue
                seen.add(canonical)
                concepts.append(ConceptNode(
                    concept_id=f"public:{phrase}",
                    concept_name=phrase,
                    concept_type="KNOWN_CONCEPT",
                    confidence=0.92,
                ))
        return concepts

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

    @staticmethod
    def _clean_tokens(text: str) -> List[str]:
        """Split *text* into lowercase word tokens, dropping punctuation.

        Tokens are maximal runs of letters/digits with internal hyphens or
        apostrophes kept ('exposure-prone', "don't").  This canonical form lets
        a concept match the overlap text whether whitespace-splitting fused
        punctuation onto a word ('antigen(HBsAg)' -> ['antigen', 'hbsag']) or
        spaCy produced clean tokens directly.
        """
        import re
        return re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", text.lower())

    @staticmethod
    def _singularize_token(token: str) -> str:
        """Collapse a common English plural to its singular-ish canonical form.

        Applied symmetrically to both the known-concept vocabulary and the
        overlap text so a seed's singular surface form ("exposure prone
        procedure") still matches the plural in source text ("exposure prone
        procedures") without enumerating every inflection.  It need not be
        linguistically perfect — both sides are normalised identically, so any
        consistent mapping still pairs singular and plural.  Conservative:
        short words and invariant plurals ("ss"/"us"/"is") are left alone.
        """
        if len(token) <= 3:
            return token
        if token.endswith("ies"):
            return token[:-3] + "y"          # activities -> activity
        if token.endswith(("ches", "shes", "xes", "zes", "sses")):
            return token[:-2]                 # processes -> process, boxes -> box
        if token.endswith("s") and not token.endswith(("ss", "us", "is")):
            return token[:-1]                 # procedures -> procedure
        return token

    @staticmethod
    def _canonicalize_phrase(phrase: str) -> str:
        """Canonicalize *phrase* into a hyphen/plural-insensitive lookup key.

        Lowercases, splits on whitespace and hyphens (keeping apostrophes), and
        singularizes each token, so these all collapse to one key:

          "exposure-prone procedures"  -> "exposure prone procedure"
          "exposure prone procedure"   -> "exposure prone procedure"
          "exposure prone procedures"  -> "exposure prone procedure"

        Applied symmetrically to the known-concept vocabulary and the overlap
        text, so a seed's hyphenated name or singular surface form still
        matches the unhyphenated/plural phrasing in source text.
        """
        import re
        tokens = re.findall(r"[^\W_]+(?:'[^\W_]+)*", phrase.lower())
        return ' '.join(
            GenericMultiLevelChunkingFramework._singularize_token(t)
            for t in tokens
        )

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
           before it if that would exceed *max_chunk_size*), snapping the
           shift to the nearest sentence boundary when one is reachable so
           the split still lands on a clean sentence end.
        5. If multiple spanning concepts: prioritise highest confidence.
        6. Re-check at the new position — a shift can land inside another
           concept — and repeat until the boundary stops on a clean spot.

        When *unresolved_bisections* is provided, any spanning concept
        that cannot be resolved by boundary shifting is appended to the
        list as an ``UnresolvedBisection`` record.

        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 1.1, 1.2, 1.4
        """
        try:
            concept_extractor = self._get_concept_extractor()

            # Build overlap zone, preserving each side's original whitespace so
            # newline-anchored list/paragraph boundaries survive into
            # _find_sentence_boundaries for snap-back.  Flattening with
            # ' '.join(...) here stripped newlines and left only period-based
            # sentence ends as snap targets.
            pre_words, pre_seps = self._split_words_preserving_whitespace(pre_boundary_text)
            post_words, post_seps = self._split_words_preserving_whitespace(post_boundary_text)
            if len(pre_words) > overlap_window:
                pre_words = pre_words[-overlap_window:]
                pre_seps = pre_seps[-overlap_window:]
            if len(post_words) > overlap_window:
                post_words = post_words[:overlap_window]
                post_seps = post_seps[:overlap_window]
            overlap_pre = pre_words
            overlap_post = post_words
            pre_part = self._reconstruct_with_whitespace(overlap_pre, pre_seps)
            post_part = self._reconstruct_with_whitespace(overlap_post, post_seps)
            overlap_text = (pre_part + ' ' + post_part).strip()

            # Extract concepts from overlap zone.  The regex source is
            # software/ML-seeded; augment it with domain-aware spaCy spans so
            # medical phrases spanning the boundary are protected.
            overlap_concepts = concept_extractor.extract_concepts_regex(overlap_text)
            overlap_concepts.extend(self._extract_domain_concepts(overlap_text))
            overlap_concepts.extend(self._match_known_concepts(overlap_text))

            if not overlap_concepts:
                return boundary_word_index  # no concepts in overlap zone

            # Check each concept for boundary spanning
            boundary_in_overlap = len(overlap_pre)  # word index of boundary within overlap text
            overlap_words_list = overlap_pre + overlap_post

            # Decompose each overlap word into clean tokens, remembering the
            # word index each clean token came from.  A concept extracted via
            # spaCy (clean tokens) then matches even when whitespace-splitting
            # fused punctuation onto a word ('antigen(HBsAg)' ->
            # ['antigen', 'hbsag']), or leaves it attached ('antigen.').
            clean_tokens = []
            clean_token_to_word = []
            for wi, word in enumerate(overlap_words_list):
                for sub in self._clean_tokens(word):
                    clean_tokens.append(sub)
                    clean_token_to_word.append(wi)

            # Precompute every multi-word concept occurrence as
            # (concept, start_word_idx, end_word_idx) within the overlap zone.
            occurrences = []
            for concept in overlap_concepts:
                concept_tokens = self._clean_tokens(concept.concept_name)
                if len(concept_tokens) < 2:
                    continue  # only multi-word concepts can be bisected
                for i in range(len(clean_tokens) - len(concept_tokens) + 1):
                    if clean_tokens[i:i + len(concept_tokens)] == concept_tokens:
                        start = clean_token_to_word[i]
                        end = clean_token_to_word[i + len(concept_tokens) - 1] + 1
                        occurrences.append((concept, start, end))

            # Iteratively resolve spanning concepts.  A shift past one concept
            # can land inside another, and a backward shift can bisect yet
            # another, so re-run the spanning check at each new position until
            # the boundary stops on a clean spot.  ``visited`` guards against
            # oscillation between two positions when ``max_chunk_size`` is so
            # tight that no shift can permanently resolve the overlap.
            #
            # Each shift snaps to a sentence boundary when one is reachable:
            # moving to the raw concept edge (``end``/``start``) would leave
            # the split mid-sentence and undo the sentence contiguity the
            # semantic boundary detector just established.  Forward shifts
            # (concept kept in this chunk) target the nearest sentence end at
            # or beyond the concept edge; backward shifts (concept moved to
            # the next chunk) target the nearest sentence end at or before the
            # concept start.  When no sentence end sits in the overlap window,
            # the raw concept edge is used (unchanged behaviour).
            sentence_boundaries = []
            if occurrences:
                sentence_boundaries = self._find_sentence_boundaries(
                    overlap_text
                )

            current_boundary = boundary_word_index
            current_in_overlap = boundary_in_overlap
            visited = {current_in_overlap}
            final_spanning = []

            for _ in range(len(overlap_words_list) + 2):
                spanning = [
                    (c, s, e) for (c, s, e) in occurrences
                    if s < current_in_overlap < e
                ]
                if not spanning:
                    final_spanning = []
                    break  # stable: nothing spans here

                best = max(spanning, key=lambda x: x[0].confidence)
                concept, start_in_overlap, end_in_overlap = best

                # Shift forward (keep the concept in the current chunk) if the
                # resulting chunk still fits within ``max_chunk_size``.
                shift_forward = end_in_overlap - current_in_overlap
                if current_boundary + shift_forward <= max_chunk_size:
                    next_in_overlap = end_in_overlap
                    # Snap to the nearest sentence end at/beyond the concept
                    # edge so the boundary also ends a sentence, not mid-word.
                    for sb in sentence_boundaries:
                        if sb >= end_in_overlap:
                            extra = sb - current_in_overlap
                            if current_boundary + extra <= max_chunk_size:
                                next_in_overlap = sb
                            break
                    if next_in_overlap in visited:
                        final_spanning = spanning
                        break  # oscillation — accept the bisection
                    visited.add(next_in_overlap)
                    current_boundary += next_in_overlap - current_in_overlap
                    current_in_overlap = next_in_overlap
                    continue

                # Can't shift forward — shift backward (put the concept in the
                # next chunk) unless that empties the leading chunk.
                shift_backward = current_in_overlap - start_in_overlap
                new_boundary_backward = current_boundary - shift_backward
                if new_boundary_backward > 0:
                    next_in_overlap = start_in_overlap
                    # Snap to the nearest sentence end at/before the concept
                    # start, unless that would empty the leading chunk.
                    for sb in reversed(sentence_boundaries):
                        if sb <= start_in_overlap:
                            if current_boundary - (current_in_overlap - sb) > 0:
                                next_in_overlap = sb
                            break
                    if next_in_overlap in visited:
                        final_spanning = spanning
                        break  # oscillation — accept the bisection
                    visited.add(next_in_overlap)
                    current_boundary -= current_in_overlap - next_in_overlap
                    current_in_overlap = next_in_overlap
                    continue

                # Neither direction works — accept the bisection.
                final_spanning = spanning
                break

            # Record every concept that still spans the final boundary.  Only
            # concepts the loop could not shift past are bisected; resolved
            # concepts (shifted past) are deliberately left out.
            if unresolved_bisections is not None:
                for (c, _, _) in final_spanning:
                    unresolved_bisections.append(UnresolvedBisection(
                        concept_name=c.concept_name,
                        concept_confidence=c.confidence,
                        boundary_index=current_boundary,
                        chunk_before_id="",
                        chunk_after_id="",
                    ))
            return current_boundary

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
                sub_chunks = self._split_large_chunk(
                    chunk, chunking_reqs, domain_config,
                    document_id=document_id,
                    content_type=content_profile.content_type,
                )
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
                         document_id: str = "",
                         content_type: Optional[ContentType] = None) -> List[ProcessedChunk]:
        """Split a large chunk into smaller chunks at semantic/concept boundaries.

        The previous implementation split blindly at ``preferred_chunk_size``
        words, which could bisect a sentence or a multi-word concept.  This
        version uses the same semantic-boundary search as primary chunking,
        then adjusts for concept contiguity, and only falls back to a hard
        word-count split when no boundary exists anywhere in the buffer.

        Note: this path is currently unreachable in practice — primary chunking
        enforces ``max_chunk_size`` as an upper bound (the concept-adjustment
        forward shift is capped at ``max_chunk_size`` and the no-boundary
        fallback emits exactly ``preferred_chunk_size`` words), so a primary
        chunk never exceeds ``max_chunk_size``.  Chunk ``content`` is also
        newline-normalised, so the newline-anchored domain delimiters and
        list-item rules cannot fire here; they are honoured in primary only.
        """
        words = chunk.content.split()
        target_size = chunking_reqs.preferred_chunk_size
        max_size = getattr(chunking_reqs, 'max_chunk_size', target_size * 2)
        settings = get_settings()
        overlap_window = getattr(settings, 'overlap_window', 20)

        sub_chunks = []
        current_words = []
        sub_chunk_index = 0

        for word in words:
            current_words.append(word)

            if len(current_words) >= target_size:
                boundary_pos = self._find_semantic_boundary(
                    ' '.join(current_words), content_type, domain_config
                )

                if boundary_pos > 0:
                    pre_text = ' '.join(current_words[:boundary_pos])
                    post_text = ' '.join(current_words[boundary_pos:])
                    boundary_pos = self._adjust_boundary_for_concept_contiguity(
                        pre_boundary_text=pre_text,
                        post_boundary_text=post_text,
                        boundary_word_index=boundary_pos,
                        max_chunk_size=max_size,
                        current_chunk_size=boundary_pos,
                        overlap_window=overlap_window,
                        unresolved_bisections=None,
                    )

                if boundary_pos > 0:
                    sub_words = current_words[:boundary_pos]
                    current_words = current_words[boundary_pos:]
                else:
                    sub_words = current_words
                    current_words = []

                sub_chunk = ProcessedChunk(
                    id=self._generate_chunk_id(document_id, ' '.join(sub_words)),
                    content=' '.join(sub_words),
                    start_position=chunk.start_position + sub_chunk_index * target_size,
                    end_position=chunk.start_position + (sub_chunk_index + 1) * target_size,
                    metadata={
                        'chunk_type': 'secondary',
                        'parent_chunk_id': chunk.id,  # Reference parent by ID
                        'sub_chunk_index': sub_chunk_index,
                        'word_count': len(sub_words)
                    }
                )
                sub_chunks.append(sub_chunk)
                sub_chunk_index += 1

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