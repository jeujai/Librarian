"""
Knowledge Graph Integration for Configuration Updates.

This module implements YAGO/ConceptNet change detection, automated
configuration refresh triggers, and incremental configuration updates
based on new knowledge.
"""

import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from ...database.connection import get_database_connection
from ...models.chunking import ContentProfile, DomainConfig

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeGraphChange:
    """Detected change in external knowledge graphs."""
    change_id: str
    source: str  # 'yago' or 'conceptnet'
    change_type: str  # 'entity_added', 'relationship_added', 'property_updated'
    entity_id: str
    entity_label: str
    change_details: Dict[str, Any]
    detected_at: datetime
    relevance_score: float  # 0.0-1.0 relevance to our domains
    affected_domains: List[str]


@dataclass
class ConfigurationUpdate:
    """Configuration update based on knowledge graph changes."""
    update_id: str
    domain_name: str
    update_type: str  # 'delimiter_addition', 'pattern_refinement', 'threshold_adjustment'
    current_config: DomainConfig
    proposed_config: DomainConfig
    triggering_changes: List[KnowledgeGraphChange]
    confidence_score: float
    validation_status: str  # 'pending', 'validated', 'rejected'
    created_at: datetime
    applied_at: Optional[datetime] = None


@dataclass
class DomainKnowledgeProfile:
    """Knowledge profile for a domain based on external KGs."""
    domain_name: str
    yago_entities: List[Dict[str, Any]]
    conceptnet_concepts: List[Dict[str, Any]]
    domain_ontology: Dict[str, Any]
    last_updated: datetime
    update_frequency_hours: int = 24


class KnowledgeGraphConfigUpdater:
    """
    Knowledge graph integration for automated configuration updates.
    
    Implements change detection from YAGO and ConceptNet, relevance
    assessment, and automated configuration refresh based on new knowledge.
    """
    
    def __init__(self):
        """Initialize the knowledge graph config updater."""
        
        # API endpoints
        self.yago_endpoint = "https://yago-knowledge.org/sparql/query"
        self.conceptnet_endpoint = "http://api.conceptnet.io"
        
        # Change detection configuration
        self.change_detection_config = {
            'check_interval_hours': 6,
            'relevance_threshold': 0.3,
            'max_changes_per_check': 100,
            'entity_cache_duration_hours': 24
        }
        
        # Configuration update thresholds
        self.update_thresholds = {
            'min_confidence_for_auto_update': 0.8,
            'min_relevance_for_consideration': 0.4,
            'max_updates_per_domain_per_day': 3
        }
        
        # Domain knowledge profiles
        self.domain_profiles = {}
        
        # Change tracking
        self.detected_changes = defaultdict(list)
        self.pending_updates = defaultdict(list)
        
        logger.info("Initialized Knowledge Graph Config Updater")
    
    def detect_yago_changes(self, domain_entities: List[str]) -> List[KnowledgeGraphChange]:
        """
        Detect changes in YAGO for domain-relevant entities.
        
        Args:
            domain_entities: List of YAGO entity IDs to monitor
            
        Returns:
            List of detected changes
        """
        changes = []
        
        try:
            # Query for recent changes to monitored entities
            query = self._build_yago_changes_query(domain_entities)
            
            response = requests.get(
                self.yago_endpoint,
                params={'query': query, 'format': 'json'},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                changes = self._parse_yago_changes(data)
            else:
                logger.warning(f"YAGO query failed: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Failed to detect YAGO changes: {e}")
        
        return changes
    
    def detect_conceptnet_changes(self, domain_concepts: List[str]) -> List[KnowledgeGraphChange]:
        """
        Detect changes in ConceptNet for domain-relevant concepts.
        
        Args:
            domain_concepts: List of ConceptNet concepts to monitor
            
        Returns:
            List of detected changes
        """
        changes = []
        
        try:
            for concept in domain_concepts:
                # Query ConceptNet for recent edges
                url = f"{self.conceptnet_endpoint}/query"
                params = {
                    'node': f'/c/en/{concept}',
                    'limit': 50
                }
                
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    concept_changes = self._parse_conceptnet_changes(concept, data)
                    changes.extend(concept_changes)
                
                # Rate limiting
                time.sleep(0.1)
        
        except Exception as e:
            logger.error(f"Failed to detect ConceptNet changes: {e}")
        
        return changes
    
    def assess_change_relevance(self, change: KnowledgeGraphChange, 
                              domain_profile: DomainKnowledgeProfile) -> float:
        """
        Assess relevance of a knowledge graph change to a domain.
        
        Args:
            change: Knowledge graph change
            domain_profile: Domain knowledge profile
            
        Returns:
            Relevance score (0.0-1.0)
        """
        relevance_score = 0.0
        
        # Check entity relevance
        if change.source == 'yago':
            relevance_score += self._assess_yago_relevance(change, domain_profile)
        elif change.source == 'conceptnet':
            relevance_score += self._assess_conceptnet_relevance(change, domain_profile)
        
        # Boost for change type importance
        type_weights = {
            'entity_added': 0.8,
            'relationship_added': 0.9,
            'property_updated': 0.6,
            'category_changed': 0.7
        }
        
        type_weight = type_weights.get(change.change_type, 0.5)
        relevance_score *= type_weight
        
        return min(1.0, relevance_score)
    
    def generate_configuration_updates(self, domain_name: str, 
                                     relevant_changes: List[KnowledgeGraphChange]) -> List[ConfigurationUpdate]:
        """
        Generate configuration updates based on knowledge graph changes.
        
        Args:
            domain_name: Name of the domain
            relevant_changes: List of relevant changes
            
        Returns:
            List of proposed configuration updates
        """
        if not relevant_changes:
            return []
        
        # Get current configuration
        current_config = self._get_current_config(domain_name)
        if not current_config:
            logger.warning(f"No current config found for domain {domain_name}")
            return []
        
        updates = []
        
        # Group changes by type
        changes_by_type = defaultdict(list)
        for change in relevant_changes:
            changes_by_type[change.change_type].append(change)
        
        # Generate updates for each change type
        for change_type, changes in changes_by_type.items():
            if change_type == 'entity_added':
                update = self._generate_entity_addition_update(domain_name, current_config, changes)
                if update:
                    updates.append(update)
            
            elif change_type == 'relationship_added':
                update = self._generate_relationship_update(domain_name, current_config, changes)
                if update:
                    updates.append(update)
            
            elif change_type == 'property_updated':
                update = self._generate_property_update(domain_name, current_config, changes)
                if update:
                    updates.append(update)
        
        return updates
    
    def validate_configuration_update(self, update: ConfigurationUpdate) -> bool:
        """
        Validate a proposed configuration update.
        
        Args:
            update: Configuration update to validate
            
        Returns:
            True if update is valid and should be applied
        """
        # Basic validation
        if not update.proposed_config.validate():
            logger.warning(f"Proposed config for update {update.update_id} failed validation")
            return False
        
        # Check confidence threshold
        if update.confidence_score < self.update_thresholds['min_confidence_for_auto_update']:
            logger.info(f"Update {update.update_id} below confidence threshold")
            return False
        
        # Check update frequency limits
        if not self._check_update_frequency_limits(update.domain_name):
            logger.info(f"Update frequency limit reached for domain {update.domain_name}")
            return False
        
        # Validate specific update types
        if update.update_type == 'delimiter_addition':
            return self._validate_delimiter_addition(update)
        elif update.update_type == 'pattern_refinement':
            return self._validate_pattern_refinement(update)
        elif update.update_type == 'threshold_adjustment':
            return self._validate_threshold_adjustment(update)
        
        return True
    
    def apply_configuration_update(self, update: ConfigurationUpdate) -> bool:
        """
        Apply a validated configuration update.
        
        Args:
            update: Configuration update to apply
            
        Returns:
            True if update was successfully applied
        """
        try:
            # Store the updated configuration
            success = self._store_updated_configuration(update.domain_name, update.proposed_config)
            
            if success:
                update.applied_at = datetime.now()
                update.validation_status = 'applied'
                
                # Store update record
                self._store_configuration_update(update)
                
                logger.info(f"Applied configuration update {update.update_id} to domain {update.domain_name}")
                return True
            else:
                update.validation_status = 'failed'
                self._store_configuration_update(update)
                return False
        
        except Exception as e:
            logger.error(f"Failed to apply configuration update: {e}")
            return False
    
    def refresh_domain_knowledge_profile(self, domain_name: str) -> DomainKnowledgeProfile:
        """
        Refresh knowledge profile for a domain from external KGs.
        
        Args:
            domain_name: Name of the domain
            
        Returns:
            Updated domain knowledge profile
        """
        # Get domain categories and entities
        domain_categories = self._get_domain_categories(domain_name)
        
        # Query YAGO for domain entities
        yago_entities = self._query_yago_entities(domain_categories)
        
        # Query ConceptNet for domain concepts
        conceptnet_concepts = self._query_conceptnet_concepts(domain_categories)
        
        # Build domain ontology
        domain_ontology = self._build_domain_ontology(yago_entities, conceptnet_concepts)
        
        # Create updated profile
        profile = DomainKnowledgeProfile(
            domain_name=domain_name,
            yago_entities=yago_entities,
            conceptnet_concepts=conceptnet_concepts,
            domain_ontology=domain_ontology,
            last_updated=datetime.now()
        )
        
        # Store profile
        self.domain_profiles[domain_name] = profile
        self._store_domain_knowledge_profile(profile)
        
        logger.info(f"Refreshed knowledge profile for domain {domain_name}")
        
        return profile
    
    def monitor_and_update_configurations(self) -> Dict[str, List[str]]:
        """
        Monitor knowledge graphs and update configurations as needed.
        
        Returns:
            Dictionary mapping domain names to lists of applied update IDs
        """
        applied_updates = defaultdict(list)
        
        # Get all active domains
        active_domains = self._get_active_domains()
        
        for domain_name in active_domains:
            try:
                # Refresh domain knowledge profile if needed
                profile = self.domain_profiles.get(domain_name)
                if not profile or self._should_refresh_profile(profile):
                    profile = self.refresh_domain_knowledge_profile(domain_name)
                
                # Detect changes
                yago_changes = self.detect_yago_changes(
                    [e['id'] for e in profile.yago_entities]
                )
                conceptnet_changes = self.detect_conceptnet_changes(
                    [c['concept'] for c in profile.conceptnet_concepts]
                )
                
                all_changes = yago_changes + conceptnet_changes
                
                # Filter relevant changes
                relevant_changes = []
                for change in all_changes:
                    relevance = self.assess_change_relevance(change, profile)
                    if relevance >= self.update_thresholds['min_relevance_for_consideration']:
                        change.relevance_score = relevance
                        relevant_changes.append(change)
                
                # Generate and apply updates
                if relevant_changes:
                    updates = self.generate_configuration_updates(domain_name, relevant_changes)
                    
                    for update in updates:
                        if self.validate_configuration_update(update):
                            if self.apply_configuration_update(update):
                                applied_updates[domain_name].append(update.update_id)
            
            except Exception as e:
                logger.error(f"Failed to monitor domain {domain_name}: {e}")
        
        return dict(applied_updates)
    
    def _build_yago_changes_query(self, entity_ids: List[str]) -> str:
        """Build SPARQL query for YAGO changes."""
        
        # Simplified query - in practice would be more sophisticated
        entities_filter = " ".join([f"wd:{entity_id}" for entity_id in entity_ids[:10]])  # Limit to 10
        
        query = f"""
        SELECT ?entity ?entityLabel ?property ?value ?valueLabel WHERE {{
          VALUES ?entity {{ {entities_filter} }}
          ?entity ?property ?value .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}
        LIMIT 100
        """
        
        return query
    
    def _parse_yago_changes(self, data: Dict[str, Any]) -> List[KnowledgeGraphChange]:
        """Parse YAGO query results into changes."""
        changes = []
        
        try:
            bindings = data.get('results', {}).get('bindings', [])
            
            for binding in bindings:
                entity_uri = binding.get('entity', {}).get('value', '')
                entity_id = entity_uri.split('/')[-1] if entity_uri else ''
                entity_label = binding.get('entityLabel', {}).get('value', '')
                
                if entity_id:
                    change = KnowledgeGraphChange(
                        change_id=str(uuid.uuid4()),
                        source='yago',
                        change_type='property_updated',
                        entity_id=entity_id,
                        entity_label=entity_label,
                        change_details={
                            'property': binding.get('property', {}).get('value', ''),
                            'value': binding.get('value', {}).get('value', ''),
                            'value_label': binding.get('valueLabel', {}).get('value', '')
                        },
                        detected_at=datetime.now(),
                        relevance_score=0.0,
                        affected_domains=[]
                    )
                    changes.append(change)
        
        except Exception as e:
            logger.error(f"Failed to parse YAGO changes: {e}")
        
        return changes
    
    def _parse_conceptnet_changes(self, concept: str, data: Dict[str, Any]) -> List[KnowledgeGraphChange]:
        """Parse ConceptNet query results into changes."""
        changes = []
        
        try:
            edges = data.get('edges', [])
            
            for edge in edges:
                change = KnowledgeGraphChange(
                    change_id=str(uuid.uuid4()),
                    source='conceptnet',
                    change_type='relationship_added',
                    entity_id=concept,
                    entity_label=concept,
                    change_details={
                        'relation': edge.get('rel', {}).get('label', ''),
                        'start': edge.get('start', {}).get('label', ''),
                        'end': edge.get('end', {}).get('label', ''),
                        'weight': edge.get('weight', 0.0)
                    },
                    detected_at=datetime.now(),
                    relevance_score=0.0,
                    affected_domains=[]
                )
                changes.append(change)
        
        except Exception as e:
            logger.error(f"Failed to parse ConceptNet changes: {e}")
        
        return changes
    
    def _assess_yago_relevance(self, change: KnowledgeGraphChange, 
                                 profile: DomainKnowledgeProfile) -> float:
        """Assess relevance of YAGO change to domain."""
        
        # Check if entity is in domain profile
        for entity in profile.yago_entities:
            if entity['id'] == change.entity_id:
                return 0.9  # High relevance for direct entities
        
        # Check for related entities (simplified)
        if any(change.entity_label.lower() in entity['label'].lower() 
               for entity in profile.yago_entities):
            return 0.6
        
        return 0.2  # Low baseline relevance
    
    def _assess_conceptnet_relevance(self, change: KnowledgeGraphChange, 
                                   profile: DomainKnowledgeProfile) -> float:
        """Assess relevance of ConceptNet change to domain."""
        
        # Check if concept is in domain profile
        for concept in profile.conceptnet_concepts:
            if concept['concept'] == change.entity_id:
                return 0.9
        
        # Check for related concepts
        change_details = change.change_details
        start_concept = change_details.get('start', '').lower()
        end_concept = change_details.get('end', '').lower()
        
        for concept in profile.conceptnet_concepts:
            concept_name = concept['concept'].lower()
            if concept_name in start_concept or concept_name in end_concept:
                return 0.7
        
        return 0.3
    
    def _generate_entity_addition_update(self, domain_name: str, current_config: DomainConfig,
                                       changes: List[KnowledgeGraphChange]) -> Optional[ConfigurationUpdate]:
        """Generate update for entity additions."""
        
        # Extract new entities and their properties
        new_entities = []
        for change in changes:
            new_entities.append({
                'id': change.entity_id,
                'label': change.entity_label,
                'details': change.change_details
            })
        
        # Generate new delimiters based on entities
        new_delimiters = self._generate_delimiters_from_entities(new_entities)
        
        if not new_delimiters:
            return None
        
        # Create updated configuration
        updated_config = DomainConfig(
            domain_name=current_config.domain_name,
            delimiters=current_config.delimiters + new_delimiters,
            chunk_size_modifiers=current_config.chunk_size_modifiers.copy(),
            preservation_patterns=current_config.preservation_patterns.copy(),
            bridge_thresholds=current_config.bridge_thresholds.copy(),
            cross_reference_patterns=current_config.cross_reference_patterns.copy(),
            generation_method='kg_enhanced',
            confidence_score=0.8
        )
        
        return ConfigurationUpdate(
            update_id=str(uuid.uuid4()),
            domain_name=domain_name,
            update_type='delimiter_addition',
            current_config=current_config,
            proposed_config=updated_config,
            triggering_changes=changes,
            confidence_score=0.8,
            validation_status='pending',
            created_at=datetime.now()
        )
    
    def _generate_relationship_update(self, domain_name: str, current_config: DomainConfig,
                                    changes: List[KnowledgeGraphChange]) -> Optional[ConfigurationUpdate]:
        """Generate update for relationship additions."""
        
        # Analyze relationships to determine configuration changes
        relationship_patterns = []
        for change in changes:
            details = change.change_details
            relation = details.get('relation', '')
            
            if relation in ['IsA', 'PartOf', 'HasProperty']:
                relationship_patterns.append(f"{details.get('start', '')} {relation} {details.get('end', '')}")
        
        if not relationship_patterns:
            return None
        
        # Add relationship patterns to cross-reference patterns
        updated_config = DomainConfig(
            domain_name=current_config.domain_name,
            delimiters=current_config.delimiters.copy(),
            chunk_size_modifiers=current_config.chunk_size_modifiers.copy(),
            preservation_patterns=current_config.preservation_patterns.copy(),
            bridge_thresholds=current_config.bridge_thresholds.copy(),
            cross_reference_patterns=current_config.cross_reference_patterns + relationship_patterns,
            generation_method='kg_enhanced',
            confidence_score=0.7
        )
        
        return ConfigurationUpdate(
            update_id=str(uuid.uuid4()),
            domain_name=domain_name,
            update_type='pattern_refinement',
            current_config=current_config,
            proposed_config=updated_config,
            triggering_changes=changes,
            confidence_score=0.7,
            validation_status='pending',
            created_at=datetime.now()
        )
    
    def _generate_property_update(self, domain_name: str, current_config: DomainConfig,
                                changes: List[KnowledgeGraphChange]) -> Optional[ConfigurationUpdate]:
        """Generate update for property changes."""
        
        # Analyze property changes to adjust thresholds
        threshold_adjustments = {}
        
        for change in changes:
            details = change.change_details
            property_uri = details.get('property', '')
            
            # Map properties to threshold adjustments (simplified)
            if 'complexity' in property_uri.lower():
                threshold_adjustments['complexity_threshold'] = 0.05
            elif 'importance' in property_uri.lower():
                threshold_adjustments['bridge_threshold'] = -0.02
        
        if not threshold_adjustments:
            return None
        
        # Apply threshold adjustments
        updated_thresholds = current_config.bridge_thresholds.copy()
        for key, adjustment in threshold_adjustments.items():
            if key in updated_thresholds:
                updated_thresholds[key] = max(0.0, min(1.0, updated_thresholds[key] + adjustment))
        
        updated_config = DomainConfig(
            domain_name=current_config.domain_name,
            delimiters=current_config.delimiters.copy(),
            chunk_size_modifiers=current_config.chunk_size_modifiers.copy(),
            preservation_patterns=current_config.preservation_patterns.copy(),
            bridge_thresholds=updated_thresholds,
            cross_reference_patterns=current_config.cross_reference_patterns.copy(),
            generation_method='kg_enhanced',
            confidence_score=0.6
        )
        
        return ConfigurationUpdate(
            update_id=str(uuid.uuid4()),
            domain_name=domain_name,
            update_type='threshold_adjustment',
            current_config=current_config,
            proposed_config=updated_config,
            triggering_changes=changes,
            confidence_score=0.6,
            validation_status='pending',
            created_at=datetime.now()
        )
    
    def _generate_delimiters_from_entities(self, entities: List[Dict[str, Any]]) -> List:
        """Generate delimiter patterns from entities."""
        from ...models.chunking import DelimiterPattern
        
        delimiters = []
        
        for entity in entities:
            label = entity['label'].lower()
            
            # Generate patterns based on entity types (simplified)
            if any(term in label for term in ['section', 'chapter', 'part']):
                pattern = DelimiterPattern(
                    pattern=f"\\b{label}\\s+\\d+",
                    priority=3,
                    description=f"Pattern for {label} markers"
                )
                delimiters.append(pattern)
        
        return delimiters
    
    def _validate_delimiter_addition(self, update: ConfigurationUpdate) -> bool:
        """Validate delimiter addition update."""
        
        # Check that new delimiters are valid regex patterns
        new_delimiters = set(d.pattern for d in update.proposed_config.delimiters) - \
                        set(d.pattern for d in update.current_config.delimiters)
        
        for pattern in new_delimiters:
            try:
                import re
                re.compile(pattern)
            except re.error:
                logger.warning(f"Invalid regex pattern in delimiter update: {pattern}")
                return False
        
        return True
    
    def _validate_pattern_refinement(self, update: ConfigurationUpdate) -> bool:
        """Validate pattern refinement update."""
        
        # Check that new patterns are reasonable
        new_patterns = set(update.proposed_config.cross_reference_patterns) - \
                      set(update.current_config.cross_reference_patterns)
        
        # Ensure patterns are not too generic
        for pattern in new_patterns:
            if len(pattern.split()) < 2:  # Too short
                return False
        
        return True
    
    def _validate_threshold_adjustment(self, update: ConfigurationUpdate) -> bool:
        """Validate threshold adjustment update."""
        
        # Check that threshold changes are reasonable
        current_thresholds = update.current_config.bridge_thresholds
        proposed_thresholds = update.proposed_config.bridge_thresholds
        
        for key in proposed_thresholds:
            if key in current_thresholds:
                change = abs(proposed_thresholds[key] - current_thresholds[key])
                if change > 0.2:  # Too large change
                    return False
        
        return True
    
    def _check_update_frequency_limits(self, domain_name: str) -> bool:
        """Check if domain is within update frequency limits."""
        
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Count updates in last 24 hours
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                query = """
                SELECT COUNT(*) FROM kg_configuration_updates 
                WHERE domain_name = %s AND applied_at >= %s
                """
                cursor.execute(query, (domain_name, cutoff_time))
                count = cursor.fetchone()[0]
                
                return count < self.update_thresholds['max_updates_per_domain_per_day']
        
        except Exception as e:
            logger.error(f"Failed to check update frequency: {e}")
            return True  # Allow update if check fails
    
    def _get_current_config(self, domain_name: str) -> Optional[DomainConfig]:
        """Get current configuration for domain."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT config_data FROM domain_configurations 
                WHERE domain_name = %s AND is_active = true
                ORDER BY version DESC LIMIT 1
                """
                cursor.execute(query, (domain_name,))
                result = cursor.fetchone()
                
                if result:
                    config_data = json.loads(result[0])
                    return DomainConfig.from_dict(config_data)
        
        except Exception as e:
            logger.error(f"Failed to get current config: {e}")
        
        return None
    
    def _get_domain_categories(self, domain_name: str) -> List[str]:
        """Get domain categories for knowledge graph queries."""
        
        # This would typically come from the domain configuration or content analysis
        # For now, return some default categories based on domain name
        category_mapping = {
            'medical': ['medicine', 'health', 'disease', 'treatment'],
            'legal': ['law', 'legal', 'court', 'legislation'],
            'technical': ['technology', 'engineering', 'software', 'computer'],
            'academic': ['research', 'science', 'education', 'academic']
        }
        
        for key, categories in category_mapping.items():
            if key in domain_name.lower():
                return categories
        
        return ['general', 'knowledge']
    
    def _query_yago_entities(self, categories: List[str]) -> List[Dict[str, Any]]:
        """Query YAGO for entities in given categories."""
        entities = []
        
        try:
            # Build query for entities in categories
            category_filter = " ".join([f'"{cat}"@en' for cat in categories])
            
            query = f"""
            SELECT ?entity ?entityLabel WHERE {{
              ?entity rdfs:label ?entityLabel .
              FILTER(CONTAINS(LCASE(?entityLabel), "{categories[0]}"))
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
            }}
            LIMIT 20
            """
            
            response = requests.get(
                self.yago_endpoint,
                params={'query': query, 'format': 'json'},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                bindings = data.get('results', {}).get('bindings', [])
                
                for binding in bindings:
                    entity_uri = binding.get('entity', {}).get('value', '')
                    entity_id = entity_uri.split('/')[-1] if entity_uri else ''
                    entity_label = binding.get('entityLabel', {}).get('value', '')
                    
                    if entity_id and entity_label:
                        entities.append({
                            'id': entity_id,
                            'label': entity_label,
                            'uri': entity_uri
                        })
        
        except Exception as e:
            logger.error(f"Failed to query YAGO entities: {e}")
        
        return entities
    
    def _query_conceptnet_concepts(self, categories: List[str]) -> List[Dict[str, Any]]:
        """Query ConceptNet for concepts in given categories."""
        concepts = []
        
        try:
            for category in categories[:3]:  # Limit to 3 categories
                url = f"{self.conceptnet_endpoint}/search"
                params = {
                    'text': category,
                    'language': 'en',
                    'limit': 10
                }
                
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    for item in data.get('edges', []):
                        start = item.get('start', {})
                        if start.get('language') == 'en':
                            concepts.append({
                                'concept': start.get('label', ''),
                                'uri': start.get('@id', ''),
                                'category': category
                            })
                
                time.sleep(0.1)  # Rate limiting
        
        except Exception as e:
            logger.error(f"Failed to query ConceptNet concepts: {e}")
        
        return concepts
    
    def _build_domain_ontology(self, yago_entities: List[Dict[str, Any]], 
                             conceptnet_concepts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build domain ontology from entities and concepts."""
        
        ontology = {
            'entities': {entity['id']: entity['label'] for entity in yago_entities},
            'concepts': {concept['concept']: concept['category'] for concept in conceptnet_concepts},
            'relationships': {},  # Would be populated with actual relationships
            'hierarchy': {}  # Would be populated with hierarchical relationships
        }
        
        return ontology
    
    def _should_refresh_profile(self, profile: DomainKnowledgeProfile) -> bool:
        """Check if domain profile should be refreshed."""
        
        time_since_update = datetime.now() - profile.last_updated
        return time_since_update.total_seconds() > (profile.update_frequency_hours * 3600)
    
    def _get_active_domains(self) -> List[str]:
        """Get list of active domains."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                SELECT DISTINCT domain_name FROM domain_configurations 
                WHERE is_active = true
                """
                cursor.execute(query)
                results = cursor.fetchall()
                
                return [row[0] for row in results]
        
        except Exception as e:
            logger.error(f"Failed to get active domains: {e}")
            return []
    
    def _store_updated_configuration(self, domain_name: str, config: DomainConfig) -> bool:
        """Store updated configuration in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Deactivate current configuration
                update_query = """
                UPDATE domain_configurations 
                SET is_active = false 
                WHERE domain_name = %s AND is_active = true
                """
                cursor.execute(update_query, (domain_name,))
                
                # Insert new configuration
                insert_query = """
                INSERT INTO domain_configurations 
                (domain_name, version, config_data, generation_method, 
                 confidence_score, is_active, created_at)
                VALUES (%s, 
                        (SELECT COALESCE(MAX(version), 0) + 1 FROM domain_configurations WHERE domain_name = %s),
                        %s, %s, %s, true, %s)
                """
                
                cursor.execute(insert_query, (
                    domain_name, domain_name, json.dumps(config.to_dict()),
                    config.generation_method, config.confidence_score, datetime.now()
                ))
                
                conn.commit()
                return True
        
        except Exception as e:
            logger.error(f"Failed to store updated configuration: {e}")
            return False
    
    def _store_configuration_update(self, update: ConfigurationUpdate) -> None:
        """Store configuration update record in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS kg_configuration_updates (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    update_id VARCHAR(100) UNIQUE NOT NULL,
                    domain_name VARCHAR(100) NOT NULL,
                    update_type VARCHAR(50) NOT NULL,
                    current_config JSONB NOT NULL,
                    proposed_config JSONB NOT NULL,
                    triggering_changes JSONB,
                    confidence_score FLOAT,
                    validation_status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    applied_at TIMESTAMP
                )
                """
                cursor.execute(create_table_query)
                
                insert_query = """
                INSERT INTO kg_configuration_updates 
                (update_id, domain_name, update_type, current_config, proposed_config,
                 triggering_changes, confidence_score, validation_status, created_at, applied_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (update_id) DO UPDATE SET
                    validation_status = EXCLUDED.validation_status,
                    applied_at = EXCLUDED.applied_at
                """
                
                triggering_changes_json = json.dumps([
                    {
                        'change_id': c.change_id,
                        'source': c.source,
                        'change_type': c.change_type,
                        'entity_id': c.entity_id,
                        'relevance_score': c.relevance_score
                    } for c in update.triggering_changes
                ])
                
                cursor.execute(insert_query, (
                    update.update_id, update.domain_name, update.update_type,
                    json.dumps(update.current_config.to_dict()),
                    json.dumps(update.proposed_config.to_dict()),
                    triggering_changes_json, update.confidence_score,
                    update.validation_status, update.created_at, update.applied_at
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store configuration update: {e}")
    
    def _store_domain_knowledge_profile(self, profile: DomainKnowledgeProfile) -> None:
        """Store domain knowledge profile in database."""
        try:
            with get_database_connection() as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                create_table_query = """
                CREATE TABLE IF NOT EXISTS domain_knowledge_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    domain_name VARCHAR(100) UNIQUE NOT NULL,
                    yago_entities JSONB,
                    conceptnet_concepts JSONB,
                    domain_ontology JSONB,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    update_frequency_hours INTEGER DEFAULT 24
                )
                """
                cursor.execute(create_table_query)
                
                upsert_query = """
                INSERT INTO domain_knowledge_profiles 
                (domain_name, yago_entities, conceptnet_concepts, domain_ontology,
                 last_updated, update_frequency_hours)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (domain_name) DO UPDATE SET
                    yago_entities = EXCLUDED.yago_entities,
                    conceptnet_concepts = EXCLUDED.conceptnet_concepts,
                    domain_ontology = EXCLUDED.domain_ontology,
                    last_updated = EXCLUDED.last_updated,
                    update_frequency_hours = EXCLUDED.update_frequency_hours
                """
                
                cursor.execute(upsert_query, (
                    profile.domain_name, json.dumps(profile.yago_entities),
                    json.dumps(profile.conceptnet_concepts), json.dumps(profile.domain_ontology),
                    profile.last_updated, profile.update_frequency_hours
                ))
                
                conn.commit()
        
        except Exception as e:
            logger.error(f"Failed to store domain knowledge profile: {e}")