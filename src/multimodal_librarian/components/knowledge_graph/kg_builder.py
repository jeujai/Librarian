"""
Knowledge Graph Builder Component.

This component extracts concepts and relationships from all content types,
builds incremental knowledge graphs, and manages knowledge graph construction.
"""

import asyncio
import json
import logging
import math
import re
import threading
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ...config import get_settings
from ...models.core import ContentType, KnowledgeChunk, RelationshipType
from ...models.knowledge_graph import (
    ConceptExtraction,
    ConceptNode,
    KnowledgeGraphStats,
    RelationshipEdge,
    Triple,
)
from .relation_type_mapper import RelationTypeMapper

logger = logging.getLogger(__name__)

# Thread-local storage for reusing event loops in pool worker threads
_kg_thread_local = threading.local()

# Thread pool for CPU-bound embedding operations
_kg_executor: Optional[ThreadPoolExecutor] = None


def _get_kg_executor() -> ThreadPoolExecutor:
    """Get or create the KG thread pool executor for CPU-bound operations."""
    global _kg_executor
    if _kg_executor is None:
        _kg_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="kg_embedding"
        )
        logger.info("Created KG embedding thread pool executor")
    return _kg_executor


# ---------------------------------------------------------------------------
# Domain Prompt Registry & Prompt Template for LLM-based concept extraction
# ---------------------------------------------------------------------------

DOMAIN_PROMPT_REGISTRY: Dict[ContentType, Dict[str, Any]] = {
    ContentType.TECHNICAL: {
        "domain_description": "technical documentation",
        "concept_types": ["API", "PROTOCOL", "ALGORITHM", "DATA_STRUCTURE", "FRAMEWORK", "DESIGN_PATTERN"],
    },
    ContentType.MEDICAL: {
        "domain_description": "medical/clinical content",
        "concept_types": [
            "DISEASE", "DRUG", "PROCEDURE", "ANATOMY", "LAB_TEST", "GENE", "PATHWAY",
            "GUIDELINE", "POLICY", "PROTOCOL", "PRECAUTION", "RESTRICTION",
            "RECOMMENDATION", "EXPOSURE_RISK", "TRANSMISSION_PRECAUTION",
            "OCCUPATIONAL_HEALTH", "SCREENING", "VACCINATION", "TREATMENT_REGIMEN",
        ],
    },
    ContentType.LEGAL: {
        "domain_description": "legal content",
        "concept_types": ["STATUTE", "CASE_NAME", "DOCTRINE", "PARTY", "JURISDICTION", "REGULATORY_BODY"],
    },
    ContentType.ACADEMIC: {
        "domain_description": "academic/research content",
        "concept_types": ["THEORY", "METHODOLOGY", "RESEARCHER", "INSTITUTION", "DATASET", "METRIC"],
    },
    ContentType.NARRATIVE: {
        "domain_description": "narrative content",
        "concept_types": ["CHARACTER", "LOCATION", "EVENT", "THEME", "TIME_PERIOD"],
    },
    ContentType.GENERAL: {
        "domain_description": "general content",
        "concept_types": ["ENTITY", "TOPIC", "ORGANIZATION", "PERSON", "LOCATION"],
    },
}

CONCEPT_EXTRACTION_PROMPT_TEMPLATE = """Extract key concepts from the following {domain_description}.
Valid concept types: {concept_types}

Return ONLY a JSON array. No explanation, no markdown, no extra text.
Each element must have "name" and "type" fields.

IMPORTANT: Extract multi-word compound terms as single concepts.
Prefer specific phrases over individual words (e.g., "work restrictions" not "work" + "restrictions").

Example output:
[{{"name": "hepatitis B surface antigen", "type": "LAB_TEST"}},
 {{"name": "work restrictions", "type": "RESTRICTION"}},
 {{"name": "postexposure prophylaxis", "type": "PROTOCOL"}}]

Only extract terms explicitly mentioned in the text.

Text:
{text}

JSON:"""


# Curated medical multi-word seed for the MULTI_WORD regex pattern.
#
# The regex concept source otherwise has zero medical coverage (its seed is
# software/ML vocabulary), so the synchronous chunking path's boundary
# contiguity check would rely entirely on spaCy to keep a clinical compound
# like "hepatitis B surface antigen" whole.  scispacy can split such phrases
# (or spaCy may be unavailable), so this narrow, unambiguous seed guarantees
# the high-value compounds are protected regardless.  Kept as an alternation
# with inline pluralisation (``s?`` / ``(?:y|ies)``) so both "pathogen" and
# "pathogens" match.
_MEDICAL_MULTI_WORD_SEED = (
    # Viral hepatitis / lab markers
    r"hepatitis B surface antigens?",
    r"hepatitis B surface antibod(?:y|ies)",
    r"hepatitis B core antibod(?:y|ies)",
    r"hepatitis B e antigens?",
    r"hepatitis B e antibod(?:y|ies)",
    r"hepatitis B virus",
    r"hepatitis C virus",
    r"hepatitis B vaccination",
    r"hepatitis B vaccines?",
    r"liver function tests?",
    # Bloodborne pathogens / exposure
    r"bloodborne pathogens?",
    r"occupational exposures?",
    r"needlestick injur(?:y|ies)",
    r"percutaneous exposures?",
    r"mucous membrane exposures?",
    r"source patients?",
    r"post-exposure prophylaxis",
    r"postexposure prophylaxis",
    # Infection control / precautions
    r"standard precautions?",
    r"infection control",
    r"hand hygiene",
    r"personal protective equipment",
    r"exposure-prone procedures?",
    # Personnel / restrictions / guidelines
    r"healthcare personnel",
    r"health care personnel",
    r"healthcare workers?",
    r"health care workers?",
    r"work restrictions?",
    r"management guidelines?",
    # Treatment modalities / regimens (general — co-linking anchors, not tied
    # to any one drug class).  These guarantee the high-value multi-word
    # therapy/regimen compounds stay whole; the co-linking pass links any such
    # concept to the agents it includes via the generic dose pass.
    r"first-line therapy",
    r"initial empiric therapy",
    r"empiric therapy",
    r"definitive therapy",
    r"adjuvant therapy",
    r"neoadjuvant therapy",
    r"maintenance therapy",
    r"antimicrobial therapy",
    r"antiviral therapy",
    r"antifungal therapy",
    r"immunosuppressive therapy",
    r"combination therapy",
    r"chemotherapy regimen",
    r"treatment regimen",
    r"therapeutic regimen",
    r"monotherapy",
    r"empiric treatment",
)


# --- Bottom-up drug + dose composition patterns -----------------------------
# A dose looks like "<number><unit>" optionally " / <number><unit>" (combined
# drugs: amoxicillin/clavulanate 500 mg/125 mg), followed by an optional
# frequency tail ("three times daily", "twice daily", "every 8 h", "daily").
# The drug is a single token (may contain '/', '-', '+' internally) and MUST
# already exist as an extracted concept — the composition pass is
# self-anchoring, so it never mints compounds from non-drug words ("the 2 g").
_DOSE_NUMBER = r"\d+(?:[.,–-]\d+)?"
_DOSE_UNIT = r"(?:mcg|µg|ug|mg|g|kg|mL|ml|units?|IU|mEq|mmol)"
_DOSE_VALUE = (
    rf"{_DOSE_NUMBER}\s*{_DOSE_UNIT}"
    rf"(?:\s*/\s*{_DOSE_NUMBER}\s*{_DOSE_UNIT})?"
)
_DOSE_FREQ_TOKEN = (
    r"(?:once|twice|three times|four times|daily|hourly|weekly|monthly"
    r"|every\s+(?:\d+\s*)?(?:hours?|hrs?|h|days?|weeks?)|bid|tid|qid"
    r"|\d+\s*(?:hours?|hrs?|h)?"
    # Timing / duration qualifiers (loading doses, treatment courses).  These
    # preserve the temporal scoping that distinguishes a first-day loading dose
    # ("500 mg on first day") from a maintenance dose, and a finite course
    # ("for 5 days") from an indefinite one.  Generic — no drug-class tokens.
    r"|on\s+(?:the\s+)?(?:(?:first|1st)\s+day|day\s+\d+)"
    r"|for\s+\d+(?:\s*[-–]\s*\d+)?\s+(?:days?|weeks?|months?)"
    r"|days?\s+\d+(?:\s*[-–]\s*\d+)?)"
)

# Route-of-administration tokens.  A route word between the dose and the
# frequency ("500 mg orally three times daily", "1 g IV every 24 h") would
# otherwise break the schedule tail and drop the frequency.  Routes are
# overwhelmingly "-ly" adverbs (orally, intravenously, subcutaneously,
# intraperitoneally, epidurally, ...), so a catch-all ``[a-z]+ly`` covers the
# long tail in addition to the explicit terms below.  Class-agnostic
# (antibiotic, antiviral, oncologic alike).  Trade-off: the catch-all also
# admits rare prose adverbs ("typically", "usually") into the tail — accepted,
# since the frequency is preserved at the cost of a stray adverb in the name.
_DOSE_ROUTE_TOKEN = (
    r"(?:orally|oral|by\s+mouth|per\s+os|p\.?o\.?"
    r"|intravenously|intravenous|i\.?v\.?"
    r"|intramuscularly|intramuscular|i\.?m\.?"
    r"|subcutaneously|subcutaneous|subq|sub-q|s\.?c\.?|s\.?q\.?"
    r"|topically|topical|transdermally|transdermal"
    r"|sublingually|sublingual|s\.?l\.?"
    r"|buccally|buccal"
    r"|intranasally|intranasal"
    r"|inhaled|inhalation|nebulized|nebulised"
    r"|rectally|rectal|vaginally|vaginal"
    r"|intrathecally|intrathecal"
    r"|intra-articular|intraarticular"
    r"|[a-z]+ly\b)"
)

# Combined dose-tail token: frequency/timing OR route.  The schedule tail can
# interleave route, frequency, and duration qualifiers ("orally three times
# daily for 5 days").
_DOSE_SCHEDULE_TOKEN = rf"(?:{_DOSE_FREQ_TOKEN}|{_DOSE_ROUTE_TOKEN})"
_DOSE_SPAN = re.compile(
    rf"(?P<drug>[A-Za-z][A-Za-z0-9/+\-]*)[,\s]+"
    rf"(?P<dose>{_DOSE_VALUE})"
    rf"(?P<freq>(?:\s+{_DOSE_SCHEDULE_TOKEN}){{1,4}})?",
    re.IGNORECASE,
)

# Dose-only pattern (no drug prefix) for the multi-word-drug backward scan.
# Anchors on the dose itself; the drug is recovered by looking backward past a
# short formulation/salt modifier ("extended release", "succinate").
_DOSE_ONLY_PATTERN = re.compile(
    rf"(?P<dose>{_DOSE_VALUE})(?P<freq>(?:\s+{_DOSE_SCHEDULE_TOKEN}){{1,4}})?",
    re.IGNORECASE,
)

# Chained-dose continuation: "azithromycin 500 mg on first day then 250 mg
# daily".  The primary _DOSE_SPAN captures only the first dose; the second dose
# follows a connector ("then"/"and then"/"followed by") and would otherwise be
# dropped (its "drug" token is the connector word, which fails self-anchoring).
# This pattern matches the orphan dose+tail so a second pass can attribute it
# back to the nearest preceding drug that the primary pass anchored on.
_CHAINED_DOSE_PATTERN = re.compile(
    rf"\b(?:and\s+then|followed\s+by|then)\b\s+"
    rf"(?P<dose>{_DOSE_VALUE})"
    rf"(?P<freq>(?:\s+{_DOSE_SCHEDULE_TOKEN}){{1,4}})?",
    re.IGNORECASE,
)

# Treatment-modality nouns for co-linking.  Identifies a concept as a
# therapy/regimen/treatment node (the thing to link FROM) regardless of drug
# class — antibiotic, antiviral, antifungal, oncologic, or immunosuppressive.
# The agent side of the link comes from the generic dose pass (HAS_DOSE
# subjects), never from a hardcoded drug-name list, so the co-linking stays
# class-agnostic.
_TREATMENT_PATTERN = re.compile(
    r"\b(?:therapy|therapies|regimen|regimens|treatment|treatments"
    r"|prophylaxis|chemotherapy|immunotherapy)\b",
    re.IGNORECASE,
)

# Coarse POS tags that a drug→dose gap token may carry and still be part of the
# drug's identity (a salt or formulation).  Everything else in the gap is prose
# ("is usually", "given as") and is dropped.  Content-word whitelist rather than
# a stopword blacklist, so it can never leak a function word into a compound.
_KEEP_POS = frozenset({"NOUN", "PROPN", "ADJ"})

# POS tags that a drug *agent* may carry.  Narrower than _KEEP_POS: a drug
# name is a noun/proper-noun, never an adjective or adverb, so function-word
# concepts ("the", "then", "daily") — which still exist in the corpus-mined
# concept set — are rejected as agents while "amoxicillin" (NOUN) and
# "Azithromycin" (PROPN) pass.
_AGENT_POS = frozenset({"NOUN", "PROPN"})


def _token_pos_spans(text: str, pos_tags: Optional[List[dict]]) -> Optional[List[Tuple[int, int, str]]]:
    """Reconstruct ``(start, end, coarse_pos)`` spans for POS-tagged tokens.

    The model server returns spaCy tokens in order with a coarse ``pos`` but no
    character offsets.  Walk ``text`` with a forward cursor, matching each token
    in order, to recover offsets.  Returns ``None`` on any mismatch so callers
    can degrade gracefully (and never guess a wrong POS).
    """
    if not pos_tags:
        return None
    spans: List[Tuple[int, int, str]] = []
    cursor = 0
    for t in pos_tags:
        token = (t.get("token") or "").strip()
        if not token:
            continue
        idx = text.find(token, cursor)
        if idx == -1:
            return None
        pos = (t.get("pos") or "").upper()
        spans.append((idx, idx + len(token), pos))
        cursor = idx + len(token)
    return spans


def _span_has_agent_pos(
    start: int, end: int, token_spans: Optional[List[Tuple[int, int, str]]]
) -> bool:
    """Whether the text span overlaps a NOUN/PROPN token (a drug agent).

    Gates drug→dose composition on the *agent* being a real content word.
    Function-word concepts ("the", "then", "daily") still exist in the
    corpus-mined concept set and would otherwise leak into compounds
    ("the 2007 g", "then 250 mg daily").  When POS is unavailable
    (``token_spans is None``) the gate degrades to accepting, since the
    caller cannot distinguish and must not over-filter.
    """
    if token_spans is None:
        return True
    for ts, te, pos in token_spans:
        if ts < end and te > start and pos in _AGENT_POS:
            return True
    return False


class ConceptExtractor:
    """Extracts concepts from text using multiple methods."""
    
    def __init__(self):
        self.settings = get_settings()
        self._embedding_model = None  # Lazy loaded (local fallback only)
        self._model_server_client = None  # Model server client (preferred)
        self._model_lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
        
        # Curated concept patterns (regex-only extraction)
        # ENTITY, PROCESS, PROPERTY patterns removed — replaced by spaCy NER
        self.concept_patterns = {
            'CODE_TERM': [
                r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b',                    # snake_case: allow_dangerous_code, max_retries
                r'\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\b',               # camelCase: getData, processDocument
                r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b',                       # PascalCase: ConnectionManager, DataProcessor
                r'\b[a-zA-Z_][a-zA-Z0-9_]*=[A-Za-z0-9_]+\b',             # param assignment: allowed_dangerous_code=True
                r'\b[a-zA-Z_][a-zA-Z0-9_]*\(\)',                           # function calls: process_document(), getData()
                r'\b[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*){1,4}\b',         # dotted: os.path.join, config.settings
            ],
            'MULTI_WORD': [
                r'\b(?:knowledge graph|vector database|natural language processing|'
                r'machine learning|deep learning|neural network|'
                r'information retrieval|semantic search|named entity recognition|'
                r'text embedding|content analysis|concept extraction|'
                r'graph database|search engine|data model|'
                r'chunk(?:ing)?\s+(?:strategy|framework|pipeline|size)|'
                r'retrieval\s+(?:quality|pipeline|service|augmented)|'
                r'embedding\s+(?:model|dimension|space|vector))\b',
                r'\b(?:' + '|'.join(_MEDICAL_MULTI_WORD_SEED) + r')\b',
            ],
            'ACRONYM': [
                r'\b[A-Z]{2,6}\b',
            ],
        }
        
        # Acronym stopword filter — common short English words that match the ACRONYM pattern
        self._acronym_stopwords = {
            "IT", "IS", "OR", "AN", "AT", "IF", "IN", "ON", "TO", "UP",
            "DO", "GO", "NO", "SO", "BY", "HE", "ME", "WE", "US", "AM",
            "BE", "OF", "AS",
        }
        
        # Lazy-initialized OllamaClient (no import-time connection)
        self._ollama_client = None  # Optional[OllamaClient]

        # UMLS client for n-gram clinical term lookup during extraction.
        # Set via set_umls_client() after construction (UMLS client is
        # created after KnowledgeGraphBuilder in _update_knowledge_graph).
        self._umls_client = None  # Optional[UMLSClient]
        
        # Corpus-level collocation frequency cache.
        # Keyed by normalized bigram string (e.g. "knowledge_graph"), storing:
        #   frequency: cumulative count across all documents
        #   doc_count: number of documents the bigram appeared in
        self._collocation_cache: Dict[str, Dict[str, int]] = {}

        # DeepSeek fallback for concept extraction (lazy init)
        self._deepseek_service = None
        self._deepseek_initialized = False

        # Provider statistics for observability
        self._concept_provider_stats = {
            'ollama_success': 0,
            'deepseek_fallback': 0,
            'both_failed': 0,
        }
    
    async def _get_ollama_client(self):
        """Get or initialize the Ollama client (lazy, cached).

        Follows the same lazy-init pattern as
        ``SmartBridgeGenerator._get_ollama_client`` — the import and
        availability check happen on first call only.  Returns ``None``
        when Ollama is unreachable so callers can degrade gracefully.

        Caches negative results via ``_ollama_checked`` sentinel to avoid
        re-checking availability on every chunk when Ollama is down.
        """
        if self._ollama_client is not None:
            return self._ollama_client

        # Already checked and found unavailable — skip re-check
        if getattr(self, '_ollama_checked', False):
            return None

        try:
            from ...clients.ollama_client import get_ollama_client

            client = get_ollama_client()
            if await client.is_available():
                self._ollama_client = client
                return client
            else:
                logger.warning("Ollama not available, LLM concept extraction will be skipped")
                self._ollama_checked = True
                return None
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama client: {e}")
            self._ollama_checked = True
            return None

    def set_umls_client(self, umls_client) -> None:
        """Set the UMLS client for n-gram clinical term lookup.

        Must be called before extract_all_concepts_async() if UMLS-based
        clinical term extraction is desired.  Degrades gracefully when
        not set (extract_concepts_umls_ngrams returns empty).
        """
        self._umls_client = umls_client

    # ------------------------------------------------------------------
    # DeepSeek lazy initialization for concept extraction fallback
    # ------------------------------------------------------------------

    def _ensure_deepseek(self):
        """Lazily initialize DeepSeek for concept extraction fallback.

        Sets ``_deepseek_initialized`` to ``True`` even on failure to avoid
        re-attempting initialization on every call.  Returns the service, or
        ``None`` when DeepSeek is unavailable (no API key, etc.).
        """
        if self._deepseek_initialized:
            return self._deepseek_service
        self._deepseek_initialized = True

        try:
            from ...services.deepseek_ai_service import DeepSeekAIService

            self._deepseek_service = DeepSeekAIService()
            logger.info("Initialized DeepSeek for KG concept extraction fallback (lazy init)")
        except Exception as e:
            logger.warning(f"DeepSeek init failed for concept extraction: {e}")
            self._deepseek_service = None

        return self._deepseek_service

    async def _extract_concepts_deepseek(
        self, text: str, prompt: str
    ) -> List[Dict]:
        """Extract concepts via DeepSeek (fallback from Ollama).

        Uses the same prompt and JSON parsing as the Ollama path.
        Returns ``[]`` if DeepSeek is unavailable or fails.
        """
        service = self._ensure_deepseek()
        if service is None:
            return []

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You extract key concepts from text and return them as a "
                        "JSON array of objects with 'name' and 'type' fields. "
                        "Return ONLY the JSON array, no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            response = await service.generate_response(
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )

            if not response.content or response.confidence_score <= 0:
                logger.debug("DeepSeek returned empty response for concept extraction")
                return []

            entries = self._extract_json_array(response.content)
            if entries is None:
                logger.debug(
                    "DeepSeek returned unparseable response (first 300 chars): %.300s",
                    response.content,
                )
                return []

            return entries  # Return raw dicts; caller builds ConceptNodes
        except Exception as e:
            logger.warning("DeepSeek concept extraction failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Shared prompt builder
    # ------------------------------------------------------------------

    def _build_concept_prompt(
        self, text: str, content_type: ContentType
    ) -> str:
        """Build the domain-aware concept extraction prompt.

        Shared by both Ollama and DeepSeek code paths so the same prompt
        template is used regardless of provider.
        """
        config = DOMAIN_PROMPT_REGISTRY[content_type]
        return CONCEPT_EXTRACTION_PROMPT_TEMPLATE.format(
            domain_description=config["domain_description"],
            concept_types=", ".join(config["concept_types"]),
            text=text[:2000],
        )

    # ------------------------------------------------------------------
    # LLM-based concept extraction (Ollama)
    # ------------------------------------------------------------------

    async def extract_concepts_ollama(
        self, text: str, content_type: ContentType = ContentType.GENERAL
    ) -> Tuple[List[ConceptNode], bool]:
        """Extract concepts via the local Ollama LLM, with DeepSeek fallback.

        Sends a domain-aware prompt to Ollama, parses the JSON response,
        and returns ConceptNodes with domain-aware confidence scores.
        If Ollama fails, falls back to DeepSeek using the same prompt.

        Returns ``(concepts, llm_failed)`` where ``llm_failed=True`` when
        both Ollama and DeepSeek fail.
        """
        # Build shared prompt (used by both Ollama and DeepSeek)
        prompt = self._build_concept_prompt(text, content_type)

        # Domain-aware confidence
        if content_type in (ContentType.MEDICAL, ContentType.LEGAL):
            base_confidence = 0.65
        else:
            base_confidence = 0.70

        # --- Try Ollama first ---
        grounded = await self._try_ollama_extraction(text, prompt)

        if grounded is not None:
            self._concept_provider_stats['ollama_success'] += 1
            return (self._build_concept_nodes(grounded, base_confidence), False)

        # --- Ollama failed, fall back to DeepSeek ---
        logger.info("Ollama concept extraction failed, falling back to DeepSeek")
        deepseek_grounded = await self._extract_concepts_deepseek(text, prompt)

        if deepseek_grounded:
            self._concept_provider_stats['deepseek_fallback'] += 1
            return (self._build_concept_nodes(deepseek_grounded, base_confidence), False)

        # Both failed
        self._concept_provider_stats['both_failed'] += 1
        return ([], True)

    async def _try_ollama_extraction(
        self, text: str, prompt: str
    ) -> Optional[List[Dict]]:
        """Attempt concept extraction via Ollama.

        Submits only the Ollama HTTP call through the shared pool
        (task_type="kg") for fair share scheduling with bridge
        generation.  All other work (JSON parsing) stays on the
        caller's event loop.

        Returns a list of grounded candidate dicts on success,
        an empty list when Ollama responded but produced no usable
        concepts (unparseable JSON, empty content), or ``None``
        only on infrastructure failures (pool exhausted, connection
        error, timeout).
        """
        try:
            # Check availability first (cached negative result avoids
            # repeated checks when Ollama is down).
            if getattr(self, '_ollama_checked', False):
                return None

            from ...services.ollama_pool_manager import (
                PoolExhaustedError,
                submit_ollama_work,
            )

            def _ollama_sync():
                import asyncio as _aio

                from ...clients.ollama_client import get_ollama_client

                # Reuse a per-thread event loop AND a per-thread
                # Ollama client.  The httpx AsyncClient inside the
                # Ollama client binds its internal asyncio primitives
                # (locks, events) to the loop that created it.
                # Creating the client on the SAME loop that will
                # run_until_complete avoids "bound to a different
                # event loop" errors.
                loop = getattr(_kg_thread_local, 'event_loop', None)
                if loop is None or loop.is_closed():
                    loop = _aio.new_event_loop()
                    _kg_thread_local.event_loop = loop
                    # Force a new client for the new loop
                    _kg_thread_local.ollama_client = None

                client = getattr(_kg_thread_local, 'ollama_client', None)
                if client is None:
                    client = get_ollama_client()
                    _kg_thread_local.ollama_client = client

                return loop.run_until_complete(
                    client.generate(prompt, temperature=0.2, max_tokens=1500)
                )

            try:
                future = submit_ollama_work(
                    _ollama_sync,
                    task_type="kg",
                )
                response = future.result(timeout=120)
            except PoolExhaustedError:
                logger.warning("Ollama pool exhausted for KG extraction")
                return None
            except Exception as pool_err:
                logger.warning("Ollama pool call failed: %s", pool_err)
                return None

            if not response.is_successful():
                logger.warning("Ollama concept extraction failed: %s", response.error)
                return []

            entries = self._extract_json_array(response.content)
            if entries is None:
                logger.debug(
                    "Ollama returned unparseable response (first 300 chars): %.300s",
                    response.content,
                )
                return []

            return entries
        except Exception as e:
            logger.warning("Unexpected error in Ollama concept extraction: %s", e)
            return None

    def _build_concept_nodes(
        self, grounded: List[Dict], base_confidence: float
    ) -> List[ConceptNode]:
        """Convert grounded candidate dicts into ConceptNode instances."""
        concepts: List[ConceptNode] = []
        for entry in grounded:
            name = entry.get("name", "")
            ctype = entry.get("type", "")
            if not name or not ctype:
                continue
            normalized = self._normalize_concept_name(name)
            concept = ConceptNode(
                concept_id=f"public:{name.lower()}",
                concept_name=name,
                concept_type=ctype,
                confidence=base_confidence,
                source_chunks=[],
            )
            concepts.append(concept)

        logger.info("Extracted %d concepts via LLM", len(concepts))
        return concepts

    @property
    def concept_provider_stats(self) -> Dict[str, int]:
        """Expose provider statistics for observability."""
        return dict(self._concept_provider_stats)

    @staticmethod
    def _extract_json_array(text: str) -> Optional[List[Dict]]:
        """Robustly extract a JSON array from LLM output.

        Handles common issues with small models:
        - Markdown code fences (```json ... ```)
        - Leading/trailing prose around the JSON
        - Truncated arrays (attempts to close them)

        Returns the parsed list or ``None`` if extraction fails.
        """
        raw = text.strip()

        # Strip markdown fences
        if "```" in raw:
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
            if fence_match:
                raw = fence_match.group(1).strip()

        # Try direct parse first
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # Find the first '[' and try to parse from there
        bracket_pos = raw.find("[")
        if bracket_pos == -1:
            return None

        candidate = raw[bracket_pos:]

        # Try parsing as-is
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # Model may have truncated — try closing the array
        # Find the last complete object (last '}')
        last_brace = candidate.rfind("}")
        if last_brace > 0:
            truncated = candidate[: last_brace + 1] + "]"
            try:
                result = json.loads(truncated)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

        return None

    @property
    def embedding_model(self):
        """
        Embedding model property - models are served by model-server container.
        
        NOTE: Local model loading has been removed. Use generate_embeddings_async()
        which calls the model server for non-blocking operation.
        """
        logger.warning("Local embedding model not available - use generate_embeddings_async() instead")
        return None
    
    async def _get_model_server_client(self):
        """Get or initialize the model server client."""
        if self._model_server_client is not None:
            return self._model_server_client

        try:
            from ...clients.model_server_client import (
                ModelServerClient,
                get_model_client,
                initialize_model_client,
            )
            
            client = get_model_client()
            if client is None:
                try:
                    await initialize_model_client()
                    client = get_model_client()
                except Exception:
                    pass
            
            if client is None or not client.enabled:
                import os
                url = os.environ.get('MODEL_SERVER_URL', 'http://model-server:8001')
                client = ModelServerClient(base_url=url)
            
            if client and client.enabled:
                self._model_server_client = client
        except Exception as e:
            logger.warning(f"Model server not available: {e}")
        return self._model_server_client
    
    async def generate_embeddings_async(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings asynchronously using model server (non-blocking).
        
        Model server is required - no local fallback.
        """
        # Try model server first
        client = await self._get_model_server_client()
        if client is not None:
            try:
                embeddings = await client.generate_embeddings(texts)
                if embeddings:
                    return np.array(embeddings)
            except Exception as e:
                logger.warning(f"Model server embedding failed: {e}")
        
        # Fallback to local model via thread pool
        executor = _get_kg_executor()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, self._encode_sync, texts)
    
    def _encode_sync(self, texts: List[str]) -> np.ndarray:
        """Synchronous encode - called in thread pool."""
        return self.embedding_model.encode(texts)
    
    def extract_concepts_regex(self, text: str) -> List[ConceptNode]:
        """Extract concepts using curated regex patterns only (MULTI_WORD, CODE_TERM, ACRONYM + PMI).

        Assigns pattern-specific confidence scores from settings:
        - MULTI_WORD (seed list): ``multi_word_seed_confidence`` (default 0.85)
        - ACRONYM: ``acronym_confidence`` (default 0.6)
        - All other types: 0.7

        Applies a frequency boost of ``frequency_boost_increment`` per
        additional occurrence, capped at ``frequency_boost_cap`` above the
        base confidence.

        After the pattern loop the method:
        1. Updates the corpus-level collocation cache.
        2. Merges PMI-discovered collocations (deduplicating by normalised name,
           keeping the higher-confidence seed match when both exist).
        3. Runs acronym-expansion alias linking.
        """
        # Read confidence settings with safe defaults
        multi_word_seed_conf = getattr(self.settings, 'multi_word_seed_confidence', 0.85)
        acronym_conf = getattr(self.settings, 'acronym_confidence', 0.6)
        freq_increment = getattr(self.settings, 'frequency_boost_increment', 0.02)
        freq_cap = getattr(self.settings, 'frequency_boost_cap', 0.1)

        concepts = []
        concept_id_map = {}
        # Track cumulative frequency boost per concept_id
        freq_boost_map: Dict[str, float] = {}

        for concept_type, patterns in self.concept_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    concept_name = match.group().strip()
                    if len(concept_name) < 3:  # Skip very short concepts
                        continue

                    # Filter ACRONYM matches against stopword set
                    if concept_type == 'ACRONYM' and concept_name.upper() in self._acronym_stopwords:
                        continue

                    # Normalize concept name
                    normalized_name = self._normalize_concept_name(concept_name)
                    concept_id = f"public:{concept_name.lower()}"

                    if concept_id not in concept_id_map:
                        # Determine base confidence by pattern type
                        if concept_type == 'MULTI_WORD':
                            base_confidence = multi_word_seed_conf
                        elif concept_type == 'ACRONYM':
                            base_confidence = acronym_conf
                        else:
                            base_confidence = 0.7  # NER confidence for other types

                        concept = ConceptNode(
                            concept_id=concept_id,
                            concept_name=concept_name,
                            concept_type=concept_type,
                            confidence=base_confidence,
                        )
                        concepts.append(concept)
                        concept_id_map[concept_id] = concept
                        freq_boost_map[concept_id] = 0.0
                    else:
                        # Repeated occurrence — apply frequency boost
                        existing_concept = concept_id_map[concept_id]
                        current_boost = freq_boost_map[concept_id]
                        if current_boost < freq_cap:
                            added = min(freq_increment, freq_cap - current_boost)
                            existing_concept.confidence += added
                            freq_boost_map[concept_id] = current_boost + added

                        # Add as alias if different surface form
                        if concept_name not in existing_concept.aliases and concept_name != existing_concept.concept_name:
                            existing_concept.add_alias(concept_name)

        # Update corpus-level collocation cache
        self._update_collocation_cache(text)

        # Merge PMI-discovered collocations, deduplicating by normalised name
        pmi_concepts = self._extract_collocations_pmi(text)
        for pmi_concept in pmi_concepts:
            normalized_name = self._normalize_concept_name(pmi_concept.concept_name)
            pmi_id = f"public:{pmi_concept.concept_name.lower()}"
            if pmi_id not in concept_id_map:
                concepts.append(pmi_concept)
                concept_id_map[pmi_id] = pmi_concept

        # Link acronym expansions (stub-safe — method may not exist yet)
        if hasattr(self, '_link_acronym_expansions'):
            self._link_acronym_expansions(text, concepts, concept_id_map)

        return concepts
    
    # Patterns that indicate a token is code, not a named entity
    # Used to filter false positives from spaCy NER
    _code_pattern_filters = [
        re.compile(r'^[a-z_][a-z0-9_]*\(\)$'),           # function calls: chelsea(), process_data()
        re.compile(r'^[a-z_][a-z0-9_]*\('),              # function with args: imread(
        re.compile(r'^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$'),  # snake_case: my_function
        re.compile(r'^[a-z]+\.[a-z]'),                    # module.attr: os.path
        re.compile(r'^\$[a-zA-Z]'),                       # shell vars: $PATH
        re.compile(r'^[a-z]+://', re.IGNORECASE),        # URLs: http://
    ]

    async def extract_concepts_with_ner(self, text: str) -> Tuple[List[ConceptNode], bool]:
        """Extract concepts using spaCy NER via model server.

        Calls ``ModelServerClient.get_entities()`` and converts each spaCy
        entity dict into a :class:`ConceptNode` with ``concept_type`` set to
        the spaCy label and ``confidence`` of 0.85.

        Filters out code-like patterns (function calls, snake_case identifiers)
        that spaCy may incorrectly tag as named entities.

        Returns ``(concepts, ner_failed)`` where ``ner_failed=True`` when the
        model server is unavailable or ``get_entities`` raises an exception.
        """
        client = await self._get_model_server_client()
        if client is None:
            logger.warning(
                "Model server unavailable, skipping NER extraction"
            )
            return ([], True)

        try:
            entity_lists = await client.get_entities([text])
        except Exception as e:
            logger.warning(f"NER extraction failed: {e}")
            return ([], True)

        concepts: List[ConceptNode] = []
        seen: set = set()
        for entity in entity_lists[0] if entity_lists else []:
            name = entity.get("text", "").strip()
            label = entity.get("label", "ENTITY")
            if not name or len(name) < 2:
                continue
            
            # Filter out code-like patterns that spaCy misidentifies as entities
            # e.g., "chelsea()" is a scikit-image test function, not a person
            is_code = False
            for pattern in self._code_pattern_filters:
                if pattern.match(name):
                    logger.debug(
                        f"Filtering NER entity '{name}' (label={label}) - matches code pattern"
                    )
                    is_code = True
                    break
            
            # Also filter lowercase single words that appear in code context
            # (e.g., "chelsea" when followed by "()" in the source text)
            if not is_code and name.islower() and ' ' not in name:
                # Check if this appears as a function call in the text
                func_call_pattern = re.compile(
                    rf'\b{re.escape(name)}\s*\(', re.IGNORECASE
                )
                if func_call_pattern.search(text):
                    logger.debug(
                        f"Filtering NER entity '{name}' (label={label}) - "
                        f"appears as function call in text"
                    )
                    is_code = True
            
            if is_code:
                continue
            
            normalized = self._normalize_concept_name(name)
            concept_id = f"public:{name.lower()}"
            if concept_id in seen:
                continue
            seen.add(concept_id)
            concepts.append(
                ConceptNode(
                    concept_id=concept_id,
                    concept_name=name,
                    concept_type=label,
                    confidence=0.85,
                )
            )
        return (concepts, False)

    async def extract_gerund_compounds(self, text: str) -> List[ConceptNode]:
        """Form gerund-as-modifier compound candidates ("lifting restrictions").

        spaCy's NER and Ollama often read a leading gerund as a verb and never
        emit the compound ("lifting restrictions" -> "lifting" + "restrictions"
        as separate concepts).  Here we parse the text *in context* and, for any
        token attached to an immediately-following noun as a modifier — a VBG
        via ``compound``/``amod``, or an NN via ``compound`` whose surface form
        is an ``-ing`` gerund (subject position, where spaCy tags the gerund as
        a plain noun) — emit the adjacent two-token span as a candidate concept
        so grounding can decompose it.  The ``-ing`` guard keeps ordinary
        noun-noun compounds (already extracted elsewhere) out of scope.

        Best-effort: returns ``[]`` when the model server is unavailable or the
        parse fails.
        """
        client = await self._get_model_server_client()
        if client is None:
            return []

        try:
            results = await client.process_nlp([text], tasks=["pos"])
        except Exception as e:
            logger.debug(f"Gerund-compound extraction failed: {e}")
            return []

        pos_tags = (results[0].get("pos_tags") or []) if results else []

        concepts: List[ConceptNode] = []
        seen: set = set()
        for i, t in enumerate(pos_tags):
            tag = (t.get("tag") or "").upper()
            dep = (t.get("dep") or "").lower()
            mod_text = (t.get("token") or "").strip()
            is_compound_modifier = (
                (tag == "VBG" and dep in ("compound", "amod"))
                or (tag == "NN" and dep == "compound" and mod_text.lower().endswith("ing"))
            )
            if not is_compound_modifier:
                continue
            head_i = t.get("head_i")
            if head_i is None or head_i != i + 1:
                continue
            head = pos_tags[head_i]
            if (head.get("pos") or "").upper() not in ("NOUN", "PROPN"):
                continue
            head_text = (head.get("token") or "").strip()
            name = f"{mod_text} {head_text}"
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            concepts.append(
                ConceptNode(
                    concept_id=f"public:{key}",
                    concept_name=name,
                    concept_type="ENTITY",
                    confidence=0.6,
                )
            )
        return concepts

    async def _synthesize_compositional_grounding(
        self,
        concepts: List[ConceptNode],
    ) -> Tuple[List[ConceptNode], List[RelationshipEdge]]:
        """Link multi-word compounds to their dependency head + modifiers.

        Emits ``HAS_HEAD``/``HAS_MODIFIER`` grounding edges to lower-granularity
        part concepts, minting missing parts with
        ``provenance="materialized-for-grounding"`` (the write path's MERGE then
        performs the public-scope-first reuse, stamping provenance only on create).

        Each compound is parsed *in isolation* (its own surface form), not from
        the surrounding sentence: spaCy mis-parses verb/noun-ambiguous compounds
        in context ("work restrictions" -> "work" as a ROOT verb), which drops the
        head/modifier split.  When the isolated parse yields no full-span noun
        chunk, the head is resolved from the dependency arcs via
        :meth:`_resolve_head_from_deps`: a bare VBG whose noun is a ``dobj`` is
        flipped to gerund-as-modifier (head = the noun), and phrases with no noun
        head ("due to") are skipped.

        Best-effort: on model-server failure or a non-noun phrase, returns empty
        lists and never blocks extraction.
        """
        multi_word = [c for c in concepts if len(c.concept_name.split()) >= 2]
        if not multi_word:
            return ([], [])

        client = await self._get_model_server_client()
        if client is None:
            return ([], [])

        try:
            results = await client.process_nlp(
                [c.concept_name for c in multi_word],
                tasks=["noun_chunks", "pos"],
            )
        except Exception as e:
            logger.debug(f"Noun-chunk extraction failed (skipping grounding): {e}")
            return ([], [])

        by_name: Dict[str, ConceptNode] = {
            c.concept_name.lower(): c for c in concepts
        }
        extra_concepts: List[ConceptNode] = []
        extra_relationships: List[RelationshipEdge] = []

        def _resolve_part(part_text: str) -> ConceptNode:
            part_key = part_text.lower()
            part = by_name.get(part_key)
            if part is None:
                part = ConceptNode(
                    concept_id=f"public:{part_key}",
                    concept_name=part_text,
                    concept_type="ENTITY",
                    confidence=0.5,
                    provenance="materialized-for-grounding",
                    scope="public",
                )
                by_name[part_key] = part
                extra_concepts.append(part)
            return part

        for concept, result in zip(multi_word, results):
            name = concept.concept_name
            chunk_list = result.get("noun_chunks") or []
            pos_tags = result.get("pos_tags") or []
            root_text = None
            modifiers: List[str] = []

            for chunk in chunk_list:
                if (chunk.get("text") or "").strip().lower() == name.lower():
                    root_text = (chunk.get("root_text") or "").strip()
                    modifiers = [
                        m.strip()
                        for m in (chunk.get("modifier_texts") or [])
                        if m.strip()
                    ]
                    break

            if not (root_text and modifiers):
                # No full-span noun chunk.  Resolve the head from the
                # dependency parse rather than a positional "final token"
                # heuristic: this recognizes gerund-as-modifier (a bare VBG
                # whose noun is a dobj) and skips non-noun phrases ("due to").
                root_text, modifiers = self._resolve_head_from_deps(pos_tags)
                if not (root_text and modifiers):
                    continue

            if not root_text or not modifiers:
                continue

            head = _resolve_part(root_text)
            seen_parts = {root_text.lower()}
            for m in modifiers:
                if m.lower() in seen_parts:
                    continue
                seen_parts.add(m.lower())
                part = _resolve_part(m)
                extra_relationships.append(
                    RelationshipEdge(
                        subject_concept=concept.concept_id,
                        predicate="HAS_MODIFIER",
                        object_concept=part.concept_id,
                        confidence=0.6,
                        relationship_type=RelationshipType.ASSOCIATIVE,
                    )
                )
            extra_relationships.append(
                RelationshipEdge(
                    subject_concept=concept.concept_id,
                    predicate="HAS_HEAD",
                    object_concept=head.concept_id,
                    confidence=0.6,
                    relationship_type=RelationshipType.ASSOCIATIVE,
                )
            )

        return (extra_concepts, extra_relationships)

    @staticmethod
    def _resolve_head_from_deps(
        pos_tags: List[Dict[str, Any]],
    ) -> Tuple[Optional[str], List[str]]:
        """Resolve a compound's head + modifiers from dependency arcs.

        spaCy parses a bare multi-word phrase in isolation and, for a
        "gerund + noun" compound ("lifting restrictions"), defaults to the
        *verb* reading: the gerund is the ROOT and the noun its ``dobj``.
        That is gerund-as-modifier, not a clause, so we flip the arc and
        promote the nominal object to head.

        Returns ``(head_text, [modifier, ...])`` or ``(None, [])`` when the
        phrase has no noun head ("due to").
        """
        if not pos_tags:
            return (None, [])

        root_idx = None
        for i, t in enumerate(pos_tags):
            if (t.get("dep") or "").upper() == "ROOT":
                root_idx = i
                break
        if root_idx is None:
            return (None, [])

        root = pos_tags[root_idx]
        root_pos = (root.get("pos") or "").upper()
        root_tag = (root.get("tag") or "").upper()

        head_idx = None
        if root_pos in ("NOUN", "PROPN"):
            head_idx = root_idx
        elif root_tag == "VBG":
            # Gerund-as-modifier: the gerund heads the (isolated) phrase and
            # takes a nominal object; promote that noun to compound head.
            for i, t in enumerate(pos_tags):
                if (t.get("pos") or "").upper() not in ("NOUN", "PROPN"):
                    continue
                if (t.get("dep") or "").lower() not in ("dobj", "obj", "iobj"):
                    continue
                if t.get("head_i") == root_idx:
                    head_idx = i
                    break
        # else: non-noun root (ADP, ADV, ...) — nothing to ground on.

        if head_idx is None:
            return (None, [])

        head_text = (pos_tags[head_idx].get("token") or "").strip()
        if not head_text:
            return (None, [])

        content_pos = {"NOUN", "PROPN", "ADJ", "VERB", "NUM"}
        modifiers = [
            (t.get("token") or "").strip()
            for i, t in enumerate(pos_tags)
            if i != head_idx and (t.get("pos") or "").upper() in content_pos
        ]
        modifiers = [m for m in modifiers if m]

        return (head_text, modifiers)

    def _compose_drug_dose_concepts(
        self,
        text: str,
        concepts: List[ConceptNode],
        pos_tags: Optional[List[dict]] = None,
        chunk_id: Optional[str] = None,
    ) -> Tuple[List[ConceptNode], List[RelationshipEdge]]:
        """Compose drug + dose compounds bottom-up (inverse of grounding).

        :meth:`_synthesize_compositional_grounding` is top-down only — it
        decomposes multi-word concepts into head/modifier parts and can never
        build compounds upward.  This pass does the reverse: it anchors on
        drug-name concepts already extracted, composes each with the dose
        phrase that immediately follows in the source text, and emits a
        compound concept ("amoxicillin 1 g three times daily") plus a
        ``HAS_DOSE`` edge from the drug to the compound.

        Self-anchoring gate: the drug token must already be an extracted
        concept (single word), so the pass never mints compounds from
        non-drug words ("the 2 g").  Callers gate this on
        ``ContentType.MEDICAL`` — a non-medical document contains no such
        patterns and would otherwise yield nothing.
        """
        by_name: Dict[str, ConceptNode] = {
            c.concept_name.lower(): c for c in concepts
        }
        # Snapshot of the original concepts (before compounds are added), used
        # by the backward-scan pass to avoid re-anchoring on just-created
        # compound nodes ("azithromycin 500 mg" → "azithromycin 500 mg 250 mg").
        original_concepts: List[ConceptNode] = list(by_name.values())
        extra_concepts: List[ConceptNode] = []
        extra_relationships: List[RelationshipEdge] = []

        def emit_compound(
            drug_display: str, drug_concept: ConceptNode, dose: str, freq: str
        ) -> None:
            """Register one drug+dose compound and its HAS_DOSE edge."""
            compound = f"{drug_display} {dose}"
            if freq:
                compound += f" {freq}"
            compound = compound.strip(" .,;:")

            if compound.lower() in by_name:
                return  # already present as a concept

            node = ConceptNode(
                concept_id=f"public:{compound.lower()}",
                concept_name=compound,
                concept_type="ENTITY",
                confidence=0.7,
                provenance="corpus-mined",
                scope="public",
            )
            if chunk_id:
                node.add_source_chunk(chunk_id)
            extra_concepts.append(node)
            by_name[compound.lower()] = node
            extra_relationships.append(RelationshipEdge(
                subject_concept=drug_concept.concept_id,
                predicate="HAS_DOSE",
                object_concept=node.concept_id,
                confidence=0.7,
                relationship_type=RelationshipType.HIERARCHICAL,
            ))

        def resolve_drug(drug_raw: str) -> Optional[ConceptNode]:
            """Map a drug token to its concept, accepting slash-separated
            combination drugs (amoxicillin/clavulanate) by anchoring on any
            known component.  General — no specific drug names hardcoded."""
            concept = by_name.get(drug_raw.lower())
            if concept is not None:
                return concept
            if "/" in drug_raw:
                for part in drug_raw.split("/"):
                    concept = by_name.get(part.strip().lower())
                    if concept is not None:
                        return concept
            return None

        # POS spans for the whole chunk.  Used to (a) gate the drug agent on
        # being a content word and (b) keep salt/formulation content words in
        # the multi-word gap while dropping function-word prose.  None when the
        # model server is unavailable → both passes degrade gracefully.
        token_spans = _token_pos_spans(text, pos_tags)

        # First pass: primary drug + dose spans (adjacent, comma-separated, or
        # slash-combination drugs).  Records each drug's span (for the chained
        # pass) and each captured dose's span (so the backward-scan pass skips
        # doses already handled, e.g. the "/clavulanate" component of a
        # combination drug).
        primary_spans: List[Tuple[int, int, ConceptNode]] = []
        primary_dose_spans: Set[Tuple[int, int]] = set()
        for match in _DOSE_SPAN.finditer(text):
            if not _span_has_agent_pos(
                match.start("drug"), match.end("drug"), token_spans
            ):
                continue  # function-word "agent" ("the", "then", "daily")
            drug_raw = match.group("drug").strip()
            drug_concept = resolve_drug(drug_raw)
            if drug_concept is None:
                continue  # self-anchoring: only compose around known drugs

            primary_spans.append((match.start(), match.end(), drug_concept))
            primary_dose_spans.add(match.span("dose"))
            emit_compound(
                drug_raw,
                drug_concept,
                match.group("dose").strip(),
                (match.group("freq") or "").strip(),
            )

        # Second pass: multi-word drug names with a short formulation/salt
        # modifier between the drug and the dose ("clarithromycin extended
        # release 1,000 mg", "metoprolol succinate 50 mg").  The primary regex
        # anchors on the token immediately before the dose (e.g. "release"),
        # which is not a known concept; here we look backward up to a bounded
        # token gap for a known original concept instead.  Fully general — no
        # hardcoded modifier vocabulary.
        _MAX_MODIFIER_GAP = 2
        concept_spans: List[Tuple[int, int, ConceptNode]] = []
        for concept in original_concepts:
            name = concept.concept_name
            for m in re.finditer(r"\b" + re.escape(name) + r"\b", text, re.IGNORECASE):
                concept_spans.append((m.end(), m.start(), concept))
        concept_spans.sort(key=lambda s: s[0])  # ascending by end position

        for dmatch in _DOSE_ONLY_PATTERN.finditer(text):
            if dmatch.span("dose") in primary_dose_spans:
                continue  # already composed by the primary pass (slash component)
            dose_start = dmatch.start()
            nearest: Optional[ConceptNode] = None
            nearest_end = -1
            nearest_start = -1
            for end, start, concept in concept_spans:
                if end > dose_start:
                    break
                nearest = concept
                nearest_end = end
                nearest_start = start
            if nearest is None:
                continue
            if not _span_has_agent_pos(nearest_start, nearest_end, token_spans):
                continue  # backward-scan landed on a function word, not a drug
            gap_tokens = [
                t for t in text[nearest_end:dose_start].split()
                if any(ch.isalnum() for ch in t)
            ]
            if len(gap_tokens) > _MAX_MODIFIER_GAP:
                continue
            # Preserve only content-word gap tokens (salt/formulation) in the
            # compound name, dropping function-word prose.  "succinate" and
            # "extended release" survive; "is usually" is filtered out, so
            # "amoxicillin is usually 500 mg" never yields a junk compound.
            kept_tokens: List[str] = []
            if token_spans is not None:
                for span_start, span_end, pos in token_spans:
                    if span_start >= nearest_end and span_end <= dose_start and pos in _KEEP_POS:
                        kept_tokens.append(text[span_start:span_end])
            drug_display = nearest.concept_name
            if kept_tokens:
                drug_display = f"{nearest.concept_name} " + " ".join(kept_tokens)
            emit_compound(
                drug_display,
                nearest,
                dmatch.group("dose").strip(),
                (dmatch.group("freq") or "").strip(),
            )

        # Third pass: chained doses ("... then 250 mg daily") attributed to
        # the nearest preceding primary drug.  Without this, the second dose of
        # "azithromycin 500 mg on first day then 250 mg daily" is shredded into
        # a noise concept and never linked to azithromycin.
        for cmatch in _CHAINED_DOSE_PATTERN.finditer(text):
            drug_concept: Optional[ConceptNode] = None
            for start, end, dc in reversed(primary_spans):
                if end <= cmatch.start():
                    drug_concept = dc
                    break
            if drug_concept is None:
                continue
            emit_compound(
                drug_concept.concept_name,
                drug_concept,
                cmatch.group("dose").strip(),
                (cmatch.group("freq") or "").strip(),
            )

        return (extra_concepts, extra_relationships)

    def _compose_treatment_links(
        self,
        concepts: List[ConceptNode],
        agent_concept_ids: Set[str],
    ) -> List[RelationshipEdge]:
        """Link therapy/regimen concepts to the agents they include.

        Generalizes "regimen co-linking": rather than hardcoding antibiotic
        names or suffixes, this pass links any treatment-modality concept
        ("empiric therapy", "chemotherapy regimen", "antiviral therapy", …) to
        the *agents* it appears alongside in the same chunk.  Agents are
        identified by the generic dose pass (``HAS_DOSE`` subjects), which
        anchors on ``agent + number+unit`` for any drug class, so antibiotic,
        antiviral, and oncologic regimens all flow through the same path.

        Self-anchoring gate: both endpoints must already be extracted concepts,
        so the pass never mints an agent from an arbitrary word.  Callers gate
        this on ``ContentType.MEDICAL``.
        """
        treatment_ids = {
            c.concept_id for c in concepts
            if _TREATMENT_PATTERN.search(c.concept_name)
        }
        if not treatment_ids:
            return []

        agent_ids = set(agent_concept_ids)
        agent_ids.difference_update(treatment_ids)

        edges: List[RelationshipEdge] = []
        for treatment_id in treatment_ids:
            for agent_id in agent_ids:
                edges.append(RelationshipEdge(
                    subject_concept=treatment_id,
                    predicate="INCLUDES",
                    object_concept=agent_id,
                    confidence=0.6,
                    relationship_type=RelationshipType.ASSOCIATIVE,
                ))
        return edges

    async def extract_concepts_umls_ngrams(
        self, text: str
    ) -> Tuple[List[ConceptNode], bool]:
        """Extract clinical terms via UMLS n-gram lookup.

        Generates all contiguous 2-to-5-grams from the text, then
        batch-looks them up in UMLS via :meth:`UMLSClient.batch_search_by_names`.
        Only n-grams that match a UMLS concept (by preferred name or synonym)
        are returned as concepts.

        Degrades gracefully: returns ``([], True)`` when the UMLS client is
        not configured or the lookup fails.

        Returns ``(concepts, umls_failed)``.
        """
        if self._umls_client is None:
            return ([], True)

        words = text.split()
        if len(words) < 2:
            return ([], True)

        # Generate all contiguous 2-to-5-grams
        candidates: List[str] = []
        max_n = min(5, len(words))
        for n in range(2, max_n + 1):
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i:i + n])
                gram = gram.strip("?.,!\"';:()[]{}").strip()
                if gram and len(gram) > 2:
                    candidates.append(gram)

        if not candidates:
            return ([], True)

        try:
            umls_map = await self._umls_client.batch_search_by_names(candidates)
        except Exception:
            logger.warning("UMLS n-gram lookup failed", exc_info=True)
            return ([], True)

        if not umls_map:
            return ([], False)

        concepts: List[ConceptNode] = []
        seen: set = set()
        for name in candidates:
            if name not in umls_map:
                continue
            normalized = self._normalize_concept_name(name)
            concept_id = f"public:{name.lower()}"
            if concept_id in seen:
                continue
            seen.add(concept_id)
            concepts.append(
                ConceptNode(
                    concept_id=concept_id,
                    concept_name=name,
                    concept_type="UMLS",
                    confidence=0.90,
                )
            )

        logger.debug(
            "UMLS n-gram extraction: %d candidates → %d concepts",
            len(candidates), len(concepts),
        )
        return (concepts, False)

    async def extract_all_concepts_async(
        self, text: str, content_type: ContentType = ContentType.GENERAL
    ) -> Tuple[List[ConceptNode], bool, bool]:
        """Combine NER + Ollama + UMLS + regex + gerund extraction and deduplicate.

        Runs :meth:`extract_concepts_with_ner`,
        :meth:`extract_concepts_ollama`, :meth:`extract_concepts_umls_ngrams`,
        and :meth:`extract_gerund_compounds` concurrently via
        ``asyncio.gather``, then :meth:`extract_concepts_regex`
        synchronously.  Deduplicates by normalized concept name,
        keeping the higher-confidence entry.

        Returns ``(concepts, ner_failed, llm_failed)`` so callers can track
        per-chunk failure flags for the quality gate.

        If the model server, Ollama, or UMLS is unavailable the respective
        method returns ``([], True)`` and the pipeline continues with the
        remaining sources.
        """
        ner_result, ollama_result, umls_result, gerund_concepts = await asyncio.gather(
            self.extract_concepts_with_ner(text),
            self.extract_concepts_ollama(text, content_type),
            self.extract_concepts_umls_ngrams(text),
            self.extract_gerund_compounds(text),
        )
        ner_concepts, ner_failed = ner_result
        ollama_concepts, llm_failed = ollama_result
        umls_concepts, _umls_failed = umls_result
        regex_concepts = self.extract_concepts_regex(text)

        # Merge: index by raw name_lower (case-normalized surface form), keep
        # higher confidence.  Identity is (name_lower, scope), not the stopword
        # slug, so distinct senses ("work restrictions" vs "restrictions for
        # work") are not over-merged.
        merged: Dict[str, ConceptNode] = {}
        for concept in ner_concepts + regex_concepts + ollama_concepts + umls_concepts + gerund_concepts:
            key = concept.concept_name.lower()
            existing = merged.get(key)
            if existing is None:
                merged[key] = concept
                continue
            if concept.confidence > existing.confidence:
                merged[key] = concept
        return (list(merged.values()), ner_failed, llm_failed)

    def extract_concepts_definition_patterns(self, text: str, chunk_id: str) -> List[ConceptNode]:
        """Extract concepts using LLM-based analysis."""
        # This would integrate with an LLM API like OpenAI GPT-4
        # For now, implementing a simplified version
        concepts = []
        
        # Extract key terms and phrases
        sentences = text.split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            
            # Look for definition patterns
            definition_patterns = [
                r'(.+?)\s+is\s+(?:a|an)\s+(.+)',
                r'(.+?)\s+refers\s+to\s+(.+)',
                r'(.+?)\s+means\s+(.+)',
                r'(.+?):\s+(.+)'
            ]
            
            for pattern in definition_patterns:
                match = re.search(pattern, sentence, re.IGNORECASE)
                if match:
                    concept_name = match.group(1).strip()
                    definition = match.group(2).strip()
                    
                    if len(concept_name) > 2 and len(definition) > 5:
                        concept_id = f"public:{concept_name.lower()}"
                        concept = ConceptNode(
                            concept_id=concept_id,
                            concept_name=concept_name,
                            concept_type="ENTITY",
                            confidence=0.8,  # LLM confidence
                            source_chunks=[chunk_id]
                        )
                        concepts.append(concept)
        
        return concepts
    
    def extract_concepts_embedding(self, text: str, chunk_id: str, 
                                 existing_concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Extract concepts using embedding-based similarity (sync version - use async when possible)."""
        if not existing_concepts:
            return []
        
        # Skip if no local embedding model (model-server-separation architecture)
        # Use extract_concepts_embedding_async for embedding-based extraction
        if self.embedding_model is None:
            logger.debug("Skipping embedding-based concept extraction - no local model (use async version)")
            return []
        
        # Generate embedding for the text - this is blocking, prefer async version
        text_embedding = self._encode_sync([text])[0]
        
        # Find similar concepts based on embeddings
        similar_concepts = []
        for concept in existing_concepts:
            # Generate embedding for concept name
            concept_embedding = self._encode_sync([concept.concept_name])[0]
            
            # Calculate similarity
            similarity = np.dot(text_embedding, concept_embedding) / (
                np.linalg.norm(text_embedding) * np.linalg.norm(concept_embedding)
            )
            
            if similarity > 0.7:  # High similarity threshold
                # Create a reference to existing concept
                referenced_concept = ConceptNode(
                    concept_id=concept.concept_id,
                    concept_name=concept.concept_name,
                    concept_type=concept.concept_type,
                    confidence=similarity,
                    source_chunks=[chunk_id]
                )
                similar_concepts.append(referenced_concept)
        
        return similar_concepts
    
    async def extract_concepts_embedding_async(self, text: str, chunk_id: str, 
                                              existing_concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Extract concepts using embedding-based similarity (async, non-blocking via model server)."""
        if not existing_concepts:
            return []
        
        try:
            # Get model server client
            model_server_client = await self._get_model_server_client()
            if model_server_client is None:
                logger.debug("Model server not available for embedding-based concept extraction")
                return []
            
            # Generate embedding for the text via model server
            text_embeddings = await model_server_client.generate_embeddings([text])
            if not text_embeddings:
                logger.warning("Failed to generate text embedding via model server")
                return []
            text_embedding = np.array(text_embeddings[0])
            
            # Find similar concepts based on embeddings
            similar_concepts = []
            concept_names = [concept.concept_name for concept in existing_concepts]
            
            # Batch encode all concept names via model server
            concept_embeddings = await model_server_client.generate_embeddings(concept_names)
            if not concept_embeddings:
                logger.warning("Failed to generate concept embeddings via model server")
                return []
            
            for concept, concept_embedding in zip(existing_concepts, concept_embeddings):
                concept_embedding = np.array(concept_embedding)
                # Calculate similarity
                similarity = np.dot(text_embedding, concept_embedding) / (
                    np.linalg.norm(text_embedding) * np.linalg.norm(concept_embedding)
                )
                
                if similarity > 0.7:  # High similarity threshold
                    # Create a reference to existing concept
                    referenced_concept = ConceptNode(
                        concept_id=concept.concept_id,
                        concept_name=concept.concept_name,
                        concept_type=concept.concept_type,
                        confidence=float(similarity),
                        source_chunks=[chunk_id]
                    )
                    similar_concepts.append(referenced_concept)
            
            return similar_concepts
            
        except Exception as e:
            logger.warning(f"Error in embedding-based concept extraction: {e}")
            return []
    
    def _normalize_concept_name(self, name: str) -> str:
        """Normalize concept name for ID generation."""
        # Remove articles and common words
        stop_words = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with'}
        words = name.lower().split()
        filtered_words = [word for word in words if word not in stop_words]
        return '_'.join(filtered_words)

    def _update_collocation_cache(self, text: str) -> None:
        """
        Update the corpus-level collocation frequency cache with bigrams from *text*.

        Each call represents one document.  For every unique bigram in the text
        we increment ``doc_count`` by 1 and add the bigram's occurrence count to
        ``frequency``.

        Args:
            text: The full document (or chunk) text to analyse.
        """
        words = text.lower().split()
        if len(words) < 2:
            return

        bigram_freq = Counter(zip(words, words[1:]))
        seen_bigrams: Set[str] = set()

        for (w1, w2), count in bigram_freq.items():
            key = f"{w1}_{w2}"
            if key not in self._collocation_cache:
                self._collocation_cache[key] = {"frequency": 0, "doc_count": 0}
            self._collocation_cache[key]["frequency"] += count
            if key not in seen_bigrams:
                self._collocation_cache[key]["doc_count"] += 1
                seen_bigrams.add(key)

    # Stopwords for PMI collocation filtering
    _pmi_stopwords = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "and", "or", "but", "if",
        "then", "than", "that", "this", "these", "those", "for", "from",
        "with", "into", "of", "to", "in", "on", "at", "by", "as", "not", "no",
    })

    def _extract_collocations_pmi(self, text: str) -> List[ConceptNode]:
        """
        Extract multi-word concepts via Pointwise Mutual Information.

        PMI(x,y) = log2(P(x,y) / (P(x) * P(y)))

        A PMI threshold of 5.0 means the bigram co-occurs ~32x more often
        than expected by chance. This is a conservative threshold that
        filters most noise while catching genuine collocations.

        When the corpus-level collocation cache has entries, PMI is computed
        using corpus-level frequencies for improved accuracy.  For the first
        document (empty cache) the method falls back to document-level PMI.

        Args:
            text: The chunk text to analyze.

        Returns:
            List of ConceptNode objects for bigrams exceeding the PMI threshold.
        """
        words = text.lower().split()
        if len(words) < 10:
            return []  # too short for meaningful statistics

        pmi_threshold = getattr(self.settings, 'pmi_threshold', 5.0)
        base_confidence = getattr(self.settings, 'multi_word_pmi_confidence', 0.65)

        use_corpus = bool(self._collocation_cache)

        if use_corpus:
            # Corpus-level PMI: aggregate frequencies from the cache
            corpus_total = sum(
                entry["frequency"] for entry in self._collocation_cache.values()
            )
            # Build corpus-level unigram frequencies from cached bigrams
            corpus_word_freq: Counter = Counter()
            for key, entry in self._collocation_cache.items():
                w1, w2 = key.split("_", 1)
                corpus_word_freq[w1] += entry["frequency"]
                corpus_word_freq[w2] += entry["frequency"]
        else:
            corpus_total = 0
            corpus_word_freq = Counter()

        # Document-level frequencies (always needed for occurrence count check)
        word_freq = Counter(words)
        bigrams = list(zip(words, words[1:]))
        bigram_freq = Counter(bigrams)
        total = len(words)

        concepts = []
        for (w1, w2), count in bigram_freq.items():
            if count < 2:
                continue  # require at least 2 occurrences
            if w1 in self._pmi_stopwords or w2 in self._pmi_stopwords:
                continue  # skip stopword bigrams

            if use_corpus:
                cache_key = f"{w1}_{w2}"
                cached = self._collocation_cache.get(cache_key)
                if cached and corpus_total > 0:
                    p_xy = cached["frequency"] / corpus_total
                    p_x = corpus_word_freq.get(w1, 1) / (2 * corpus_total)
                    p_y = corpus_word_freq.get(w2, 1) / (2 * corpus_total)
                else:
                    # Bigram not in cache yet — fall back to document-level
                    p_xy = count / total
                    p_x = word_freq[w1] / total
                    p_y = word_freq[w2] / total
            else:
                # No cache — pure document-level PMI
                p_xy = count / total
                p_x = word_freq[w1] / total
                p_y = word_freq[w2] / total

            if p_x * p_y == 0:
                continue  # avoid division by zero

            pmi = math.log2(p_xy / (p_x * p_y))

            if pmi >= pmi_threshold:
                phrase = f"{w1} {w2}"
                confidence = base_confidence + min(0.1, (count - 2) * 0.02)
                normalized = self._normalize_concept_name(phrase)
                concept_id = f"public:{phrase.lower()}"

                concepts.append(ConceptNode(
                    concept_id=concept_id,
                    concept_name=phrase,
                    concept_type="MULTI_WORD",
                    confidence=confidence,
                    source_chunks=[],
                ))

        return concepts

    def _link_acronym_expansions(
        self,
        text: str,
        concepts: List[ConceptNode],
        concept_id_map: Dict[str, ConceptNode],
    ) -> None:
        """Link acronyms to their expanded forms as aliases.

        Detects patterns like ``"Expanded Form (ACRONYM)"`` and
        ``"ACRONYM (Expanded Form)"`` and links matching concepts
        via ``add_alias``.
        """
        # Pattern 1: "Expanded Form (ACRONYM)" — e.g. "Natural Language Processing (NLP)"
        expansion_first = re.finditer(
            r'([A-Z][a-z]+(?:\s+[A-Za-z]+)*)\s*\(([A-Z]{2,6})\)',
            text,
        )
        # Pattern 2: "ACRONYM (Expanded Form)" — e.g. "NLP (Natural Language Processing)"
        acronym_first = re.finditer(
            r'([A-Z]{2,6})\s*\(([A-Z][a-z]+(?:\s+[A-Za-z]+)*)\)',
            text,
        )

        pairs: List[tuple] = []  # (acronym_text, expansion_text)
        for m in expansion_first:
            pairs.append((m.group(2), m.group(1)))
        for m in acronym_first:
            pairs.append((m.group(1), m.group(2)))

        for acronym_text, expansion_text in pairs:
            # Skip stopword acronyms
            if acronym_text.upper() in self._acronym_stopwords:
                continue

            # Look up both forms by derived surrogate (public:<name_lower>)
            acronym_concept = concept_id_map.get(f"public:{acronym_text.lower()}")
            expansion_concept = concept_id_map.get(f"public:{expansion_text.lower()}")

            if acronym_concept is not None:
                acronym_concept.add_alias(expansion_text)
            if expansion_concept is not None:
                expansion_concept.add_alias(acronym_text)

    def _extract_cross_references(
        self, text: str, chunk_id: str
    ) -> list:
        """Extract explicit cross-reference patterns from chunk text.

        Returns list of CrossReference instances.

        Requirements: 5.1
        """
        from multimodal_librarian.models.kg_retrieval import CrossReference

        ref_patterns = [
            (
                r'(?:see|refer\s+to)\s+'
                r'(section|chapter|page|figure|table)'
                r'\s+(\d+(?:\.\d+)*)',
                'explicit',
            ),
            (
                r'as\s+(?:mentioned|discussed|shown|described)'
                r'\s+in\s+(section|chapter|page|figure|table)'
                r'\s+(\d+(?:\.\d+)*)',
                'backward',
            ),
            (
                r'(section|chapter|page|figure|table)'
                r'\s+(\d+(?:\.\d+)*)'
                r'\s+(?:above|below|earlier|later)',
                'positional',
            ),
        ]

        references: list = []
        for pattern, ref_type in ref_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                references.append(CrossReference(
                    source_chunk_id=chunk_id,
                    reference_type=ref_type,
                    target_type=match.group(1).lower(),
                    target_label=match.group(2),
                    raw_text=match.group(0),
                ))
        return references





class RelationshipExtractor:
    """Extracts relationships between concepts."""
    
    def __init__(self):
        self.settings = get_settings()
        
        # Common relationship patterns
        self.relationship_patterns = {
            'IS_A': [
                r'(.+?)\s+is\s+(?:a|an)\s+(.+)',
                r'(.+?)\s+are\s+(.+)'
            ],
            'PART_OF': [
                r'(.+?)\s+(?:is\s+)?part\s+of\s+(.+)',
                r'(.+?)\s+belongs\s+to\s+(.+)',
                r'(.+?)\s+contains\s+(.+)'
            ],
            'CAUSES': [
                r'(.+?)\s+causes\s+(.+)',
                r'(.+?)\s+leads\s+to\s+(.+)',
                r'(.+?)\s+results\s+in\s+(.+)'
            ],
            'RELATED_TO': [
                r'(.+?)\s+(?:is\s+)?related\s+to\s+(.+)',
                r'(.+?)\s+(?:is\s+)?associated\s+with\s+(.+)',
                r'(.+?)\s+(?:is\s+)?connected\s+to\s+(.+)'
            ]
        }
    
    def extract_relationships_pattern(self, text: str, concepts: List[ConceptNode]) -> List[RelationshipEdge]:
        """Extract relationships using pattern matching."""
        relationships = []
        concept_names = {concept.concept_name.lower(): concept for concept in concepts}
        
        for predicate, patterns in self.relationship_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    subject = match.group(1).strip().lower()
                    object_text = match.group(2).strip().lower()
                    
                    # Find matching concepts
                    subject_concept = None
                    object_concept = None
                    
                    for concept_name, concept in concept_names.items():
                        if concept_name in subject:
                            subject_concept = concept
                        if concept_name in object_text:
                            object_concept = concept
                    
                    if subject_concept and object_concept and subject_concept != object_concept:
                        relationship = RelationshipEdge(
                            subject_concept=subject_concept.concept_id,
                            predicate=predicate,
                            object_concept=object_concept.concept_id,
                            confidence=0.7,
                            relationship_type=self._get_relationship_type(predicate)
                        )
                        relationships.append(relationship)
        
        return relationships
    
    def extract_relationships_llm(self, text: str, concepts: List[ConceptNode], 
                                chunk_id: str) -> List[RelationshipEdge]:
        """Extract relationships using LLM-based analysis.

        Note: The previous co-occurrence RELATED_TO logic has been removed.
        Real semantic relationships are now sourced from ConceptNet via the
        validation gate, and pattern-based relationships (IS_A, PART_OF,
        CAUSES) are handled by extract_relationships_pattern().
        """
        # Co-occurrence relationship creation removed — replaced by
        # ConceptNet relationships from the validation gate.
        return []
    
    def extract_relationships_embedding(self, concepts: List[ConceptNode], 
                                      embedding_model) -> List[RelationshipEdge]:
        """Extract relationships using embedding-based similarity (sync version)."""
        relationships = []
        
        if len(concepts) < 2:
            return relationships
        
        # Skip if no embedding model available (model-server-separation architecture)
        if embedding_model is None:
            logger.debug("Skipping embedding-based relationship extraction - no local model available")
            return relationships
        
        # Generate embeddings for all concepts
        concept_texts = [concept.concept_name for concept in concepts]
        embeddings = embedding_model.encode(concept_texts)
        
        # Find similar concepts
        for i, concept1 in enumerate(concepts):
            for j, concept2 in enumerate(concepts[i+1:], i+1):
                similarity = np.dot(embeddings[i], embeddings[j]) / (
                    np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
                )
                
                if similarity > 0.85:  # Similarity threshold (raised from 0.8 to reduce noise)
                    relationship = RelationshipEdge(
                        subject_concept=concept1.concept_id,
                        predicate="SIMILAR_TO",
                        object_concept=concept2.concept_id,
                        confidence=similarity,
                        relationship_type=RelationshipType.ASSOCIATIVE
                    )
                    relationships.append(relationship)
        
        return relationships
    
    async def extract_relationships_embedding_async(self, concepts: List[ConceptNode], 
                                                   model_server_client) -> List[RelationshipEdge]:
        """Extract relationships using embedding-based similarity via model server (async, non-blocking)."""
        relationships = []
        
        if len(concepts) < 2:
            return relationships
        
        if model_server_client is None:
            logger.debug("Skipping embedding-based relationship extraction - no model server available")
            return relationships
        
        try:
            # Generate embeddings for all concepts via model server
            concept_texts = [concept.concept_name for concept in concepts]
            embeddings_list = await model_server_client.generate_embeddings(concept_texts)
            
            if not embeddings_list:
                logger.warning("Model server returned empty embeddings for relationship extraction")
                return relationships
            
            embeddings = np.array(embeddings_list)
            
            # Find similar concepts
            for i, concept1 in enumerate(concepts):
                for j, concept2 in enumerate(concepts[i+1:], i+1):
                    similarity = np.dot(embeddings[i], embeddings[j]) / (
                        np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
                    )
                    
                    if similarity > 0.85:  # Similarity threshold (raised from 0.8 to reduce noise)
                        relationship = RelationshipEdge(
                            subject_concept=concept1.concept_id,
                            predicate="SIMILAR_TO",
                            object_concept=concept2.concept_id,
                            confidence=float(similarity),
                            relationship_type=RelationshipType.ASSOCIATIVE
                        )
                        relationships.append(relationship)
            
            logger.debug(f"Extracted {len(relationships)} embedding-based relationships")
            return relationships
            
        except Exception as e:
            logger.warning(f"Error in embedding-based relationship extraction: {e}")
            return relationships
        
        return relationships
    
    def _get_relationship_type(self, predicate: str) -> RelationshipType:
        """Map predicate to relationship type."""
        return RelationTypeMapper.classify(predicate)


class KnowledgeGraphBuilder:
    """Main knowledge graph builder component."""
    
    def __init__(self, neo4j_client=None):
        self.settings = get_settings()
        self.concept_extractor = ConceptExtractor()
        self.relationship_extractor = RelationshipExtractor()
        self._embedding_model = None  # Lazy loaded (local fallback only)
        self._model_server_client = None  # Model server client (preferred)
        self._neo4j_client = neo4j_client  # For ConceptNet validation (optional)
        self._conceptnet_validator = None  # Lazy-initialized

        # In-memory storage for development (would use database in production)
        self.concepts: Dict[str, ConceptNode] = {}
        self.relationships: Dict[str, RelationshipEdge] = {}
        self.extractions: Dict[str, ConceptExtraction] = {}

        logger.info("Knowledge Graph Builder initialized (models will load on first use)")
    
    @property
    def embedding_model(self):
        """
        Lazy load embedding model on first access.
        
        NOTE: This is the LOCAL fallback model. Prefer using model server via
        generate_embeddings_async() for non-blocking operation.
        """
        logger.warning("Local embedding model not available - use generate_embeddings_async() instead")
        return None
    
    async def _get_model_server_client(self):
        """Get or initialize the model server client."""
        if self._model_server_client is not None:
            return self._model_server_client

        try:
            from ...clients.model_server_client import (
                ModelServerClient,
                get_model_client,
                initialize_model_client,
            )
            
            client = get_model_client()
            if client is None:
                try:
                    await initialize_model_client()
                    client = get_model_client()
                except Exception:
                    pass
            
            if client is None or not client.enabled:
                import os
                url = os.environ.get('MODEL_SERVER_URL', 'http://model-server:8001')
                client = ModelServerClient(base_url=url)
            
            if client and client.enabled:
                self._model_server_client = client
        except Exception as e:
            logger.warning(f"Model server not available: {e}")
        return self._model_server_client

    async def _get_pos_tags(self, text: str) -> Optional[List[dict]]:
        """Fetch spaCy POS tags for a chunk (best-effort; None on failure).

        Used to filter drug→dose gap tokens in the composition pass.  Returns
        the raw ``pos_tags`` list so callers can reconstruct token offsets.
        """
        try:
            client = await self._get_model_server_client()
            if client is None:
                return None
            results = await client.process_nlp([text], tasks=["pos"])
            return (results[0].get("pos_tags") or []) if results else None
        except Exception as e:
            logger.debug(f"POS tag fetch failed: {e}")
            return None

    def _get_conceptnet_validator(self):
        """Get or create the ConceptNet validator (requires neo4j_client)."""
        if self._conceptnet_validator is None and self._neo4j_client is not None:
            try:
                from .conceptnet_validator import ConceptNetValidator
                self._conceptnet_validator = ConceptNetValidator(self._neo4j_client)
            except Exception as e:
                logger.warning(f"Failed to initialize ConceptNet validator: {e}")
        return self._conceptnet_validator
    
    async def generate_embeddings_async(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings asynchronously using model server (non-blocking).
        
        Model server is required - no local fallback.
        """
        # Try model server first
        client = await self._get_model_server_client()
        if client is not None:
            try:
                embeddings = await client.generate_embeddings(texts)
                if embeddings:
                    return np.array(embeddings)
            except Exception as e:
                logger.warning(f"Model server embedding failed: {e}")
        
        # Fallback to local model via thread pool
        executor = _get_kg_executor()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            executor, 
            lambda: self.embedding_model.encode(texts)
        )
        return self._embedding_model
    
    def extract_knowledge_triples(self, content: str, source_id: str) -> List[Triple]:
        """Extract (subject, predicate, object) relationships from content."""
        try:
            # Extract concepts first
            concepts = self.extract_concepts_from_content(content, source_id)
            
            # Extract relationships
            relationships = self.extract_relationships_from_content(content, concepts, source_id)
            
            # Convert to triples
            triples = []
            for relationship in relationships:
                triple = Triple(
                    subject=relationship.subject_concept,
                    predicate=relationship.predicate,
                    object=relationship.object_concept,
                    confidence=relationship.confidence,
                    source_id=source_id,
                    extraction_method="HYBRID"
                )
                triples.append(triple)
            
            logger.info(f"Extracted {len(triples)} triples from content {source_id}")
            return triples
            
        except Exception as e:
            logger.error(f"Error extracting knowledge triples: {e}")
            return []
    
    def extract_concepts_from_content(self, content: str, chunk_id: str) -> List[ConceptNode]:
        """Extract concepts from content using multiple methods."""
        all_concepts = []
        
        try:
            # Method 1: Regex pattern extraction (MULTI_WORD, CODE_TERM, ACRONYM + PMI)
            regex_concepts = self.concept_extractor.extract_concepts_regex(content)
            all_concepts.extend(regex_concepts)
            
            # Method 2: LLM-based extraction
            llm_concepts = self.concept_extractor.extract_concepts_definition_patterns(content, chunk_id)
            all_concepts.extend(llm_concepts)
            
            # Method 3: Embedding-based similarity to existing concepts
            existing_concepts = list(self.concepts.values())
            embedding_concepts = self.concept_extractor.extract_concepts_embedding(
                content, chunk_id, existing_concepts
            )
            all_concepts.extend(embedding_concepts)
            
            # Deduplicate and merge concepts
            merged_concepts = self._merge_similar_concepts(all_concepts)
            
            # Add source chunk reference
            for concept in merged_concepts:
                concept.add_source_chunk(chunk_id)
            
            logger.info(f"Extracted {len(merged_concepts)} concepts from chunk {chunk_id}")
            return merged_concepts
            
        except Exception as e:
            logger.error(f"Error extracting concepts: {e}")
            return []
    
    async def extract_concepts_from_content_async(self, content: str, chunk_id: str) -> List[ConceptNode]:
        """Extract concepts from content using multiple methods (async, non-blocking)."""
        all_concepts = []
        
        try:
            # Method 1: Regex pattern extraction (sync - fast)
            regex_concepts = self.concept_extractor.extract_concepts_regex(content)
            all_concepts.extend(regex_concepts)
            
            # Method 2: LLM-based extraction (sync - pattern matching)
            llm_concepts = self.concept_extractor.extract_concepts_definition_patterns(content, chunk_id)
            all_concepts.extend(llm_concepts)
            
            # Method 3: Embedding-based similarity to existing concepts (async - uses model server)
            existing_concepts = list(self.concepts.values())
            if existing_concepts:
                embedding_concepts = await self.concept_extractor.extract_concepts_embedding_async(
                    content, chunk_id, existing_concepts
                )
                all_concepts.extend(embedding_concepts)
            
            # Deduplicate and merge concepts
            merged_concepts = self._merge_similar_concepts(all_concepts)
            
            # Add source chunk reference
            for concept in merged_concepts:
                concept.add_source_chunk(chunk_id)
            
            logger.info(f"Extracted {len(merged_concepts)} concepts (async) from chunk {chunk_id}")
            return merged_concepts
            
        except Exception as e:
            logger.error(f"Error extracting concepts (async): {e}")
            return []
    
    def extract_relationships_from_content(self, content: str, concepts: List[ConceptNode], 
                                         chunk_id: str) -> List[RelationshipEdge]:
        """Extract relationships from content using multiple methods (sync - pattern and LLM only)."""
        all_relationships = []
        
        try:
            # Method 1: Pattern-based extraction
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                content, concepts
            )
            all_relationships.extend(pattern_relationships)
            
            # Method 2: LLM-based extraction
            llm_relationships = self.relationship_extractor.extract_relationships_llm(
                content, concepts, chunk_id
            )
            all_relationships.extend(llm_relationships)
            
            # Method 3: Embedding-based similarity (skipped in sync - use async version)
            # Note: self.embedding_model is None in model-server-separation architecture
            # Use extract_relationships_from_content_async for embedding-based extraction
            embedding_relationships = self.relationship_extractor.extract_relationships_embedding(
                concepts, self.embedding_model
            )
            all_relationships.extend(embedding_relationships)
            
            # Add evidence chunk reference
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk_id)
            
            # Deduplicate relationships
            unique_relationships = self._deduplicate_relationships(all_relationships)
            
            logger.info(f"Extracted {len(unique_relationships)} relationships from chunk {chunk_id}")
            return unique_relationships
            
        except Exception as e:
            logger.error(f"Error extracting relationships: {e}")
            return []
    
    async def extract_relationships_from_content_async(self, content: str, concepts: List[ConceptNode], 
                                                       chunk_id: str) -> List[RelationshipEdge]:
        """Extract relationships from content using all methods including model server embeddings (async)."""
        all_relationships = []
        
        try:
            # Method 1: Pattern-based extraction
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                content, concepts
            )
            all_relationships.extend(pattern_relationships)
            
            # Method 2: LLM-based extraction
            llm_relationships = self.relationship_extractor.extract_relationships_llm(
                content, concepts, chunk_id
            )
            all_relationships.extend(llm_relationships)
            
            # Method 3: Embedding-based similarity via model server
            model_server_client = await self._get_model_server_client()
            embedding_relationships = await self.relationship_extractor.extract_relationships_embedding_async(
                concepts, model_server_client
            )
            all_relationships.extend(embedding_relationships)
            
            # Add evidence chunk reference
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk_id)
            
            # Deduplicate relationships
            unique_relationships = self._deduplicate_relationships(all_relationships)
            
            logger.info(f"Extracted {len(unique_relationships)} relationships (async) from chunk {chunk_id}")
            return unique_relationships
            
        except Exception as e:
            logger.error(f"Error extracting relationships (async): {e}")
            return []
    
    def build_confidence_scores(self, extractions: List[ConceptExtraction]) -> Dict[str, float]:
        """Build confidence scores for extracted relationships."""
        confidence_scores = {}
        
        try:
            for extraction in extractions:
                # Calculate concept confidence
                for concept in extraction.extracted_concepts:
                    if concept.concept_id not in confidence_scores:
                        confidence_scores[concept.concept_id] = []
                    confidence_scores[concept.concept_id].append(concept.confidence)
                
                # Calculate relationship confidence
                for relationship in extraction.extracted_relationships:
                    rel_key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
                    if rel_key not in confidence_scores:
                        confidence_scores[rel_key] = []
                    confidence_scores[rel_key].append(relationship.confidence)
            
            # Average confidence scores
            averaged_scores = {}
            for key, scores in confidence_scores.items():
                averaged_scores[key] = sum(scores) / len(scores)
            
            return averaged_scores
            
        except Exception as e:
            logger.error(f"Error building confidence scores: {e}")
            return {}
    
    def process_knowledge_chunk(self, chunk: KnowledgeChunk) -> ConceptExtraction:
        """Process a knowledge chunk and extract concepts and relationships (sync version)."""
        try:
            extraction_id = str(uuid.uuid4())
            
            # Extract concepts and relationships
            concepts = self.extract_concepts_from_content(chunk.content, chunk.id)
            relationships = self.extract_relationships_from_content(chunk.content, concepts, chunk.id)
            
            # Calculate overall confidence
            all_confidences = [c.confidence for c in concepts] + [r.confidence for r in relationships]
            overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
            
            # Create extraction record
            extraction = ConceptExtraction(
                extraction_id=extraction_id,
                chunk_id=chunk.id,
                extracted_concepts=concepts,
                extracted_relationships=relationships,
                extraction_method="HYBRID",
                confidence_score=overall_confidence
            )
            
            # Store extraction
            self.extractions[extraction_id] = extraction
            
            # Update knowledge graph
            self._update_knowledge_graph(concepts, relationships)
            
            logger.info(f"Processed knowledge chunk {chunk.id} with {len(concepts)} concepts and {len(relationships)} relationships")
            return extraction
            
        except Exception as e:
            logger.error(f"Error processing knowledge chunk: {e}")
            return ConceptExtraction(
                extraction_id=str(uuid.uuid4()),
                chunk_id=chunk.id,
                extracted_concepts=[],
                extracted_relationships=[],
                confidence_score=0.0
            )
    
    async def process_knowledge_chunk_async(self, chunk: KnowledgeChunk) -> ConceptExtraction:
        """Process a knowledge chunk with async NER + regex extraction and ConceptNet validation."""
        try:
            extraction_id = str(uuid.uuid4())

            # Step 1: Extract concepts using combined NER + Ollama + regex pipeline
            content_type = getattr(chunk, 'content_type', ContentType.GENERAL)
            concepts, _ner_failed, _llm_failed = await self.concept_extractor.extract_all_concepts_async(
                chunk.content, content_type=content_type
            )

            # Add source chunk reference
            for concept in concepts:
                concept.add_source_chunk(chunk.id)

            # Step 2: Validate concepts through ConceptNet gate (if available)
            conceptnet_relationships: List[RelationshipEdge] = []
            validator = self._get_conceptnet_validator()
            if validator is not None:
                try:
                    validation_result = await validator.validate_concepts(concepts)
                    concepts = validation_result.validated_concepts
                    conceptnet_relationships = validation_result.conceptnet_relationships
                    logger.info(
                        f"ConceptNet validation: kept {len(concepts)} concepts "
                        f"(conceptnet={validation_result.kept_by_conceptnet}, "
                        f"ner={validation_result.kept_by_ner}, "
                        f"pattern={validation_result.kept_by_pattern}, "
                        f"discarded={validation_result.discarded_count})"
                    )
                except Exception as e:
                    logger.warning(
                        f"ConceptNet validation failed, using raw extraction: {e}"
                    )
            else:
                logger.debug(
                    "ConceptNet validator not available, skipping validation gate"
                )

            # Step 3: Extract pattern-based relationships (IS_A, PART_OF, CAUSES)
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                chunk.content, concepts
            )

            # Step 4: Extract embedding-based relationships
            model_server_client = await self._get_model_server_client()
            embedding_relationships = await self.relationship_extractor.extract_relationships_embedding_async(
                concepts, model_server_client
            )

            # Combine: ConceptNet relationships + pattern relationships + embedding relationships
            # ConceptNet relationships replace co-occurrence RELATED_TO
            all_relationships = conceptnet_relationships + pattern_relationships + embedding_relationships

            # Add evidence chunk reference
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk.id)

            # Deduplicate relationships
            relationships = self._deduplicate_relationships(all_relationships)

            # Calculate overall confidence
            all_confidences = [c.confidence for c in concepts] + [r.confidence for r in relationships]
            overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

            # Create extraction record
            extraction = ConceptExtraction(
                extraction_id=extraction_id,
                chunk_id=chunk.id,
                extracted_concepts=concepts,
                extracted_relationships=relationships,
                extraction_method="HYBRID_ASYNC",
                confidence_score=overall_confidence
            )

            # Store extraction
            self.extractions[extraction_id] = extraction

            # Update knowledge graph
            self._update_knowledge_graph(concepts, relationships)

            logger.info(f"Processed knowledge chunk (async) {chunk.id} with {len(concepts)} concepts and {len(relationships)} relationships")
            return extraction

        except Exception as e:
            logger.error(f"Error processing knowledge chunk (async): {e}")
            return ConceptExtraction(
                extraction_id=str(uuid.uuid4()),
                chunk_id=chunk.id,
                extracted_concepts=[],
                extracted_relationships=[],
                confidence_score=0.0
            )

    async def process_knowledge_chunk_extract_only(self, chunk: KnowledgeChunk) -> Tuple[ConceptExtraction, bool, bool]:
        """Extract concepts and relationships from a chunk WITHOUT ConceptNet validation.

        Identical to process_knowledge_chunk_async but skips the per-chunk
        ConceptNet validation gate (Step 2). Validation is deferred to
        batch level via validate_batch_concepts().

        Returns ``(extraction, ner_failed, llm_failed)`` so the caller can
        accumulate per-document failure counters for the quality gate.
        """
        try:
            extraction_id = str(uuid.uuid4())

            # Step 1: Extract concepts using combined NER + Ollama + regex pipeline
            content_type = getattr(chunk, 'content_type', ContentType.GENERAL)
            concepts, ner_failed, llm_failed = await self.concept_extractor.extract_all_concepts_async(
                chunk.content, content_type=content_type
            )
            for concept in concepts:
                concept.add_source_chunk(chunk.id)

            # Step 1b: Compose drug + dose compounds bottom-up (HAS_DOSE),
            # medical scope only.  Anchors on already-extracted drug concepts.
            dose_concepts = []
            dose_relationships = []
            if content_type == ContentType.MEDICAL:
                pos_tags = await self._get_pos_tags(chunk.content)
                dose_concepts, dose_relationships = \
                    self.concept_extractor._compose_drug_dose_concepts(
                        chunk.content, concepts, pos_tags=pos_tags,
                        chunk_id=chunk.id,
                    )
            if dose_concepts:
                concepts.extend(dose_concepts)

            # Step 1b': Link therapy/regimen concepts to the agents they
            # include (INCLUDES), medical scope only.  Agents are the HAS_DOSE
            # subjects from the dose pass (generic, not drug-class-specific).
            treatment_relationships = []
            if content_type == ContentType.MEDICAL:
                agent_ids = {rel.subject_concept for rel in dose_relationships}
                treatment_relationships = \
                    self.concept_extractor._compose_treatment_links(
                        concepts, agent_ids
                    )

            # Step 1c: Synthesize compositional grounding (HAS_HEAD/HAS_MODIFIER).
            # Mints missing head/modifier parts with provenance
            # "materialized-for-grounding"; best-effort (never blocks extraction).
            extra_concepts, grounding_relationships = \
                await self.concept_extractor._synthesize_compositional_grounding(
                    concepts
                )
            if extra_concepts:
                concepts.extend(extra_concepts)

            # Step 2: SKIPPED — no per-chunk ConceptNet validation

            # Step 3: Extract pattern-based relationships
            pattern_relationships = self.relationship_extractor.extract_relationships_pattern(
                chunk.content, concepts
            )

            # Step 4: Extract embedding-based relationships
            model_server_client = await self._get_model_server_client()
            embedding_relationships = await self.relationship_extractor.extract_relationships_embedding_async(
                concepts, model_server_client
            )

            all_relationships = (
                pattern_relationships + embedding_relationships
                + grounding_relationships + dose_relationships
                + treatment_relationships
            )
            for relationship in all_relationships:
                relationship.add_evidence_chunk(chunk.id)

            relationships = self._deduplicate_relationships(all_relationships)

            all_confidences = [c.confidence for c in concepts] + [r.confidence for r in relationships]
            overall_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0

            extraction = ConceptExtraction(
                extraction_id=extraction_id,
                chunk_id=chunk.id,
                extracted_concepts=concepts,
                extracted_relationships=relationships,
                extraction_method="HYBRID_ASYNC_EXTRACT_ONLY",
                confidence_score=overall_confidence
            )

            self.extractions[extraction_id] = extraction
            self._update_knowledge_graph(concepts, relationships)

            logger.info(
                f"Extracted (no validation) chunk {chunk.id}: "
                f"{len(concepts)} concepts, {len(relationships)} relationships"
            )
            return (extraction, ner_failed, llm_failed)

        except Exception as e:
            logger.error(f"Error in extract-only processing: {e}")
            return (ConceptExtraction(
                extraction_id=str(uuid.uuid4()),
                chunk_id=chunk.id,
                extracted_concepts=[],
                extracted_relationships=[],
                confidence_score=0.0
            ), False, False)

    async def validate_batch_concepts(
        self, concepts: List[ConceptNode]
    ) -> tuple:
        """Validate a batch of concepts through ConceptNet in one pass.

        Deduplicates concepts by normalized name, runs a single
        validate_concepts() call, then returns the filtered list.

        Returns:
            (validated_concepts, conceptnet_relationships, stats_dict)
        """
        validator = self._get_conceptnet_validator()
        if validator is None:
            logger.debug("No ConceptNet validator; returning all concepts unfiltered")
            return concepts, [], {"kept": len(concepts), "discarded": 0}

        # Deduplicate by lowered name, merging source_chunks from all occurrences
        seen: dict = {}
        for c in concepts:
            key = c.concept_name.lower().strip()
            if key not in seen:
                seen[key] = c
            else:
                existing = seen[key]
                if c.confidence > existing.confidence:
                    # Keep higher-confidence version but merge source_chunks
                    for chunk_id in existing.source_chunks:
                        c.add_source_chunk(chunk_id)
                    seen[key] = c
                else:
                    # Merge source_chunks into existing
                    for chunk_id in c.source_chunks:
                        existing.add_source_chunk(chunk_id)
        unique_concepts = list(seen.values())

        try:
            result = await validator.validate_concepts(unique_concepts)
            stats = {
                "kept": len(result.validated_concepts),
                "discarded": result.discarded_count,
                "conceptnet": result.kept_by_conceptnet,
                "ner": result.kept_by_ner,
                "pattern": result.kept_by_pattern,
            }
            logger.info(
                f"Batch ConceptNet validation: {len(unique_concepts)} unique → "
                f"{len(result.validated_concepts)} kept "
                f"(conceptnet={result.kept_by_conceptnet}, "
                f"ner={result.kept_by_ner}, "
                f"pattern={result.kept_by_pattern}, "
                f"discarded={result.discarded_count})"
            )
            return result.validated_concepts, result.conceptnet_relationships, stats
        except Exception as e:
            logger.warning(f"Batch ConceptNet validation failed: {e}")
            return concepts, [], {"kept": len(concepts), "discarded": 0, "error": str(e)}


    
    def _merge_similar_concepts(self, concepts: List[ConceptNode]) -> List[ConceptNode]:
        """Merge similar concepts to avoid duplicates."""
        merged = {}
        
        for concept in concepts:
            # Use normalized name as key
            key = concept.concept_name.lower().strip()
            
            if key in merged:
                # Merge with existing concept
                existing = merged[key]
                existing.confidence = max(existing.confidence, concept.confidence)
                for alias in concept.aliases:
                    existing.add_alias(alias)
                for chunk_id in concept.source_chunks:
                    existing.add_source_chunk(chunk_id)
            else:
                merged[key] = concept
        
        return list(merged.values())
    
    def _deduplicate_relationships(self, relationships: List[RelationshipEdge]) -> List[RelationshipEdge]:
        """Remove duplicate relationships."""
        unique = {}
        
        for relationship in relationships:
            key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
            
            if key in unique:
                # Merge evidence
                existing = unique[key]
                existing.confidence = max(existing.confidence, relationship.confidence)
                for chunk_id in relationship.evidence_chunks:
                    existing.add_evidence_chunk(chunk_id)
            else:
                unique[key] = relationship
        
        return list(unique.values())
    
    def _update_knowledge_graph(self, concepts: List[ConceptNode], 
                              relationships: List[RelationshipEdge]) -> None:
        """Update the in-memory knowledge graph."""
        # Add concepts
        for concept in concepts:
            if concept.concept_id in self.concepts:
                # Merge with existing
                existing = self.concepts[concept.concept_id]
                existing.confidence = max(existing.confidence, concept.confidence)
                for alias in concept.aliases:
                    existing.add_alias(alias)
                for chunk_id in concept.source_chunks:
                    existing.add_source_chunk(chunk_id)
            else:
                self.concepts[concept.concept_id] = concept
        
        # Add relationships
        for relationship in relationships:
            key = f"{relationship.subject_concept}_{relationship.predicate}_{relationship.object_concept}"
            if key in self.relationships:
                # Merge with existing
                existing = self.relationships[key]
                existing.confidence = max(existing.confidence, relationship.confidence)
                for chunk_id in relationship.evidence_chunks:
                    existing.add_evidence_chunk(chunk_id)
            else:
                self.relationships[key] = relationship
    
    def get_knowledge_graph_stats(self) -> KnowledgeGraphStats:
        """Get statistics about the current knowledge graph."""
        stats = KnowledgeGraphStats()
        concepts = list(self.concepts.values())
        relationships = list(self.relationships.values())
        stats.update_stats(concepts, relationships)
        return stats
    
    def get_concepts_by_type(self, concept_type: str) -> List[ConceptNode]:
        """Get all concepts of a specific type."""
        return [concept for concept in self.concepts.values() 
                if concept.concept_type == concept_type]
    
    def get_relationships_by_predicate(self, predicate: str) -> List[RelationshipEdge]:
        """Get all relationships with a specific predicate."""
        return [relationship for relationship in self.relationships.values() 
                if relationship.predicate == predicate]
    
    def find_concept_by_name(self, name: str) -> Optional[ConceptNode]:
        """Find a concept by name or alias."""
        name_lower = name.lower()
        
        for concept in self.concepts.values():
            if concept.concept_name.lower() == name_lower:
                return concept
            if name_lower in [alias.lower() for alias in concept.aliases]:
                return concept
        
        return None

    def _reconcile_cross_references(
        self,
        cross_references: List,
        chunk_metadata: Dict[str, Dict[str, Any]],
    ) -> list:
        """Resolve cross-reference targets to chunk IDs using section/chapter metadata.

        Args:
            cross_references: List of CrossReference objects from _extract_cross_references
            chunk_metadata: Mapping of chunk_id -> metadata dict. Each metadata dict
                should contain keys like 'section', 'chapter', 'page', 'figure', 'table'
                with their corresponding label values (e.g., {'section': '3.1', 'chapter': '4'}).

        Returns:
            The same list of CrossReference objects with resolved_chunk_ids populated
            where possible. Unresolved references have resolved_chunk_ids = None.

        Requirements: 5.2, 5.3
        """

        # Build reverse index: (target_type, target_label) -> [chunk_ids]
        target_index: Dict[tuple, List[str]] = {}
        for chunk_id, meta in chunk_metadata.items():
            for key in ('section', 'chapter', 'page', 'figure', 'table'):
                label = meta.get(key)
                if label is not None:
                    idx_key = (key, str(label))
                    target_index.setdefault(idx_key, []).append(chunk_id)

        # Resolve each cross-reference
        resolved_count = 0
        for ref in cross_references:
            lookup_key = (ref.target_type, ref.target_label)
            matched_chunks = target_index.get(lookup_key)
            if matched_chunks:
                ref.resolved_chunk_ids = matched_chunks
                resolved_count += 1
                # Create REFERENCES edges in the in-memory KG
                for target_chunk_id in matched_chunks:
                    edge_key = f"{ref.source_chunk_id}_REFERENCES_{target_chunk_id}"
                    if edge_key not in self.relationships:
                        edge = RelationshipEdge(
                            subject_concept=ref.source_chunk_id,
                            predicate="REFERENCES",
                            object_concept=target_chunk_id,
                            confidence=0.8,
                            evidence_chunks=[ref.source_chunk_id],
                        )
                        self.relationships[edge_key] = edge
            else:
                logger.warning(
                    f"Unresolved cross-reference: {ref.raw_text} "
                    f"(target: {ref.target_type} {ref.target_label})"
                )

        logger.info(f"Reconciled {resolved_count}/{len(cross_references)} cross-references")
        return cross_references

