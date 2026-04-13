"""
RRF Parser Module.

Streaming parsers for UMLS Metathesaurus RRF (Rich Release Format) files.
Each parser is a generator that yields typed dataclass rows, filtering
by language and source vocabulary as appropriate. Malformed rows are
logged with line numbers and skipped.

Supported files:
  - MRCONSO.RRF: Concept names and sources
  - MRREL.RRF: Relationships between concepts
  - MRSTY.RRF: Semantic type assignments
  - MRDEF.RRF: Concept definitions
"""

import os
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Set, Tuple

import structlog

logger = structlog.get_logger(__name__)

# Minimum expected field counts per RRF file type
_MRCONSO_MIN_FIELDS = 17
_MRREL_MIN_FIELDS = 11
_MRSTY_MIN_FIELDS = 2
_MRDEF_MIN_FIELDS = 6

# Required and optional RRF files
_REQUIRED_FILES = ["MRCONSO.RRF", "MRREL.RRF"]
_OPTIONAL_FILES = ["MRSTY.RRF", "MRDEF.RRF", "SRDEF"]


@dataclass
class MRCONSORow:
    """A parsed row from MRCONSO.RRF."""

    cui: str
    lat: str
    ts: str
    stt: str
    sab: str
    str_name: str
    suppress: str


@dataclass
class MRRELRow:
    """A parsed row from MRREL.RRF."""

    cui1: str
    rel: str
    cui2: str
    rela: str
    sab: str


@dataclass
class MRSTYRow:
    """A parsed row from MRSTY.RRF."""

    cui: str
    tui: str


@dataclass
class MRDEFRow:
    """A parsed row from MRDEF.RRF."""

    cui: str
    sab: str
    definition: str


def parse_mrconso(
    path: str,
    source_vocabs: Optional[Set[str]] = None,
) -> Iterator[MRCONSORow]:
    """Stream MRCONSO.RRF rows, filtering to English and optional vocab set.

    Reads line-by-line to keep memory bounded. Yields one ``MRCONSORow``
    per valid, filtered row. Rows with fewer than 17 pipe-delimited
    fields are logged as warnings and skipped.

    Args:
        path: Path to MRCONSO.RRF file.
        source_vocabs: If provided, only rows whose SAB is in this set
            are yielded.

    Yields:
        MRCONSORow for each valid English-language row passing filters.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"MRCONSO file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            line = raw_line.rstrip("\n").rstrip("\r")
            if not line:
                continue

            fields = line.split("|")
            if len(fields) < _MRCONSO_MIN_FIELDS:
                logger.warning(
                    "mrconso_malformed_row",
                    line_number=line_num,
                    field_count=len(fields),
                    content=line[:120],
                )
                continue

            lat = fields[1]
            if lat != "ENG":
                continue

            sab = fields[11]
            if source_vocabs is not None and sab not in source_vocabs:
                continue

            yield MRCONSORow(
                cui=fields[0],
                lat=lat,
                ts=fields[2],
                stt=fields[4],
                sab=sab,
                str_name=fields[14],
                suppress=fields[16],
            )


def parse_mrrel(
    path: str,
    source_vocabs: Optional[Set[str]] = None,
) -> Iterator[MRRELRow]:
    """Stream MRREL.RRF rows, filtering to optional vocab set.

    Args:
        path: Path to MRREL.RRF file.
        source_vocabs: If provided, only rows whose SAB is in this set
            are yielded.

    Yields:
        MRRELRow for each valid row passing filters.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"MRREL file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            line = raw_line.rstrip("\n").rstrip("\r")
            if not line:
                continue

            fields = line.split("|")
            if len(fields) < _MRREL_MIN_FIELDS:
                logger.warning(
                    "mrrel_malformed_row",
                    line_number=line_num,
                    field_count=len(fields),
                    content=line[:120],
                )
                continue

            sab = fields[10]
            if source_vocabs is not None and sab not in source_vocabs:
                continue

            yield MRRELRow(
                cui1=fields[0],
                rel=fields[3],
                cui2=fields[4],
                rela=fields[7],
                sab=sab,
            )


def parse_mrsty(path: str) -> Iterator[MRSTYRow]:
    """Stream MRSTY.RRF rows.

    Args:
        path: Path to MRSTY.RRF file.

    Yields:
        MRSTYRow for each valid row.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"MRSTY file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            line = raw_line.rstrip("\n").rstrip("\r")
            if not line:
                continue

            fields = line.split("|")
            if len(fields) < _MRSTY_MIN_FIELDS:
                logger.warning(
                    "mrsty_malformed_row",
                    line_number=line_num,
                    field_count=len(fields),
                    content=line[:120],
                )
                continue

            yield MRSTYRow(cui=fields[0], tui=fields[1])


def parse_mrdef(
    path: str,
    source_vocabs: Optional[Set[str]] = None,
) -> Iterator[MRDEFRow]:
    """Stream MRDEF.RRF rows, filtering to optional vocab set.

    Args:
        path: Path to MRDEF.RRF file.
        source_vocabs: If provided, only rows whose SAB is in this set
            are yielded.

    Yields:
        MRDEFRow for each valid row passing filters.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"MRDEF file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, start=1):
            line = raw_line.rstrip("\n").rstrip("\r")
            if not line:
                continue

            fields = line.split("|")
            if len(fields) < _MRDEF_MIN_FIELDS:
                logger.warning(
                    "mrdef_malformed_row",
                    line_number=line_num,
                    field_count=len(fields),
                    content=line[:120],
                )
                continue

            sab = fields[4]
            if source_vocabs is not None and sab not in source_vocabs:
                continue

            yield MRDEFRow(
                cui=fields[0],
                sab=sab,
                definition=fields[5],
            )


def validate_rrf_directory(
    rrf_dir: str,
) -> Tuple[Dict[str, str], List[str]]:
    """Check for required and optional RRF files in a directory.

    Args:
        rrf_dir: Path to directory containing RRF files.

    Returns:
        A tuple of ``(found_files, missing_required)`` where
        *found_files* maps filename to its full path for every
        required or optional file that exists, and
        *missing_required* lists filenames that are required but
        absent.
    """
    found_files: Dict[str, str] = {}
    missing_required: List[str] = []

    all_files = _REQUIRED_FILES + _OPTIONAL_FILES

    for filename in all_files:
        full_path = os.path.join(rrf_dir, filename)
        if os.path.exists(full_path):
            found_files[filename] = full_path
        elif filename in _REQUIRED_FILES:
            missing_required.append(filename)

    if found_files:
        logger.info(
            "rrf_directory_validated",
            found=list(found_files.keys()),
            missing_required=missing_required,
        )

    return found_files, missing_required
