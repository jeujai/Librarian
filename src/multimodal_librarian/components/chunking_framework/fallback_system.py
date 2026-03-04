"""
Intelligent Fallback System.

This module implements sentence-boundary aware mechanical overlap,
content-type specific fallback strategies, fallback quality assessment,
and fallback-to-bridge upgrade detection.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import numpy as np
from collections import Counter

from ...models.core import ContentType, BridgeStrategy
from ...models.chunking import BridgeChunk, GapAnalysis, ValidationResult

logger = logging.getLogger(__name__)


class FallbackStrategy(Enum):
    """Types of fallback strategies."""
    MECHANICAL_OVERLAP = "mechanical_overlap"
    SENTENCE_BOUNDARY = "sentence_boundary"
    SEMANTIC_TRANSITION = "semantic_transition"
    CONTENT_SPECIFIC = "content_specific"
    MINIMAL_BRIDGE = "minimal_bridge"


@dataclass
class FallbackConfig:
    """Configuration for fallback strategies."""
    overlap_percentage: float = 0.15  # Percentage of chunk to overlap
    min_overlap_words: int = 10  # Minimum words in overlap
    max_overlap_words: int = 50  # Maximum words in overlap
    preserve_sentences: bool = True  # Preserve sentence boundaries
    preserve_paragraphs: bool = True  # Preserve paragraph boundaries
    
    # Content-type specific settings
    content_type_configs: Dict[ContentType, Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.content_type_configs is None:
            self.content_type_configs = {
                ContentType.TECHNICAL: {
                    'overlap_percentage': 0.20,
                    'preserve_code_blocks': True,
                    'preserve_function_definitions': True,
                    'min_overlap_words': 15
                },
                ContentType.MEDICAL: {
                    'overlap_percentage': 0.25,
                    'preserve_clinical_sections': True,
                    'preserve_safety_warnings': True,
                    'min_overlap_words': 20
                },
                ContentType.LEGAL: {
                    'overlap_percentage': 0.30,
                    'preserve_section_numbers': True,
                    'preserve_legal_citations': True,
                    'min_overlap_words': 25
                },
                ContentType.ACADEMIC: {
                    'overlap_percentage': 0.18,
                    'preserve_citations': True,
                    'preserve_section_headers': True,
                    'min_overlap_words': 15
                },
                ContentType.NARRATIVE: {
                    'overlap_percentage': 0.12,
                    'preserve_dialogue': True,
                    'preserve_scene_breaks': False,
                    'min_overlap_words': 8
                },
                ContentType.GENERAL: {
                    'overlap_percentage': 0.15,
                    'min_overlap_words': 10
                }
            }
    
    def get_config(self, content_type: ContentType) -> Dict[str, Any]:
        """Get configuration for specific content type."""
        base_config = {
            'overlap_percentage': self.overlap_percentage,
            'min_overlap_words': self.min_overlap_words,
            'max_overlap_words': self.max_overlap_words,
            'preserve_sentences': self.preserve_sentences,
            'preserve_paragraphs': self.preserve_paragraphs
        }
        
        content_config = self.content_type_configs.get(content_type, {})
        base_config.update(content_config)
        
        return base_config


@dataclass
class FallbackResult:
    """Result of fallback processing."""
    fallback_content: str
    strategy_used: FallbackStrategy
    quality_score: float
    overlap_info: Dict[str, Any]
    upgrade_potential: float  # Potential for upgrading to bridge
    processing_notes: List[str]
    
    def is_upgrade_candidate(self, threshold: float = 0.7) -> bool:
        """Check if this fallback is a candidate for bridge upgrade."""
        return self.upgrade_potential >= threshold


@dataclass
class OverlapAnalysis:
    """Analysis of overlap between chunks."""
    overlap_words: List[str]
    overlap_sentences: List[str]
    overlap_percentage: float
    boundary_quality: float
    semantic_coherence: float
    
    def get_overlap_text(self) -> str:
        """Get the overlap text."""
        return ' '.join(self.overlap_sentences) if self.overlap_sentences else ' '.join(self.overlap_words)


class IntelligentFallbackSystem:
    """
    Intelligent fallback system for when bridge generation fails.
    
    Implements sentence-boundary aware mechanical overlap, content-type specific strategies,
    quality assessment, and upgrade detection for converting fallbacks to bridges.
    """
    
    def __init__(self, config: Optional[FallbackConfig] = None):
        """Initialize the intelligent fallback system."""
        self.config = config or FallbackConfig()
        
        # Fallback statistics
        self.fallback_stats = {
            'total_fallbacks': 0,
            'strategy_usage': {strategy.value: 0 for strategy in FallbackStrategy},
            'average_quality': 0.0,
            'upgrade_candidates': 0,
            'successful_upgrades': 0
        }
        
        # Content-specific patterns
        self.content_patterns = self._initialize_content_patterns()
        
        # Quality assessment weights
        self.quality_weights = {
            'boundary_preservation': 0.3,
            'semantic_coherence': 0.25,
            'content_completeness': 0.2,
            'readability': 0.15,
            'content_specific_quality': 0.1
        }
    
    def _initialize_content_patterns(self) -> Dict[ContentType, Dict[str, List[str]]]:
        """Initialize content-specific patterns for preservation."""
        return {
            ContentType.TECHNICAL: {
                'preserve_patterns': [
                    r'```[\s\S]*?```',  # Code blocks
                    r'class\s+\w+[\s\S]*?(?=\nclass|\n\n|\Z)',  # Class definitions
                    r'def\s+\w+[\s\S]*?(?=\ndef|\nclass|\n\n|\Z)',  # Function definitions
                    r'(?:function|method|API|interface)\s+\w+',  # API references
                ],
                'boundary_markers': [
                    r'\n\s*```',  # Code block boundaries
                    r'\n\s*(?:class|def)\s+\w+',  # Definition boundaries
                    r'\n\s*#\s+',  # Comment boundaries
                ],
                'avoid_splitting': [
                    r'```[\s\S]*?```',  # Don't split code blocks
                    r'(?:function|method)\s+\w+\([^)]*\)',  # Function signatures
                ]
            },
            
            ContentType.MEDICAL: {
                'preserve_patterns': [
                    r'(?:Contraindications?|Side Effects?)[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                    r'Dosage[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                    r'(?:Symptoms?|Diagnosis|Treatment)[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                    r'Patient\s+\d+[\s\S]*?(?=\nPatient|\n\n|\Z)',
                ],
                'boundary_markers': [
                    r'\n\s*(?:Symptoms?|Diagnosis|Treatment|Dosage):',
                    r'\n\s*(?:Contraindications?|Side Effects?):',
                    r'\n\s*Patient\s+\d+',
                ],
                'avoid_splitting': [
                    r'(?:Contraindications?|Side Effects?)[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                    r'Dosage[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                ]
            },
            
            ContentType.LEGAL: {
                'preserve_patterns': [
                    r'Section\s+\d+[\s\S]*?(?=\nSection|\nArticle|\n\n|\Z)',
                    r'Article\s+[IVX]+[\s\S]*?(?=\nArticle|\nSection|\n\n|\Z)',
                    r'\([a-z]\)[\s\S]*?(?=\n\([a-z]\)|\n\d+\.|\n\n|\Z)',
                    r'\b\w+\s+v\.\s+\w+\b',  # Case citations
                ],
                'boundary_markers': [
                    r'\n\s*Section\s+\d+',
                    r'\n\s*Article\s+[IVX]+',
                    r'\n\s*\([a-z]\)',
                ],
                'avoid_splitting': [
                    r'Section\s+\d+[\s\S]*?(?=\nSection|\nArticle|\n\n|\Z)',
                    r'Article\s+[IVX]+[\s\S]*?(?=\nArticle|\nSection|\n\n|\Z)',
                ]
            },
            
            ContentType.ACADEMIC: {
                'preserve_patterns': [
                    r'(?:Figure|Table)\s+\d+[\s\S]*?(?=\n(?:Figure|Table)|\n\n|\Z)',
                    r'\([^)]*\d{4}[^)]*\)',  # Citations
                    r'(?:Abstract|Introduction|Methodology|Results|Discussion|Conclusion)[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                    r'References[\s\S]*?\Z',
                ],
                'boundary_markers': [
                    r'\n\s*(?:Abstract|Introduction|Methodology|Results|Discussion|Conclusion):',
                    r'\n\s*(?:Figure|Table)\s+\d+',
                    r'\n\s*\d+\.\d+\s+',  # Subsection numbers
                ],
                'avoid_splitting': [
                    r'(?:Figure|Table)\s+\d+[\s\S]*?(?=\n(?:Figure|Table)|\n\n|\Z)',
                    r'References[\s\S]*?\Z',
                ]
            },
            
            ContentType.NARRATIVE: {
                'preserve_patterns': [
                    r'Chapter\s+\d+[\s\S]*?(?=\nChapter|\Z)',
                    r'"[^"]*"',  # Dialogue
                    r'\*\s*\*\s*\*[\s\S]*?(?=\*\s*\*\s*\*|\nChapter|\Z)',  # Scene breaks
                ],
                'boundary_markers': [
                    r'\n\s*Chapter\s+\d+',
                    r'\n\s*\*\s*\*\s*\*',  # Scene breaks
                    r'\n\n',  # Paragraph breaks
                ],
                'avoid_splitting': [
                    r'"[^"]*"',  # Don't split dialogue
                    r'Chapter\s+\d+[\s\S]*?(?=\nChapter|\Z)',
                ]
            },
            
            ContentType.GENERAL: {
                'preserve_patterns': [
                    r'\n\s*\d+\.\s+',  # Numbered lists
                    r'\n\s*[-*•]\s+',  # Bullet points
                ],
                'boundary_markers': [
                    r'\n\s*\d+\.\s+',
                    r'\n\n',  # Paragraph breaks
                ],
                'avoid_splitting': []
            }
        }
    
    def create_fallback(self, chunk1: str, chunk2: str, gap_analysis: GapAnalysis,
                       content_type: ContentType = ContentType.GENERAL,
                       failed_bridge_attempt: Optional[str] = None) -> FallbackResult:
        """
        Create sentence-boundary aware mechanical overlap.
        
        Args:
            chunk1: First chunk content
            chunk2: Second chunk content
            gap_analysis: Gap analysis results
            content_type: Content type for specific strategies
            failed_bridge_attempt: Previous failed bridge attempt (if any)
            
        Returns:
            FallbackResult with fallback content and metadata
        """
        logger.debug(f"Creating fallback for content type: {content_type.value}")
        
        # Get content-specific configuration
        content_config = self.config.get_config(content_type)
        
        # Analyze overlap potential
        overlap_analysis = self._analyze_overlap_potential(chunk1, chunk2, content_type)
        
        # Determine best fallback strategy
        strategy = self._determine_fallback_strategy(
            chunk1, chunk2, gap_analysis, content_type, overlap_analysis
        )
        
        # Create fallback content based on strategy
        fallback_content, processing_notes = self._create_fallback_content(
            chunk1, chunk2, strategy, content_type, overlap_analysis, content_config
        )
        
        # Assess fallback quality
        quality_score = self._assess_fallback_quality(
            fallback_content, chunk1, chunk2, content_type, strategy
        )
        
        # Calculate upgrade potential
        upgrade_potential = self._calculate_upgrade_potential(
            fallback_content, chunk1, chunk2, gap_analysis, quality_score, failed_bridge_attempt
        )
        
        # Update statistics
        self._update_fallback_stats(strategy, quality_score, upgrade_potential)
        
        return FallbackResult(
            fallback_content=fallback_content,
            strategy_used=strategy,
            quality_score=quality_score,
            overlap_info=overlap_analysis.__dict__,
            upgrade_potential=upgrade_potential,
            processing_notes=processing_notes
        )
    
    def _analyze_overlap_potential(self, chunk1: str, chunk2: str, 
                                 content_type: ContentType) -> OverlapAnalysis:
        """Analyze potential overlap between chunks."""
        
        # Extract sentences from both chunks
        chunk1_sentences = self._extract_sentences(chunk1)
        chunk2_sentences = self._extract_sentences(chunk2)
        
        # Find overlapping content
        chunk1_words = set(chunk1.lower().split())
        chunk2_words = set(chunk2.lower().split())
        
        # Remove stop words for better analysis
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
        chunk1_words -= stop_words
        chunk2_words -= stop_words
        
        overlap_words = list(chunk1_words.intersection(chunk2_words))
        
        # Find overlapping sentences (by similarity)
        overlap_sentences = self._find_overlapping_sentences(chunk1_sentences, chunk2_sentences)
        
        # Calculate overlap percentage
        total_words = len(chunk1_words.union(chunk2_words))
        overlap_percentage = len(overlap_words) / total_words if total_words > 0 else 0.0
        
        # Assess boundary quality
        boundary_quality = self._assess_boundary_quality(chunk1, chunk2, content_type)
        
        # Calculate semantic coherence
        semantic_coherence = self._calculate_semantic_coherence(chunk1, chunk2, overlap_words)
        
        return OverlapAnalysis(
            overlap_words=overlap_words,
            overlap_sentences=overlap_sentences,
            overlap_percentage=overlap_percentage,
            boundary_quality=boundary_quality,
            semantic_coherence=semantic_coherence
        )
    
    def _extract_sentences(self, text: str) -> List[str]:
        """Extract sentences from text with improved boundary detection."""
        # Handle common abbreviations that shouldn't end sentences
        abbreviations = ['Dr.', 'Mr.', 'Mrs.', 'Ms.', 'Prof.', 'Inc.', 'Ltd.', 'Corp.', 'etc.', 'vs.', 'e.g.', 'i.e.']
        
        # Temporarily replace abbreviations
        temp_text = text
        for i, abbr in enumerate(abbreviations):
            temp_text = temp_text.replace(abbr, f"__ABBR_{i}__")
        
        # Split on sentence boundaries
        sentences = re.split(r'[.!?]+\s+', temp_text)
        
        # Restore abbreviations
        for i, abbr in enumerate(abbreviations):
            sentences = [s.replace(f"__ABBR_{i}__", abbr) for s in sentences]
        
        # Clean up sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def _find_overlapping_sentences(self, sentences1: List[str], sentences2: List[str]) -> List[str]:
        """Find sentences that overlap between chunks."""
        overlapping = []
        
        for s1 in sentences1[-3:]:  # Check last 3 sentences of chunk1
            for s2 in sentences2[:3]:  # Check first 3 sentences of chunk2
                # Simple similarity check based on word overlap
                words1 = set(s1.lower().split())
                words2 = set(s2.lower().split())
                
                if len(words1) > 0 and len(words2) > 0:
                    overlap_ratio = len(words1.intersection(words2)) / len(words1.union(words2))
                    if overlap_ratio > 0.3:  # 30% word overlap threshold
                        overlapping.append(s1)
                        break
        
        return overlapping
    
    def _assess_boundary_quality(self, chunk1: str, chunk2: str, content_type: ContentType) -> float:
        """Assess the quality of chunk boundaries."""
        quality_factors = []
        
        # Check sentence boundary quality
        chunk1_ends_complete = chunk1.rstrip().endswith(('.', '!', '?', ':', ';'))
        chunk2_starts_complete = chunk2.lstrip()[0].isupper() if chunk2.lstrip() else False
        
        sentence_quality = 1.0 if chunk1_ends_complete and chunk2_starts_complete else 0.3
        quality_factors.append(sentence_quality)
        
        # Check paragraph boundary quality
        chunk1_ends_paragraph = chunk1.rstrip().endswith('\n\n') or chunk1.rstrip().endswith('\n')
        paragraph_quality = 0.8 if chunk1_ends_paragraph else 0.5
        quality_factors.append(paragraph_quality)
        
        # Content-specific boundary quality
        content_quality = self._assess_content_specific_boundaries(chunk1, chunk2, content_type)
        quality_factors.append(content_quality)
        
        return sum(quality_factors) / len(quality_factors)
    
    def _assess_content_specific_boundaries(self, chunk1: str, chunk2: str, content_type: ContentType) -> float:
        """Assess content-specific boundary quality."""
        patterns = self.content_patterns.get(content_type, {})
        boundary_markers = patterns.get('boundary_markers', [])
        
        if not boundary_markers:
            return 0.7  # Default quality
        
        # Check if boundaries align with content-specific markers
        boundary_score = 0.0
        
        for marker in boundary_markers:
            if re.search(marker, chunk1[-100:]) or re.search(marker, chunk2[:100]):
                boundary_score += 1.0
        
        # Normalize score
        return min(1.0, boundary_score / len(boundary_markers) + 0.3)
    
    def _calculate_semantic_coherence(self, chunk1: str, chunk2: str, overlap_words: List[str]) -> float:
        """Calculate semantic coherence between chunks."""
        # Simple coherence based on shared concepts and transition words
        transition_words = ['however', 'therefore', 'furthermore', 'moreover', 'additionally', 
                          'consequently', 'meanwhile', 'similarly', 'likewise', 'in contrast']
        
        chunk2_start = chunk2[:200].lower()
        
        # Check for transition words
        transition_score = 0.0
        for word in transition_words:
            if word in chunk2_start:
                transition_score = 0.8
                break
        
        # Check for concept continuity
        concept_score = len(overlap_words) / 20.0  # Normalize to reasonable range
        concept_score = min(1.0, concept_score)
        
        # Combine scores
        coherence = (transition_score * 0.4 + concept_score * 0.6)
        
        return coherence
    
    def _determine_fallback_strategy(self, chunk1: str, chunk2: str, gap_analysis: GapAnalysis,
                                   content_type: ContentType, overlap_analysis: OverlapAnalysis) -> FallbackStrategy:
        """Determine the best fallback strategy."""
        
        # If high overlap and good boundaries, use mechanical overlap
        if (overlap_analysis.overlap_percentage > 0.2 and 
            overlap_analysis.boundary_quality > 0.7):
            return FallbackStrategy.MECHANICAL_OVERLAP
        
        # If good sentence boundaries, use sentence-boundary strategy
        if overlap_analysis.boundary_quality > 0.6:
            return FallbackStrategy.SENTENCE_BOUNDARY
        
        # If semantic coherence is good, use semantic transition
        if overlap_analysis.semantic_coherence > 0.5:
            return FallbackStrategy.SEMANTIC_TRANSITION
        
        # Use content-specific strategy for specialized content
        if content_type in [ContentType.TECHNICAL, ContentType.MEDICAL, ContentType.LEGAL]:
            return FallbackStrategy.CONTENT_SPECIFIC
        
        # Default to minimal bridge
        return FallbackStrategy.MINIMAL_BRIDGE
    
    def _create_fallback_content(self, chunk1: str, chunk2: str, strategy: FallbackStrategy,
                               content_type: ContentType, overlap_analysis: OverlapAnalysis,
                               content_config: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Create fallback content based on strategy."""
        processing_notes = []
        
        if strategy == FallbackStrategy.MECHANICAL_OVERLAP:
            content, notes = self._create_mechanical_overlap(chunk1, chunk2, content_config, overlap_analysis)
            processing_notes.extend(notes)
        
        elif strategy == FallbackStrategy.SENTENCE_BOUNDARY:
            content, notes = self._create_sentence_boundary_fallback(chunk1, chunk2, content_config)
            processing_notes.extend(notes)
        
        elif strategy == FallbackStrategy.SEMANTIC_TRANSITION:
            content, notes = self._create_semantic_transition(chunk1, chunk2, overlap_analysis)
            processing_notes.extend(notes)
        
        elif strategy == FallbackStrategy.CONTENT_SPECIFIC:
            content, notes = self._create_content_specific_fallback(chunk1, chunk2, content_type, content_config)
            processing_notes.extend(notes)
        
        else:  # MINIMAL_BRIDGE
            content, notes = self._create_minimal_bridge(chunk1, chunk2)
            processing_notes.extend(notes)
        
        return content, processing_notes
    
    def _create_mechanical_overlap(self, chunk1: str, chunk2: str, content_config: Dict[str, Any],
                                 overlap_analysis: OverlapAnalysis) -> Tuple[str, List[str]]:
        """Create mechanical overlap fallback."""
        notes = ["Using mechanical overlap strategy"]
        
        overlap_percentage = content_config.get('overlap_percentage', 0.15)
        min_words = content_config.get('min_overlap_words', 10)
        max_words = content_config.get('max_overlap_words', 50)
        
        # Calculate overlap size
        chunk1_words = chunk1.split()
        chunk2_words = chunk2.split()
        
        overlap_size = max(min_words, min(max_words, int(len(chunk1_words) * overlap_percentage)))
        
        # Extract overlap from end of chunk1 and beginning of chunk2
        chunk1_overlap = ' '.join(chunk1_words[-overlap_size:])
        chunk2_overlap = ' '.join(chunk2_words[:overlap_size])
        
        # If we have overlapping sentences, use those
        if overlap_analysis.overlap_sentences:
            overlap_content = ' '.join(overlap_analysis.overlap_sentences)
            notes.append(f"Used {len(overlap_analysis.overlap_sentences)} overlapping sentences")
        else:
            # Create overlap from word-level analysis
            if overlap_analysis.overlap_words:
                # Create a sentence using overlapping words
                overlap_words = overlap_analysis.overlap_words[:10]  # Limit to 10 words
                overlap_content = f"Continuing with {', '.join(overlap_words[:3])}, "
                notes.append(f"Created overlap using {len(overlap_words)} shared words")
            else:
                # Simple concatenation with transition
                overlap_content = f"{chunk1_overlap} {chunk2_overlap}"
                notes.append("Used simple word-based overlap")
        
        return overlap_content, notes
    
    def _create_sentence_boundary_fallback(self, chunk1: str, chunk2: str, 
                                         content_config: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Create sentence-boundary aware fallback."""
        notes = ["Using sentence boundary strategy"]
        
        # Extract last complete sentence from chunk1
        chunk1_sentences = self._extract_sentences(chunk1)
        chunk2_sentences = self._extract_sentences(chunk2)
        
        if chunk1_sentences and chunk2_sentences:
            last_sentence = chunk1_sentences[-1]
            first_sentence = chunk2_sentences[0]
            
            # Create smooth transition
            if last_sentence.endswith('.'):
                transition = f"{last_sentence} {first_sentence}"
            else:
                transition = f"{last_sentence}. {first_sentence}"
            
            notes.append("Connected complete sentences")
            return transition, notes
        
        # Fallback to simple connection
        overlap_percentage = content_config.get('overlap_percentage', 0.15)
        chunk1_words = chunk1.split()
        chunk2_words = chunk2.split()
        
        overlap_size = max(5, int(len(chunk1_words) * overlap_percentage))
        
        chunk1_end = ' '.join(chunk1_words[-overlap_size:])
        chunk2_start = ' '.join(chunk2_words[:overlap_size])
        
        transition = f"{chunk1_end} {chunk2_start}"
        notes.append("Used word-level boundary fallback")
        
        return transition, notes
    
    def _create_semantic_transition(self, chunk1: str, chunk2: str, 
                                  overlap_analysis: OverlapAnalysis) -> Tuple[str, List[str]]:
        """Create semantic transition fallback."""
        notes = ["Using semantic transition strategy"]
        
        # Use overlapping concepts to create transition
        if overlap_analysis.overlap_words:
            key_concepts = overlap_analysis.overlap_words[:5]  # Top 5 concepts
            
            # Create transition phrase
            if len(key_concepts) >= 3:
                transition = f"Building on the concepts of {', '.join(key_concepts[:2])}, and {key_concepts[2]}, "
            elif len(key_concepts) == 2:
                transition = f"Continuing with {key_concepts[0]} and {key_concepts[1]}, "
            else:
                transition = f"Following the discussion of {key_concepts[0]}, "
            
            notes.append(f"Created transition using {len(key_concepts)} key concepts")
        else:
            # Generic semantic transition
            transition = "Continuing with the next aspect of this topic, "
            notes.append("Used generic semantic transition")
        
        return transition, notes
    
    def _create_content_specific_fallback(self, chunk1: str, chunk2: str, content_type: ContentType,
                                        content_config: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Create content-type specific fallback."""
        notes = [f"Using {content_type.value}-specific strategy"]
        
        patterns = self.content_patterns.get(content_type, {})
        preserve_patterns = patterns.get('preserve_patterns', [])
        
        # Extract content-specific elements to preserve
        preserved_elements = []
        for pattern in preserve_patterns:
            matches = re.findall(pattern, chunk1 + " " + chunk2, re.IGNORECASE | re.MULTILINE)
            preserved_elements.extend(matches[:2])  # Limit to 2 matches per pattern
        
        if preserved_elements:
            # Create transition using preserved elements
            if content_type == ContentType.TECHNICAL:
                transition = f"Continuing with the technical implementation, "
            elif content_type == ContentType.MEDICAL:
                transition = f"Following the clinical guidelines, "
            elif content_type == ContentType.LEGAL:
                transition = f"In accordance with the statutory provisions, "
            elif content_type == ContentType.ACADEMIC:
                transition = f"Building on the research findings, "
            else:
                transition = f"Continuing with the {content_type.value} content, "
            
            notes.append(f"Preserved {len(preserved_elements)} content-specific elements")
        else:
            # Generic content-specific transition
            transition = f"Proceeding with the {content_type.value} discussion, "
            notes.append("Used generic content-specific transition")
        
        return transition, notes
    
    def _create_minimal_bridge(self, chunk1: str, chunk2: str) -> Tuple[str, List[str]]:
        """Create minimal bridge fallback."""
        notes = ["Using minimal bridge strategy"]
        
        # Very simple transition
        transitions = [
            "Additionally, ",
            "Furthermore, ",
            "Moreover, ",
            "Continuing, ",
            "Next, "
        ]
        
        # Choose transition based on chunk content
        chunk2_start = chunk2[:50].lower()
        
        if any(word in chunk2_start for word in ['however', 'but', 'although']):
            transition = "In contrast, "
        elif any(word in chunk2_start for word in ['therefore', 'thus', 'consequently']):
            transition = "As a result, "
        else:
            transition = transitions[0]  # Default
        
        notes.append(f"Used minimal transition: '{transition.strip()}'")
        
        return transition, notes
    
    def _assess_fallback_quality(self, fallback_content: str, chunk1: str, chunk2: str,
                               content_type: ContentType, strategy: FallbackStrategy) -> float:
        """Assess fallback quality assessment and optimization."""
        quality_scores = {}
        
        # Boundary preservation quality
        boundary_quality = self._assess_boundary_preservation(fallback_content, chunk1, chunk2)
        quality_scores['boundary_preservation'] = boundary_quality
        
        # Semantic coherence quality
        semantic_quality = self._assess_semantic_quality(fallback_content, chunk1, chunk2)
        quality_scores['semantic_coherence'] = semantic_quality
        
        # Content completeness quality
        completeness_quality = self._assess_content_completeness(fallback_content, chunk1, chunk2)
        quality_scores['content_completeness'] = completeness_quality
        
        # Readability quality
        readability_quality = self._assess_readability(fallback_content)
        quality_scores['readability'] = readability_quality
        
        # Content-specific quality
        content_specific_quality = self._assess_content_specific_quality(
            fallback_content, chunk1, chunk2, content_type
        )
        quality_scores['content_specific_quality'] = content_specific_quality
        
        # Calculate weighted average
        total_quality = sum(
            quality_scores[metric] * self.quality_weights[metric]
            for metric in quality_scores
        )
        
        return total_quality
    
    def _assess_boundary_preservation(self, fallback_content: str, chunk1: str, chunk2: str) -> float:
        """Assess how well boundaries are preserved."""
        # Check if fallback maintains sentence structure
        has_proper_sentences = bool(re.search(r'[.!?]\s+[A-Z]', fallback_content))
        
        # Check if fallback connects smoothly
        starts_properly = fallback_content[0].isupper() if fallback_content else False
        ends_properly = fallback_content.rstrip().endswith(('.', '!', '?', ','))
        
        boundary_score = 0.0
        if has_proper_sentences:
            boundary_score += 0.4
        if starts_properly:
            boundary_score += 0.3
        if ends_properly:
            boundary_score += 0.3
        
        return boundary_score
    
    def _assess_semantic_quality(self, fallback_content: str, chunk1: str, chunk2: str) -> float:
        """Assess semantic quality of fallback."""
        # Check for semantic coherence indicators
        coherence_indicators = ['continuing', 'following', 'building on', 'additionally', 
                              'furthermore', 'moreover', 'next', 'then']
        
        fallback_lower = fallback_content.lower()
        
        coherence_score = 0.0
        for indicator in coherence_indicators:
            if indicator in fallback_lower:
                coherence_score = 0.8
                break
        
        # Check for concept continuity
        chunk1_words = set(chunk1.lower().split())
        chunk2_words = set(chunk2.lower().split())
        fallback_words = set(fallback_content.lower().split())
        
        # Remove stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        chunk1_words -= stop_words
        chunk2_words -= stop_words
        fallback_words -= stop_words
        
        # Calculate concept overlap
        chunk1_overlap = len(fallback_words.intersection(chunk1_words)) / max(len(fallback_words), 1)
        chunk2_overlap = len(fallback_words.intersection(chunk2_words)) / max(len(fallback_words), 1)
        
        concept_score = (chunk1_overlap + chunk2_overlap) / 2.0
        
        return (coherence_score * 0.6 + concept_score * 0.4)
    
    def _assess_content_completeness(self, fallback_content: str, chunk1: str, chunk2: str) -> float:
        """Assess content completeness."""
        # Check if fallback provides meaningful connection
        meaningful_words = len([word for word in fallback_content.split() 
                              if len(word) > 3 and word.lower() not in {'with', 'that', 'this', 'from'}])
        
        # Normalize based on fallback length
        fallback_length = len(fallback_content.split())
        
        if fallback_length == 0:
            return 0.0
        
        completeness_ratio = meaningful_words / fallback_length
        
        # Bonus for appropriate length
        length_bonus = 0.0
        if 5 <= fallback_length <= 20:  # Appropriate length range
            length_bonus = 0.2
        
        return min(1.0, completeness_ratio + length_bonus)
    
    def _assess_readability(self, fallback_content: str) -> float:
        """Assess readability of fallback content."""
        if not fallback_content.strip():
            return 0.0
        
        # Simple readability metrics
        words = fallback_content.split()
        sentences = len(re.split(r'[.!?]+', fallback_content))
        
        if sentences == 0:
            return 0.5  # Neutral score for no sentences
        
        avg_words_per_sentence = len(words) / sentences
        
        # Optimal range: 10-20 words per sentence
        if 10 <= avg_words_per_sentence <= 20:
            readability_score = 1.0
        elif 5 <= avg_words_per_sentence < 10 or 20 < avg_words_per_sentence <= 30:
            readability_score = 0.7
        else:
            readability_score = 0.4
        
        # Check for proper capitalization and punctuation
        proper_start = fallback_content[0].isupper() if fallback_content else False
        proper_end = fallback_content.rstrip().endswith(('.', '!', '?', ','))
        
        if proper_start and proper_end:
            readability_score += 0.2
        
        return min(1.0, readability_score)
    
    def _assess_content_specific_quality(self, fallback_content: str, chunk1: str, chunk2: str,
                                       content_type: ContentType) -> float:
        """Assess content-type specific quality."""
        if content_type == ContentType.TECHNICAL:
            # Check for technical appropriateness
            technical_terms = ['implementation', 'function', 'method', 'system', 'process', 'algorithm']
            fallback_lower = fallback_content.lower()
            
            technical_score = 0.0
            for term in technical_terms:
                if term in fallback_lower:
                    technical_score = 0.8
                    break
            
            return technical_score
        
        elif content_type == ContentType.MEDICAL:
            # Check for clinical appropriateness
            clinical_terms = ['clinical', 'patient', 'treatment', 'diagnosis', 'medical', 'therapeutic']
            fallback_lower = fallback_content.lower()
            
            clinical_score = 0.0
            for term in clinical_terms:
                if term in fallback_lower:
                    clinical_score = 0.8
                    break
            
            return clinical_score
        
        elif content_type == ContentType.LEGAL:
            # Check for legal appropriateness
            legal_terms = ['accordance', 'pursuant', 'statutory', 'provision', 'regulation', 'legal']
            fallback_lower = fallback_content.lower()
            
            legal_score = 0.0
            for term in legal_terms:
                if term in fallback_lower:
                    legal_score = 0.8
                    break
            
            return legal_score
        
        # Default quality for other content types
        return 0.6
    
    def _calculate_upgrade_potential(self, fallback_content: str, chunk1: str, chunk2: str,
                                   gap_analysis: GapAnalysis, quality_score: float,
                                   failed_bridge_attempt: Optional[str]) -> float:
        """Calculate fallback-to-bridge upgrade detection."""
        upgrade_factors = []
        
        # Quality-based potential
        if quality_score > 0.7:
            upgrade_factors.append(0.3)  # High quality suggests good upgrade potential
        elif quality_score > 0.5:
            upgrade_factors.append(0.6)  # Medium quality has higher upgrade potential
        else:
            upgrade_factors.append(0.8)  # Low quality definitely needs upgrade
        
        # Gap analysis-based potential
        if gap_analysis.necessity_score > 0.8:
            upgrade_factors.append(0.9)  # High necessity suggests bridge would be valuable
        elif gap_analysis.necessity_score > 0.5:
            upgrade_factors.append(0.6)  # Medium necessity
        else:
            upgrade_factors.append(0.3)  # Low necessity
        
        # Semantic distance-based potential
        if gap_analysis.semantic_distance > 0.7:
            upgrade_factors.append(0.8)  # Large semantic gap benefits from bridge
        elif gap_analysis.semantic_distance > 0.4:
            upgrade_factors.append(0.5)  # Medium gap
        else:
            upgrade_factors.append(0.2)  # Small gap
        
        # Failed attempt analysis
        if failed_bridge_attempt:
            # If previous bridge attempt failed, upgrade potential depends on failure reason
            if len(failed_bridge_attempt.strip()) < 10:
                upgrade_factors.append(0.9)  # Very short attempt suggests retry needed
            else:
                upgrade_factors.append(0.4)  # Substantial attempt suggests difficulty
        else:
            upgrade_factors.append(0.7)  # No previous attempt suggests potential
        
        # Calculate weighted average
        return sum(upgrade_factors) / len(upgrade_factors)
    
    def _update_fallback_stats(self, strategy: FallbackStrategy, quality_score: float, 
                             upgrade_potential: float):
        """Update fallback statistics."""
        self.fallback_stats['total_fallbacks'] += 1
        self.fallback_stats['strategy_usage'][strategy.value] += 1
        
        # Update average quality
        total = self.fallback_stats['total_fallbacks']
        current_avg = self.fallback_stats['average_quality']
        self.fallback_stats['average_quality'] = (
            (current_avg * (total - 1) + quality_score) / total
        )
        
        # Track upgrade candidates
        if upgrade_potential >= 0.7:
            self.fallback_stats['upgrade_candidates'] += 1
    
    def detect_upgrade_opportunity(self, fallback_result: FallbackResult, 
                                 performance_threshold: float = 0.6) -> bool:
        """
        Build fallback-to-bridge upgrade detection.
        
        Args:
            fallback_result: Result of fallback processing
            performance_threshold: Threshold for upgrade consideration
            
        Returns:
            True if fallback should be upgraded to bridge
        """
        # Check if quality is below threshold and upgrade potential is high
        quality_below_threshold = fallback_result.quality_score < performance_threshold
        high_upgrade_potential = fallback_result.upgrade_potential >= 0.7
        
        # Additional factors
        is_minimal_strategy = fallback_result.strategy_used == FallbackStrategy.MINIMAL_BRIDGE
        
        upgrade_recommended = (
            (quality_below_threshold and high_upgrade_potential) or
            (is_minimal_strategy and fallback_result.upgrade_potential >= 0.6)
        )
        
        if upgrade_recommended:
            logger.info(f"Upgrade opportunity detected: quality={fallback_result.quality_score:.2f}, "
                       f"potential={fallback_result.upgrade_potential:.2f}, "
                       f"strategy={fallback_result.strategy_used.value}")
        
        return upgrade_recommended
    
    def get_fallback_statistics(self) -> Dict[str, Any]:
        """Get fallback system statistics."""
        stats = self.fallback_stats.copy()
        
        if stats['total_fallbacks'] > 0:
            stats['upgrade_candidate_rate'] = stats['upgrade_candidates'] / stats['total_fallbacks']
            stats['upgrade_success_rate'] = stats['successful_upgrades'] / max(stats['upgrade_candidates'], 1)
        else:
            stats['upgrade_candidate_rate'] = 0.0
            stats['upgrade_success_rate'] = 0.0
        
        return stats
    
    def reset_statistics(self):
        """Reset fallback statistics."""
        self.fallback_stats = {
            'total_fallbacks': 0,
            'strategy_usage': {strategy.value: 0 for strategy in FallbackStrategy},
            'average_quality': 0.0,
            'upgrade_candidates': 0,
            'successful_upgrades': 0
        }