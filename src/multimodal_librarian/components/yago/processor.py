"""YAGO 4.5 dump processor for downloading and parsing YAGO Turtle files.

Downloads YAGO 4.5 zip archives from yago-knowledge.org, extracts
the Turtle (.ttl) files inside, and streams parsed triples per entity
yielding FilteredEntity objects for the Neo4j loader pipeline.

YAGO 4.5 is derived from Wikidata but is pre-filtered, smaller
(~200MB compressed for tiny, ~12GB for full), and uses schema.org
properties with human-readable IRIs.

The tiny variant contains a single yago-tiny.ttl file (~1.6GB).
The full variant contains a single yago-full.ttl file (~12GB+).
Both use tab-separated one-triple-per-line Turtle format after
the @prefix header block.
"""

import json
import os
import re
import subprocess
import tracemalloc
import zipfile
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Iterator

import aiohttp

from .logger import YagoLoggerMixin, log_progress
from .models import FilteredEntity

# YAGO 4.5 download URLs (zip archives)
YAGO_BASE_URL = "https://yago-knowledge.org/data/yago4.5"
YAGO_FULL_URL = f"{YAGO_BASE_URL}/yago-4.5.0.2.zip"
YAGO_TINY_URL = f"{YAGO_BASE_URL}/yago-4.5.0.2-tiny.zip"

# IRI prefixes used in YAGO Turtle files
YAGO_RESOURCE = "http://yago-knowledge.org/resource/"
SCHEMA_ORG = "http://schema.org/"
WIKIDATA_ENTITY_PREFIX = "http://www.wikidata.org/entity/"

# Memory limit in bytes (512MB)
MAX_MEMORY_BYTES = 512 * 1024 * 1024

# Default checkpoint interval
DEFAULT_CHECKPOINT_INTERVAL = 10000

# Regex for parsing language-tagged literals: "text"@lang
_LANG_LITERAL_RE = re.compile(r'^"(.+)"@([\w-]+)$')
# Regex for plain literals: "text"
_PLAIN_LITERAL_RE = re.compile(r'^"(.+)"$')
# Regex for typed literals: "value"^^type
_TYPED_LITERAL_RE = re.compile(r'^"(.+)"\^\^(.+)$')


class MemoryTracker:
    """Track memory usage to ensure 512MB limit compliance."""

    def __init__(self, limit_bytes: int = MAX_MEMORY_BYTES):
        self.limit_bytes = limit_bytes
        self.peak_bytes: int = 0
        self._enabled = False

    def start(self) -> None:
        self._enabled = True
        tracemalloc.start()
        self.peak_bytes = 0

    def stop(self) -> None:
        if self._enabled:
            self._enabled = False
            tracemalloc.stop()

    def get_current_mb(self) -> float:
        if not self._enabled:
            return 0.0
        current, _ = tracemalloc.get_traced_memory()
        return current / (1024 * 1024)

    def get_peak_mb(self) -> float:
        if not self._enabled:
            return 0.0
        _, peak = tracemalloc.get_traced_memory()
        return peak / (1024 * 1024)

    def check_limit(self) -> bool:
        return self.get_current_mb() * 1024 * 1024 < self.limit_bytes

    def update_peak(self) -> None:
        if not self._enabled:
            return
        current, peak = tracemalloc.get_traced_memory()
        if peak > self.peak_bytes:
            self.peak_bytes = peak


def _extract_yago_id(prefixed: str) -> str:
    """Extract entity ID from a prefixed name like 'yago:Belgium'.

    Args:
        prefixed: Prefixed name (e.g. 'yago:Belgium', 'schema:Person').

    Returns:
        Local name after the prefix (e.g. 'Belgium', 'Person').
    """
    if ":" in prefixed:
        return prefixed.split(":", 1)[1]
    return prefixed


def _expand_prefix(prefixed: str, prefixes: dict[str, str]) -> str:
    """Expand a prefixed name to a full IRI using the prefix map.

    Args:
        prefixed: Prefixed name like 'yago:Belgium'.
        prefixes: Mapping of prefix -> IRI base.

    Returns:
        Full IRI or the original string if no prefix matches.
    """
    if prefixed.startswith("<") and prefixed.endswith(">"):
        return prefixed[1:-1]
    if ":" in prefixed:
        prefix, local = prefixed.split(":", 1)
        if prefix in prefixes:
            return prefixes[prefix] + local
    return prefixed


def _extract_wikidata_qid(iri: str) -> str | None:
    """Extract Wikidata Q-number from IRI if present.

    YAGO entities link back to Wikidata via owl:sameAs.

    Args:
        iri: IRI that may be a Wikidata entity reference.

    Returns:
        Q-number like 'Q42' or None.
    """
    if iri.startswith(WIKIDATA_ENTITY_PREFIX):
        qid = iri[len(WIKIDATA_ENTITY_PREFIX):]
        if qid.startswith("Q"):
            return qid
    return None


def _parse_literal(obj_str: str) -> tuple[str, str | None]:
    """Parse a Turtle literal string into (value, language).

    Args:
        obj_str: Raw object string from the triple line.

    Returns:
        Tuple of (string_value, language_tag_or_None).
    """
    m = _LANG_LITERAL_RE.match(obj_str)
    if m:
        return m.group(1), m.group(2).lower()

    m = _TYPED_LITERAL_RE.match(obj_str)
    if m:
        return m.group(1), None

    m = _PLAIN_LITERAL_RE.match(obj_str)
    if m:
        return m.group(1), None

    return obj_str, None


def _is_english_lang(lang: str | None) -> bool:
    """Check if a language tag is English or untagged."""
    if lang is None:
        return True
    return lang in ("en", "en-us", "en-gb", "en-ca")



class YagoDumpProcessor(YagoLoggerMixin):
    """Process YAGO 4.5 Turtle dumps with memory-efficient streaming.

    Downloads YAGO 4.5 zip archives, extracts the Turtle files,
    then streams line-by-line through the extracted TTL, grouping
    triples by subject and yielding FilteredEntity objects.

    The tiny variant contains a single yago-tiny.ttl (~1.6GB).
    The full variant contains a single yago-full.ttl.
    Both use tab-separated one-triple-per-line format after the
    @prefix header block.
    """

    CHECKPOINT_FILENAME = "yago_processor_checkpoint.json"

    YAGO_ZIPS = {
        "tiny": {
            "url": YAGO_TINY_URL,
            "filename": "yago-4.5.0.2-tiny.zip",
            "description": "Tiny subset (~200MB zip)",
        },
        "full": {
            "url": YAGO_FULL_URL,
            "filename": "yago-4.5.0.2.zip",
            "description": "Full dataset (~12GB zip)",
        },
    }

    def __init__(
        self,
        dump_dir: str | Path,
        memory_limit_bytes: int = MAX_MEMORY_BYTES,
        include_beyond_wikipedia: bool = False,
    ):
        self.dump_dir = Path(dump_dir)
        self.memory_limit_bytes = memory_limit_bytes
        self.include_beyond_wikipedia = include_beyond_wikipedia
        self._memory_tracker = MemoryTracker(limit_bytes=memory_limit_bytes)
        self._processed_count = 0
        self._total_size: int | None = None
        self._last_checkpoint_entity_id: str | None = None
        self._checkpoint_file = self.dump_dir / self.CHECKPOINT_FILENAME

    @property
    def memory_tracker(self) -> MemoryTracker:
        return self._memory_tracker

    def get_progress(self) -> float:
        if self._total_size is None or self._total_size == 0:
            return -1.0
        return min(100.0, (self._processed_count / self._total_size) * 100)

    async def download(
        self,
        variant: str = "tiny",
        resume: bool = True,
    ) -> str:
        """Download a YAGO zip archive with resume support."""
        zip_info = self.YAGO_ZIPS[variant]
        url = zip_info["url"]
        dest = self.dump_dir / zip_info["filename"]

        self.logger.info("Starting YAGO download", variant=variant, url=url)
        self.dump_dir.mkdir(parents=True, exist_ok=True)

        headers = {}
        start_offset = 0

        if resume and dest.exists():
            start_offset = dest.stat().st_size
            self.logger.info(
                "Resuming download",
                file_size_mb=round(start_offset / (1024 * 1024), 2),
            )
            headers["Range"] = f"bytes={start_offset}-"

        timeout = aiohttp.ClientTimeout(total=None, sock_read=600)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url) as resp:
                total = int(resp.headers.get("Content-Length", 0))

            if start_offset >= total and total > 0:
                self.logger.info(
                    "Download already complete",
                    size_mb=round(total / (1024**2), 1),
                )
                return str(dest)

            async with session.get(url, headers=headers) as response:
                if response.status not in (200, 206):
                    raise RuntimeError(
                        f"Download failed: HTTP {response.status}"
                    )

                mode = "ab" if start_offset > 0 else "wb"
                downloaded = start_offset
                last_log = downloaded
                log_interval = 50 * 1024 * 1024

                with open(dest, mode) as f:
                    async for chunk in response.content.iter_chunked(
                        1024 * 1024
                    ):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded - last_log >= log_interval:
                            pct = (
                                f"{downloaded / total * 100:.1f}%"
                                if total
                                else "?"
                            )
                            self.logger.info(
                                "Download progress",
                                downloaded_mb=round(
                                    downloaded / (1024**2), 1
                                ),
                                total_mb=(
                                    round(total / (1024**2), 1)
                                    if total
                                    else None
                                ),
                                percent=pct,
                            )
                            last_log = downloaded

        final_size = dest.stat().st_size
        self.logger.info(
            "Download completed",
            variant=variant,
            size_mb=round(final_size / (1024**2), 1),
        )
        return str(dest)

    def extract_zip(self, variant: str = "tiny") -> list[Path]:
        """Extract TTL files from a downloaded YAGO zip.

        Uses the system `unzip` command because the YAGO zips
        sometimes have extra bytes that Python's zipfile can't
        stream-open (BadZipFile), but `unzip` handles gracefully.

        Returns:
            List of paths to extracted .ttl files.
        """
        zip_info = self.YAGO_ZIPS[variant]
        zip_path = self.dump_dir / zip_info["filename"]

        if not zip_path.exists():
            raise FileNotFoundError(f"Zip file not found: {zip_path}")

        extract_dir = self.dump_dir / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Check if already extracted
        existing = list(extract_dir.glob("*.ttl"))
        if existing:
            self.logger.info(
                f"Already extracted {len(existing)} TTL file(s)"
            )
            for p in existing:
                self.logger.info(
                    f"  {p.name}: "
                    f"{p.stat().st_size / (1024**2):.1f} MB"
                )
            return existing

        self.logger.info("Extracting YAGO zip", zip_path=str(zip_path))

        result = subprocess.run(
            ["unzip", "-o", str(zip_path), "-d", str(extract_dir)],
            capture_output=True,
            text=True,
        )

        if result.returncode not in (0, 1):
            # unzip returns 1 for warnings (like extra bytes) but still works
            raise RuntimeError(
                f"unzip failed (rc={result.returncode}): {result.stderr}"
            )

        extracted = list(extract_dir.glob("*.ttl"))
        for p in extracted:
            self.logger.info(
                f"Extracted {p.name}: "
                f"{p.stat().st_size / (1024**2):.1f} MB"
            )

        self.logger.info(f"Extracted {len(extracted)} TTL file(s)")
        return extracted

    async def process(
        self,
        checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
        file_keys: list[str] | None = None,
        variant: str = "tiny",
    ) -> AsyncIterator[FilteredEntity]:
        """Stream process YAGO TTL files, yielding FilteredEntity.

        Parses extracted .ttl files line-by-line, grouping triples
        by subject. When the subject changes, the accumulated entity
        is built and yielded if it has an English label.

        Args:
            checkpoint_interval: Entities between progress logs.
            file_keys: Ignored for now (tiny has single file).
            variant: Which zip variant was downloaded.

        Yields:
            FilteredEntity for each entity with an English label.
        """
        extract_dir = self.dump_dir / "extracted"
        ttl_files = sorted(extract_dir.glob("*.ttl"))

        if not ttl_files:
            self.logger.warning("No TTL files found in extract dir")
            return

        self.logger.info(
            "Starting YAGO processing",
            file_count=len(ttl_files),
        )
        self._memory_tracker.start()

        # Load checkpoint
        skip_until = None
        if self._checkpoint_file.exists():
            try:
                with open(self._checkpoint_file, "r") as f:
                    cp = json.load(f)
                skip_until = cp.get("last_entity_id")
                self.logger.info(
                    "Resuming from checkpoint",
                    last_entity_id=skip_until,
                )
            except (json.JSONDecodeError, IOError):
                pass

        try:
            entity_count = 0
            last_reported = 0

            for fpath in ttl_files:
                self.logger.info(
                    f"Processing {fpath.name}",
                    size_mb=round(fpath.stat().st_size / (1024**2), 1),
                )

                for entity in self._stream_ttl_file(fpath, skip_until):
                    yield entity
                    entity_count += 1
                    self._processed_count += 1
                    self._last_checkpoint_entity_id = entity.entity_id

                    if (
                        entity_count - last_reported
                        >= checkpoint_interval
                    ):
                        self.logger.info(
                            **log_progress(
                                "processing",
                                entity_count,
                                rate=entity_count,
                            )
                        )
                        last_reported = entity_count

                # Clear skip for next file
                skip_until = None

            self._save_checkpoint()
            self.logger.info(
                "Processing completed",
                total_entities=entity_count,
            )

        finally:
            self._memory_tracker.stop()

    def _stream_ttl_file(
        self,
        fpath: Path,
        skip_until: str | None = None,
    ) -> Iterator[FilteredEntity]:
        """Stream-parse a Turtle file line-by-line.

        YAGO 4.5 TTL files use one triple per line (tab-separated)
        after the @prefix header. We read line by line, expand
        prefixed names, group triples by subject, and yield
        FilteredEntity when the subject changes.

        Args:
            fpath: Path to .ttl file.
            skip_until: Entity ID to skip to (checkpoint resume).

        Yields:
            FilteredEntity for each YAGO resource with an English label.
        """
        prefixes: dict[str, str] = {}
        current_subject: str | None = None
        current_data: dict | None = None
        skip_mode = skip_until is not None
        line_count = 0

        with open(fpath, "r", encoding="utf-8") as f:
            for raw_line in f:
                line_count += 1
                line = raw_line.strip()

                # Skip empty lines
                if not line:
                    continue

                # Parse @prefix declarations
                if line.startswith("@prefix"):
                    self._parse_prefix_line(line, prefixes)
                    continue

                # Skip comment lines
                if line.startswith("#"):
                    continue

                # Skip schema definition lines (multi-line Turtle
                # blocks that use ; and , continuations). These start
                # with schema:, ys:, sh: prefixes and contain shape
                # definitions we don't need for entity extraction.
                # We detect them by checking if the line starts with
                # a known schema prefix or is a continuation (starts
                # with whitespace followed by a predicate).
                if line.startswith(("ys:", "sh:")):
                    continue
                if line.startswith(" ") or line.startswith("\t"):
                    # Continuation of a multi-line block — only in
                    # the schema header section. Once we hit entity
                    # data (yago: subjects), all lines are tab-sep
                    # single triples. But schema blocks at the top
                    # use indented continuations.
                    if current_subject is None:
                        continue

                # Parse triple: subject \t predicate \t object .
                triple = self._parse_triple_line(line, prefixes)
                if triple is None:
                    continue

                subj, pred, obj = triple

                # Only process yago: resource entities
                if not subj.startswith(YAGO_RESOURCE):
                    # Also accept schema.org subjects for taxonomy
                    if not subj.startswith(SCHEMA_ORG):
                        continue

                entity_id = self._iri_to_id(subj)

                # Handle checkpoint skip
                if skip_mode:
                    if entity_id == skip_until:
                        skip_mode = False
                    continue

                # Subject changed — yield previous entity
                if entity_id != current_subject:
                    if current_subject is not None and current_data:
                        entity = self._build_entity(
                            current_subject, current_data
                        )
                        if entity is not None:
                            yield entity

                    current_subject = entity_id
                    current_data = {
                        "labels": [],
                        "descriptions": [],
                        "aliases": [],
                        "types": [],
                        "subclass_of": [],
                        "same_as": [],
                        "see_also": [],
                        "wikidata_id": None,
                    }

                # Accumulate triple
                self._accumulate_triple(pred, obj, current_data)

        # Yield last entity
        if current_subject is not None and current_data:
            entity = self._build_entity(current_subject, current_data)
            if entity is not None:
                yield entity

        self.logger.info(
            f"Finished {fpath.name}: {line_count:,} lines"
        )

    def _parse_prefix_line(
        self, line: str, prefixes: dict[str, str]
    ) -> None:
        """Parse an @prefix line and add to prefix map."""
        # @prefix yago: <http://yago-knowledge.org/resource/> .
        parts = line.split()
        if len(parts) >= 3:
            prefix = parts[1].rstrip(":")
            iri = parts[2].strip("<>")
            prefixes[prefix] = iri

    def _parse_triple_line(
        self, line: str, prefixes: dict[str, str]
    ) -> tuple[str, str, str] | None:
        """Parse a tab-separated triple line.

        Expected format: subject \\t predicate \\t object .

        Returns:
            Tuple of (subject_iri, predicate_iri, object_str) or None.
        """
        # Remove trailing ' .'
        if line.endswith(" ."):
            line = line[:-2]
        elif line.endswith("\t."):
            line = line[:-2]
        elif line.endswith("."):
            line = line[:-1]

        line = line.strip()

        # Split on tabs
        parts = line.split("\t")
        if len(parts) < 3:
            # Try splitting on multiple spaces for schema lines
            parts = line.split(None, 2)
            if len(parts) < 3:
                return None

        subj_raw = parts[0].strip()
        pred_raw = parts[1].strip()
        obj_raw = parts[2].strip()

        # Expand prefixes for subject and predicate
        subj = _expand_prefix(subj_raw, prefixes)
        pred = _expand_prefix(pred_raw, prefixes)

        return subj, pred, obj_raw

    def _iri_to_id(self, iri: str) -> str:
        """Convert a full IRI to a short entity ID."""
        if iri.startswith(YAGO_RESOURCE):
            return iri[len(YAGO_RESOURCE):]
        if iri.startswith(SCHEMA_ORG):
            return iri[len(SCHEMA_ORG):]
        return iri

    def _accumulate_triple(
        self, pred: str, obj_raw: str, data: dict
    ) -> None:
        """Accumulate a triple into the entity data dict."""
        # rdfs:label or schema:name
        if pred in (
            "http://www.w3.org/2000/01/rdf-schema#label",
            f"{SCHEMA_ORG}name",
        ):
            value, lang = _parse_literal(obj_raw)
            if _is_english_lang(lang):
                data["labels"].append(value)

        # rdfs:comment or schema:description
        elif pred in (
            "http://www.w3.org/2000/01/rdf-schema#comment",
            f"{SCHEMA_ORG}description",
        ):
            value, lang = _parse_literal(obj_raw)
            if _is_english_lang(lang):
                data["descriptions"].append(value)

        # schema:alternateName
        elif pred == f"{SCHEMA_ORG}alternateName":
            value, lang = _parse_literal(obj_raw)
            if _is_english_lang(lang):
                data["aliases"].append(value)

        # rdf:type
        elif pred == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type":
            type_id = _extract_yago_id(obj_raw)
            if type_id:
                data["types"].append(type_id)

        # rdfs:subClassOf
        elif pred == "http://www.w3.org/2000/01/rdf-schema#subClassOf":
            parent_id = _extract_yago_id(obj_raw)
            if parent_id:
                data["subclass_of"].append(parent_id)

        # owl:sameAs or schema:sameAs
        elif pred in (
            "http://www.w3.org/2002/07/owl#sameAs",
            f"{SCHEMA_ORG}sameAs",
        ):
            # obj_raw might be a prefixed name or a literal
            value, _ = _parse_literal(obj_raw)
            qid = _extract_wikidata_qid(value)
            if qid:
                data["wikidata_id"] = qid
            data["same_as"].append(value)

    def _build_entity(
        self, entity_id: str, data: dict
    ) -> FilteredEntity | None:
        """Build a FilteredEntity from accumulated triple data."""
        label = data["labels"][0] if data["labels"] else None
        if not label:
            return None

        description = (
            data["descriptions"][0] if data["descriptions"] else None
        )

        # Use wikidata Q-ID if available, else YAGO ID
        eid = data.get("wikidata_id") or entity_id

        return FilteredEntity(
            entity_id=eid,
            label=label,
            description=description,
            instance_of=data["types"],
            subclass_of=data["subclass_of"],
            aliases=data["aliases"],
            see_also=data["see_also"],
        )

    def _save_checkpoint(self) -> None:
        """Save checkpoint with last processed entity ID."""
        checkpoint_data = {
            "last_entity_id": self._last_checkpoint_entity_id,
            "last_processed_timestamp": datetime.utcnow().isoformat(),
            "processed_count": self._processed_count,
        }
        try:
            with open(self._checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2)
        except IOError as e:
            self.logger.warning(f"Failed to save checkpoint: {e}")

    def get_checkpoint(self) -> dict | None:
        if not self._checkpoint_file.exists():
            return None
        try:
            with open(self._checkpoint_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def clear_checkpoint(self) -> None:
        if self._checkpoint_file.exists():
            self._checkpoint_file.unlink()
            self._last_checkpoint_entity_id = None
            self.logger.info("Checkpoint cleared")

    def get_memory_usage_mb(self) -> float:
        return self._memory_tracker.get_current_mb()

    def get_peak_memory_mb(self) -> float:
        return self._memory_tracker.get_peak_mb()
