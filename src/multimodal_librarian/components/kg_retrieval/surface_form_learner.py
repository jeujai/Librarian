"""Corpus-derived surface-form learning (paraphrase case).

Pure, I/O-free helpers + prompt templates for the two-stage pipeline described
in ``.kiro/specs/corpus-derived-surface-forms/design.md``:

1. **Propose** — an LLM proposes candidate surface forms for a concept name,
   first from the bare name, then re-seeded with real corpus passages (the
   bootstrap loop) so the corpus — not a hand-written template — supplies the
   domain idioms (e.g. ``category III`` for ``practice restrictions``).

2. **Select** — candidates are validated against the corpus: a candidate
   survives only if it (a) is a well-formed noun phrase (not a clause or a
   dangling fragment), (b) appears in the corpus, (c) co-occurs with the
   concept's semantic anchor *in the same sentence* (not merely the same
   chunk), and (d) clears a cross-encoder precision threshold.

The abstraction case (a name that never appears in the corpus in its intended
sense) is *not* handled here — it is a concept-level ``SIMILAR_TO`` link, see
``.kiro/specs/abstraction-concept-resolution/design.md``.
"""

import json
import re
from typing import Dict, Iterable, List, Optional

# --- Select-stage thresholds (tunable via env in the consuming script) ---
DEFAULT_COOCCUR_THRESHOLD = 0.4
DEFAULT_MIN_SCORE = 0.505

# --- Co-occurrence anchors by semantic type ---
#
# Anchors are a *type-scoped* lexicon, not a per-concept list.  A candidate
# surface form is kept only if it co-occurs in the same sentence as one of
# these anchor terms — this is what separates "category III" (72% co-occur
# with restriction language) from "category I/II" (0-18%) and from
# co-located-but-unrelated phrases like "safer devices".
#
# Anchors must be the type's *co-text* (the distinctive language that
# surrounds a mention), NOT synonyms of the concept name.  A name-synonym
# anchor is self-confirming: "guideline" as an anchor is a substring of the
# candidate "asthma management guidelines", so it can never reject a
# paraphrase of "management guidelines".  That is why PROCESS anchors are
# application/execution co-text ("follow", "step", "algorithm") rather than
# "guideline"/"protocol"/"manage".
TYPE_ANCHORS: Dict[str, List[str]] = {
    "RESTRICTION": [
        "restrict", "prohibit", "exclud", "should not", "must not",
        "not perform", "refrain", "barred", "exposure-prone", "exposure prone",
    ],
    "PROCESS": [
        "hcp", "healthcare personnel", "health care worker", "healthcare worker",
        "follow", "implement", "perform", "step", "algorithm", "recommend",
    ],
    "PROCEDURE": [
        "procedure", "perform", "exposure-prone", "exposure prone", "surgical",
    ],
    "ENTITY": [
        "patient", "healthcare", "health care", "worker", "personnel", "infected",
    ],
}

# --- LLM proposal prompts ---
BARE_PROPOSE_TEMPLATE = (
    'A concept named "{concept}" ({ctype}) exists in a knowledge graph. '
    "List up to 10 short noun phrases a medical guideline document would LITERALLY use "
    "to name this concept (noun phrases only, not clauses or verb phrases). "
    "Return ONLY a JSON array of strings, no commentary."
)

CONTEXT_PROPOSE_TEMPLATE = (
    'A concept named "{concept}" ({ctype}) exists. Here are sample passages from '
    "the corpus where related language appears:\n"
    '"""\n{context}\n"""\n'
    "List up to 10 short noun phrases these or similar passages use to name "
    '"{concept}" (noun phrases only, not clauses or verb phrases), including any '
    'category designations (e.g. "category III"). '
    "Return ONLY a JSON array of strings, no commentary."
)

# Line-break hyphenation ("exposure-\nprone") is a PDF-extraction artifact that
# otherwise breaks anchor matching across a wrapped line.
_HYPHEN_BREAK_RE = re.compile(r"-\s*\n\s*")

# Split a passage into sentences for the same-sentence co-occurrence gate.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# Shape gate: a surface form is a noun phrase, not a clause or fragment.  Two
# targeted rejections cover the malformed outputs the proposal LLM otherwise
# emits when it quotes corpus passages verbatim — fragments that dangle a
# function word, and verb phrases that open with a finite verb.
_TRAILING_FUNCTION_WORDS = frozenset({
    "of", "the", "a", "an", "for", "in", "to", "with", "and", "or",
    "by", "at", "on", "into", "from",
})

_LEADING_VERBS = frozenset({
    "prevent", "avoid", "adhere", "follow", "perform", "refrain", "exclude",
    "prohibit", "restrict", "ensure", "require", "reduce", "limit", "protect",
    "screen", "monitor", "isolate", "treat", "test", "manage", "implement",
    "maintain", "evaluate", "assess", "recommend",
})


def normalize_text(text: str) -> str:
    """Lowercase and collapse line-break hyphenation (drop the break, keep the hyphen)."""
    return _HYPHEN_BREAK_RE.sub("-", (text or "").lower())


def anchors_for(concept_type: Optional[str], name: str) -> List[str]:
    """Return the co-occurrence anchors for a concept.

    Derived from the concept's semantic type; falls back to the name's own
    content words for unknown types.
    """
    t = (concept_type or "").strip().upper()
    anchors = list(TYPE_ANCHORS.get(t, []))
    if not anchors:
        for token in re.findall(r"[a-z]+", (name or "").lower()):
            if len(token) > 3 and token not in anchors:
                anchors.append(token)
    return anchors


def cooccur_in_same_sentence(text: str, candidate: str, anchors: Iterable[str]) -> bool:
    """True if ``candidate`` and any anchor appear in the same sentence."""
    cand = normalize_text(candidate)
    if not cand:
        return False
    # Normalize the whole passage first so line-break hyphenation is collapsed
    # *before* the newline-aware sentence splitter runs; otherwise "exposure-\n
    # prone" is split into two sentences and the joined anchor never matches.
    anchors = [normalize_text(a) for a in anchors]
    normalized = normalize_text(text)
    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        sent = normalize_text(sentence)
        if cand in sent and any(a in sent for a in anchors):
            return True
    return False


def cooccur_rate(chunks: Iterable[str], candidate: str, anchors: Iterable[str]) -> float:
    """Fraction of chunks where ``candidate`` co-occurs (same sentence) with an anchor."""
    chunks = list(chunks)
    if not chunks:
        return 0.0
    hits = sum(1 for c in chunks if cooccur_in_same_sentence(c, candidate, anchors))
    return hits / len(chunks)


def parse_json_list(text: str) -> List[str]:
    """Parse an LLM JSON-array-of-strings response, tolerating code fences.

    Returns an empty list on any malformed/truncated response.
    """
    if not text:
        return []
    cleaned = re.sub(r"```[a-zA-Z]*", "", text).strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        arr = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [s.strip() for s in arr if isinstance(s, str) and s.strip()]


def is_valid_surface_form(candidate: str) -> bool:
    """True if ``candidate`` is a well-formed noun phrase, not a clause/fragment.

    Rejects a dangling trailing function word ("guidelines for the management
    of") and a leading finite verb ("prevent spread of illness").  These are the
    two shapes the proposal LLM produces when it quotes a passage verbatim
    instead of naming the concept.
    """
    words = normalize_text(candidate).split()
    if not words:
        return False
    if words[-1] in _TRAILING_FUNCTION_WORDS:
        return False
    if words[0] in _LEADING_VERBS:
        return False
    return True


def evaluate_candidates(
    candidates: Iterable[str],
    anchors: Iterable[str],
    chunks_by_candidate: Dict[str, List[str]],
    score_by_candidate: Dict[str, float],
    min_score: float = DEFAULT_MIN_SCORE,
    cooccur_threshold: float = DEFAULT_COOCCUR_THRESHOLD,
) -> List[str]:
    """Select surviving surface forms from LLM-proposed candidates.

    A candidate survives iff:
      1. it is a well-formed noun phrase (not a clause or dangling fragment),
      2. it appears in the corpus (non-empty chunk list),
      3. it co-occurs with an anchor in the same sentence at or above
         ``cooccur_threshold``, and
      4. its cross-encoder score clears ``min_score``.

    This is the corpus-grounding gate that filters the LLM's over-generation.
    """
    survivors: List[str] = []
    for candidate in candidates:
        if not is_valid_surface_form(candidate):
            continue
        chunks = chunks_by_candidate.get(candidate, [])
        if not chunks:
            continue
        if cooccur_rate(chunks, candidate, anchors) < cooccur_threshold:
            continue
        if score_by_candidate.get(candidate, 0.0) < min_score:
            continue
        survivors.append(candidate)
    return survivors
