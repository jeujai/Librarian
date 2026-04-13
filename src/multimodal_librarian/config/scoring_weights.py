"""Shared scoring weights for KG vs bridge/semantic contributions.

These weights express how much KG-based results (NER + LLM concept
extraction) contribute to final query quality relative to bridge
generation and semantic similarity.  They are used in:

- **Quality gate** (`services/quality_gate.py`): composite failure
  rate = max(NER, LLM) × KG_WEIGHT + bridge × BRIDGE_WEIGHT
- **Semantic reranker** (`kg_retrieval/semantic_reranker.py`): final
  score = kg_score × KG_WEIGHT + semantic_score × SEMANTIC_WEIGHT

When the balance changes (e.g. bridges become more important), update
the values here and both paths stay in sync.
"""

import os

_DEFAULT_KG_WEIGHT = 0.7
_DEFAULT_BRIDGE_WEIGHT = 0.3


def _load_weight(env_var: str, default: float) -> float:
    val = os.environ.get(env_var)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            pass
    return default


KG_WEIGHT: float = _load_weight("SCORING_KG_WEIGHT", _DEFAULT_KG_WEIGHT)
BRIDGE_WEIGHT: float = _load_weight(
    "SCORING_BRIDGE_WEIGHT", _DEFAULT_BRIDGE_WEIGHT
)
