"""Data models for YAGO entities."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FilteredEntity:
    """Entity filtered from YAGO dump with English data only."""
    entity_id: str  # e.g., "Q42"
    label: Optional[str]  # English label
    description: Optional[str]  # English description
    instance_of: List[str]  # P31 target IDs
    subclass_of: List[str]  # P279 target IDs
    aliases: List[str]  # Alias labels
    see_also: List[str]  # See also IDs


@dataclass
class YagoEntityData:
    """YAGO entity data for enrichment queries."""
    entity_id: str
    label: str
    description: Optional[str] = None
    instance_of: List[str] = field(default_factory=list)
    subclass_of: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    confidence: float = 1.0  # Local data has full confidence

    @classmethod
    def from_filtered_entity(cls, entity: FilteredEntity) -> "YagoEntityData":
        """Create from filtered entity."""
        return cls(
            entity_id=entity.entity_id,
            label=entity.label or "",
            description=entity.description,
            instance_of=entity.instance_of,
            subclass_of=entity.subclass_of,
            aliases=entity.aliases,
        )


@dataclass
class YagoSearchResult:
    """Search result for fuzzy lookup."""
    entity_id: str
    label: str
    description: Optional[str]
    score: float = 1.0