"""
ActiveJobsDispatcher — fan-out real-time progress events to Active Jobs subscribers.

Receives progress events from the Redis progress subscriber, applies per-document
throttling, and broadcasts ActiveJobsUpdateMessages to all WebSocket connections
that have subscribed to active-jobs updates.

Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3,
              6.1, 6.2, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import structlog

from ..api.models.active_jobs_models import (
    ActiveJobPayload,
    ActiveJobsSnapshotMessage,
    ActiveJobsUpdateMessage,
    SubstageInfo,
)

logger = structlog.get_logger(__name__)


class ActiveJobsDispatcher:
    """Receives progress events, throttles per-document, and broadcasts to subscribers."""

    def __init__(
        self,
        connection_manager: Any,
        processing_status_service: Any,
        status_report_service: Optional[Any] = None,
        throttle_interval_ms: int = 1000,
    ) -> None:
        self._connection_manager = connection_manager
        self._processing_status_service = processing_status_service
        self._status_report_service = status_report_service

        # Env var override for throttle (Req 8.3)
        env_interval = os.environ.get("ACTIVE_JOBS_UPDATE_INTERVAL_MS")
        if env_interval is not None:
            try:
                throttle_interval_ms = int(env_interval)
            except (ValueError, TypeError):
                pass

        self._throttle_interval_s: float = throttle_interval_ms / 1000.0

        # Per-document throttle bookkeeping
        self._last_sent: Dict[str, float] = {}          # doc_id -> monotonic timestamp
        self._pending_state: Dict[str, dict] = {}        # doc_id -> latest event_data
        self._flush_tasks: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Payload construction (Req 2.2, 6.1, 6.2)
    # ------------------------------------------------------------------

    async def _build_job_payload(self, event_data: dict) -> ActiveJobPayload:
        """Construct an ActiveJobPayload from a progress event dict."""
        doc_id = str(event_data.get("document_id", ""))

        # Elapsed time calculation (Req 6.1, 6.2)
        elapsed: Optional[float] = None
        started_at = event_data.get("started_at")
        tracker = self._get_tracker(doc_id)
        if started_at is not None:
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at)
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        else:
            # Try to get started_at from in-memory tracker
            if tracker is not None and tracker.started_at is not None:
                sa = tracker.started_at
                if sa.tzinfo is None:
                    sa = sa.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - sa).total_seconds()

        # Substage inclusion (Req 3.1, 3.2, 3.3)
        substages = self._read_substages(doc_id)

        # Get title from event data, or fall back to in-memory tracker filename,
        # or finally look up from database
        title = (
            event_data.get("document_title")
            or event_data.get("title")
        )
        if not title and tracker is not None:
            title = tracker.filename
            # Don't use "unknown" as a valid title
            if title == "unknown":
                title = None
        if not title:
            # Last resort: look up from database
            title = await self._lookup_document_title(doc_id)
        if not title:
            # Use document_id as fallback so the UI never shows "Unknown"
            title = f"Document {doc_id[:8]}…"
        return ActiveJobPayload(
            document_id=doc_id,
            document_title=title,
            status=event_data.get("status", "running"),
            current_step=event_data.get("current_step"),
            progress_percentage=int(event_data.get("progress_percentage", 0)),
            elapsed_seconds=elapsed,
            retry_count=int(event_data.get("retry_count", 0)),
            substages=substages,
            error_message=event_data.get("error_message"),
        )

    def _get_tracker(self, document_id: str) -> Any:
        """Safely retrieve the in-memory tracker for a document."""
        if self._processing_status_service is None:
            return None
        try:
            tracking = getattr(self._processing_status_service, "_tracking", {})
            return tracking.get(document_id)
        except Exception:
            return None

    async def _lookup_document_title(self, document_id: str) -> Optional[str]:
        """Look up document title from database via StatusReportService."""
        if self._status_report_service is None:
            return None
        try:
            db_client = getattr(self._status_report_service, "_db_client", None)
            if db_client is None:
                return None
            rows = await db_client.execute_query(
                """
                SELECT COALESCE(NULLIF(title, ''), file_path, 'Untitled') AS title
                FROM multimodal_librarian.knowledge_sources
                WHERE id = $1::uuid
                """,
                document_id
            )
            if rows and len(rows) > 0:
                return rows[0].get("title")
        except Exception:
            pass
        return None

    @staticmethod
    def _read_substages(document_id: str) -> Optional[List[SubstageInfo]]:
        """Read Redis substage fractions and return SubstageInfo list or None."""
        try:
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

            return [
                SubstageInfo(label="Bridges", percentage=min(int(b * 100), 100)),
                SubstageInfo(label="KG", percentage=min(int(k * 100), 100)),
            ]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Progress event handler (Req 2.1, 2.3, 2.4, 3.1, 3.2, 3.3)
    # ------------------------------------------------------------------

    async def on_progress_event(self, event_data: dict) -> None:
        """Called by _redis_progress_subscriber for every progress message.

        Accumulates latest state per document and flushes on throttle interval.
        Completion and failure events are flushed immediately.
        """
        doc_id = str(event_data.get("document_id", ""))
        if not doc_id:
            return

        subscribers = self._connection_manager.get_active_jobs_subscribers()
        if not subscribers:
            return

        msg_type = event_data.get("type")
        status = event_data.get("status", "running")

        # Enrich event_data with failure info (Req 2.4)
        if msg_type == "failure" or status == "failed":
            event_data.setdefault("status", "failed")
            event_data.setdefault(
                "error_message",
                event_data.get("error", "Unknown error"),
            )

        # Completion events (Req 2.3)
        if msg_type == "completion" or status == "completed":
            event_data["status"] = "completed"

        # Accumulate latest state
        self._pending_state[doc_id] = event_data

        # Terminal events flush immediately
        if event_data.get("status") in ("completed", "failed"):
            await self._flush_throttled(doc_id)
            return

        # Throttle check
        now = time.monotonic()
        last = self._last_sent.get(doc_id, 0.0)
        if now - last >= self._throttle_interval_s:
            await self._flush_throttled(doc_id)
        else:
            # Schedule a deferred flush if not already pending
            if doc_id not in self._flush_tasks:
                delay = self._throttle_interval_s - (now - last)
                loop = asyncio.get_running_loop()
                self._flush_tasks[doc_id] = loop.call_later(
                    delay,
                    lambda did=doc_id: asyncio.ensure_future(
                        self._deferred_flush(did)
                    ),
                )

    async def _deferred_flush(self, document_id: str) -> None:
        """Callback for scheduled throttle flush."""
        self._flush_tasks.pop(document_id, None)
        if document_id in self._pending_state:
            await self._flush_throttled(document_id)

    # ------------------------------------------------------------------
    # Throttled flush (Req 2.1, 3.1, 3.2, 3.3, 8.1, 8.2)
    # ------------------------------------------------------------------

    async def _flush_throttled(self, document_id: str) -> None:
        """Send the latest accumulated state for a document to all subscribers."""
        event_data = self._pending_state.pop(document_id, None)
        if event_data is None:
            return

        # Cancel any pending deferred flush
        task = self._flush_tasks.pop(document_id, None)
        if task is not None and hasattr(task, "cancel"):
            task.cancel()

        self._last_sent[document_id] = time.monotonic()

        # Clean up throttle state for terminal events
        if event_data.get("status") in ("completed", "failed"):
            self._last_sent.pop(document_id, None)

        try:
            payload = await self._build_job_payload(event_data)
        except Exception as exc:
            logger.error(
                "Failed to build job payload",
                document_id=document_id,
                error=str(exc),
            )
            return

        message = ActiveJobsUpdateMessage(
            job=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        msg_dict = message.model_dump()

        subscribers: Set[str] = set(
            self._connection_manager.get_active_jobs_subscribers()
        )
        failed_connections: List[str] = []

        for conn_id in subscribers:
            try:
                await self._connection_manager.send_personal_message(
                    msg_dict, conn_id
                )
            except Exception as exc:
                logger.error(
                    "Failed to send active_jobs_update",
                    connection_id=conn_id,
                    document_id=document_id,
                    error=str(exc),
                )
                failed_connections.append(conn_id)

        # Remove failed connections from subscriber set
        for conn_id in failed_connections:
            try:
                self._connection_manager.unsubscribe_active_jobs(conn_id)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Initial snapshot (Req 4.1, 4.2, 4.3, 7.1, 7.2, 7.3)
    # ------------------------------------------------------------------

    async def send_initial_snapshot(self, connection_id: str) -> None:
        """Send full active_jobs_snapshot to a newly subscribed connection."""
        jobs: List[ActiveJobPayload] = []
        error_msg: Optional[str] = None

        try:
            jobs = await self._build_snapshot_jobs()
        except Exception as exc:
            logger.error("Failed to build snapshot", error=str(exc))
            error_msg = f"Failed to build active jobs snapshot: {exc}"

        message = ActiveJobsSnapshotMessage(
            jobs=jobs,
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=error_msg,
        )

        try:
            await self._connection_manager.send_personal_message(
                message.model_dump(), connection_id
            )
        except Exception as exc:
            logger.error(
                "Failed to send snapshot",
                connection_id=connection_id,
                error=str(exc),
            )
            try:
                self._connection_manager.unsubscribe_active_jobs(connection_id)
            except Exception:
                pass

    async def _build_snapshot_jobs(self) -> List[ActiveJobPayload]:
        """Query DB + in-memory data and reshape into job payloads.

        Graceful degradation (Req 7.1, 7.2, 7.3):
        - PSS unavailable → DB only
        - DB unavailable → in-memory only
        - Both unavailable → empty list (caller sets error)
        """
        db_jobs: Optional[List[Dict[str, Any]]] = None
        db_available = False

        # Attempt DB fetch via StatusReportService
        if self._status_report_service is not None:
            try:
                db_jobs = await self._status_report_service._fetch_active_jobs()
                db_available = True
            except Exception as exc:
                logger.warning("DB fetch failed for snapshot", error=str(exc))

        # Merge with in-memory data if DB succeeded
        if db_available and db_jobs is not None:
            srs = self._status_report_service
            if self._processing_status_service is not None and srs:
                try:
                    db_jobs = srs._merge_in_memory_data(db_jobs)
                except Exception as exc:
                    logger.warning("In-memory merge failed", error=str(exc))
            else:
                logger.warning("PSS unavailable, snapshot from DB only")
        elif not db_available:
            # DB unavailable — try in-memory only (Req 7.2)
            if self._processing_status_service is not None:
                try:
                    db_jobs = self._build_in_memory_only_jobs()
                except Exception as exc:
                    logger.warning("In-memory snapshot failed", error=str(exc))
                    raise
            else:
                # Both unavailable (Req 7.3)
                raise RuntimeError("Both DB and PSS unavailable for snapshot")

        if db_jobs is None:
            db_jobs = []

        return self._rows_to_payloads(db_jobs)

    def _build_in_memory_only_jobs(self) -> List[Dict[str, Any]]:
        """Build synthetic job rows from in-memory tracking only."""
        tracking = getattr(self._processing_status_service, "_tracking", {})
        rows: List[Dict[str, Any]] = []
        for doc_id, tracker in tracking.items():
            if tracker.status.value in ("completed", "failed"):
                continue
            rows.append(
                {
                    "source_id": doc_id,
                    "status": tracker.status.value,
                    "progress_percentage": tracker.progress_percentage,
                    "current_step": tracker.current_stage,
                    "started_at": tracker.started_at,
                    "retry_count": 0,
                    "error_message": tracker.error_message,
                    "document_title": tracker.filename,
                }
            )
        return rows

    def _rows_to_payloads(
        self, rows: List[Dict[str, Any]]
    ) -> List[ActiveJobPayload]:
        """Convert merged DB/in-memory rows to ActiveJobPayload objects."""
        payloads: List[ActiveJobPayload] = []
        for row in rows:
            doc_id = str(row.get("source_id", row.get("id", "")))

            # Elapsed time (Req 6.1, 6.2)
            elapsed: Optional[float] = None
            started_at = row.get("started_at")
            if started_at is not None:
                if isinstance(started_at, str):
                    started_at = datetime.fromisoformat(started_at)
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

            substages = self._read_substages(doc_id)

            payloads.append(
                ActiveJobPayload(
                    document_id=doc_id,
                    document_title=row.get("document_title", ""),
                    status=row.get("status", "running"),
                    current_step=row.get("current_step"),
                    progress_percentage=int(row.get("progress_percentage", 0)),
                    elapsed_seconds=elapsed,
                    retry_count=int(row.get("retry_count", 0)),
                    substages=substages,
                    error_message=row.get("error_message"),
                )
            )
        return payloads
