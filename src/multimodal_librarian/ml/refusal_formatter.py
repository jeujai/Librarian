"""
Refusal Formatter — detects and formats refusal responses.

When the RAG pipeline cannot find relevant information for a query, it
returns a response containing phrases like "could not find any
information" or "not mentioned in any of the given documents".  These
responses need to be detected and reformatted into concise,
conversational refusals that teach the fine-tuned model to say
"I don't know" rather than fabricate medical content.

This module provides three stateless functions:

- ``is_refusal_response(response_text)`` — returns ``True`` if the
  response contains any known refusal indicator phrase.
- ``has_refusal_then_fabrication(response_text)`` — returns ``True``
  if the response starts with a refusal but then provides unrelated
  medical information (a common RAG failure mode).
- ``format_refusal(question, response_text)`` — produces a short
  (<200 tokens), conversational refusal that acknowledges the question
  without fabricating medical content.

Requirements: 2.1, 2.2, 2.4, 2.5
"""

from __future__ import annotations

import re
from typing import List

# ---------------------------------------------------------------------------
# Refusal indicator phrases
# ---------------------------------------------------------------------------

# Phrases that indicate the RAG pipeline could not find information.
# Matching is case-insensitive (see ``is_refusal_response``).
REFUSAL_INDICATORS: List[str] = [
    "could not find any information",
    "not mentioned in any of the given documents",
    "no information available",
    "unable to find relevant information",
    "no relevant sources",
    "don't have information about",
]

# ---------------------------------------------------------------------------
# Fabrication detection patterns
# ---------------------------------------------------------------------------

# Medical content markers that suggest fabricated information when they
# appear *after* a refusal phrase.  These are intentionally broad to
# catch common fabrication patterns without requiring an LLM call.
_DOSAGE_PATTERN: re.Pattern[str] = re.compile(
    r"\b\d+\s*(?:mg|mcg|µg|ml|mL|g|units?|IU)\b",
    re.IGNORECASE,
)

_TREATMENT_REGIMEN_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:administer|prescribe|dosage|dose|twice\s+daily|"
    r"once\s+daily|three\s+times|every\s+\d+\s+hours|"
    r"oral(?:ly)?|intravenous(?:ly)?|subcutaneous(?:ly)?|"
    r"intramuscular(?:ly)?)\b",
    re.IGNORECASE,
)

_DRUG_INTERACTION_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:contraindicated|drug\s+interaction|"
    r"co-administer|concomitant\s+use|"
    r"CYP\d[A-Z]\d|half-life|bioavailability|"
    r"pharmacokinetic)\b",
    re.IGNORECASE,
)

# Minimum character length of the "informative" portion after a refusal
# for it to be considered fabrication.  Short trailing text (e.g.,
# "However, you might consult your doctor.") is not fabrication.
_MIN_FABRICATION_LENGTH: int = 200


# ---------------------------------------------------------------------------
# Refusal formatting templates
# ---------------------------------------------------------------------------

# A small set of conversational refusal templates.  ``format_refusal``
# rotates through them based on a hash of the question to provide
# variety without randomness (deterministic for the same question).
_REFUSAL_TEMPLATES: List[str] = [
    (
        "I don't have information about {topic} in my available sources. "
        "You might want to check with a healthcare professional or "
        "consult a specialized medical database for more details."
    ),
    (
        "I wasn't able to find information about {topic} in the "
        "documents I have access to. A healthcare provider or a "
        "dedicated medical reference could be a good next step."
    ),
    (
        "The sources I have access to don't cover {topic}. "
        "For accurate information, consider reaching out to a "
        "qualified healthcare professional."
    ),
    (
        "I couldn't locate any information about {topic} in my "
        "knowledge base. A medical professional or specialized "
        "resource would be better suited to help with this."
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_refusal_response(response_text: str) -> bool:
    """Detect if a RAG response is a refusal (no information found).

    Checks whether the response text contains any phrase from
    :data:`REFUSAL_INDICATORS` using case-insensitive matching.

    Args:
        response_text: The RAG pipeline response text to check.

    Returns:
        ``True`` if any refusal indicator phrase is present,
        ``False`` otherwise.
    """
    if not response_text:
        return False

    lower = response_text.lower()
    return any(indicator in lower for indicator in REFUSAL_INDICATORS)


def has_refusal_then_fabrication(response_text: str) -> bool:
    """Detect if a response starts with a refusal then fabricates info.

    A common RAG failure mode is a response that begins with "I could
    not find any information about X" but then provides detailed medical
    information about a different substance or topic.  This function
    detects that pattern by:

    1. Finding the earliest refusal indicator phrase in the response.
    2. Extracting the text that follows the refusal phrase.
    3. Checking whether the trailing text contains medical content
       markers (dosages, treatment regimens, drug interactions) and
       exceeds a minimum length threshold.

    Args:
        response_text: The RAG pipeline response text to check.

    Returns:
        ``True`` if the response starts with a refusal and then
        provides substantive medical content, ``False`` otherwise.
    """
    if not response_text:
        return False

    lower = response_text.lower()

    # Find the earliest refusal indicator
    earliest_pos = -1
    earliest_indicator = ""
    for indicator in REFUSAL_INDICATORS:
        pos = lower.find(indicator)
        if pos != -1 and (earliest_pos == -1 or pos < earliest_pos):
            earliest_pos = pos
            earliest_indicator = indicator

    if earliest_pos == -1:
        # No refusal phrase found — not a refusal-then-fabrication
        return False

    # The refusal should appear near the start of the response.
    # If the refusal phrase is buried deep in the text, this is not
    # the "starts with refusal" pattern we're looking for.
    text_before_refusal = response_text[:earliest_pos].strip()
    if len(text_before_refusal) > 100:
        return False

    # Extract text after the refusal phrase
    after_refusal_start = earliest_pos + len(earliest_indicator)
    trailing_text = response_text[after_refusal_start:]

    # The trailing text must be substantial enough to constitute
    # fabricated content, not just a brief closing remark.
    if len(trailing_text.strip()) < _MIN_FABRICATION_LENGTH:
        return False

    # Check for medical content markers in the trailing text
    has_medical_content = (
        bool(_DOSAGE_PATTERN.search(trailing_text))
        or bool(_TREATMENT_REGIMEN_PATTERN.search(trailing_text))
        or bool(_DRUG_INTERACTION_PATTERN.search(trailing_text))
    )

    return has_medical_content


def format_refusal(question: str, response_text: str) -> str:
    """Format a refusal response as a concise, conversational refusal.

    Produces a short response (under 200 estimated tokens using the
    chars / 4 heuristic) that:

    - Acknowledges the question
    - States the information is not in the available sources
    - Optionally suggests where the user might look
    - Does **not** fabricate any medical content

    The template is selected deterministically based on a hash of the
    question text, providing variety across different questions while
    remaining reproducible.

    Args:
        question: The original user question.
        response_text: The original RAG response (used for context but
            not included in the output).

    Returns:
        A formatted refusal string under 200 estimated tokens.
    """
    # Extract a short topic phrase from the question for the template.
    # Use the question itself, trimmed to a reasonable length.
    topic = _extract_topic(question)

    # Select a template deterministically based on the question hash
    template_index = hash(question) % len(_REFUSAL_TEMPLATES)
    template = _REFUSAL_TEMPLATES[template_index]

    return template.format(topic=topic)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_topic(question: str) -> str:
    """Extract a short topic phrase from a question for refusal templates.

    Strips common question prefixes ("What is", "Can you tell me about",
    "How does", etc.) and trailing punctuation to produce a concise
    topic string.  If the question is very short, it is returned as-is
    (minus trailing punctuation).

    Args:
        question: The original user question.

    Returns:
        A topic phrase suitable for insertion into a refusal template.
    """
    if not question:
        return "this topic"

    # Strip leading/trailing whitespace and trailing punctuation
    topic = question.strip().rstrip("?!.")

    # Try to remove common question prefixes to get the core topic
    _PREFIX_PATTERNS: List[re.Pattern[str]] = [
        re.compile(
            r"^(?:can\s+you\s+)?tell\s+me\s+about\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^what\s+(?:is|are)\s+(?:the\s+)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"^how\s+(?:does|do|is|are|can)\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:do\s+you\s+)?(?:have|know)\s+"
            r"(?:any\s+)?(?:information\s+)?(?:about|on)\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^what\s+(?:can\s+you\s+tell\s+me\s+about"
            r"|do\s+you\s+know\s+about)\s+",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:i\s+(?:want|need)\s+to\s+know\s+about"
            r"|i'm\s+looking\s+for\s+information\s+"
            r"(?:about|on))\s+",
            re.IGNORECASE,
        ),
    ]

    for pattern in _PREFIX_PATTERNS:
        stripped = pattern.sub("", topic)
        if stripped != topic and len(stripped) > 2:
            topic = stripped
            break

    # Ensure the topic isn't too long for the template
    if len(topic) > 100:
        topic = topic[:100].rsplit(" ", 1)[0]

    # Fallback if stripping left nothing useful
    if not topic or len(topic) < 2:
        topic = "this topic"

    return topic
