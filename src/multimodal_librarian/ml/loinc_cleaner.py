"""
LOINC Cleaner — strips LOINC-coded fields from UMLS concept names.

UMLS concept names often contain LOINC-coded fields such as
pipe-separated components (e.g., ``cycloSPORINE|Pt|Bld|LC/MS/MS``),
HTML entities (``&#x7C;``), and coded suffixes (``ANYProp``, ``ANYTm``,
``ANYSys``, ``ANYMeth``, ``Pt``, ``Bld``, ``Ser``, ``Plas``, etc.).
These produce unnatural questions when used directly in templates.

This module provides two stateless functions:

- ``clean_concept_name(raw_name)`` — returns the human-readable portion
  of a concept name after stripping all LOINC-coded patterns.
- ``is_loinc_coded(name)`` — returns ``True`` if any LOINC pattern is
  present in the input string.

Requirements: 1.3, 4.2
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Regex patterns matching LOINC-coded fields in UMLS concept names
# ---------------------------------------------------------------------------

# Pipe-separated fields: matches a pipe character followed by any
# non-pipe content.  LOINC concept names encode component|property|
# time|system|scale|method as pipe-delimited segments.
_LOINC_PIPE_PATTERN: re.Pattern[str] = re.compile(r"\|[^|]*")

# HTML-encoded entities commonly found in UMLS exports.
# Matches sequences like &#x7C; (pipe), &#xNN; (arbitrary hex).
_HTML_ENTITY_PATTERN: re.Pattern[str] = re.compile(
    r"&#x[0-9A-Fa-f]+;", re.IGNORECASE
)

# The specific HTML entity for pipe (&#x7C;) — decoded to an actual pipe
# so the pipe pattern can handle it in the next pass.
_HTML_PIPE_ENTITY: re.Pattern[str] = re.compile(
    r"&#x0*7[Cc];", re.IGNORECASE
)

# Coded suffixes that appear as standalone tokens in LOINC concept names.
# These represent LOINC axis abbreviations (property, timing, system,
# method, scale) and common specimen/body-fluid codes.
_CODED_SUFFIX_PATTERN: re.Pattern[str] = re.compile(
    r"\b("
    r"ANYProp|ANYTm|ANYSys|ANYMeth"
    r"|Pt|Bld|Ser|Plas"
    r"|Urine|CSF"
    r"|LC/MS/MS|IA"
    r"|Qn|Ord|Nom"
    r")\b"
)


def clean_concept_name(raw_name: str) -> str:
    """Strip LOINC-coded fields from a UMLS concept name.

    Applies three cleaning passes in order:

    1. Remove pipe-separated fields (everything from the first ``|``
       onward in each pipe segment).
    2. Remove HTML entities (``&#xNN;``).
    3. Remove coded suffixes (``ANYProp``, ``Pt``, ``Bld``, etc.).

    The result is stripped of leading/trailing whitespace and collapsed
    to single spaces.  Returns an empty string if nothing human-readable
    remains after cleaning.

    Args:
        raw_name: The raw UMLS concept name, potentially containing
            LOINC-coded fields.

    Returns:
        The human-readable portion of the concept name, or ``""`` if
        nothing remains.
    """
    if not raw_name:
        return ""

    # First, decode HTML-encoded pipe entities (&#x7C;) into real pipes
    # so the pipe pattern can strip them in the next pass.
    cleaned = _HTML_PIPE_ENTITY.sub("|", raw_name)
    # Remove remaining HTML entities (non-pipe hex codes)
    cleaned = _HTML_ENTITY_PATTERN.sub(" ", cleaned)
    # Strip pipe-separated fields
    cleaned = _LOINC_PIPE_PATTERN.sub("", cleaned)
    # Strip coded suffixes
    cleaned = _CODED_SUFFIX_PATTERN.sub("", cleaned)

    # Collapse multiple whitespace characters into a single space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def is_loinc_coded(name: str) -> bool:
    """Return ``True`` if the name contains any LOINC-coded fields.

    Checks for the presence of pipe-separated fields, HTML entities,
    or coded suffixes.

    Args:
        name: The concept name string to check.

    Returns:
        ``True`` if any LOINC pattern is detected, ``False`` otherwise.
    """
    if not name:
        return False

    if _LOINC_PIPE_PATTERN.search(name):
        return True
    if _HTML_ENTITY_PATTERN.search(name):
        return True
    if _CODED_SUFFIX_PATTERN.search(name):
        return True

    return False
