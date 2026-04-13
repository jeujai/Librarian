"""
Service for generating processing status reports.

Aggregates data from PostgreSQL (processing_jobs + knowledge_sources)
and optionally merges in-memory tracking data from ProcessingStatusService
to produce structured StatusReport payloads delivered over WebSocket.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.2, 3.5, 4.4
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog

from multimodal_librarian.api.models.chat_document_models import (
    JobDetail,
    ReportSummary,
    StatusReport,
)

logger = structlog.get_logger(__name__)


class StatusReportService:
    """Generates processing status reports from DB + in-memory data."""

    def __init__(
        self,
        db_client: Any,
        processing_status_service: Any = None,
        recent_window_minutes: int = 30,
    ):
        """
        Args:
            db_client: RelationalStoreClient for PostgreSQL queries.
            processing_status_service: Optional ProcessingStatusService for
                in-memory progress augmentation.
            recent_window_minutes: How far back to include completed/failed
                jobs (default 30 minutes).
        """
        self._db_client = db_client
        self._processing_status_service = processing_status_service
        self._recent_window_minutes = recent_window_minutes

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_report(self) -> StatusReport:
        """Orchestrate fetch, merge, build summary, return StatusReport.

        Returns a zero-count report when no jobs exist (Req 2.6).
        Returns an error-style report when the DB is unreachable (Req 4.4).

        After calling this method, ``last_job_metadata_map`` is populated
        with a ``{document_id: job_metadata_dict}`` mapping that can be
        forwarded to :meth:`format_human_summary` for model-failure
        substage rows.
        """
        try:
            active_rows = await self._fetch_active_jobs()
            recent_rows = await self._fetch_recent_jobs()
        except Exception as exc:
            logger.error(
                "Database unavailable for status report",
                error=str(exc),
            )
            self.last_job_metadata_map: Dict[str, Dict[str, Any]] = {}
            return self._error_report(
                "Status information is temporarily unavailable."
            )

        # Merge in-memory tracking data when available
        active_rows = self._merge_in_memory_data(active_rows)

        all_rows = active_rows + recent_rows

        # Build metadata map for format_human_summary substage rows
        import json as _json
        meta_map: Dict[str, Dict[str, Any]] = {}
        for row in all_rows:
            doc_id = str(row.get("source_id", row.get("id", "")))
            meta = row.get("job_metadata")
            if isinstance(meta, str):
                meta = _json.loads(meta) if meta else {}
            if meta:
                meta_map[doc_id] = meta
        self.last_job_metadata_map = meta_map

        jobs = self._rows_to_job_details(all_rows)
        summary = self._build_summary(jobs)

        return StatusReport(
            summary=summary,
            jobs=jobs,
            generated_at=datetime.now(timezone.utc),
        )

    def format_human_summary(self, summary: ReportSummary, jobs: Optional[List[JobDetail]] = None, job_metadata_map: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
        """Generate a tabular report with per-job details.

        When *jobs* is provided, renders tables grouped by status.
        Falls back to a short text line when no jobs exist.

        Requirement: 3.5
        """
        lines: List[str] = []

        if not jobs:
            lines.append("No active or recent processing jobs.")
            return "\n".join(lines)

        # Active / pending jobs table
        active = [j for j in jobs if j.status in ("pending", "running")]
        if active:
            lines.append("**Active Jobs**")
            lines.append("")
            lines.append(
                "| Document | Status | Step | Progress | Elapsed | Retries |"
            )
            lines.append(
                "|----------|--------|------|----------|---------|---------|"
            )
            for j in active:
                elapsed = self._fmt_elapsed(j.elapsed_seconds)
                title = self._truncate(j.document_title, 30)
                lines.append(
                    f"| {title} | {j.status} | {j.current_step or '—'} "
                    f"| {j.progress_percentage}% | {elapsed} | {j.retry_count} |"
                )
                # Add substage breakdown rows for parallel processing
                meta_for_doc = (job_metadata_map or {}).get(j.document_id)
                substages = self._get_substage_rows(j.document_id, job_metadata=meta_for_doc)
                if substages:
                    for label, pct in substages:
                        lines.append(
                            f"| | | ↳ {label} | {pct} | | |"
                        )

        # Completed jobs table
        completed = [j for j in jobs if j.status == "completed"]
        if completed:
            if active:
                lines.append("")
            lines.append("**Recently Completed**")
            lines.append("")
            lines.append(
                "| Document | Duration | Chunks | Step |"
            )
            lines.append(
                "|----------|----------|--------|------|"
            )
            for j in completed:
                duration = self._fmt_elapsed(j.total_processing_seconds)
                title = self._truncate(j.document_title, 30)
                chunks = str(j.chunk_count) if j.chunk_count is not None else "—"
                lines.append(
                    f"| {title} | {duration} | {chunks} "
                    f"| {j.current_step or '—'} |"
                )

        # Failed jobs table
        failed = [j for j in jobs if j.status == "failed"]
        if failed:
            if active or completed:
                lines.append("")
            lines.append("**Failed**")
            lines.append("")
            lines.append(
                "| Document | Failed Step | Error | Retry? |"
            )
            lines.append(
                "|----------|-------------|-------|--------|"
            )
            for j in failed:
                title = self._truncate(j.document_title, 30)
                err = self._truncate(j.error_message or "—", 40)
                retry = "Yes" if j.retry_available else "No"
                lines.append(
                    f"| {title} | {j.failed_step or '—'} "
                    f"| {err} | {retry} |"
                )

        if not active and not completed and not failed:
            lines.append("No active or recent processing jobs.")

        return "\n".join(lines)

    async def generate_throughput_report(
        self, offset: int = 0, limit: int = 10
    ) -> Tuple[str, int]:
        """Generate a paginated tabular throughput report for completed uploads.

        Includes per-stage durations from job_metadata.stage_timings when available.

        After calling this method, ``last_throughput_quality_data`` is
        populated with a list of quality gate dicts (one per table row,
        in order) that the frontend can use for the breakdown popup.

        Returns:
            A tuple of (markdown_text, total_count).
        """
        self.last_throughput_quality_data: List[Optional[Dict[str, Any]]] = []
        try:
            # Get total count first
            count_rows = await self._db_client.execute_query("""
                SELECT COUNT(*) AS total
                FROM multimodal_librarian.processing_jobs pj
                WHERE pj.status = 'completed'
                  AND pj.completed_at IS NOT NULL
                  AND pj.started_at IS NOT NULL
            """)
            total_count = count_rows[0]["total"] if count_rows else 0

            rows = await self._db_client.execute_query(f"""
                SELECT
                    ks.title,
                    ks.file_size,
                    pj.started_at,
                    pj.completed_at,
                    pj.job_metadata,
                    es.duration_ms AS enrichment_ms,
                    es.total_concepts,
                    (SELECT COUNT(*) FROM multimodal_librarian.knowledge_chunks kc
                     WHERE kc.source_id = ks.id) AS chunk_count
                FROM multimodal_librarian.processing_jobs pj
                JOIN multimodal_librarian.knowledge_sources ks ON pj.source_id = ks.id
                LEFT JOIN multimodal_librarian.enrichment_status es ON es.document_id = pj.source_id
                WHERE pj.status = 'completed'
                  AND pj.completed_at IS NOT NULL
                  AND pj.started_at IS NOT NULL
                ORDER BY pj.completed_at DESC
                OFFSET {offset} LIMIT {limit}
            """)
        except Exception as exc:
            logger.error("Throughput query failed", error=str(exc))
            return ("Throughput data is temporarily unavailable.", 0)

        if total_count == 0:
            return ("No completed uploads found.", 0)

        # Check if any row has stage_timings
        import json as _json
        has_stages = False
        for r in rows:
            meta = r.get("job_metadata")
            if isinstance(meta, str):
                meta = _json.loads(meta) if meta else {}
            if meta and meta.get("stage_timings"):
                has_stages = True
                break

        lines: List[str] = []
        lines.append("**Upload Telemetry**")
        lines.append("")

        if has_stages:
            lines.append(
                "| Document | Size | Chunks | Extract | Chunk+Embed | Bridges | KG | Model | Enrich | Finalize | Total |"
            )
            lines.append(
                "|----------|------|--------|---------|-------------|---------|-----|-------|--------|----------|-------|"
            )
        else:
            lines.append(
                "| Document | Size | Chunks | Enrichment |"
            )
            lines.append(
                "|----------|------|--------|------------|"
            )

        # When offset exceeds total rows, return heading + headers with empty body
        if not rows:
            return ("\n".join(lines), total_count)

        for r in rows:
            title = self._truncate(
                r.get("document_title") or r.get("title") or "Untitled", 28
            )
            file_size = r.get("file_size") or 0
            chunk_count = r.get("chunk_count") or 0
            started_at = r.get("started_at")
            completed_at = r.get("completed_at")
            enrichment_ms = r.get("enrichment_ms")
            total_concepts = r.get("total_concepts") or 0

            total_s: Optional[float] = None
            if started_at and completed_at:
                try:
                    total_s = (completed_at - started_at).total_seconds()
                except Exception:
                    total_s = None

            size_mb = file_size / (1024 * 1024) if file_size else 0
            if size_mb >= 1.0:
                size_str = f"{size_mb:.1f}MB"
            elif size_mb >= 0.01:
                size_str = f"{size_mb * 1024:.0f}KB"
            elif file_size:
                size_str = f"{file_size:,}B"
            else:
                size_str = "—"

            meta = r.get("job_metadata")
            if isinstance(meta, str):
                meta = _json.loads(meta) if meta else {}
            timings = (meta or {}).get("stage_timings", {})

            if has_stages:
                extract = self._fmt_elapsed(timings.get("extract_pdf"))
                chunks = self._fmt_elapsed(timings.get("generate_chunks"))
                bridges = self._fmt_elapsed(timings.get("generate_bridges"))
                kg = self._fmt_elapsed(timings.get("update_knowledge_graph"))
                model_str = self._fmt_quality_gate(meta)
                enrich = self._fmt_elapsed(
                    enrichment_ms / 1000 if enrichment_ms else None
                )
                finalize = self._fmt_elapsed(timings.get("finalize"))
                lines.append(
                    f"| {title} | {size_str} | {chunk_count:,} "
                    f"| {extract} | {chunks} | {bridges} | {kg} "
                    f"| {model_str} | {enrich} | {finalize} | {self._fmt_elapsed(total_s)} |"
                )
                # Collect quality gate data for frontend popup
                qg = (meta or {}).get("quality_gate")
                self.last_throughput_quality_data.append(qg)
            else:
                enrichment_str = self._fmt_elapsed(
                    enrichment_ms / 1000 if enrichment_ms else None
                )
                if total_concepts and enrichment_ms:
                    enrichment_str += f" ({total_concepts:,})"
                lines.append(
                    f"| {title} | {size_str} | {chunk_count:,} "
                    f"| {enrichment_str} |"
                )

        return ("\n".join(lines), total_count)

    async def generate_enrichment_report(self) -> str:
        """Generate a tabular enrichment report for all documents."""
        try:
            rows = await self._db_client.execute_query("""
                SELECT
                    ks.title,
                    es.state,
                    es.total_concepts,
                    es.concepts_enriched,
                    es.yago_hits,
                    es.conceptnet_hits,
                    es.cache_hits,
                    es.error_count,
                    es.duration_ms,
                    pj.job_metadata,
                    pj.status AS job_status
                FROM multimodal_librarian.enrichment_status es
                JOIN multimodal_librarian.knowledge_sources ks
                    ON es.document_id = ks.id
                LEFT JOIN multimodal_librarian.processing_jobs pj
                    ON pj.source_id = ks.id
                ORDER BY es.completed_at DESC NULLS LAST
            """)
        except Exception as exc:
            logger.error("Enrichment report query failed", error=str(exc))
            return "Enrichment data is temporarily unavailable."

        if not rows:
            return "No enrichment records found."

        lines: List[str] = []
        lines.append("**Enrichment Report**")
        lines.append("")
        lines.append(
            "| Document | State | Model Fail % | Concepts | Enriched | YAGO | ConceptNet | Cache | Errors | Duration |"
        )
        lines.append(
            "|----------|-------|--------------|----------|----------|------|------------|-------|--------|----------|"
        )

        import json as _json

        for r in rows:
            title = self._truncate(r.get("title") or "Untitled", 28)
            state = r.get("state") or "—"
            total = r.get("total_concepts") or 0
            enriched = r.get("concepts_enriched") or 0
            yago = r.get("yago_hits") or 0
            cn = r.get("conceptnet_hits") or 0
            cache = r.get("cache_hits") or 0
            errors = r.get("error_count") or 0
            duration_ms = r.get("duration_ms")
            dur_str = self._fmt_elapsed(duration_ms / 1000 if duration_ms else None)

            # Quality gate data from job_metadata
            meta = r.get("job_metadata")
            if isinstance(meta, str):
                meta = _json.loads(meta) if meta else {}
            qg = (meta or {}).get("quality_gate")

            if qg:
                model_fail_str = f"{qg['composite_rate'] * 100:.0f}%"
            else:
                model_fail_str = "—"

            # Override state when quality gate failed
            job_status = r.get("job_status")
            if qg and qg.get("passed") is False:
                state = "FAILED (QG)"
            elif job_status == "failed" and state not in ("FAILED (QG)",):
                # Keep existing state from enrichment_status unless QG override
                pass

            lines.append(
                f"| {title} | {state} | {model_fail_str} | {total:,} | {enriched:,} "
                f"| {yago:,} | {cn:,} | {cache:,} | {errors} | {dur_str} |"
            )

        return "\n".join(lines)


    async def generate_failed_uploads_report(self) -> str:
        """Generate a report of all failed upload jobs."""
        try:
            rows = await self._db_client.execute_query("""
                SELECT
                    ks.title,
                    pj.current_step,
                    pj.error_message,
                    pj.retry_count,
                    pj.started_at,
                    pj.completed_at,
                    pj.job_metadata
                FROM multimodal_librarian.processing_jobs pj
                JOIN multimodal_librarian.knowledge_sources ks
                    ON pj.source_id = ks.id
                WHERE pj.status = 'failed'
                ORDER BY pj.completed_at DESC NULLS LAST
            """)
        except Exception as exc:
            logger.error("Failed uploads query failed", error=str(exc))
            return "Failed uploads data is temporarily unavailable."

        if not rows:
            return "No failed uploads found. All uploads completed successfully."

        import json as _json

        lines: List[str] = []
        lines.append("**Failed Uploads**")
        lines.append("")
        lines.append(
            "| Document | Failed Step | Error | Retries | Duration |"
        )
        lines.append(
            "|----------|-------------|-------|---------|----------|"
        )

        for r in rows:
            title = self._truncate(r.get("title") or "Untitled", 28)
            step = r.get("current_step") or "—"
            error = self._truncate(r.get("error_message") or "—", 40)
            retries = r.get("retry_count") or 0
            started = r.get("started_at")
            completed = r.get("completed_at")
            dur: Optional[float] = None
            if started and completed:
                try:
                    dur = (completed - started).total_seconds()
                except Exception:
                    pass

            # Try to get the failed stage from job_metadata
            meta = r.get("job_metadata")
            if isinstance(meta, str):
                meta = _json.loads(meta) if meta else {}
            failed_stage = (meta or {}).get("failed_stage") or step

            lines.append(
                f"| {title} | {failed_stage} "
                f"| {error} | {retries} | {self._fmt_elapsed(dur)} |"
            )

        lines.append("")
        lines.append(f"Total: {len(rows)} failed upload(s)")

        return "\n".join(lines)

    @staticmethod
    def _get_substage_rows(document_id: str, job_metadata: Optional[Dict[str, Any]] = None) -> Optional[list]:
        """Read parallel substage percentages from Redis.
        Returns list of (label, pct_str) tuples, or None."""
        try:
            import json as _json
            import os

            import redis as _redis
            broker_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
            r = _redis.Redis.from_url(broker_url)
            bridge_val = r.get(f"docprog:{document_id}:bridges")
            kg_val = r.get(f"docprog:{document_id}:kg")
            if bridge_val is None and kg_val is None:
                return None
            b = float(bridge_val) if bridge_val else 0.0
            k = float(kg_val) if kg_val else 0.0
            if b >= 1.0 and k >= 1.0:
                return None
            rows = []
            b_pct = "done" if b >= 1.0 else f"{min(int(b * 100), 100)}%"
            k_pct = "done" if k >= 1.0 else f"{min(int(k * 100), 100)}%"
            rows.append(("Bridges", b_pct))
            rows.append(("KG", k_pct))

            # Add model failure substage when KG is running.
            # Check Redis first, then fall back to job_metadata.
            if k < 1.0:
                model_qg_raw = r.get(f"docprog:{document_id}:model_qg")
                qg = None
                if model_qg_raw:
                    try:
                        qg = _json.loads(model_qg_raw)
                    except (ValueError, TypeError):
                        pass
                if not qg and job_metadata:
                    qg = job_metadata.get("quality_gate")
                if qg and "composite_rate" in qg and "threshold" in qg:
                    comp_pct = f"{qg['composite_rate'] * 100:.0f}%"
                    thresh_pct = f"{qg['threshold'] * 100:.0f}%"
                    rows.append(("Model", f"{comp_pct}/{thresh_pct}"))

            return rows
        except Exception:
            return None

    @staticmethod
    def _fmt_elapsed(seconds: Optional[float]) -> str:
        """Format seconds into a human-readable duration string."""
        if seconds is None:
            return "—"
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            m, s = divmod(int(seconds), 60)
            return f"{m}m {s}s"
        h, remainder = divmod(int(seconds), 3600)
        m, s = divmod(remainder, 60)
        return f"{h}h {m}m"

    @staticmethod
    def _fmt_quality_gate(meta: Optional[Dict[str, Any]]) -> str:
        """Format the quality gate data for the Model column.

        Returns ``"composite%/threshold%"`` when data is available,
        prefixed with ``"⚠ "`` and suffixed with ``" (FAIL)"`` when the
        gate did not pass.  Returns ``"—"`` when no quality gate data
        exists (e.g. documents processed before this feature).
        """
        if not meta:
            return "—"
        qg = meta.get("quality_gate")
        if not qg:
            return "—"
        composite_pct = f"{qg['composite_rate'] * 100:.0f}%"
        threshold_pct = f"{qg['threshold'] * 100:.0f}%"
        if qg.get("passed") is False:
            return f"⚠ {composite_pct}/{threshold_pct} (FAIL)"
        return f"{composite_pct}/{threshold_pct}"

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """Truncate text with ellipsis if too long."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    async def _fetch_active_jobs(self) -> List[Dict[str, Any]]:
        """Query processing_jobs JOIN knowledge_sources.

        Active = status IN ('pending', 'running').
        Requirement: 2.1
        """
        query = """
            SELECT
                pj.id,
                pj.source_id,
                pj.status,
                pj.progress_percentage,
                pj.current_step,
                pj.started_at,
                pj.retry_count,
                pj.error_message,
                pj.job_metadata,
                COALESCE(NULLIF(ks.title, ''), ks.file_path, 'Untitled') AS document_title
            FROM multimodal_librarian.processing_jobs pj
            JOIN multimodal_librarian.knowledge_sources ks
                ON pj.source_id = ks.id
            WHERE pj.status IN ('pending', 'running')
            ORDER BY pj.started_at ASC
        """
        rows: List[Dict[str, Any]] = (
            await self._db_client.execute_query(query)
        )
        return rows

    async def _fetch_recent_jobs(self) -> List[Dict[str, Any]]:
        """Query processing_jobs JOIN knowledge_sources.

        Recent = completed/failed within the configured window.
        Requirement: 2.2
        """
        query = """
            SELECT
                pj.id,
                pj.source_id,
                pj.status,
                pj.progress_percentage,
                pj.current_step,
                pj.started_at,
                pj.completed_at,
                pj.retry_count,
                pj.error_message,
                pj.job_metadata,
                COALESCE(NULLIF(ks.title, ''), ks.file_path, 'Untitled') AS document_title
            FROM multimodal_librarian.processing_jobs pj
            JOIN multimodal_librarian.knowledge_sources ks
                ON pj.source_id = ks.id
            WHERE pj.status IN ('completed', 'failed')
              AND pj.completed_at >= NOW()
                  - INTERVAL ':minutes minutes'
            ORDER BY pj.completed_at DESC
        """
        filled = query.replace(
            ":minutes",
            str(self._recent_window_minutes),
        )
        rows: List[Dict[str, Any]] = (
            await self._db_client.execute_query(filled)
        )
        return rows

    # ------------------------------------------------------------------
    # In-memory merge (placeholder – full impl in Task 3)
    # ------------------------------------------------------------------

    def _merge_in_memory_data(
        self, db_jobs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge in-memory tracking data into DB job rows.

        For each active DB job, checks ProcessingStatusService._tracking
        for a matching document_id. Uses in-memory progress_percentage
        and current_stage when last_updated is more recent than the DB
        row's started_at (best available DB timestamp proxy).

        Jobs tracked in-memory but absent from DB are appended as
        synthetic rows so they appear in the report.

        Skips gracefully when ProcessingStatusService is None (Req 5.3).
        Requirements: 5.1, 5.2, 5.3
        """
        if self._processing_status_service is None:
            return db_jobs

        tracking: Dict[str, Any] = self._processing_status_service._tracking
        if not tracking:
            return db_jobs

        # Build set of document IDs already present in DB rows
        seen_doc_ids: set = set()
        merged: List[Dict[str, Any]] = []

        for row in db_jobs:
            doc_id = str(row.get("source_id", row.get("id", "")))
            seen_doc_ids.add(doc_id)

            tracker = tracking.get(doc_id)
            if tracker is None:
                merged.append(row)
                continue

            # Determine whether in-memory data is more recent
            db_timestamp = row.get("started_at")
            if db_timestamp is not None:
                if isinstance(db_timestamp, str):
                    db_timestamp = datetime.fromisoformat(db_timestamp)
                if db_timestamp.tzinfo is None:
                    db_timestamp = db_timestamp.replace(tzinfo=timezone.utc)

            mem_updated = tracker.last_updated
            if mem_updated is not None and mem_updated.tzinfo is None:
                mem_updated = mem_updated.replace(tzinfo=timezone.utc)

            if mem_updated is not None and (
                db_timestamp is None or mem_updated > db_timestamp
            ):
                # Prefer in-memory values (Req 5.1)
                updated_row = dict(row)
                updated_row["progress_percentage"] = (
                    tracker.progress_percentage
                )
                updated_row["current_step"] = tracker.current_stage
                merged.append(updated_row)
            else:
                merged.append(row)

        # Include jobs tracked in-memory but not yet in DB (Req 5.2)
        for doc_id, tracker in tracking.items():
            if doc_id in seen_doc_ids:
                continue
            # Skip completed/failed trackers — they aren't "active"
            if tracker.status.value in ("completed", "failed"):
                continue
            merged.append(
                {
                    "source_id": doc_id,
                    "status": tracker.status.value,
                    "progress_percentage": tracker.progress_percentage,
                    "current_step": tracker.current_stage,
                    "started_at": tracker.started_at,
                    "retry_count": 0,
                    "error_message": tracker.error_message,
                    "job_metadata": {},
                    "document_title": tracker.filename,
                }
            )

        return merged

    # ------------------------------------------------------------------
    # Transformation helpers
    # ------------------------------------------------------------------

    def _rows_to_job_details(
        self, rows: List[Dict[str, Any]]
    ) -> List[JobDetail]:
        """Convert raw DB rows into JobDetail models.

        Requirements: 2.3, 2.4, 2.5
        """
        jobs: List[JobDetail] = []
        now = datetime.now(timezone.utc)

        for row in rows:
            started_at = row.get("started_at")
            completed_at = row.get("completed_at")
            status = row.get("status", "pending")
            metadata = row.get("job_metadata") or {}

            # Elapsed seconds since started_at
            elapsed: Optional[float] = None
            if started_at:
                if isinstance(started_at, str):
                    started_at = datetime.fromisoformat(started_at)
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                elapsed = (now - started_at).total_seconds()

            # Total processing seconds for completed jobs
            total_processing: Optional[float] = None
            if status == "completed" and started_at and completed_at:
                if isinstance(completed_at, str):
                    completed_at = datetime.fromisoformat(completed_at)
                if completed_at.tzinfo is None:
                    completed_at = completed_at.replace(tzinfo=timezone.utc)
                total_processing = (completed_at - started_at).total_seconds()

            # Chunk count from job_metadata for completed jobs
            chunk_count: Optional[int] = None
            if status == "completed":
                chunk_count = metadata.get("chunk_count")

            # Failed job fields
            error_message: Optional[str] = None
            failed_step: Optional[str] = None
            retry_available = False
            if status == "failed":
                error_message = row.get("error_message")
                failed_step = row.get("current_step")
                retry_available = metadata.get("retry_available", False)

            jobs.append(
                JobDetail(
                    document_id=str(row.get("source_id", row.get("id", ""))),
                    document_title=row.get("document_title", "Untitled"),
                    status=status,
                    current_step=row.get("current_step"),
                    progress_percentage=int(row.get("progress_percentage", 0)),
                    elapsed_seconds=elapsed,
                    retry_count=int(row.get("retry_count", 0)),
                    total_processing_seconds=total_processing,
                    chunk_count=chunk_count,
                    error_message=error_message,
                    failed_step=failed_step,
                    retry_available=retry_available,
                )
            )
        return jobs

    def _build_summary(self, jobs: List[JobDetail]) -> ReportSummary:
        """Compute aggregate counts and mean progress.

        Requirement: 3.2
        """
        active = [j for j in jobs if j.status in ("pending", "running")]
        completed = [j for j in jobs if j.status == "completed"]
        failed = [j for j in jobs if j.status == "failed"]

        if active:
            total = sum(
                j.progress_percentage for j in active
            )
            overall_progress = total / len(active)
        else:
            overall_progress = 0.0

        return ReportSummary(
            total_active=len(active),
            total_completed_recent=len(completed),
            total_failed_recent=len(failed),
            overall_progress=overall_progress,
        )

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _error_report(message: str) -> StatusReport:
        """Return a minimal report conveying an error message."""
        return StatusReport(
            summary=ReportSummary(
                total_active=0,
                total_completed_recent=0,
                total_failed_recent=0,
                overall_progress=0.0,
            ),
            jobs=[],
            generated_at=datetime.now(timezone.utc),
        )
