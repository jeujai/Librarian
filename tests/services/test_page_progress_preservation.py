"""
Preservation Property Tests — Property 2

These tests capture the BASELINE behavior of the unfixed code for inputs
where the bug condition does NOT hold. They must PASS on unfixed code,
ensuring that the eventual fix does not regress non-buggy behavior.

Test cases:
1. Normal page progress: chunks where all page_number <= total_pages
   — verify current_page equals max(page_numbers)
2. Missing page metadata: chunks without page_number
   — verify current_page is NOT in metadata
3. Non-page metadata: verify chunks_stored_so_far, total_chunks,
   embeddings_stored_so_far are computed correctly
4. Progress percentage range: verify embedding progress is in 20–25%
   range, chunk progress in 15–20% range

**Validates: Requirements 1.4, 1.5**
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def _normal_chunk_strategy(total_pages: int):
    """
    Generate a single chunk dict with page_number in [1, total_pages].
    This is the NON-bug-condition: page_number <= total_pages.
    """
    return st.fixed_dictionaries({
        "id": st.uuids().map(str),
        "content": st.text(min_size=1, max_size=50),
        "chunk_type": st.just("text"),
        "metadata": st.fixed_dictionaries({
            "page_number": st.integers(min_value=1, max_value=total_pages),
            "chunk_index": st.integers(min_value=0, max_value=500),
            "content_type": st.just("text"),
        }),
    })


def _normal_chunks_with_pages():
    """
    Strategy producing (chunks, total_pages) where ALL page_number <= total_pages.
    """
    return (
        st.integers(min_value=1, max_value=200)
        .flatmap(lambda tp: st.tuples(
            st.lists(
                _normal_chunk_strategy(tp),
                min_size=1,
                max_size=10,
            ),
            st.just(tp),
        ))
    )


def _chunk_without_page_number():
    """
    Generate a single chunk dict WITHOUT page_number in metadata.
    """
    return st.fixed_dictionaries({
        "id": st.uuids().map(str),
        "content": st.text(min_size=1, max_size=50),
        "chunk_type": st.just("text"),
        "metadata": st.fixed_dictionaries({
            "chunk_index": st.integers(min_value=0, max_value=500),
            "content_type": st.just("text"),
        }),
    })


def _chunks_without_pages():
    """
    Strategy producing (chunks, total_pages) where NO chunk has page_number.
    """
    return st.tuples(
        st.lists(
            _chunk_without_page_number(),
            min_size=1,
            max_size=10,
        ),
        st.integers(min_value=1, max_value=200),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_metadata_from_calls(mock_update):
    """
    Return a list of metadata dicts passed to _update_job_status_sync
    via the `metadata=` keyword argument.
    """
    results = []
    for call in mock_update.call_args_list:
        meta = call.kwargs.get("metadata") if call.kwargs else None
        if meta and isinstance(meta, dict):
            results.append(meta)
    return results


def _collect_progress_from_calls(mock_update):
    """
    Return a list of progress float values (positional arg index 2)
    passed to _update_job_status_sync.
    """
    results = []
    for call in mock_update.call_args_list:
        if call.args and len(call.args) >= 3:
            results.append(float(call.args[2]))
    return results


# ---------------------------------------------------------------------------
# Test 1: Normal page progress — current_page equals max(page_numbers)
# ---------------------------------------------------------------------------

class TestNormalPageProgress:
    """
    **Validates: Requirements 1.4, 1.5**

    For chunks where ALL page_number <= total_pages (non-bug-condition),
    verify that current_page equals max(page_numbers) from the chunks.
    This captures the existing correct behavior that must be preserved.
    """

    @given(data=_normal_chunks_with_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_embedding_normal_page_equals_max(self, data):
        """
        **Validates: Requirements 1.4**

        Property: For all chunk lists where every page_number <= total_pages,
        the progress metadata current_page equals max(page_numbers).
        """
        chunks, total_pages = data
        expected_max_page = max(
            c["metadata"]["page_number"] for c in chunks
        )

        mock_update = AsyncMock()
        mock_vector_client = AsyncMock()
        mock_vector_client.store_embeddings = AsyncMock()

        mock_model_client = MagicMock()
        mock_model_client.enabled = True

        document_id = str(uuid.uuid4())

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.clients.database_factory.DatabaseClientFactory"
            ) as MockFactory,
            patch(
                "multimodal_librarian.config.config_factory.get_database_config",
                return_value=MagicMock(),
            ),
            patch(
                "multimodal_librarian.clients.model_server_client.initialize_model_client",
                AsyncMock(return_value=mock_model_client),
            ),
        ):
            factory_instance = MockFactory.return_value
            factory_instance.get_vector_client.return_value = mock_vector_client

            from multimodal_librarian.services.celery_service import (
                _store_embeddings_in_vector_db,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_embeddings_in_vector_db(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        # The last progress update should have current_page == expected_max_page
        pages_reported = [m["current_page"] for m in metas if "current_page" in m]
        if pages_reported:
            assert pages_reported[-1] == expected_max_page, (
                f"Expected current_page={expected_max_page}, "
                f"got {pages_reported[-1]}"
            )

    @given(data=_normal_chunks_with_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_chunk_storage_normal_page_equals_max(self, data):
        """
        **Validates: Requirements 1.4**

        Property: For all chunk lists where every page_number <= total_pages,
        _store_chunks_in_database() reports current_page == max(page_numbers).
        """
        chunks, total_pages = data
        expected_max_page = max(
            c["metadata"]["page_number"] for c in chunks
        )

        # Add required fields for _store_chunks_in_database
        for i, chunk in enumerate(chunks):
            chunk.setdefault("page_number", chunk.get("metadata", {}).get("page_number"))
            chunk.setdefault("section_title", None)

        mock_update = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        document_id = str(uuid.uuid4())

        # Force time-based progress updates to fire every iteration
        call_count = 0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            return call_count * 10.0

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.database.connection.get_async_connection",
                AsyncMock(return_value=mock_conn),
            ),
            patch(
                "time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            from multimodal_librarian.services.celery_service import (
                _store_chunks_in_database,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_chunks_in_database(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        pages_reported = [m["current_page"] for m in metas if "current_page" in m]
        if pages_reported:
            assert pages_reported[-1] == expected_max_page, (
                f"Expected current_page={expected_max_page}, "
                f"got {pages_reported[-1]}"
            )


# ---------------------------------------------------------------------------
# Test 2: Missing page metadata — current_page NOT in metadata
# ---------------------------------------------------------------------------

class TestMissingPageMetadata:
    """
    **Validates: Requirements 1.4, 1.5**

    For chunks WITHOUT page_number in metadata, verify that
    current_page is NOT added to progress metadata.
    """

    @given(data=_chunks_without_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_embedding_no_page_when_missing(self, data):
        """
        **Validates: Requirements 1.5**

        Property: For all chunk lists without page_number metadata,
        current_page must NOT appear in progress metadata.
        """
        chunks, total_pages = data

        mock_update = AsyncMock()
        mock_vector_client = AsyncMock()
        mock_vector_client.store_embeddings = AsyncMock()

        mock_model_client = MagicMock()
        mock_model_client.enabled = True

        document_id = str(uuid.uuid4())

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.clients.database_factory.DatabaseClientFactory"
            ) as MockFactory,
            patch(
                "multimodal_librarian.config.config_factory.get_database_config",
                return_value=MagicMock(),
            ),
            patch(
                "multimodal_librarian.clients.model_server_client.initialize_model_client",
                AsyncMock(return_value=mock_model_client),
            ),
        ):
            factory_instance = MockFactory.return_value
            factory_instance.get_vector_client.return_value = mock_vector_client

            from multimodal_librarian.services.celery_service import (
                _store_embeddings_in_vector_db,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_embeddings_in_vector_db(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        for meta in metas:
            assert "current_page" not in meta, (
                f"current_page should NOT be in metadata when chunks "
                f"have no page_number, but got: {meta}"
            )

    @given(data=_chunks_without_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_chunk_storage_no_page_when_missing(self, data):
        """
        **Validates: Requirements 1.5**

        Property: For all chunk lists without page_number metadata,
        _store_chunks_in_database() must NOT include current_page
        in progress metadata.
        """
        chunks, total_pages = data

        # Chunks without page_number at top level either
        for chunk in chunks:
            chunk.setdefault("page_number", None)
            chunk.setdefault("section_title", None)

        mock_update = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        document_id = str(uuid.uuid4())

        call_count = 0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            return call_count * 10.0

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.database.connection.get_async_connection",
                AsyncMock(return_value=mock_conn),
            ),
            patch(
                "time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            from multimodal_librarian.services.celery_service import (
                _store_chunks_in_database,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_chunks_in_database(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        for meta in metas:
            assert "current_page" not in meta, (
                f"current_page should NOT be in metadata when chunks "
                f"have no page_number, but got: {meta}"
            )


# ---------------------------------------------------------------------------
# Test 3: Non-page metadata — chunks_stored_so_far, total_chunks,
#          embeddings_stored_so_far computed correctly
# ---------------------------------------------------------------------------

class TestNonPageMetadata:
    """
    **Validates: Requirements 1.4, 1.5**

    Verify that non-page metadata fields (chunks_stored_so_far,
    total_chunks, embeddings_stored_so_far) are computed correctly
    regardless of page numbers.
    """

    @given(data=_normal_chunks_with_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_embedding_non_page_metadata_correct(self, data):
        """
        **Validates: Requirements 1.5**

        Property: For all chunk lists, embeddings_stored_so_far and
        total_chunks in progress metadata are computed correctly.
        embeddings_stored_so_far should equal the number of chunks
        processed so far, and total_chunks should equal len(chunks).
        """
        chunks, total_pages = data
        total_chunks = len(chunks)

        mock_update = AsyncMock()
        mock_vector_client = AsyncMock()
        mock_vector_client.store_embeddings = AsyncMock()

        mock_model_client = MagicMock()
        mock_model_client.enabled = True

        document_id = str(uuid.uuid4())

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.clients.database_factory.DatabaseClientFactory"
            ) as MockFactory,
            patch(
                "multimodal_librarian.config.config_factory.get_database_config",
                return_value=MagicMock(),
            ),
            patch(
                "multimodal_librarian.clients.model_server_client.initialize_model_client",
                AsyncMock(return_value=mock_model_client),
            ),
        ):
            factory_instance = MockFactory.return_value
            factory_instance.get_vector_client.return_value = mock_vector_client

            from multimodal_librarian.services.celery_service import (
                _store_embeddings_in_vector_db,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_embeddings_in_vector_db(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        for meta in metas:
            assert "total_chunks" in meta, "total_chunks must be in metadata"
            assert meta["total_chunks"] == total_chunks, (
                f"total_chunks should be {total_chunks}, got {meta['total_chunks']}"
            )
            assert "embeddings_stored_so_far" in meta, (
                "embeddings_stored_so_far must be in metadata"
            )
            assert 1 <= meta["embeddings_stored_so_far"] <= total_chunks, (
                f"embeddings_stored_so_far={meta['embeddings_stored_so_far']} "
                f"out of range [1, {total_chunks}]"
            )

    @given(data=_normal_chunks_with_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_chunk_storage_non_page_metadata_correct(self, data):
        """
        **Validates: Requirements 1.5**

        Property: For all chunk lists, chunks_stored_so_far and
        total_chunks in progress metadata are computed correctly.
        """
        chunks, total_pages = data
        total_chunks = len(chunks)

        for i, chunk in enumerate(chunks):
            chunk.setdefault("page_number", chunk.get("metadata", {}).get("page_number"))
            chunk.setdefault("section_title", None)

        mock_update = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        document_id = str(uuid.uuid4())

        call_count = 0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            return call_count * 10.0

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.database.connection.get_async_connection",
                AsyncMock(return_value=mock_conn),
            ),
            patch(
                "time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            from multimodal_librarian.services.celery_service import (
                _store_chunks_in_database,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_chunks_in_database(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        metas = _collect_metadata_from_calls(mock_update)
        for meta in metas:
            assert "total_chunks" in meta, "total_chunks must be in metadata"
            assert meta["total_chunks"] == total_chunks, (
                f"total_chunks should be {total_chunks}, got {meta['total_chunks']}"
            )
            assert "chunks_stored_so_far" in meta, (
                "chunks_stored_so_far must be in metadata"
            )
            assert 1 <= meta["chunks_stored_so_far"] <= total_chunks, (
                f"chunks_stored_so_far={meta['chunks_stored_so_far']} "
                f"out of range [1, {total_chunks}]"
            )


# ---------------------------------------------------------------------------
# Test 4: Progress percentage range — embeddings 20–25%, chunks 15–20%
# ---------------------------------------------------------------------------

class TestProgressPercentageRange:
    """
    **Validates: Requirements 1.4, 1.5**

    Verify that embedding progress is in the 20–25% range and
    chunk storage progress is in the 15–20% range.
    """

    @given(data=_normal_chunks_with_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_embedding_progress_in_range(self, data):
        """
        **Validates: Requirements 1.4**

        Property: For all chunk lists, the embedding progress percentage
        reported to _update_job_status_sync is in the [20.0, 25.0] range.
        """
        chunks, total_pages = data

        mock_update = AsyncMock()
        mock_vector_client = AsyncMock()
        mock_vector_client.store_embeddings = AsyncMock()

        mock_model_client = MagicMock()
        mock_model_client.enabled = True

        document_id = str(uuid.uuid4())

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.clients.database_factory.DatabaseClientFactory"
            ) as MockFactory,
            patch(
                "multimodal_librarian.config.config_factory.get_database_config",
                return_value=MagicMock(),
            ),
            patch(
                "multimodal_librarian.clients.model_server_client.initialize_model_client",
                AsyncMock(return_value=mock_model_client),
            ),
        ):
            factory_instance = MockFactory.return_value
            factory_instance.get_vector_client.return_value = mock_vector_client

            from multimodal_librarian.services.celery_service import (
                _store_embeddings_in_vector_db,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_embeddings_in_vector_db(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        progress_values = _collect_progress_from_calls(mock_update)
        for pct in progress_values:
            assert 20.0 <= pct <= 25.0, (
                f"Embedding progress {pct}% outside expected range [20, 25]"
            )

    @given(data=_normal_chunks_with_pages())
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_chunk_storage_progress_in_range(self, data):
        """
        **Validates: Requirements 1.4**

        Property: For all chunk lists, the chunk storage progress
        percentage reported to _update_job_status_sync is in the
        [15.0, 20.0] range.
        """
        chunks, total_pages = data

        for i, chunk in enumerate(chunks):
            chunk.setdefault("page_number", chunk.get("metadata", {}).get("page_number"))
            chunk.setdefault("section_title", None)

        mock_update = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_transaction = AsyncMock()
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=False)
        mock_conn.transaction = MagicMock(return_value=mock_transaction)

        document_id = str(uuid.uuid4())

        call_count = 0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            return call_count * 10.0

        with (
            patch(
                "multimodal_librarian.services.celery_service._update_job_status_sync",
                mock_update,
            ),
            patch(
                "multimodal_librarian.services.celery_service._is_document_deleted",
                AsyncMock(return_value=False),
            ),
            patch(
                "multimodal_librarian.database.connection.get_async_connection",
                AsyncMock(return_value=mock_conn),
            ),
            patch(
                "time.monotonic",
                side_effect=fake_monotonic,
            ),
        ):
            from multimodal_librarian.services.celery_service import (
                _store_chunks_in_database,
            )

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    _store_chunks_in_database(document_id, chunks, total_pages)
                )
            finally:
                loop.close()

        progress_values = _collect_progress_from_calls(mock_update)
        for pct in progress_values:
            assert 15.0 <= pct <= 20.0, (
                f"Chunk storage progress {pct}% outside expected range [15, 20]"
            )
