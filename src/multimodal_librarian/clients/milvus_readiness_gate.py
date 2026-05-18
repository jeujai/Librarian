"""Milvus readiness gate: data contracts, structured log, and gate class.

This module hosts the :class:`ReadinessStatus` dataclass, the
``milvus_readiness_evaluated`` structured log contract, and the
:class:`MilvusReadinessGate` class used to guard the Milvus
``knowledge_chunks`` collection after a stack restart.

Task 3.1 (already landed): data shape + log contract only.
Task 3.2 (this addition): :class:`MilvusReadinessGate` implementing the
design Track A pseudocode verbatim. DI wiring is deferred to task 3.3
and the Track B failure-callback hook (registered defensively here) is
activated when task 3.4 adds ``MilvusClient.register_failure_callback``.

See ``.kiro/specs/milvus-post-restart-retrieval-regression/design.md``
Tracks A and C for the full specification, and bugfix clauses 2.3, 2.4,
2.5, 2.6 for the requirements this module helps satisfy once wired.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Any, Final, FrozenSet, Optional, Tuple

import structlog

# pymilvus is the project's vector backend. The imports are module-level
# so that unit tests (``tests/clients/test_milvus_readiness_gate_bug_condition.py``)
# can ``monkeypatch.setattr(mrg, "utility", ...)`` and
# ``monkeypatch.setattr(mrg, "Collection", ...)`` to redirect the gate's
# I/O onto in-memory fakes without requiring a live Milvus server.
try:
    from pymilvus import Collection, utility  # type: ignore[import]
    from pymilvus.exceptions import MilvusException  # type: ignore[import]

    _PYMILVUS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when pymilvus absent
    Collection = None  # type: ignore[assignment]
    utility = None  # type: ignore[assignment]

    class MilvusException(Exception):  # type: ignore[no-redef]
        """Fallback MilvusException stub when pymilvus is not installed."""

    _PYMILVUS_AVAILABLE = False

logger = structlog.get_logger(__name__)

#: Valid values for :attr:`ReadinessStatus.gate_decision`.
#:
#: Each decision maps 1:1 onto one of the candidate root causes RC1-RC5
#: per design Track C:
#:
#: * ``"ready"`` - all sub-checks passed; retrieval may proceed.
#: * ``"collection_missing"`` - ``utility.has_collection`` returned
#:   ``False`` (RC1, volume loss).
#: * ``"not_loaded"`` - ``Collection.load()`` has not completed since
#:   the most recent connection (RC2).
#: * ``"index_missing"`` - ``collection.indexes`` has no entry for the
#:   ``vector`` field (RC4).
#: * ``"entity_parity_failed"`` - ``abs(pg_chunk_count - num_entities)``
#:   exceeds the computed tolerance (RC1 or partial RC3).
#: * ``"connection_failed"`` - ``vector_client.connect()`` raised (RC5,
#:   or the server is actually unreachable).
GATE_DECISIONS: Final[FrozenSet[str]] = frozenset(
    {
        "ready",
        "collection_missing",
        "not_loaded",
        "index_missing",
        "entity_parity_failed",
        "connection_failed",
    }
)

#: Default Milvus collection name observed by the gate. Matches
#: ``MILVUS_COLLECTION_NAME`` in ``docker-compose.yml``.
DEFAULT_COLLECTION_NAME: Final[str] = "knowledge_chunks"

#: Structured log event name emitted by :func:`_emit_readiness_log`.
#: This constant is the single source of truth for the Track C log
#: contract and is referenced by tests that assert the event fires.
READINESS_LOG_EVENT: Final[str] = "milvus_readiness_evaluated"

#: SQL used for the PostgreSQL parity probe. Kept as a module-level
#: constant so any future schema change is a one-line edit. The
#: ``AS count`` alias ensures the returned row has a stable ``count``
#: key across SQLAlchemy dialect differences.
#:
#: The Milvus ``knowledge_chunks`` collection is a **superset** of the
#: PostgreSQL ``knowledge_chunks`` table: ``_store_bridge_embeddings_in_vector_db``
#: (see ``services/celery_service.py``) inserts LLM-generated bridge
#: vectors into the SAME Milvus collection while tracking them in the
#: separate ``multimodal_librarian.bridge_chunks`` table. The parity
#: check therefore sums both tables so the invariant
#: ``num_entities ≈ pg_chunk_count + pg_bridge_count`` holds on a
#: healthy system. Counting only ``knowledge_chunks`` incorrectly
#: reports ``entity_parity_failed`` on any system that has run bridge
#: generation, because Milvus legitimately holds more rows than the
#: single Postgres table.
_PG_CHUNK_COUNT_SQL: Final[str] = (
    "SELECT "
    "(SELECT COUNT(*) FROM multimodal_librarian.knowledge_chunks) "
    "+ "
    "(SELECT COUNT(*) FROM multimodal_librarian.bridge_chunks) "
    "AS count"
)


@dataclass(frozen=True)
class ReadinessStatus:
    """Snapshot of a single Milvus readiness-gate evaluation.

    Fields correspond exactly to the Track A ``ReadinessStatus``
    contract in
    ``.kiro/specs/milvus-post-restart-retrieval-regression/design.md``.
    The dataclass is frozen so a status captured at evaluation time
    cannot drift before being logged or returned to a caller.

    Attributes:
        ready: Overall readiness verdict. Only ``True`` when every
            sub-check succeeds and ``gate_decision == "ready"``.
        collection_exists: Whether ``utility.has_collection`` returned
            ``True`` for the target collection.
        is_loaded: Whether ``Collection.load()`` has completed since
            the most recent connection.
        has_vector_index: Whether ``collection.indexes`` contains an
            entry for the ``vector`` field.
        num_entities: ``collection.num_entities`` at evaluation time.
            Zero when the collection is missing or the probe failed.
        pg_chunk_count: Row count of
            ``multimodal_librarian.knowledge_chunks`` at evaluation
            time. Zero when the relational probe failed.
        delta: ``pg_chunk_count - num_entities``. Positive when
            PostgreSQL holds more rows than Milvus.
        tolerance: Absolute parity tolerance (in entities) applied when
            deciding ``entity_parity_failed``. Per design,
            ``max(1, ceil(parity_tolerance_fraction * pg_chunk_count))``.
        gate_decision: Exactly one of the tokens in
            :data:`GATE_DECISIONS`. Maps 1:1 onto RC1-RC5 per design
            Track C.
        evaluated_at: UNIX timestamp (seconds, ``time.time()``) at
            which the evaluation completed.
    """

    ready: bool
    collection_exists: bool
    is_loaded: bool
    has_vector_index: bool
    num_entities: int
    pg_chunk_count: int
    delta: int
    tolerance: int
    gate_decision: str
    evaluated_at: float

    def __post_init__(self) -> None:
        # Structural validation so misuse fails loudly at construction
        # rather than silently surfacing in logs downstream. This is
        # data-shape enforcement only; no I/O or runtime side effects.
        if self.gate_decision not in GATE_DECISIONS:
            raise ValueError(
                "gate_decision must be one of "
                f"{sorted(GATE_DECISIONS)}; got {self.gate_decision!r}"
            )
        if self.ready and self.gate_decision != "ready":
            raise ValueError(
                "ready=True requires gate_decision='ready'; "
                f"got {self.gate_decision!r}"
            )
        if not self.ready and self.gate_decision == "ready":
            raise ValueError(
                "gate_decision='ready' requires ready=True"
            )


def _emit_readiness_log(
    status: ReadinessStatus,
    *,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    evaluation_duration_ms: float = 0.0,
) -> None:
    """Emit the ``milvus_readiness_evaluated`` structured log event.

    Logs a single structured entry at ``INFO`` when ``status.ready`` is
    ``True`` and at ``WARNING`` otherwise, carrying the full field set
    from design Track C. This helper is the single diagnostic contract
    that lets RC1-RC5 be distinguished post-restart.

    ``connection_established`` is derived from
    ``status.gate_decision != "connection_failed"`` so there is exactly
    one source of truth per evaluation. ``evaluated_at_ms`` is derived
    from the dataclass's ``evaluated_at`` (seconds since epoch) in the
    same way.

    Args:
        status: The evaluated :class:`ReadinessStatus` to log.
        collection_name: Collection the gate was evaluated against.
            Defaults to :data:`DEFAULT_COLLECTION_NAME`.
        evaluation_duration_ms: Wall-clock duration of the evaluation,
            in milliseconds. Zero when unknown (the expected case for
            callers that build a status outside the gate's own
            evaluation path).
    """

    payload = {
        "collection_name": collection_name,
        "connection_established": status.gate_decision != "connection_failed",
        "collection_exists": status.collection_exists,
        "is_loaded": status.is_loaded,
        "has_vector_index": status.has_vector_index,
        "num_entities": status.num_entities,
        "pg_chunk_count": status.pg_chunk_count,
        "delta": status.delta,
        "tolerance": status.tolerance,
        "gate_decision": status.gate_decision,
        "evaluated_at_ms": int(status.evaluated_at * 1000),
        "evaluation_duration_ms": float(evaluation_duration_ms),
    }

    if status.ready:
        logger.info(READINESS_LOG_EVENT, **payload)
    else:
        logger.warning(READINESS_LOG_EVENT, **payload)


# ---------------------------------------------------------------------------
# MilvusReadinessGate — Track A primary fix path
# ---------------------------------------------------------------------------


class MilvusReadinessGate:
    """Readiness gate for the ``knowledge_chunks`` Milvus collection.

    Evaluates the ``CollectionStateInvariant`` from design Track A:

        1. ``vector_client`` is connected to the current Milvus server.
        2. ``utility.has_collection(collection_name)`` returns ``True``.
        3. ``Collection(collection_name).load()`` completes without
           raising :class:`~pymilvus.exceptions.MilvusException`.
        4. ``collection.indexes`` contains an entry with
           ``field_name == "vector"``.
        5. ``abs(pg_chunk_count - num_entities)`` is within
           ``max(1, ceil(parity_tolerance_fraction * pg_chunk_count))``,
           AND the collection is not empty while PostgreSQL holds rows
           (per design Track C RC1 fingerprint — tolerance floor of 1
           must not mask a full volume loss on small collections).

    The first failing check short-circuits the evaluation and sets the
    ``gate_decision`` token (``collection_missing`` / ``not_loaded`` /
    ``index_missing`` / ``entity_parity_failed`` / ``connection_failed``);
    the remaining probes are skipped. Only a fully-passing evaluation
    sets ``gate_decision="ready"`` and ``ready=True``.

    Caching: healthy-path results are cached for
    ``ready_cache_ttl_seconds`` (default 30s) so repeated
    ``is_ready()`` calls pay only an ``O(1)`` read (design P9,
    Requirements 3.6). Failing results are cached for the shorter
    ``not_ready_cache_ttl_seconds`` (default 2s) so a recovering
    collection is picked up quickly without hammering the server.

    DI steering compliance: ``__init__`` performs no network I/O — it
    only stores references and defensively registers a Track B failure
    callback via ``vector_client.register_failure_callback(...)`` when
    that method exists (task 3.4 adds it). All Milvus and PostgreSQL
    probes happen inside :meth:`readiness_status` /
    :meth:`_evaluate_readiness`, never at import or construction time.

    Thread safety: an :class:`asyncio.Lock` serializes the evaluation
    path so two concurrent ``is_ready()`` calls share a single underlying
    probe (rather than each issuing redundant Milvus round-trips).

    Non-destructive guarantee: this class reads from Milvus and
    PostgreSQL and calls the idempotent ``Collection.load()``. It never
    calls ``utility.drop_collection``, never deletes a volume, and
    never writes to either store (design P8, bugfix 3.5 / 3.7).
    """

    def __init__(
        self,
        vector_client: Any,
        relational_client: Any,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        parity_tolerance_fraction: float = 0.01,
        ready_cache_ttl_seconds: float = 30.0,
        not_ready_cache_ttl_seconds: float = 2.0,
    ) -> None:
        """Construct a readiness gate.

        Args:
            vector_client: A ``VectorStoreClient`` (``MilvusClient`` in
                the local environment). Used only to determine the
                pymilvus connection alias via ``connection_name`` and
                to trigger a reconnect via ``connect()`` when the
                client reports itself disconnected. Must expose a
                ``connection_name`` attribute; optionally a
                ``register_failure_callback`` method (task 3.4).
            relational_client: A ``RelationalStoreClient`` (the local
                PostgreSQL client). Used only via
                ``execute_query(sql)`` for the
                ``SELECT COUNT(*) FROM multimodal_librarian.knowledge_chunks``
                parity probe.
            collection_name: Milvus collection to guard. Defaults to
                :data:`DEFAULT_COLLECTION_NAME`.
            parity_tolerance_fraction: Fraction of ``pg_chunk_count``
                tolerated as in-flight drift between PostgreSQL commit
                and Milvus flush. Default 1 % with a floor of 1 (see
                design "Parity tolerance choice").
            ready_cache_ttl_seconds: How long a ``ready=True`` verdict
                is reused without re-probing.
            not_ready_cache_ttl_seconds: How long a ``ready=False``
                verdict is reused before re-probing. Kept short so a
                recovering collection is picked up promptly.
        """

        self._vector_client = vector_client
        self._relational_client = relational_client
        self._collection_name = collection_name
        self._parity_tolerance_fraction = parity_tolerance_fraction
        self._ready_cache_ttl_seconds = ready_cache_ttl_seconds
        self._not_ready_cache_ttl_seconds = not_ready_cache_ttl_seconds

        self._lock = asyncio.Lock()
        self._cached_status: Optional[ReadinessStatus] = None
        self._cached_at: float = 0.0
        self._closed: bool = False

        # Track B hook (task 3.4). Register defensively so this class
        # remains compatible with an unmodified MilvusClient — tests in
        # task 3.2 assert that the callback IS registered when the
        # client supports it; callers running against a client that has
        # not yet added ``register_failure_callback`` see a silent skip.
        self._register_failure_callback()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def is_ready(self) -> bool:
        """Return whether retrieval is currently safe to serve.

        Convenience wrapper around :meth:`readiness_status`. Callers
        that only care about the boolean verdict should prefer this.
        Honors the TTL cache, so on the healthy path a burst of
        concurrent requests pays only a single O(1) read after the
        first evaluation (design P9, Requirements 3.6).
        """

        status = await self.readiness_status()
        return status.ready

    async def readiness_status(self) -> ReadinessStatus:
        """Evaluate (or serve from cache) the current readiness status.

        Honors the ``ready_cache_ttl_seconds`` /
        ``not_ready_cache_ttl_seconds`` window and emits the Track C
        structured log event exactly once per fresh evaluation (never
        on a cache hit, so the log is a faithful audit trail of probe
        activity).

        Returns:
            The frozen :class:`ReadinessStatus` snapshot for the
            current evaluation window.
        """

        async with self._lock:
            cached = self._cached_status
            now = time.time()
            if cached is not None and not self._closed:
                ttl = (
                    self._ready_cache_ttl_seconds
                    if cached.ready
                    else self._not_ready_cache_ttl_seconds
                )
                if (now - self._cached_at) < ttl:
                    return cached

            status, duration_ms = await self._evaluate_readiness()
            self._cached_status = status
            self._cached_at = status.evaluated_at

            # Single call site for the Track C log contract.
            _emit_readiness_log(
                status,
                collection_name=self._collection_name,
                evaluation_duration_ms=duration_ms,
            )
            return status

    async def invalidate(self) -> None:
        """Drop the cached readiness status without re-evaluating.

        Called by Track B (task 3.4) via the failure-callback hook when
        a runtime search raises
        :class:`~pymilvus.exceptions.MilvusException` classified as
        ``"collection not loaded"`` or
        ``ConnectionNotExistException``. The next
        :meth:`readiness_status` call performs a fresh probe, so a
        stale ``ready=True`` cannot survive a silent server restart.
        """

        async with self._lock:
            self._cached_status = None
            self._cached_at = 0.0

    async def close(self) -> None:
        """Release resources and mark the gate unusable for caching.

        Idempotent: calling twice is safe. Wired into
        ``cleanup_all_dependencies`` by task 3.3. The gate does not own
        the underlying clients, so we do NOT call
        ``vector_client.disconnect()`` or
        ``relational_client.disconnect()`` here — lifecycle of those
        belongs to their own DI providers.
        """

        async with self._lock:
            self._cached_status = None
            self._cached_at = 0.0
            self._closed = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _register_failure_callback(self) -> None:
        """Defensively register ``self.invalidate`` with the vector client.

        Task 3.4 adds ``MilvusClient.register_failure_callback``; until
        it lands, the attribute may be absent and this is a no-op. We
        swallow any raise so gate construction remains side-effect-free
        per the DI steering "no import-time I/O" contract.
        """

        try:
            register = getattr(
                self._vector_client, "register_failure_callback", None
            )
            if callable(register):
                register(self.invalidate)
        except Exception:  # pragma: no cover - purely defensive
            # Registration must never prevent gate construction.
            # The failure mode without Track B is "stale ready=True may
            # persist for up to ready_cache_ttl_seconds after a silent
            # server restart" — acceptable per design until task 3.4.
            pass

    async def _evaluate_readiness(self) -> Tuple[ReadinessStatus, float]:
        """Run the full five-step readiness evaluation.

        Implements the ``evaluateReadiness`` pseudocode from design
        Track A verbatim. Returns both the frozen status and the
        wall-clock duration so the caller can populate the Track C log
        payload without re-timing.
        """

        start = time.time()
        loop = asyncio.get_running_loop()

        # Evaluation accumulator — populated as each step succeeds.
        collection_exists = False
        is_loaded = False
        has_vector_index = False
        num_entities = 0
        pg_chunk_count = 0
        gate_decision = "ready"
        ready = True

        # --- Step 1: connection -------------------------------------
        # MilvusClient exposes ``_connected: bool`` (see
        # ``clients/milvus_client.py`` line ~203). The gate only
        # reconnects when the client reports itself disconnected, so
        # healthy-path evaluations never trigger a redundant connect().
        if not getattr(self._vector_client, "_connected", True):
            try:
                await self._vector_client.connect()
            except Exception:
                gate_decision = "connection_failed"
                ready = False

        # --- Step 2: has_collection ---------------------------------
        if gate_decision == "ready":
            try:
                alias = getattr(
                    self._vector_client, "connection_name", "default"
                )
                has_collection = await loop.run_in_executor(
                    None,
                    lambda: utility.has_collection(
                        self._collection_name, using=alias
                    ),
                )
                collection_exists = bool(has_collection)
            except Exception:
                # Utility probe failure → treat as connection failure.
                # has_collection raises only when the underlying
                # pymilvus connection is broken — design Track C maps
                # this to ``connection_failed``.
                gate_decision = "connection_failed"
                ready = False

            if gate_decision == "ready" and not collection_exists:
                gate_decision = "collection_missing"
                ready = False

        # --- Step 3: Collection(...).load() -------------------------
        collection: Any = None
        if gate_decision == "ready":
            try:
                alias = getattr(
                    self._vector_client, "connection_name", "default"
                )
                collection = Collection(
                    self._collection_name, using=alias
                )
                await loop.run_in_executor(None, collection.load)
                is_loaded = True
            except MilvusException:
                gate_decision = "not_loaded"
                ready = False
            except Exception:
                # Any unexpected failure during load is a not-loaded
                # state from the gate's point of view — the collection
                # is not safe to query.
                gate_decision = "not_loaded"
                ready = False

        # --- Step 4: index on ``vector`` field ----------------------
        if gate_decision == "ready" and collection is not None:
            try:
                indexes = await loop.run_in_executor(
                    None, lambda: collection.indexes
                )
            except Exception:
                indexes = []
            has_vector_index = any(
                getattr(idx, "field_name", None) == "vector"
                for idx in (indexes or [])
            )
            if not has_vector_index:
                gate_decision = "index_missing"
                ready = False

        # --- Step 5: num_entities -----------------------------------
        if gate_decision == "ready" and collection is not None:
            try:
                num_entities = int(
                    await loop.run_in_executor(
                        None, lambda: collection.num_entities
                    )
                )
            except Exception:
                num_entities = 0

        # --- Step 6: PostgreSQL parity probe ------------------------
        if gate_decision == "ready":
            try:
                rows = await self._relational_client.execute_query(
                    _PG_CHUNK_COUNT_SQL
                )
                pg_chunk_count = _extract_count(rows)
            except Exception:
                # Conservative: if we can't determine pg_chunk_count,
                # the parity invariant cannot be verified; refuse.
                gate_decision = "entity_parity_failed"
                ready = False

        # --- Step 7 & 8: tolerance + parity -------------------------
        tolerance = max(
            1,
            math.ceil(self._parity_tolerance_fraction * pg_chunk_count),
        )
        delta = pg_chunk_count - num_entities
        if gate_decision == "ready":
            # Standard parity check from the design pseudocode.
            parity_exceeded = abs(delta) > tolerance
            # Track C RC1 fingerprint: num_entities == 0 while
            # pg_chunk_count > 0 is volume loss, not in-flight drift —
            # the tolerance floor of 1 must not mask full data loss
            # on very small collections (design "Parity tolerance
            # choice": "a volume loss (delta = full count) is never
            # mistaken for in-flight inserts").
            full_volume_loss = num_entities == 0 and pg_chunk_count > 0
            if parity_exceeded or full_volume_loss:
                gate_decision = "entity_parity_failed"
                ready = False

        # --- Step 9: finalize ---------------------------------------
        status = ReadinessStatus(
            ready=ready,
            collection_exists=collection_exists,
            is_loaded=is_loaded,
            has_vector_index=has_vector_index,
            num_entities=num_entities,
            pg_chunk_count=pg_chunk_count,
            delta=delta,
            tolerance=tolerance,
            gate_decision=gate_decision,
            evaluated_at=time.time(),
        )
        duration_ms = (time.time() - start) * 1000.0
        return status, duration_ms


# ---------------------------------------------------------------------------
# Track D short-circuit — AWS OpenSearch path
# ---------------------------------------------------------------------------


class _AlwaysReadyReadinessGate:
    """Always-ready readiness-gate stand-in for non-Milvus vector clients.

    Per design Track D, the ``CollectionStateInvariant`` checks in
    :class:`MilvusReadinessGate` are specific to Milvus (pymilvus
    collection state, Milvus-side entity counts). On AWS the retrieval
    path uses ``OpenSearchClient`` and these invariants do not apply.

    The DI provider ``get_milvus_readiness`` returns an instance of this
    class when the resolved ``vector_client`` is not a ``MilvusClient``,
    so the AWS retrieval path reports ``ready=True`` and keeps its
    existing behavior. This keeps the gate's public surface compatible
    with callers (``await readiness.readiness_status()``) while making
    the short-circuit explicit and observable.
    """

    def __init__(
        self,
        *,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ) -> None:
        self._collection_name = collection_name

    async def is_ready(self) -> bool:
        return True

    async def readiness_status(self) -> ReadinessStatus:
        # Synthesize a ``ready`` status. Most fields are neutral zeros:
        # the gate is simply not evaluating Milvus-specific state on the
        # AWS path. ``evaluated_at`` is a real timestamp so callers that
        # log the result still see monotonic values.
        return ReadinessStatus(
            ready=True,
            collection_exists=True,
            is_loaded=True,
            has_vector_index=True,
            num_entities=0,
            pg_chunk_count=0,
            delta=0,
            tolerance=0,
            gate_decision="ready",
            evaluated_at=time.time(),
        )

    async def invalidate(self) -> None:
        # No cache on the AWS path — invalidate is a no-op.
        return None

    async def close(self) -> None:
        # No resources owned — close is a no-op.
        return None


def _extract_count(rows: Any) -> int:
    """Extract ``COUNT(*)`` from an ``execute_query`` result.

    ``LocalPostgreSQLClient.execute_query`` returns a list of column-keyed
    dicts. Across SQLAlchemy dialects the column name for ``COUNT(*)``
    varies (``count``, ``count_1``, ``count(*)``), so we tolerate all
    common shapes and fall back to the first value of the first row.
    Returns ``0`` for an empty / malformed result so the caller can
    decide what to do (the gate classifies that as
    ``entity_parity_failed``).
    """

    if not rows:
        return 0
    first = rows[0]
    if isinstance(first, dict):
        for key in ("count", "count_1", "count(*)", "COUNT(*)"):
            if key in first:
                try:
                    return int(first[key])
                except (TypeError, ValueError):
                    return 0
        # Fall back to the first value of the dict — tolerant of
        # unexpected column labels.
        for value in first.values():
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return 0
    if isinstance(first, (list, tuple)) and first:
        try:
            return int(first[0])
        except (TypeError, ValueError):
            return 0
    try:
        return int(first)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "DEFAULT_COLLECTION_NAME",
    "GATE_DECISIONS",
    "READINESS_LOG_EVENT",
    "MilvusReadinessGate",
    "ReadinessStatus",
    "_AlwaysReadyReadinessGate",
    "_emit_readiness_log",
    "logger",
]
