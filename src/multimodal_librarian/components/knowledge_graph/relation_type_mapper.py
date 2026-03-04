"""Centralized mapping from ConceptNet relation types to internal taxonomy."""

from typing import Dict

from multimodal_librarian.models.core import RelationshipType


class RelationTypeMapper:
    """Centralized mapping from ConceptNet relation types to internal taxonomy.

    A stateless utility class. No constructor dependencies.
    Can be imported and used anywhere without DI concerns.
    """

    _CAUSAL: frozenset = frozenset({
        "causes", "hasprerequisite", "motivatedbygoal", "causesdesire",
        "entails", "hassubevent", "hasfirstsubevent", "haslastsubevent",
    })

    _HIERARCHICAL: frozenset = frozenset({
        "isa", "partof", "hasa", "instanceof", "mannerof",
        "madeof", "definedas", "formof",
    })

    @classmethod
    def classify(cls, raw_relation_type: str) -> RelationshipType:
        """Classify a ConceptNet relation type into the internal taxonomy.

        Case-insensitive. Unknown types default to ASSOCIATIVE.
        """
        key = raw_relation_type.lower()
        if key in cls._CAUSAL:
            return RelationshipType.CAUSAL
        if key in cls._HIERARCHICAL:
            return RelationshipType.HIERARCHICAL
        return RelationshipType.ASSOCIATIVE

    @classmethod
    def get_known_types(cls) -> Dict[str, RelationshipType]:
        """Return the full mapping dictionary for inspection/testing."""
        result: Dict[str, RelationshipType] = {}
        for t in cls._CAUSAL:
            result[t] = RelationshipType.CAUSAL
        for t in cls._HIERARCHICAL:
            result[t] = RelationshipType.HIERARCHICAL
        return result
