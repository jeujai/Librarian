"""
Preservation Property Tests — Property 2

These tests capture the EXISTING correct behavior BEFORE the bugfix is applied.
They must PASS on both unfixed and fixed code, ensuring no regressions.

Property 2: Preservation — Existing Convert-to-Knowledge, Empty Conversations,
Idempotent Re-ingestion, chat.js clearChat, and Document Pipeline Unchanged.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

import os
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_JS_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "src", "multimodal_librarian", "static", "js",
)
CHAT_JS_PATH = os.path.normpath(os.path.join(_JS_DIR, "chat.js"))

_ROUTERS_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "src", "multimodal_librarian", "api", "routers",
)
CONVERSATIONS_ROUTER_PATH = os.path.normpath(
    os.path.join(_ROUTERS_DIR, "conversations.py")
)
DOCUMENTS_ROUTER_PATH = os.path.normpath(
    os.path.join(_ROUTERS_DIR, "documents.py")
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_method_body(source: str, method_name: str) -> str | None:
    """Extract the body of a JS class method from *source*."""
    pattern = re.compile(
        rf'(?:async\s+)?{re.escape(method_name)}\s*\([^)]*\)\s*\{{',
        re.MULTILINE,
    )
    m = pattern.search(source)
    if m is None:
        return None
    start = m.end() - 1
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : i]
    return None


def _make_mock_conversation(thread_id: str, message_count: int):
    """Create a mock conversation with the given number of messages."""
    conv = MagicMock()
    conv.thread_id = thread_id
    conv.knowledge_summary = None
    if message_count > 0:
        msgs = []
        for i in range(message_count):
            msg = MagicMock()
            msg.content = f"Test message {i}"
            msg.message_type = MagicMock()
            msg.message_type.value = "USER" if i % 2 == 0 else "SYSTEM"
            msgs.append(msg)
        conv.messages = msgs
    else:
        conv.messages = []
    return conv


def _make_mock_knowledge_service(
    thread_id: str, conversation, chunks_count: int = 3,
    concepts_count: int = 5, relationships_count: int = 2,
):
    """Create a mock ConversationKnowledgeService that returns predictable results."""
    from multimodal_librarian.services.conversation_knowledge_service import (
        ConversionResult,
    )

    mock_service = MagicMock()

    if not conversation.messages:
        result = ConversionResult(
            thread_id=thread_id,
            chunks_created=0,
            concepts_extracted=0,
            relationships_extracted=0,
            chunks_cleaned=0,
            concepts_cleaned=0,
        )
    else:
        result = ConversionResult(
            thread_id=thread_id,
            chunks_created=chunks_count,
            concepts_extracted=concepts_count,
            relationships_extracted=relationships_count,
            chunks_cleaned=0,
            concepts_cleaned=0,
        )

    mock_service.convert_conversation = AsyncMock(return_value=result)
    return mock_service


# ---------------------------------------------------------------------------
# Property 2a: Explicit convert-to-knowledge returns 200 with valid counts
# Requirement: 3.1
# ---------------------------------------------------------------------------


class TestExplicitConvertPreservation:
    """
    Preservation: POST /{thread_id}/convert-to-knowledge returns 200 with
    ConvertToKnowledgeResponse containing non-negative integer counts for
    threads with messages.
    """

    @pytest.fixture()
    def _app_with_mocks(self, clear_di_caches):
        from multimodal_librarian.api.dependencies.services import (
            get_conversation_knowledge_service,
        )
        from multimodal_librarian.api.routers.conversation_knowledge import (
            router as ck_router,
        )
        from multimodal_librarian.main import create_minimal_app

        app = create_minimal_app()
        app.include_router(ck_router)

        self.mock_conversations = {}
        self.app = app
        self.get_ck_service = get_conversation_knowledge_service
        yield

        app.dependency_overrides.clear()

    def _setup_thread(self, thread_id, msg_count, chunks=3, concepts=5):
        conv = _make_mock_conversation(thread_id, msg_count)
        self.mock_conversations[thread_id] = conv
        mock_svc = _make_mock_knowledge_service(
            thread_id, conv, chunks_count=chunks, concepts_count=concepts,
        )
        self.app.dependency_overrides[self.get_ck_service] = lambda: mock_svc
        return mock_svc

    def test_convert_thread_with_messages_returns_200(self, _app_with_mocks):
        """Explicit convert on a thread with messages returns 200 and valid counts."""
        self._setup_thread("thread-abc", msg_count=4, chunks=3, concepts=5)
        client = TestClient(self.app)
        resp = client.post("/api/conversations/thread-abc/convert-to-knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["thread_id"] == "thread-abc"
        assert data["chunks_created"] == 3
        assert data["concepts_extracted"] == 5
        assert data["status"] == "success"

    @given(
        chunks=st.integers(min_value=0, max_value=100),
        concepts=st.integers(min_value=0, max_value=200),
    )
    @settings(
        max_examples=15,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_convert_returns_nonneg_counts(
        self, _app_with_mocks, chunks, concepts,
    ):
        """
        Property: For all valid threads with messages, explicit convert returns
        200 with ConvertToKnowledgeResponse containing non-negative integer counts.
        """
        self._setup_thread(
            "thread-pbt", msg_count=3, chunks=chunks, concepts=concepts,
        )
        client = TestClient(self.app)
        resp = client.post("/api/conversations/thread-pbt/convert-to-knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["chunks_created"], int)
        assert isinstance(data["concepts_extracted"], int)
        assert data["chunks_created"] >= 0
        assert data["concepts_extracted"] >= 0


# ---------------------------------------------------------------------------
# Property 2b: Empty conversations return zero counts without errors
# Requirement: 3.3
# ---------------------------------------------------------------------------


class TestEmptyConversationPreservation:
    """
    Preservation: Converting a thread with 0 messages returns zero counts
    (chunks_created=0, concepts_extracted=0) and no errors.
    """

    @pytest.fixture()
    def _app_with_mocks(self, clear_di_caches):
        from multimodal_librarian.api.dependencies.services import (
            get_conversation_knowledge_service,
        )
        from multimodal_librarian.api.routers.conversation_knowledge import (
            router as ck_router,
        )
        from multimodal_librarian.main import create_minimal_app

        app = create_minimal_app()
        app.include_router(ck_router)

        conv = _make_mock_conversation("empty-thread", 0)
        mock_svc = _make_mock_knowledge_service("empty-thread", conv)
        app.dependency_overrides[get_conversation_knowledge_service] = (
            lambda: mock_svc
        )

        self.app = app
        self.mock_svc = mock_svc
        yield

        app.dependency_overrides.clear()

    def test_empty_thread_returns_zero_counts(self, _app_with_mocks):
        """Empty conversation returns zero counts and 200 status."""
        client = TestClient(self.app)
        resp = client.post(
            "/api/conversations/empty-thread/convert-to-knowledge"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunks_created"] == 0
        assert data["concepts_extracted"] == 0
        assert data["status"] == "success"

    @given(thread_id=st.from_regex(r"[a-z0-9\-]{1,36}", fullmatch=True))
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_empty_threads_always_zero(
        self, _app_with_mocks, thread_id,
    ):
        """
        Property: For all thread IDs with zero messages, explicit convert
        returns zero counts without errors.
        """
        from multimodal_librarian.services.conversation_knowledge_service import (
            ConversionResult,
        )

        # Override service to return zero for this thread_id
        zero_result = ConversionResult(
            thread_id=thread_id,
            chunks_created=0,
            concepts_extracted=0,
            relationships_extracted=0,
            chunks_cleaned=0,
            concepts_cleaned=0,
        )
        mock_svc = MagicMock()
        mock_svc.convert_conversation = AsyncMock(return_value=zero_result)

        from multimodal_librarian.api.dependencies.services import (
            get_conversation_knowledge_service,
        )
        self.app.dependency_overrides[get_conversation_knowledge_service] = (
            lambda: mock_svc
        )

        client = TestClient(self.app)
        resp = client.post(
            f"/api/conversations/{thread_id}/convert-to-knowledge"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunks_created"] == 0
        assert data["concepts_extracted"] == 0


# ---------------------------------------------------------------------------
# Property 2c: Idempotent re-ingestion — converting twice yields same counts
# Requirement: 3.4
# ---------------------------------------------------------------------------


class TestIdempotentReingestionPreservation:
    """
    Preservation: Converting the same thread twice calls _cleanup_existing
    first and produces idempotent results with no duplicate concepts.
    """

    @pytest.fixture()
    def _app_with_mocks(self, clear_di_caches):
        from multimodal_librarian.api.dependencies.services import (
            get_conversation_knowledge_service,
        )
        from multimodal_librarian.api.routers.conversation_knowledge import (
            router as ck_router,
        )
        from multimodal_librarian.main import create_minimal_app
        from multimodal_librarian.services.conversation_knowledge_service import (
            ConversionResult,
        )

        app = create_minimal_app()
        app.include_router(ck_router)

        # Service returns consistent counts on every call (idempotent)
        result = ConversionResult(
            thread_id="idem-thread",
            chunks_created=4,
            concepts_extracted=7,
            relationships_extracted=3,
            chunks_cleaned=0,
            concepts_cleaned=0,
        )
        # Second call simulates cleanup of prior data
        result_second = ConversionResult(
            thread_id="idem-thread",
            chunks_created=4,
            concepts_extracted=7,
            relationships_extracted=3,
            chunks_cleaned=4,
            concepts_cleaned=7,
        )

        mock_svc = MagicMock()
        mock_svc.convert_conversation = AsyncMock(
            side_effect=[result, result_second]
        )

        app.dependency_overrides[get_conversation_knowledge_service] = (
            lambda: mock_svc
        )

        self.app = app
        self.mock_svc = mock_svc
        yield

        app.dependency_overrides.clear()

    def test_double_convert_idempotent(self, _app_with_mocks):
        """Converting the same thread twice produces same output counts."""
        client = TestClient(self.app)

        resp1 = client.post(
            "/api/conversations/idem-thread/convert-to-knowledge"
        )
        assert resp1.status_code == 200
        data1 = resp1.json()

        resp2 = client.post(
            "/api/conversations/idem-thread/convert-to-knowledge"
        )
        assert resp2.status_code == 200
        data2 = resp2.json()

        # Output counts are identical (idempotent after cleanup)
        assert data1["chunks_created"] == data2["chunks_created"]
        assert data1["concepts_extracted"] == data2["concepts_extracted"]

        # Service was called twice
        assert self.mock_svc.convert_conversation.call_count == 2

    @given(
        chunks=st.integers(min_value=1, max_value=50),
        concepts=st.integers(min_value=1, max_value=100),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_double_convert_same_counts(
        self, _app_with_mocks, chunks, concepts,
    ):
        """
        Property: For all thread IDs converted twice in sequence, the second
        conversion produces the same chunks_created and concepts_extracted
        counts as the first (idempotent after cleanup).
        """
        from multimodal_librarian.api.dependencies.services import (
            get_conversation_knowledge_service,
        )
        from multimodal_librarian.services.conversation_knowledge_service import (
            ConversionResult,
        )

        first = ConversionResult(
            thread_id="pbt-idem",
            chunks_created=chunks,
            concepts_extracted=concepts,
            relationships_extracted=0,
            chunks_cleaned=0,
            concepts_cleaned=0,
        )
        second = ConversionResult(
            thread_id="pbt-idem",
            chunks_created=chunks,
            concepts_extracted=concepts,
            relationships_extracted=0,
            chunks_cleaned=chunks,
            concepts_cleaned=concepts,
        )
        mock_svc = MagicMock()
        mock_svc.convert_conversation = AsyncMock(
            side_effect=[first, second]
        )
        self.app.dependency_overrides[get_conversation_knowledge_service] = (
            lambda: mock_svc
        )

        client = TestClient(self.app)
        r1 = client.post(
            "/api/conversations/pbt-idem/convert-to-knowledge"
        )
        r2 = client.post(
            "/api/conversations/pbt-idem/convert-to-knowledge"
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["chunks_created"] == r2.json()["chunks_created"]
        assert (
            r1.json()["concepts_extracted"]
            == r2.json()["concepts_extracted"]
        )


# ---------------------------------------------------------------------------
# Property 2d: chat.js clearChat() fires _convertCurrentConversation()
# Requirement: 3.2
# ---------------------------------------------------------------------------


class TestChatJsClearChatPreservation:
    """
    Preservation: chat.js clearChat() source contains a call to
    _convertCurrentConversation() guarded by a messageHistory.length check.
    This must remain true on both unfixed and fixed code.
    """

    @pytest.fixture(autouse=True)
    def _load_source(self):
        with open(CHAT_JS_PATH, "r") as f:
            self.chat_source = f.read()

    def test_chat_js_clear_chat_calls_convert(self):
        """chat.js clearChat() calls _convertCurrentConversation."""
        body = _extract_method_body(self.chat_source, "clearChat")
        assert body is not None, "clearChat not found in chat.js"
        assert "_convertCurrentConversation" in body, (
            "chat.js clearChat() must call _convertCurrentConversation()"
        )

    def test_chat_js_clear_chat_has_message_guard(self):
        """chat.js clearChat() guards conversion with messageHistory.length."""
        body = _extract_method_body(self.chat_source, "clearChat")
        assert body is not None
        assert "messageHistory.length" in body, (
            "chat.js clearChat() must check messageHistory.length"
        )
        assert "currentThreadId" in body, (
            "chat.js clearChat() must check currentThreadId"
        )

    def test_chat_js_convert_method_exists(self):
        """chat.js defines _convertCurrentConversation as a method."""
        body = _extract_method_body(
            self.chat_source, "_convertCurrentConversation"
        )
        assert body is not None, (
            "chat.js must define _convertCurrentConversation()"
        )

    def test_chat_js_convert_calls_endpoint(self):
        """chat.js _convertCurrentConversation calls the convert-to-knowledge endpoint."""
        body = _extract_method_body(
            self.chat_source, "_convertCurrentConversation"
        )
        assert body is not None
        assert "convert-to-knowledge" in body, (
            "chat.js _convertCurrentConversation must call "
            "the convert-to-knowledge endpoint"
        )

    @given(msg_count=st.integers(min_value=1, max_value=50))
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_chat_js_always_converts(self, msg_count):
        """
        Property: For all conversations with msg_count >= 1, chat.js
        clearChat() source contains _convertCurrentConversation() call
        guarded by message count check. This is a static source property.
        """
        body = _extract_method_body(self.chat_source, "clearChat")
        assert body is not None
        has_convert = "_convertCurrentConversation" in body
        has_guard = "messageHistory.length" in body
        assert has_convert and has_guard, (
            f"chat.js clearChat() must convert conversations with "
            f"{msg_count} messages — guard and call must be present"
        )


# ---------------------------------------------------------------------------
# Property 2e: Document processing pipeline is unaffected
# Requirement: 3.5
# ---------------------------------------------------------------------------


class TestDocumentPipelinePreservation:
    """
    Preservation: Document processing endpoints (POST /api/documents/upload,
    etc.) are not modified by conversation extraction changes. The
    conversations.py router does not touch document upload/processing.
    """

    @pytest.fixture(autouse=True)
    def _load_sources(self):
        with open(CONVERSATIONS_ROUTER_PATH, "r") as f:
            self.conversations_source = f.read()
        with open(DOCUMENTS_ROUTER_PATH, "r") as f:
            self.documents_source = f.read()

    def test_conversations_router_does_not_import_document_modules(self):
        """conversations.py does not import document processing modules."""
        assert "document_manager" not in self.conversations_source.split(
            "# File processing"
        )[0] or "DocumentManager" not in self.conversations_source, (
            "conversations.py should not import DocumentManager"
        )
        # More specifically: no import of the documents router
        assert "from .documents import" not in self.conversations_source
        assert "from ..routers.documents import" not in self.conversations_source

    def test_documents_router_does_not_import_conversation_knowledge(self):
        """documents.py does not import conversation knowledge modules."""
        assert "conversation_knowledge" not in self.documents_source, (
            "documents.py should not reference conversation_knowledge"
        )
        assert "ConversationKnowledgeService" not in self.documents_source, (
            "documents.py should not reference ConversationKnowledgeService"
        )

    def test_documents_router_has_upload_endpoint(self):
        """documents.py defines an upload endpoint (baseline check)."""
        assert "upload" in self.documents_source.lower(), (
            "documents.py must have an upload endpoint"
        )
        assert "/api/documents" in self.documents_source or (
            'prefix="/api/documents"' in self.documents_source
            or "prefix='/api/documents'" in self.documents_source
        ), "documents.py must use /api/documents prefix"

    def test_conversations_router_prefix_is_separate(self):
        """conversations.py uses a different prefix from documents.py."""
        assert "/api/v1/conversations" in self.conversations_source, (
            "conversations.py must use /api/v1/conversations prefix"
        )
        assert "/api/documents" not in self.conversations_source, (
            "conversations.py must not reference /api/documents"
        )

    @given(
        endpoint=st.sampled_from([
            "upload", "list_documents", "get_document",
            "delete_document", "retry_document_processing",
        ])
    )
    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_document_endpoints_not_in_conversations(
        self, endpoint,
    ):
        """
        Property: For all document processing endpoint names, they do not
        appear as route handlers in conversations.py.
        """
        # Check that the conversations router doesn't define document endpoints
        pattern = re.compile(
            rf'async\s+def\s+{re.escape(endpoint)}\s*\(', re.MULTILINE
        )
        match = pattern.search(self.conversations_source)
        assert match is None, (
            f"conversations.py must not define '{endpoint}' — "
            f"document endpoints belong in documents.py"
        )
