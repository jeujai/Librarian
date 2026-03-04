"""
Knowledge Graph Manager Component.

This component handles knowledge graph construction, management, bootstrapping
from external sources, conflict resolution, and user feedback integration.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from ...config import get_settings
from ...models.core import KnowledgeChunk, RelationshipType
from ...models.knowledge_graph import (
    ConceptNode,
    KnowledgeGraphStats,
    RelationshipEdge,
    Triple,
)
from .kg_builder import KnowledgeGraphBuilder
from .relation_type_mapper import RelationTypeMapper

logger = logging.getLogger(__name__)


class ExternalKnowledgeBootstrapper:
    """Bootstraps knowledge graph from external sources like ConceptNet and YAGO."""
    
    def __init__(self):
        self.settings = get_settings()
        self.conceptnet_base_url = "http://api.conceptnet.io"
        self.yago_base_url = "https://yago-knowledge.org/sparql/query"
        
    def bootstrap_from_conceptnet(self, domains: List[str], max_concepts: int = 1000) -> Tuple[List[ConceptNode], List[RelationshipEdge]]:
        """Bootstrap knowledge graph from ConceptNet for specific domains."""
        try:
            concepts = []
            relationships = []
            processed_concepts = set()
            
            for domain in domains:
                domain_concepts, domain_relationships = self._fetch_conceptnet_domain(
                    domain, max_concepts // len(domains)
                )
                
                # Filter out already processed concepts
                new_concepts = [c for c in domain_concepts if c.concept_id not in processed_concepts]
                concepts.extend(new_concepts)
                relationships.extend(domain_relationships)
                
                processed_concepts.update(c.concept_id for c in new_concepts)
            
            logger.info(f"Bootstrapped {len(concepts)} concepts and {len(relationships)} relationships from ConceptNet")
            return concepts, relationships
            
        except Exception as e:
            logger.error(f"Error bootstrapping from ConceptNet: {e}")
            return [], []
    
    def bootstrap_from_yago(self, domains: List[str], max_concepts: int = 1000) -> Tuple[List[ConceptNode], List[RelationshipEdge]]:
        """Bootstrap knowledge graph from YAGO for specific domains."""
        try:
            concepts = []
            relationships = []
            
            for domain in domains:
                domain_concepts, domain_relationships = self._fetch_yago_domain(
                    domain, max_concepts // len(domains)
                )
                concepts.extend(domain_concepts)
                relationships.extend(domain_relationships)
            
            logger.info(f"Bootstrapped {len(concepts)} concepts and {len(relationships)} relationships from YAGO")
            return concepts, relationships
            
        except Exception as e:
            logger.error(f"Error bootstrapping from YAGO: {e}")
            return [], []
    
    def _fetch_conceptnet_domain(self, domain: str, max_concepts: int) -> Tuple[List[ConceptNode], List[RelationshipEdge]]:
        """Fetch concepts and relationships from ConceptNet for a specific domain."""
        concepts = []
        relationships = []
        
        try:
            # Search for domain-related concepts
            search_url = f"{self.conceptnet_base_url}/search"
            params = {
                'q': domain,
                'limit': min(max_concepts, 100)
            }
            
            response = requests.get(search_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                for edge_data in data.get('edges', []):
                    # Extract concept information
                    start_concept = self._parse_conceptnet_concept(edge_data.get('start', {}))
                    end_concept = self._parse_conceptnet_concept(edge_data.get('end', {}))
                    
                    if start_concept:
                        concepts.append(start_concept)
                    if end_concept:
                        concepts.append(end_concept)
                    
                    # Extract relationship
                    if start_concept and end_concept:
                        relationship = self._parse_conceptnet_relationship(edge_data, start_concept, end_concept)
                        if relationship:
                            relationships.append(relationship)
            
        except Exception as e:
            logger.error(f"Error fetching ConceptNet domain {domain}: {e}")
        
        return concepts, relationships
    
    def _fetch_yago_domain(self, domain: str, max_concepts: int) -> Tuple[List[ConceptNode], List[RelationshipEdge]]:
        """Fetch concepts and relationships from YAGO for a specific domain."""
        concepts = []
        relationships = []
        
        try:
            # Search for domain-related entities
            search_params = {
                'action': 'wbsearchentities',
                'search': domain,
                'language': 'en',
                'format': 'json',
                'limit': min(max_concepts, 50)
            }
            
            response = requests.get(self.yago_base_url, params=search_params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                for entity in data.get('search', []):
                    concept = self._parse_yago_concept(entity)
                    if concept:
                        concepts.append(concept)
                        
                        # Fetch relationships for this concept
                        entity_relationships = self._fetch_yago_relationships(entity['id'])
                        relationships.extend(entity_relationships)
            
        except Exception as e:
            logger.error(f"Error fetching YAGO domain {domain}: {e}")
        
        return concepts, relationships
    
    def _parse_conceptnet_concept(self, concept_data: Dict) -> Optional[ConceptNode]:
        """Parse ConceptNet concept data into ConceptNode."""
        try:
            if not concept_data:
                return None
            
            uri = concept_data.get('@id', '')
            if not uri:
                return None
            
            # Extract concept name from URI
            concept_name = uri.split('/')[-1].replace('_', ' ')
            concept_id = f"conceptnet_{concept_name.lower().replace(' ', '_')}"
            
            return ConceptNode(
                concept_id=concept_id,
                concept_name=concept_name,
                concept_type="ENTITY",
                confidence=0.8,  # ConceptNet confidence
                external_ids={"conceptnet": uri}
            )
            
        except Exception as e:
            logger.error(f"Error parsing ConceptNet concept: {e}")
            return None
    
    def _parse_conceptnet_relationship(self, edge_data: Dict, start_concept: ConceptNode, 
                                     end_concept: ConceptNode) -> Optional[RelationshipEdge]:
        """Parse ConceptNet relationship data into RelationshipEdge."""
        try:
            relation = edge_data.get('rel', {})
            predicate = relation.get('@id', '').split('/')[-1]
            
            if not predicate:
                return None
            
            weight = edge_data.get('weight', 1.0)
            confidence = min(weight / 10.0, 1.0)  # Normalize weight to confidence
            
            return RelationshipEdge(
                subject_concept=start_concept.concept_id,
                predicate=predicate.upper(),
                object_concept=end_concept.concept_id,
                confidence=confidence,
                relationship_type=self._map_conceptnet_relation_type(predicate)
            )
            
        except Exception as e:
            logger.error(f"Error parsing ConceptNet relationship: {e}")
            return None
    
    def _parse_yago_concept(self, entity_data: Dict) -> Optional[ConceptNode]:
        """Parse YAGO entity data into ConceptNode."""
        try:
            entity_id = entity_data.get('id', '')
            label = entity_data.get('label', '')
            description = entity_data.get('description', '')
            
            if not entity_id or not label:
                return None
            
            concept_id = f"yago_{entity_id}"
            aliases = entity_data.get('aliases', [])
            
            return ConceptNode(
                concept_id=concept_id,
                concept_name=label,
                concept_type="ENTITY",
                aliases=aliases,
                confidence=0.9,  # YAGO confidence
                external_ids={"yago": entity_id}
            )
            
        except Exception as e:
            logger.error(f"Error parsing YAGO concept: {e}")
            return None
    
    def _fetch_yago_relationships(self, entity_id: str) -> List[RelationshipEdge]:
        """Fetch relationships for a YAGO entity."""
        relationships = []
        
        try:
            # This would require more complex SPARQL queries in practice
            # For now, returning empty list as placeholder
            pass
            
        except Exception as e:
            logger.error(f"Error fetching YAGO relationships for {entity_id}: {e}")
        
        return relationships
    
    def _map_conceptnet_relation_type(self, predicate: str) -> RelationshipType:
        """Map ConceptNet predicate to RelationshipType."""
        return RelationTypeMapper.classify(predicate)


class ConflictResolver:
    """Resolves conflicts in the knowledge graph."""
    
    def __init__(self):
        self.confidence_threshold = 0.5
        
    def resolve_concept_conflicts(self, concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Resolve conflicts between concepts."""
        try:
            # Group concepts by normalized name
            concept_groups = {}
            for concept in concepts:
                key = concept.concept_name.lower().strip()
                if key not in concept_groups:
                    concept_groups[key] = []
                concept_groups[key].append(concept)
            
            resolved_concepts = []
            for group in concept_groups.values():
                if len(group) == 1:
                    resolved_concepts.append(group[0])
                else:
                    # Merge conflicting concepts
                    merged_concept = self._merge_concepts(group)
                    resolved_concepts.append(merged_concept)
            
            logger.info(f"Resolved {len(concepts)} concepts to {len(resolved_concepts)} concepts")
            return resolved_concepts
            
        except Exception as e:
            logger.error(f"Error resolving concept conflicts: {e}")
            return concepts
    
    def resolve_relationship_conflicts(self, relationships: List[RelationshipEdge]) -> List[RelationshipEdge]:
        """Resolve conflicts between relationships."""
        try:
            # Group relationships by subject-predicate-object
            relationship_groups = {}
            for relationship in relationships:
                key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
                if key not in relationship_groups:
                    relationship_groups[key] = []
                relationship_groups[key].append(relationship)
            
            resolved_relationships = []
            for group in relationship_groups.values():
                if len(group) == 1:
                    resolved_relationships.append(group[0])
                else:
                    # Merge conflicting relationships
                    merged_relationship = self._merge_relationships(group)
                    resolved_relationships.append(merged_relationship)
            
            logger.info(f"Resolved {len(relationships)} relationships to {len(resolved_relationships)} relationships")
            return resolved_relationships
            
        except Exception as e:
            logger.error(f"Error resolving relationship conflicts: {e}")
            return relationships
    
    def validate_relationship_consistency(self, relationships: List[RelationshipEdge]) -> List[RelationshipEdge]:
        """Validate and filter inconsistent relationships."""
        try:
            valid_relationships = []
            
            for relationship in relationships:
                if self._is_relationship_consistent(relationship, relationships):
                    valid_relationships.append(relationship)
                else:
                    logger.warning(f"Inconsistent relationship filtered: {relationship.get_relationship_string()}")
            
            logger.info(f"Validated {len(valid_relationships)} consistent relationships from {len(relationships)}")
            return valid_relationships
            
        except Exception as e:
            logger.error(f"Error validating relationship consistency: {e}")
            return relationships
    
    def _merge_concepts(self, concepts: List[ConceptNode]) -> ConceptNode:
        """Merge multiple concepts into one."""
        # Use the concept with highest confidence as base
        base_concept = max(concepts, key=lambda c: c.confidence)
        
        # Merge aliases and source chunks
        all_aliases = set(base_concept.aliases)
        all_source_chunks = set(base_concept.source_chunks)
        all_external_ids = dict(base_concept.external_ids)
        
        for concept in concepts:
            if concept != base_concept:
                all_aliases.update(concept.aliases)
                all_source_chunks.update(concept.source_chunks)
                all_external_ids.update(concept.external_ids)
        
        # Create merged concept
        merged_concept = ConceptNode(
            concept_id=base_concept.concept_id,
            concept_name=base_concept.concept_name,
            concept_type=base_concept.concept_type,
            aliases=list(all_aliases),
            confidence=max(c.confidence for c in concepts),
            source_chunks=list(all_source_chunks),
            external_ids=all_external_ids
        )
        
        return merged_concept
    
    def _merge_relationships(self, relationships: List[RelationshipEdge]) -> RelationshipEdge:
        """Merge multiple relationships into one."""
        # Use the relationship with highest confidence as base
        base_relationship = max(relationships, key=lambda r: r.confidence)
        
        # Merge evidence chunks
        all_evidence_chunks = set(base_relationship.evidence_chunks)
        for relationship in relationships:
            all_evidence_chunks.update(relationship.evidence_chunks)
        
        # Create merged relationship
        merged_relationship = RelationshipEdge(
            subject_concept=base_relationship.subject_concept,
            predicate=base_relationship.predicate,
            object_concept=base_relationship.object_concept,
            confidence=max(r.confidence for r in relationships),
            evidence_chunks=list(all_evidence_chunks),
            relationship_type=base_relationship.relationship_type,
            bidirectional=any(r.bidirectional for r in relationships)
        )
        
        return merged_relationship
    
    def _is_relationship_consistent(self, relationship: RelationshipEdge, 
                                  all_relationships: List[RelationshipEdge]) -> bool:
        """Check if a relationship is consistent with others."""
        # Check for contradictory relationships
        for other in all_relationships:
            if other == relationship:
                continue
            
            # Check for direct contradictions (A -> B vs B -> A with conflicting predicates)
            if (relationship.subject_concept == other.object_concept and
                relationship.object_concept == other.subject_concept):
                
                # Some predicates are naturally bidirectional
                if self._are_predicates_compatible(relationship.predicate, other.predicate):
                    continue
                else:
                    return False
        
        return True
    
    def _are_predicates_compatible(self, predicate1: str, predicate2: str) -> bool:
        """Check if two predicates are compatible."""
        compatible_pairs = {
            ('IS_A', 'PART_OF'),
            ('RELATED_TO', 'SIMILAR_TO'),
            ('CAUSES', 'RELATED_TO')
        }
        
        pair = tuple(sorted([predicate1, predicate2]))
        return pair in compatible_pairs


class UserFeedbackIntegrator:
    """Integrates user feedback to refine knowledge graph."""
    
    def __init__(self):
        self.feedback_history = {}
        
    def process_user_feedback(self, feedback_data: Dict[str, Any]) -> None:
        """Process user feedback about knowledge graph elements."""
        try:
            feedback_id = str(uuid.uuid4())
            feedback_type = feedback_data.get('type')  # 'concept', 'relationship', 'query_result'
            element_id = feedback_data.get('element_id')
            feedback_score = feedback_data.get('score', 0.0)  # -1.0 to 1.0
            user_id = feedback_data.get('user_id')
            timestamp = datetime.now()
            
            # Store feedback
            self.feedback_history[feedback_id] = {
                'type': feedback_type,
                'element_id': element_id,
                'score': feedback_score,
                'user_id': user_id,
                'timestamp': timestamp,
                'processed': False
            }
            
            logger.info(f"Received user feedback: {feedback_type} for {element_id} with score {feedback_score}")
            
        except Exception as e:
            logger.error(f"Error processing user feedback: {e}")
    
    def apply_feedback_to_concepts(self, concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Apply user feedback to adjust concept confidence scores."""
        try:
            updated_concepts = []
            
            for concept in concepts:
                # Find relevant feedback
                concept_feedback = self._get_feedback_for_element(concept.concept_id, 'concept')
                
                if concept_feedback:
                    # Adjust confidence based on feedback
                    adjusted_confidence = self._calculate_adjusted_confidence(
                        concept.confidence, concept_feedback
                    )
                    
                    # Create updated concept
                    updated_concept = ConceptNode(
                        concept_id=concept.concept_id,
                        concept_name=concept.concept_name,
                        concept_type=concept.concept_type,
                        aliases=concept.aliases,
                        confidence=adjusted_confidence,
                        source_chunks=concept.source_chunks,
                        external_ids=concept.external_ids
                    )
                    updated_concepts.append(updated_concept)
                else:
                    updated_concepts.append(concept)
            
            logger.info(f"Applied feedback to {len(updated_concepts)} concepts")
            return updated_concepts
            
        except Exception as e:
            logger.error(f"Error applying feedback to concepts: {e}")
            return concepts
    
    def apply_feedback_to_relationships(self, relationships: List[RelationshipEdge]) -> List[RelationshipEdge]:
        """Apply user feedback to adjust relationship confidence scores."""
        try:
            updated_relationships = []
            
            for relationship in relationships:
                # Find relevant feedback
                relationship_key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
                relationship_feedback = self._get_feedback_for_element(relationship_key, 'relationship')
                
                if relationship_feedback:
                    # Adjust confidence based on feedback
                    adjusted_confidence = self._calculate_adjusted_confidence(
                        relationship.confidence, relationship_feedback
                    )
                    
                    # Create updated relationship
                    updated_relationship = RelationshipEdge(
                        subject_concept=relationship.subject_concept,
                        predicate=relationship.predicate,
                        object_concept=relationship.object_concept,
                        confidence=adjusted_confidence,
                        evidence_chunks=relationship.evidence_chunks,
                        relationship_type=relationship.relationship_type,
                        bidirectional=relationship.bidirectional
                    )
                    updated_relationships.append(updated_relationship)
                else:
                    updated_relationships.append(relationship)
            
            logger.info(f"Applied feedback to {len(updated_relationships)} relationships")
            return updated_relationships
            
        except Exception as e:
            logger.error(f"Error applying feedback to relationships: {e}")
            return relationships
    
    def get_feedback_summary(self) -> Dict[str, Any]:
        """Get summary of user feedback."""
        try:
            total_feedback = len(self.feedback_history)
            feedback_by_type = {}
            feedback_by_score = {'positive': 0, 'negative': 0, 'neutral': 0}
            
            for feedback in self.feedback_history.values():
                # Count by type
                feedback_type = feedback['type']
                feedback_by_type[feedback_type] = feedback_by_type.get(feedback_type, 0) + 1
                
                # Count by score
                score = feedback['score']
                if score > 0.1:
                    feedback_by_score['positive'] += 1
                elif score < -0.1:
                    feedback_by_score['negative'] += 1
                else:
                    feedback_by_score['neutral'] += 1
            
            return {
                'total_feedback': total_feedback,
                'feedback_by_type': feedback_by_type,
                'feedback_by_score': feedback_by_score,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting feedback summary: {e}")
            return {}
    
    def _get_feedback_for_element(self, element_id: str, element_type: str) -> List[Dict]:
        """Get all feedback for a specific element."""
        relevant_feedback = []
        
        for feedback in self.feedback_history.values():
            if feedback['type'] == element_type and feedback['element_id'] == element_id:
                relevant_feedback.append(feedback)
        
        return relevant_feedback
    
    def _calculate_adjusted_confidence(self, original_confidence: float, 
                                     feedback_list: List[Dict]) -> float:
        """Calculate adjusted confidence based on user feedback."""
        if not feedback_list:
            return original_confidence
        
        # Calculate weighted average of feedback scores
        total_weight = 0
        weighted_sum = 0
        
        for feedback in feedback_list:
            # Weight recent feedback more heavily
            age_days = (datetime.now() - feedback['timestamp']).days
            weight = max(0.1, 1.0 - (age_days / 30.0))  # Decay over 30 days
            
            total_weight += weight
            weighted_sum += feedback['score'] * weight
        
        if total_weight == 0:
            return original_confidence
        
        avg_feedback = weighted_sum / total_weight
        
        # Adjust confidence: positive feedback increases, negative decreases
        adjustment = avg_feedback * 0.2  # Max adjustment of ±0.2
        adjusted_confidence = original_confidence + adjustment
        
        # Clamp to valid range
        return max(0.0, min(1.0, adjusted_confidence))


class KnowledgeGraphManager:
    """Main knowledge graph management component."""
    
    def __init__(self, kg_builder: KnowledgeGraphBuilder):
        self.kg_builder = kg_builder
        self.bootstrapper = ExternalKnowledgeBootstrapper()
        self.conflict_resolver = ConflictResolver()
        self.feedback_integrator = UserFeedbackIntegrator()
        
        logger.info("Knowledge Graph Manager initialized")
    
    def bootstrap_knowledge_graph(self, domains: List[str]) -> None:
        """Bootstrap knowledge graph from external sources."""
        try:
            logger.info(f"Bootstrapping knowledge graph for domains: {domains}")
            
            # Bootstrap from ConceptNet
            conceptnet_concepts, conceptnet_relationships = self.bootstrapper.bootstrap_from_conceptnet(domains)
            
            # Bootstrap from YAGO
            yago_concepts, yago_relationships = self.bootstrapper.bootstrap_from_yago(domains)
            
            # Combine all concepts and relationships
            all_concepts = conceptnet_concepts + yago_concepts
            all_relationships = conceptnet_relationships + yago_relationships
            
            # Resolve conflicts
            resolved_concepts = self.conflict_resolver.resolve_concept_conflicts(all_concepts)
            resolved_relationships = self.conflict_resolver.resolve_relationship_conflicts(all_relationships)
            
            # Validate consistency
            validated_relationships = self.conflict_resolver.validate_relationship_consistency(resolved_relationships)
            
            # Update knowledge graph
            self.kg_builder._update_knowledge_graph(resolved_concepts, validated_relationships)
            
            logger.info(f"Successfully bootstrapped knowledge graph with {len(resolved_concepts)} concepts and {len(validated_relationships)} relationships")
            
        except Exception as e:
            logger.error(f"Error bootstrapping knowledge graph: {e}")
    
    def build_incremental_kg(self, new_chunks: List[KnowledgeChunk]) -> None:
        """Add knowledge from new chunks to existing graph."""
        try:
            logger.info(f"Building incremental knowledge graph from {len(new_chunks)} chunks")
            
            all_new_concepts = []
            all_new_relationships = []
            
            # Process each chunk
            for chunk in new_chunks:
                extraction = self.kg_builder.process_knowledge_chunk(chunk)
                all_new_concepts.extend(extraction.extracted_concepts)
                all_new_relationships.extend(extraction.extracted_relationships)
            
            # Apply user feedback
            feedback_adjusted_concepts = self.feedback_integrator.apply_feedback_to_concepts(all_new_concepts)
            feedback_adjusted_relationships = self.feedback_integrator.apply_feedback_to_relationships(all_new_relationships)
            
            # Resolve conflicts with existing knowledge
            existing_concepts = list(self.kg_builder.concepts.values())
            existing_relationships = list(self.kg_builder.relationships.values())
            
            combined_concepts = existing_concepts + feedback_adjusted_concepts
            combined_relationships = existing_relationships + feedback_adjusted_relationships
            
            resolved_concepts = self.conflict_resolver.resolve_concept_conflicts(combined_concepts)
            resolved_relationships = self.conflict_resolver.resolve_relationship_conflicts(combined_relationships)
            
            # Update knowledge graph
            self.kg_builder.concepts.clear()
            self.kg_builder.relationships.clear()
            self.kg_builder._update_knowledge_graph(resolved_concepts, resolved_relationships)
            
            logger.info(f"Successfully updated knowledge graph incrementally")
            
        except Exception as e:
            logger.error(f"Error building incremental knowledge graph: {e}")
    
    def process_user_feedback(self, feedback_data: Dict[str, Any]) -> None:
        """Process user feedback for knowledge graph refinement."""
        try:
            self.feedback_integrator.process_user_feedback(feedback_data)
            
            # Optionally trigger immediate re-evaluation of affected elements
            if feedback_data.get('immediate_update', False):
                self._apply_immediate_feedback_update(feedback_data)
            
        except Exception as e:
            logger.error(f"Error processing user feedback: {e}")
    
    def get_knowledge_graph_health(self) -> Dict[str, Any]:
        """Get health metrics for the knowledge graph."""
        try:
            stats = self.kg_builder.get_knowledge_graph_stats()
            feedback_summary = self.feedback_integrator.get_feedback_summary()
            
            # Calculate health metrics
            concept_coverage = len(self.kg_builder.concepts) / max(1, len(self.kg_builder.extractions))
            relationship_density = len(self.kg_builder.relationships) / max(1, len(self.kg_builder.concepts))
            
            health_metrics = {
                'total_concepts': stats.total_concepts,
                'total_relationships': stats.total_relationships,
                'average_confidence': stats.average_confidence,
                'concept_coverage': concept_coverage,
                'relationship_density': relationship_density,
                'feedback_summary': feedback_summary,
                'last_updated': stats.last_updated.isoformat()
            }
            
            return health_metrics
            
        except Exception as e:
            logger.error(f"Error getting knowledge graph health: {e}")
            return {}
    
    def _apply_immediate_feedback_update(self, feedback_data: Dict[str, Any]) -> None:
        """Apply immediate feedback update to knowledge graph."""
        try:
            element_type = feedback_data.get('type')
            element_id = feedback_data.get('element_id')
            
            if element_type == 'concept' and element_id in self.kg_builder.concepts:
                # Update concept confidence
                concept = self.kg_builder.concepts[element_id]
                feedback_list = self.feedback_integrator._get_feedback_for_element(element_id, 'concept')
                adjusted_confidence = self.feedback_integrator._calculate_adjusted_confidence(
                    concept.confidence, feedback_list
                )
                concept.confidence = adjusted_confidence
                
            elif element_type == 'relationship':
                # Update relationship confidence
                for rel_key, relationship in self.kg_builder.relationships.items():
                    if rel_key == element_id:
                        feedback_list = self.feedback_integrator._get_feedback_for_element(element_id, 'relationship')
                        adjusted_confidence = self.feedback_integrator._calculate_adjusted_confidence(
                            relationship.confidence, feedback_list
                        )
                        relationship.confidence = adjusted_confidence
                        break
            
            logger.info(f"Applied immediate feedback update for {element_type} {element_id}")
            
        except Exception as e:
            logger.error(f"Error applying immediate feedback update: {e}")
    
    async def get_document_concepts(self, document_id: str) -> List[Dict[str, Any]]:
        """Get concepts extracted from a specific document."""
        try:
            document_concepts = []
            
            # Find concepts that have source chunks from this document
            for concept in self.kg_builder.concepts.values():
                # Check if any source chunks belong to this document
                document_chunks = [
                    chunk_id for chunk_id in concept.source_chunks 
                    if chunk_id.startswith(document_id)
                ]
                
                if document_chunks:
                    document_concepts.append({
                        "id": concept.concept_id,
                        "name": concept.concept_name,
                        "type": concept.concept_type,
                        "confidence": concept.confidence,
                        "aliases": concept.aliases,
                        "source_chunks": document_chunks
                    })
            
            logger.info(f"Found {len(document_concepts)} concepts for document {document_id}")
            return document_concepts
            
        except Exception as e:
            logger.error(f"Error getting document concepts: {e}")
            return []
    
    async def get_document_relationships(self, document_id: str) -> List[Dict[str, Any]]:
        """Get relationships extracted from a specific document."""
        try:
            document_relationships = []
            
            # Find relationships that have evidence chunks from this document
            for relationship in self.kg_builder.relationships.values():
                # Check if any evidence chunks belong to this document
                document_chunks = [
                    chunk_id for chunk_id in relationship.evidence_chunks 
                    if chunk_id.startswith(document_id)
                ]
                
                if document_chunks:
                    document_relationships.append({
                        "subject": relationship.subject_concept,
                        "predicate": relationship.predicate,
                        "object": relationship.object_concept,
                        "type": relationship.relationship_type.value if hasattr(relationship.relationship_type, 'value') else str(relationship.relationship_type),
                        "confidence": relationship.confidence,
                        "bidirectional": relationship.bidirectional,
                        "evidence_chunks": document_chunks
                    })
            
            logger.info(f"Found {len(document_relationships)} relationships for document {document_id}")
            return document_relationships
            
        except Exception as e:
            logger.error(f"Error getting document relationships: {e}")
            return []
    
    async def get_similar_documents_by_concepts(self, document_id: str, limit: int = 5) -> List[Tuple[str, float]]:
        """Find documents similar to the given document based on shared concepts."""
        try:
            # Get concepts from the source document
            source_concepts = await self.get_document_concepts(document_id)
            source_concept_ids = set(concept["id"] for concept in source_concepts)
            
            if not source_concept_ids:
                return []
            
            # Find other documents that share concepts
            document_similarities = {}
            
            for concept in self.kg_builder.concepts.values():
                if concept.concept_id in source_concept_ids:
                    # Find other documents that have this concept
                    for chunk_id in concept.source_chunks:
                        # Extract document ID from chunk ID (assuming format: document_id_chunk_index)
                        parts = chunk_id.split('_')
                        if len(parts) >= 2:
                            other_doc_id = '_'.join(parts[:-1])  # Everything except the last part
                            
                            if other_doc_id != document_id:
                                if other_doc_id not in document_similarities:
                                    document_similarities[other_doc_id] = 0.0
                                
                                # Add weighted similarity based on concept confidence
                                document_similarities[other_doc_id] += concept.confidence
            
            # Normalize similarities and sort
            if document_similarities:
                max_similarity = max(document_similarities.values())
                normalized_similarities = [
                    (doc_id, similarity / max_similarity)
                    for doc_id, similarity in document_similarities.items()
                ]
                
                # Sort by similarity and return top results
                sorted_similarities = sorted(normalized_similarities, key=lambda x: x[1], reverse=True)
                return sorted_similarities[:limit]
            
            return []
            
        except Exception as e:
            logger.error(f"Error finding similar documents: {e}")
            return []