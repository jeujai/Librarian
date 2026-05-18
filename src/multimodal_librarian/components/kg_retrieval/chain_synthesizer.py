"""
Chain Synthesizer for UMLS clinical reasoning paths.

Converts raw UMLS path annotations from RelationshipTraverser into a
human-readable clinical reasoning gloss consumed by the LLM prompt.

Requirements: 6.5 (clinical reasoning path synthesis)
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Maximum number of gloss sentences to include in the prompt.
_MAX_GLOSS_SENTENCES = 6


class ChainSynthesizer:
    """Synthesizes clinical reasoning glosses from UMLS path annotations.

    Reads path_annotations collected by RelationshipTraverser and produces
    a concise summary of clinical relationships between query concepts,
    formatted for injection into the LLM system prompt as
    "KNOWLEDGE GRAPH INSIGHTS".
    """

    def __init__(self):
        logger.debug("ChainSynthesizer initialized")

    def synthesize(
        self,
        path_annotations: List[Dict[str, Any]],
        concept_id_to_name: Dict[str, str],
    ) -> str:
        """Synthesize a clinical reasoning gloss from UMLS path annotations.

        Args:
            path_annotations: List of annotation dicts from
                RelationshipTraverser. Each has keys: source_concept_a,
                source_concept_b, umls_source, relationship, umls_target,
                path_type, and optionally chunk_id.
            concept_id_to_name: Mapping from concept_id to human-readable
                concept name (from concept_matches).

        Returns:
            Formatted clinical reasoning gloss string, or empty string if
            no annotations are available.
        """
        if not path_annotations:
            return ""

        # Group annotations by concept pair, keeping only UMLS paths.
        pair_annotations: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for ann in path_annotations:
            if not ann.get("umls_source"):
                continue
            cid_a = ann.get("source_concept_a", "")
            cid_b = ann.get("source_concept_b", "")
            pair_key = _pair_key(cid_a, cid_b)
            pair_annotations[pair_key].append(ann)

        if not pair_annotations:
            return ""

        # Build one-sentence gloss per concept pair.
        gloss_lines: List[str] = []
        for pair_key, annotations in pair_annotations.items():
            name_a, name_b = _pair_names(
                pair_key, concept_id_to_name
            )
            sentence = self._synthesize_pair_gloss(
                name_a, name_b, annotations
            )
            if sentence:
                gloss_lines.append(sentence)

        if not gloss_lines:
            return ""

        # Limit to avoid bloating the prompt.
        gloss_lines = gloss_lines[:_MAX_GLOSS_SENTENCES]

        return "Clinical reasoning paths found between query concepts:\n" + "\n".join(
            f"- {line}" for line in gloss_lines
        )

    def _synthesize_pair_gloss(
        self,
        name_a: str,
        name_b: str,
        annotations: List[Dict[str, Any]],
    ) -> str:
        """Synthesize a one-sentence gloss for a single concept pair.

        For 1-hop paths, produces: "X relationship Y"
        For 2-hop paths, produces: "X relationship (via intermediate → target)"
        """
        umls_paths: List[str] = []
        seen = set()

        for ann in annotations:
            path_type = ann.get("path_type", "")
            if path_type not in ("umls_1hop", "umls_2hop"):
                continue

            umls_source = ann.get("umls_source", "")
            relationship = ann.get("relationship", "")
            umls_target = ann.get("umls_target", "")

            if not umls_source or not relationship or not umls_target:
                continue

            if path_type == "umls_1hop":
                text = f"{umls_source} {_readable_rela(relationship)} {umls_target}"
            else:
                # 2-hop: relationship is "rela1→rela2", umls_target is "mid→target"
                rel_parts = relationship.split("→")
                target_parts = umls_target.split("→")
                if len(rel_parts) == 2 and len(target_parts) == 2:
                    text = (
                        f"{umls_source} {_readable_rela(rel_parts[0])} "
                        f"{target_parts[0]}, which {_readable_rela(rel_parts[1])} "
                        f"{target_parts[1]}"
                    )
                else:
                    text = f"{umls_source} {_readable_rela(relationship)} {umls_target}"

            dedup_key = text
            if dedup_key not in seen:
                seen.add(dedup_key)
                umls_paths.append(text)

        if not umls_paths:
            return ""

        subject = f"{name_a} ↔ {name_b}"
        if len(umls_paths) == 1:
            return f"{subject}: {umls_paths[0]}"
        else:
            joined = "; ".join(umls_paths[:3])
            return f"{subject}: {joined}"


def _readable_rela(rela: str) -> str:
    """Convert UMLS rela_type to a human-readable phrase."""
    readable = {
        "isa": "is a type of",
        "inverse_isa": "is a parent of",
        "may_treat": "may treat",
        "may_be_treated_by": "may be treated by",
        "may_be_prevented_by": "may be prevented by",
        "may_prevent": "may prevent",
        "cause_of": "causes",
        "due_to": "is due to",
        "has_manifestation": "presents with",
        "manifestation_of": "is a manifestation of",
        "has_definitional_manifestation": "is defined by",
        "has_associated_finding": "is associated with",
        "associated_finding_of": "is a finding of",
        "finding_site_of": "is the site of",
        "has_finding_site": "is found at",
        "has_component": "contains",
        "component_of": "is a component of",
        "occurs_after": "occurs after",
        "occurs_before": "occurs before",
        "has_clinical_course": "has clinical course",
        "has_severity": "has severity",
        "has_stage": "has stage",
        "has_method": "uses method",
        "has_mechanism_of_action": "acts via",
        "has_therapeutic_class": "belongs to class",
        "has_physiologic_effect": "has physiologic effect",
        "may_diagnose": "may diagnose",
        "may_be_diagnosed_by": "may be diagnosed by",
        "has_causative_agent": "is caused by agent",
        "has_pharmacokinetics": "has pharmacokinetics",
        "has_procedure_site": "is performed at",
        "has_direct_procedure_site": "is directly performed at",
        "has_focus": "focuses on",
        "focus_of": "is the focus of",
    }
    return readable.get(rela, rela.replace("_", " "))


def _pair_key(cid_a: str, cid_b: str) -> str:
    """Create a stable, order-independent key for a concept pair."""
    return "||".join(sorted([cid_a, cid_b]))


def _pair_names(
    pair_key: str, concept_id_to_name: Dict[str, str]
) -> tuple:
    """Resolve a pair key back to human-readable concept names."""
    ids = pair_key.split("||")
    name_a = concept_id_to_name.get(ids[0], ids[0].rsplit("_", 1)[-1])
    name_b = concept_id_to_name.get(ids[1], ids[1].rsplit("_", 1)[-1])
    return name_a, name_b
