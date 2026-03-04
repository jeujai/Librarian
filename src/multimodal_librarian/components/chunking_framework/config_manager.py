"""
Domain Configuration Management System.

This module implements automated domain configuration generation using YAGO ontology mining,
ConceptNet pattern synthesis, configuration storage with versioning, and validation framework.
"""

import hashlib
import json
import logging
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from ...database.connection import get_database_connection
from ...models.chunking import (
    ContentProfile,
    DelimiterPattern,
    DomainConfig,
    DomainPatterns,
    OptimizationRecord,
    PerformanceMetrics,
    StoredDomainConfig,
)
from ...models.core import ContentType

logger = logging.getLogger(__name__)


class DomainConfigurationManager:
    """
    Domain configuration management system with automated generation and optimization.
    
    Implements YAGO ontology mining, ConceptNet pattern synthesis,
    configuration storage with versioning, and continuous optimization.
    """
    
    def __init__(self):
        """Initialize the domain configuration manager."""
        self.yago_endpoint = "https://yago-knowledge.org/sparql/query"
        self.conceptnet_endpoint = "http://api.conceptnet.io"
        
        # Cache for ontology data
        self._ontology_cache = {}
        self._pattern_cache = {}
        
        # Configuration templates for different domains
        self._domain_templates = self._initialize_domain_templates()
        
        # Performance tracking
        self._performance_history = defaultdict(list)
    
    def _initialize_domain_templates(self) -> Dict[str, Dict[str, Any]]:
        """Initialize base templates for different domain types."""
        return {
            'technical': {
                'base_delimiters': [
                    DelimiterPattern(r'\n\s*\d+\.\s+', priority=3, description="Numbered sections"),
                    DelimiterPattern(r'\n\s*```', priority=2, description="Code blocks"),
                    DelimiterPattern(r'\n\s*class\s+\w+', priority=2, description="Class definitions"),
                    DelimiterPattern(r'\n\s*def\s+\w+', priority=2, description="Function definitions"),
                    DelimiterPattern(r'\n\s*#\s+', priority=1, description="Comments"),
                ],
                'chunk_size_modifiers': {
                    'code_heavy': 1.3,
                    'documentation': 1.1,
                    'api_reference': 1.4,
                    'tutorial': 0.9
                },
                'preservation_patterns': [
                    r'```[\s\S]*?```',  # Code blocks
                    r'class\s+\w+[\s\S]*?(?=\nclass|\n\n|\Z)',  # Class definitions
                    r'def\s+\w+[\s\S]*?(?=\ndef|\nclass|\n\n|\Z)',  # Function definitions
                ],
                'bridge_thresholds': {
                    'semantic_gap': 0.7,
                    'code_context': 0.8,
                    'api_continuity': 0.6
                }
            },
            'medical': {
                'base_delimiters': [
                    DelimiterPattern(r'\n\s*\d+\.\d+\s+', priority=3, description="Medical subsections"),
                    DelimiterPattern(r'\n\s*(?:Symptoms?|Diagnosis|Treatment|Dosage):', priority=3, description="Medical sections"),
                    DelimiterPattern(r'\n\s*(?:Contraindications?|Side Effects?):', priority=2, description="Warning sections"),
                    DelimiterPattern(r'\n\s*(?:Patient|Case)\s+\d+', priority=2, description="Case studies"),
                ],
                'chunk_size_modifiers': {
                    'clinical_guidelines': 1.4,
                    'drug_information': 1.2,
                    'case_studies': 1.1,
                    'patient_education': 0.9
                },
                'preservation_patterns': [
                    r'(?:Contraindications?|Side Effects?)[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                    r'Dosage[\s\S]*?(?=\n[A-Z]|\n\n|\Z)',
                    r'Patient\s+\d+[\s\S]*?(?=\nPatient|\n\n|\Z)',
                ],
                'bridge_thresholds': {
                    'clinical_continuity': 0.8,
                    'safety_information': 0.9,
                    'treatment_flow': 0.7
                }
            },
            'legal': {
                'base_delimiters': [
                    DelimiterPattern(r'\n\s*\([a-z]\)\s+', priority=3, description="Lettered subsections"),
                    DelimiterPattern(r'\n\s*Section\s+\d+', priority=3, description="Legal sections"),
                    DelimiterPattern(r'\n\s*Article\s+[IVX]+', priority=3, description="Articles"),
                    DelimiterPattern(r'\n\s*\d+\.\d+\.\d+', priority=2, description="Nested numbering"),
                ],
                'chunk_size_modifiers': {
                    'statutes': 1.5,
                    'contracts': 1.3,
                    'case_law': 1.2,
                    'regulations': 1.4
                },
                'preservation_patterns': [
                    r'Section\s+\d+[\s\S]*?(?=\nSection|\nArticle|\n\n|\Z)',
                    r'Article\s+[IVX]+[\s\S]*?(?=\nArticle|\nSection|\n\n|\Z)',
                    r'\([a-z]\)[\s\S]*?(?=\n\([a-z]\)|\n\d+\.|\n\n|\Z)',
                ],
                'bridge_thresholds': {
                    'legal_continuity': 0.8,
                    'statutory_flow': 0.9,
                    'precedent_connection': 0.7
                }
            },
            'academic': {
                'base_delimiters': [
                    DelimiterPattern(r'\n\s*\d+\.\d+\s+', priority=3, description="Academic subsections"),
                    DelimiterPattern(r'\n\s*(?:Abstract|Introduction|Methodology|Results|Discussion|Conclusion):', priority=3, description="Paper sections"),
                    DelimiterPattern(r'\n\s*Figure\s+\d+', priority=2, description="Figures"),
                    DelimiterPattern(r'\n\s*Table\s+\d+', priority=2, description="Tables"),
                ],
                'chunk_size_modifiers': {
                    'research_paper': 1.3,
                    'literature_review': 1.4,
                    'methodology': 1.2,
                    'data_analysis': 1.1
                },
                'preservation_patterns': [
                    r'Abstract[\s\S]*?(?=\nIntroduction|\n\n|\Z)',
                    r'(?:Figure|Table)\s+\d+[\s\S]*?(?=\n(?:Figure|Table)|\n\n|\Z)',
                    r'References[\s\S]*?\Z',
                ],
                'bridge_thresholds': {
                    'research_continuity': 0.7,
                    'methodological_flow': 0.8,
                    'citation_context': 0.6
                }
            },
            'narrative': {
                'base_delimiters': [
                    DelimiterPattern(r'\n\s*Chapter\s+\d+', priority=3, description="Chapters"),
                    DelimiterPattern(r'\n\s*\*\s*\*\s*\*', priority=2, description="Scene breaks"),
                    DelimiterPattern(r'\n\n', priority=1, description="Paragraph breaks"),
                ],
                'chunk_size_modifiers': {
                    'dialogue_heavy': 0.8,
                    'descriptive': 1.1,
                    'action_sequence': 0.9,
                    'character_development': 1.0
                },
                'preservation_patterns': [
                    r'Chapter\s+\d+[\s\S]*?(?=\nChapter|\Z)',
                    r'"[^"]*"',  # Dialogue
                    r'\*\s*\*\s*\*[\s\S]*?(?=\*\s*\*\s*\*|\nChapter|\Z)',  # Scene breaks
                ],
                'bridge_thresholds': {
                    'narrative_flow': 0.6,
                    'character_continuity': 0.7,
                    'scene_transition': 0.8
                }
            }
        }
    
    def get_or_generate_config(self, content_profile: ContentProfile) -> DomainConfig:
        """
        Get existing or automatically generate domain configuration.
        
        Args:
            content_profile: Content profile from automated analysis
            
        Returns:
            DomainConfig for the content domain
        """
        domain_name = self._generate_domain_name(content_profile)
        
        # Try to get existing configuration
        existing_config = self._get_stored_config(domain_name)
        if existing_config and existing_config.is_active:
            logger.info(f"Using existing configuration for domain: {domain_name}")
            return existing_config.config
        
        # Generate new configuration
        logger.info(f"Generating new configuration for domain: {domain_name}")
        config = self._generate_domain_configuration(content_profile, domain_name)
        
        # Store the new configuration
        self._store_configuration(domain_name, config, content_profile)
        
        return config
    
    def _generate_domain_name(self, content_profile: ContentProfile) -> str:
        """Generate a unique domain name from content profile."""
        # Base name from content type
        base_name = content_profile.content_type.value
        
        # Add primary categories
        if content_profile.domain_categories:
            primary_categories = content_profile.domain_categories[:2]
            category_suffix = "_".join(cat.lower().replace(" ", "_") for cat in primary_categories)
            domain_name = f"{base_name}_{category_suffix}"
        else:
            domain_name = base_name
        
        # Add complexity indicator
        if content_profile.complexity_score > 0.7:
            domain_name += "_complex"
        elif content_profile.complexity_score < 0.3:
            domain_name += "_simple"
        
        # Ensure reasonable length
        if len(domain_name) > 50:
            domain_name = domain_name[:47] + "..."
        
        return domain_name
    
    def _get_stored_config(self, domain_name: str) -> Optional[StoredDomainConfig]:
        """Retrieve stored configuration from database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT config_data, version, created_at, generation_method, 
                       source_documents, performance_score, optimization_history,
                       is_active, usage_count
                FROM domain_configurations 
                WHERE domain_name = %s AND is_active = true
                ORDER BY version DESC LIMIT 1
                """
                
                cursor.execute(query, (domain_name,))
                result = cursor.fetchone()
                
                if result:
                    config_data, version, created_at, generation_method, \
                    source_documents, performance_score, optimization_history, \
                    is_active, usage_count = result
                    
                    # Parse JSON data
                    config_dict = json.loads(config_data)
                    config = DomainConfig.from_dict(config_dict)
                    
                    opt_history = []
                    if optimization_history:
                        opt_data = json.loads(optimization_history)
                        opt_history = [OptimizationRecord.from_dict(opt) for opt in opt_data]
                    
                    return StoredDomainConfig(
                        domain_name=domain_name,
                        config=config,
                        version=version,
                        created_at=created_at,
                        generation_method=generation_method,
                        source_documents=json.loads(source_documents) if source_documents else [],
                        performance_score=performance_score,
                        optimization_history=opt_history,
                        is_active=is_active,
                        usage_count=usage_count
                    )
        
        except Exception as e:
            logger.error(f"Failed to retrieve stored config for {domain_name}: {e}")
        
        return None
    
    def _generate_domain_configuration(self, content_profile: ContentProfile, 
                                     domain_name: str) -> DomainConfig:
        """Generate domain configuration using YAGO and ConceptNet analysis."""
        
        # Get base template
        content_type_key = content_profile.content_type.value
        template = self._domain_templates.get(content_type_key, self._domain_templates['narrative'])
        
        # Mine YAGO ontology for domain-specific patterns
        yago_patterns = self._mine_yago_ontology(content_profile.domain_categories)
        
        # Synthesize ConceptNet patterns
        conceptnet_patterns = self._synthesize_conceptnet_patterns(content_profile.domain_patterns)
        
        # Merge patterns with template
        delimiters = self._merge_delimiter_patterns(
            template['base_delimiters'], 
            yago_patterns.get('delimiters', []),
            conceptnet_patterns.get('delimiters', [])
        )
        
        # Generate chunk size modifiers
        chunk_size_modifiers = self._generate_chunk_size_modifiers(
            template['chunk_size_modifiers'],
            content_profile,
            yago_patterns,
            conceptnet_patterns
        )
        
        # Generate preservation patterns
        preservation_patterns = self._generate_preservation_patterns(
            template['preservation_patterns'],
            yago_patterns.get('preservation', []),
            conceptnet_patterns.get('preservation', [])
        )
        
        # Generate bridge thresholds
        bridge_thresholds = self._generate_bridge_thresholds(
            template['bridge_thresholds'],
            content_profile
        )
        
        # Generate cross-reference patterns
        cross_reference_patterns = self._generate_cross_reference_patterns(
            content_profile,
            yago_patterns,
            conceptnet_patterns
        )
        
        # Calculate confidence score
        confidence_score = self._calculate_configuration_confidence(
            content_profile, yago_patterns, conceptnet_patterns
        )
        
        return DomainConfig(
            domain_name=domain_name,
            delimiters=delimiters,
            chunk_size_modifiers=chunk_size_modifiers,
            preservation_patterns=preservation_patterns,
            bridge_thresholds=bridge_thresholds,
            cross_reference_patterns=cross_reference_patterns,
            generation_method="hybrid",
            confidence_score=confidence_score
        )
    
    def _mine_yago_ontology(self, domain_categories: List[str]) -> Dict[str, List[str]]:
        """Mine YAGO ontology for domain-specific patterns."""
        patterns = {
            'delimiters': [],
            'preservation': [],
            'structural': []
        }
        
        if not domain_categories:
            return patterns
        
        # Cache key for this set of categories
        cache_key = hashlib.md5("|".join(sorted(domain_categories)).encode()).hexdigest()
        
        if cache_key in self._ontology_cache:
            return self._ontology_cache[cache_key]
        
        try:
            # Query YAGO for structural patterns in these domains
            for category in domain_categories[:3]:  # Limit to avoid too many queries
                query = f"""
                SELECT ?item ?itemLabel ?property ?propertyLabel WHERE {{
                  ?item wdt:P31/wdt:P279* wd:Q{self._get_yago_id(category)} .
                  ?item ?property ?value .
                  ?property wdt:P31 wd:Q18616576 .  # YAGO property
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
                }}
                LIMIT 20
                """
                
                response = requests.get(
                    self.yago_endpoint,
                    params={'query': query, 'format': 'json'},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self._extract_patterns_from_yago(data, patterns)
        
        except Exception as e:
            logger.debug(f"Failed to mine YAGO ontology: {e}")
        
        # Cache the results
        self._ontology_cache[cache_key] = patterns
        return patterns
    
    def _get_yago_id(self, category: str) -> str:
        """Get YAGO ID for a category (simplified mapping)."""
        # This is a simplified mapping - in practice, you'd want a more comprehensive lookup
        category_mappings = {
            'software': 'Q7397',
            'computer': 'Q68',
            'medicine': 'Q11190',
            'law': 'Q7748',
            'book': 'Q571',
            'research': 'Q42240',
            'technology': 'Q11016',
            'science': 'Q336',
            'education': 'Q8434',
            'business': 'Q4830453'
        }
        
        category_lower = category.lower()
        for key, yago_id in category_mappings.items():
            if key in category_lower:
                return yago_id
        
        return 'Q35120'  # Default to "entity"
    
    def _extract_patterns_from_yago(self, data: Dict[str, Any], patterns: Dict[str, List[str]]):
        """Extract structural patterns from YAGO query results."""
        if not data.get('results', {}).get('bindings'):
            return
        
        # Analyze property patterns
        property_counter = Counter()
        
        for binding in data['results']['bindings']:
            if 'propertyLabel' in binding:
                prop_label = binding['propertyLabel']['value'].lower()
                property_counter[prop_label] += 1
        
        # Convert common properties to delimiter patterns
        for prop, count in property_counter.most_common(5):
            if count >= 2:
                if 'part' in prop or 'section' in prop:
                    patterns['delimiters'].append(f"yago_pattern:{prop}")
                elif 'structure' in prop or 'format' in prop:
                    patterns['structural'].append(f"yago_structure:{prop}")
    
    def _synthesize_conceptnet_patterns(self, domain_patterns: Optional[DomainPatterns]) -> Dict[str, List[str]]:
        """Synthesize ConceptNet patterns for chunking strategies."""
        patterns = {
            'delimiters': [],
            'preservation': [],
            'semantic': []
        }
        
        if not domain_patterns:
            return patterns
        
        # Convert relationship patterns to chunking patterns
        for rel_pattern in domain_patterns.relationship_patterns:
            if 'common_relation:' in rel_pattern:
                relation = rel_pattern.split(':')[1]
                if relation in ['PartOf', 'IsA', 'HasA']:
                    patterns['delimiters'].append(f"conceptnet_boundary:{relation}")
                elif relation in ['UsedFor', 'CapableOf']:
                    patterns['preservation'].append(f"conceptnet_preserve:{relation}")
        
        # Convert semantic patterns
        for sem_pattern in domain_patterns.semantic_patterns:
            patterns['semantic'].append(f"conceptnet_{sem_pattern}")
        
        # Convert delimiter patterns to actual regex patterns
        for delim_pattern in domain_patterns.delimiter_patterns:
            if delim_pattern not in patterns['delimiters']:
                patterns['delimiters'].append(delim_pattern)
        
        return patterns
    
    def _merge_delimiter_patterns(self, base_patterns: List[DelimiterPattern],
                                 yago_patterns: List[str],
                                 conceptnet_patterns: List[str]) -> List[DelimiterPattern]:
        """Merge delimiter patterns from multiple sources."""
        merged_patterns = base_patterns.copy()
        
        # Add YAGO-derived patterns
        for pattern in yago_patterns:
            if pattern.startswith('yago_pattern:'):
                # Convert to regex pattern based on the property
                prop = pattern.split(':')[1]
                if 'section' in prop:
                    regex_pattern = r'\n\s*' + prop.title() + r'\s+\d+'
                    merged_patterns.append(DelimiterPattern(
                        pattern=regex_pattern,
                        priority=2,
                        description=f"YAGO-derived {prop} pattern"
                    ))
        
        # Add ConceptNet-derived patterns
        for pattern in conceptnet_patterns:
            if pattern.startswith('conceptnet_boundary:'):
                relation = pattern.split(':')[1]
                # Create boundary patterns based on relation type
                if relation == 'PartOf':
                    merged_patterns.append(DelimiterPattern(
                        pattern=r'\n\s*(?:Part|Section|Component)\s+\d+',
                        priority=2,
                        description=f"ConceptNet {relation} boundary"
                    ))
            elif not pattern.startswith('conceptnet_'):
                # Direct regex pattern
                merged_patterns.append(DelimiterPattern(
                    pattern=pattern,
                    priority=1,
                    description="ConceptNet-derived pattern"
                ))
        
        # Sort by priority and remove duplicates
        unique_patterns = {}
        for pattern in merged_patterns:
            if pattern.pattern not in unique_patterns:
                unique_patterns[pattern.pattern] = pattern
            elif pattern.priority > unique_patterns[pattern.pattern].priority:
                unique_patterns[pattern.pattern] = pattern
        
        return sorted(unique_patterns.values(), key=lambda x: x.priority, reverse=True)
    
    def _generate_chunk_size_modifiers(self, base_modifiers: Dict[str, float],
                                     content_profile: ContentProfile,
                                     yago_patterns: Dict[str, List[str]],
                                     conceptnet_patterns: Dict[str, List[str]]) -> Dict[str, float]:
        """Generate chunk size modifiers based on content analysis."""
        modifiers = base_modifiers.copy()
        
        # Adjust based on complexity
        complexity_factor = content_profile.complexity_score
        
        if complexity_factor > 0.8:
            modifiers['high_complexity'] = 1.4
        elif complexity_factor > 0.6:
            modifiers['medium_complexity'] = 1.2
        else:
            modifiers['low_complexity'] = 0.9
        
        # Adjust based on conceptual density
        density_factor = content_profile.conceptual_density
        
        if density_factor > 0.7:
            modifiers['concept_dense'] = 1.3
        elif density_factor < 0.3:
            modifiers['concept_sparse'] = 0.8
        
        # Adjust based on cross-reference density
        ref_density = content_profile.cross_reference_density
        
        if ref_density > 0.5:
            modifiers['reference_heavy'] = 1.2
        
        # Add domain-specific modifiers from patterns
        if len(yago_patterns.get('structural', [])) > 3:
            modifiers['structured_content'] = 1.1
        
        if len(conceptnet_patterns.get('semantic', [])) > 5:
            modifiers['semantically_rich'] = 1.15
        
        return modifiers
    
    def _generate_preservation_patterns(self, base_patterns: List[str],
                                      yago_patterns: List[str],
                                      conceptnet_patterns: List[str]) -> List[str]:
        """Generate preservation patterns from multiple sources."""
        patterns = base_patterns.copy()
        
        # Add YAGO-derived preservation patterns
        for pattern in yago_patterns:
            if not any(existing in pattern for existing in patterns):
                patterns.append(pattern)
        
        # Add ConceptNet-derived preservation patterns
        for pattern in conceptnet_patterns:
            if pattern.startswith('conceptnet_preserve:'):
                relation = pattern.split(':')[1]
                if relation == 'UsedFor':
                    patterns.append(r'(?:used for|purpose|function)[\s\S]*?(?=\n[A-Z]|\n\n|\Z)')
                elif relation == 'CapableOf':
                    patterns.append(r'(?:capable of|can|ability)[\s\S]*?(?=\n[A-Z]|\n\n|\Z)')
        
        return patterns
    
    def _generate_bridge_thresholds(self, base_thresholds: Dict[str, float],
                                  content_profile: ContentProfile) -> Dict[str, float]:
        """Generate bridge thresholds based on content characteristics."""
        thresholds = base_thresholds.copy()
        
        # Adjust based on content complexity
        complexity_adjustment = (content_profile.complexity_score - 0.5) * 0.2
        
        for key in thresholds:
            thresholds[key] = max(0.4, min(0.9, thresholds[key] + complexity_adjustment))
        
        # Add content-specific thresholds
        if content_profile.cross_reference_density > 0.5:
            thresholds['cross_reference_continuity'] = 0.8
        
        if content_profile.conceptual_density > 0.7:
            thresholds['conceptual_coherence'] = 0.75
        
        # Content type specific adjustments
        if content_profile.content_type == ContentType.TECHNICAL:
            thresholds['technical_context'] = 0.8
        elif content_profile.content_type == ContentType.MEDICAL:
            thresholds['clinical_safety'] = 0.9
        elif content_profile.content_type == ContentType.LEGAL:
            thresholds['legal_precision'] = 0.85
        
        return thresholds
    
    def _generate_cross_reference_patterns(self, content_profile: ContentProfile,
                                         yago_patterns: Dict[str, List[str]],
                                         conceptnet_patterns: Dict[str, List[str]]) -> List[str]:
        """Generate cross-reference patterns for the domain."""
        patterns = []
        
        # Base cross-reference patterns
        base_patterns = [
            r'see\s+(?:section|chapter|page|figure|table)\s+\d+',
            r'(?:section|chapter|page|figure|table)\s+\d+',
            r'above|below|previously|later|aforementioned',
            r'as\s+(?:mentioned|discussed|shown|described)\s+(?:above|below|earlier|later)',
        ]
        
        patterns.extend(base_patterns)
        
        # Content type specific patterns
        if content_profile.content_type == ContentType.TECHNICAL:
            patterns.extend([
                r'(?:function|method|class)\s+\w+\(\)',
                r'see\s+(?:code|example|listing)\s+\d+',
                r'(?:API|interface)\s+reference',
            ])
        elif content_profile.content_type == ContentType.ACADEMIC:
            patterns.extend([
                r'\([^)]*\d{4}[^)]*\)',  # Citations
                r'(?:Figure|Table|Equation)\s+\d+',
                r'see\s+(?:appendix|supplement)',
            ])
        elif content_profile.content_type == ContentType.LEGAL:
            patterns.extend([
                r'(?:Section|Article|Clause)\s+\d+',
                r'pursuant\s+to',
                r'in\s+accordance\s+with',
            ])
        
        return patterns
    
    def _calculate_configuration_confidence(self, content_profile: ContentProfile,
                                          yago_patterns: Dict[str, List[str]],
                                          conceptnet_patterns: Dict[str, List[str]]) -> float:
        """Calculate confidence score for the generated configuration."""
        confidence_factors = []
        
        # Content profile completeness
        profile_completeness = 0.0
        if content_profile.domain_categories:
            profile_completeness += 0.3
        if content_profile.domain_patterns:
            profile_completeness += 0.3
        if content_profile.complexity_score > 0:
            profile_completeness += 0.2
        if content_profile.structure_hierarchy:
            profile_completeness += 0.2
        
        confidence_factors.append(profile_completeness)
        
        # Pattern richness from external sources
        yago_richness = min(len(yago_patterns.get('delimiters', [])) / 5.0, 1.0)
        conceptnet_richness = min(len(conceptnet_patterns.get('delimiters', [])) / 5.0, 1.0)
        
        confidence_factors.extend([yago_richness * 0.3, conceptnet_richness * 0.3])
        
        # Content type specificity
        type_specificity = 0.8 if content_profile.content_type != ContentType.GENERAL else 0.5
        confidence_factors.append(type_specificity * 0.2)
        
        # Calculate weighted average
        return sum(confidence_factors) / len(confidence_factors)
    
    def _store_configuration(self, domain_name: str, config: DomainConfig, 
                           content_profile: ContentProfile):
        """Store configuration with versioning and metadata."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Get next version number
                cursor.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM domain_configurations WHERE domain_name = %s",
                    (domain_name,)
                )
                version = cursor.fetchone()[0]
                
                # Prepare data for storage
                config_data = json.dumps(config.to_dict())
                source_documents = json.dumps([])  # Will be populated during usage
                optimization_history = json.dumps([])
                
                # Insert new configuration
                insert_query = """
                INSERT INTO domain_configurations 
                (domain_name, config_data, version, created_at, generation_method,
                 source_documents, performance_score, optimization_history, is_active, usage_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    domain_name, config_data, version, datetime.now(),
                    config.generation_method, source_documents, None,
                    optimization_history, True, 0
                ))
                
                conn.commit()
                logger.info(f"Stored configuration for domain {domain_name}, version {version}")
        
        except Exception as e:
            logger.error(f"Failed to store configuration for {domain_name}: {e}")
    
    def optimize_configuration(self, domain_name: str, 
                             performance_data: PerformanceMetrics) -> DomainConfig:
        """
        Automatically optimize configuration based on performance metrics.
        
        Args:
            domain_name: Name of the domain to optimize
            performance_data: Performance metrics for optimization
            
        Returns:
            Optimized DomainConfig
        """
        stored_config = self._get_stored_config(domain_name)
        if not stored_config:
            raise ValueError(f"No configuration found for domain: {domain_name}")
        
        # Analyze performance issues
        optimization_strategies = self._analyze_performance_issues(performance_data)
        
        # Apply optimizations
        optimized_config = self._apply_optimizations(stored_config.config, optimization_strategies)
        
        # Create optimization record
        optimization_record = OptimizationRecord(
            optimization_id=str(uuid.uuid4()),
            optimization_type="automated_performance_optimization",
            changes_made={strategy.type: strategy.adjustments for strategy in optimization_strategies},
            performance_before=stored_config.config.performance_baseline,
            performance_after=performance_data,
            improvement_score=self._calculate_improvement_score(
                stored_config.config.performance_baseline, performance_data
            ),
            timestamp=datetime.now()
        )
        
        # Update stored configuration
        self._update_stored_configuration(domain_name, optimized_config, optimization_record)
        
        return optimized_config
    
    def _analyze_performance_issues(self, performance_data: PerformanceMetrics) -> List[Dict[str, Any]]:
        """Analyze performance data to identify optimization opportunities."""
        strategies = []
        
        # Check chunk quality
        if performance_data.chunk_quality_score < 0.7:
            strategies.append({
                'type': 'chunk_size_adjustment',
                'target_metrics': ['chunk_quality_score'],
                'adjustments': {'size_multiplier': 1.1},
                'expected_improvement': 0.1,
                'confidence': 0.8
            })
        
        # Check bridge success rate
        if performance_data.bridge_success_rate < 0.6:
            strategies.append({
                'type': 'bridge_threshold_tuning',
                'target_metrics': ['bridge_success_rate'],
                'adjustments': {'threshold_reduction': 0.05},
                'expected_improvement': 0.15,
                'confidence': 0.7
            })
        
        # Check retrieval effectiveness
        if performance_data.retrieval_effectiveness < 0.75:
            strategies.append({
                'type': 'delimiter_refinement',
                'target_metrics': ['retrieval_effectiveness'],
                'adjustments': {'add_semantic_delimiters': True},
                'expected_improvement': 0.1,
                'confidence': 0.6
            })
        
        return strategies
    
    def _apply_optimizations(self, config: DomainConfig, 
                           strategies: List[Dict[str, Any]]) -> DomainConfig:
        """Apply optimization strategies to configuration."""
        optimized_config = DomainConfig(
            domain_name=config.domain_name,
            delimiters=config.delimiters.copy(),
            chunk_size_modifiers=config.chunk_size_modifiers.copy(),
            preservation_patterns=config.preservation_patterns.copy(),
            bridge_thresholds=config.bridge_thresholds.copy(),
            cross_reference_patterns=config.cross_reference_patterns.copy(),
            generation_method=config.generation_method,
            confidence_score=config.confidence_score
        )
        
        for strategy in strategies:
            if strategy['type'] == 'chunk_size_adjustment':
                multiplier = strategy['adjustments']['size_multiplier']
                for key in optimized_config.chunk_size_modifiers:
                    optimized_config.chunk_size_modifiers[key] *= multiplier
            
            elif strategy['type'] == 'bridge_threshold_tuning':
                reduction = strategy['adjustments']['threshold_reduction']
                for key in optimized_config.bridge_thresholds:
                    optimized_config.bridge_thresholds[key] = max(
                        0.4, optimized_config.bridge_thresholds[key] - reduction
                    )
            
            elif strategy['type'] == 'delimiter_refinement':
                if strategy['adjustments'].get('add_semantic_delimiters'):
                    # Add semantic delimiter patterns
                    semantic_delimiters = [
                        DelimiterPattern(r'\n\s*(?:However|Therefore|Furthermore|Moreover)', 
                                       priority=1, description="Semantic transitions"),
                        DelimiterPattern(r'\n\s*(?:In conclusion|To summarize|Finally)', 
                                       priority=2, description="Conclusion markers"),
                    ]
                    optimized_config.delimiters.extend(semantic_delimiters)
        
        return optimized_config
    
    def _calculate_improvement_score(self, before: Optional[PerformanceMetrics], 
                                   after: PerformanceMetrics) -> float:
        """Calculate improvement score between performance metrics."""
        if not before:
            return 0.0
        
        improvements = []
        
        # Compare key metrics
        metrics = [
            'chunk_quality_score', 'bridge_success_rate', 
            'retrieval_effectiveness', 'user_satisfaction_score'
        ]
        
        for metric in metrics:
            before_value = getattr(before, metric, 0.0)
            after_value = getattr(after, metric, 0.0)
            
            if before_value > 0:
                improvement = (after_value - before_value) / before_value
                improvements.append(improvement)
        
        return sum(improvements) / len(improvements) if improvements else 0.0
    
    def _update_stored_configuration(self, domain_name: str, config: DomainConfig,
                                   optimization_record: OptimizationRecord):
        """Update stored configuration with optimization results."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Get current configuration
                stored_config = self._get_stored_config(domain_name)
                if not stored_config:
                    return
                
                # Add optimization record to history
                stored_config.optimization_history.append(optimization_record)
                
                # Update configuration
                config_data = json.dumps(config.to_dict())
                optimization_history = json.dumps([opt.to_dict() for opt in stored_config.optimization_history])
                
                update_query = """
                UPDATE domain_configurations 
                SET config_data = %s, optimization_history = %s, 
                    performance_score = %s, version = version + 1
                WHERE domain_name = %s AND is_active = true
                """
                
                cursor.execute(update_query, (
                    config_data, optimization_history,
                    optimization_record.improvement_score, domain_name
                ))
                
                conn.commit()
                logger.info(f"Updated configuration for domain {domain_name} with optimization")
        
        except Exception as e:
            logger.error(f"Failed to update configuration for {domain_name}: {e}")

    def store_configuration(self, domain_name: str, config: DomainConfig, 
                          metadata: Dict[str, Any]) -> str:
        """
        Store versioned configuration with metadata.
        
        Args:
            domain_name: Name of the domain
            config: Configuration to store
            metadata: Additional metadata
            
        Returns:
            Configuration ID
        """
        config_id = str(uuid.uuid4())
        
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Get next version number
                cursor.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM domain_configurations WHERE domain_name = %s",
                    (domain_name,)
                )
                version = cursor.fetchone()[0]
                
                # Store configuration
                config_data = json.dumps(config.to_dict())
                metadata_json = json.dumps(metadata)
                
                insert_query = """
                INSERT INTO domain_configurations 
                (id, domain_name, config_data, version, created_at, generation_method,
                 source_documents, performance_score, optimization_history, is_active, usage_count, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (
                    config_id, domain_name, config_data, version, datetime.now(),
                    config.generation_method, json.dumps([]), None,
                    json.dumps([]), True, 0, metadata_json
                ))
                
                conn.commit()
                logger.info(f"Stored configuration {config_id} for domain {domain_name}")
                
                return config_id
        
        except Exception as e:
            logger.error(f"Failed to store configuration: {e}")
            raise