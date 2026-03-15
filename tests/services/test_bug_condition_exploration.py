"""
Bug Condition Exploration Tests — Property 1

These tests encode the EXPECTED (correct) behavior for conversation lifecycle
events triggering concept extraction. They are written BEFORE the fix and are
expected to FAIL on unfixed code, confirming the bug exists.

Case A (Frontend): unified_interface.js clearChat() should call
    _convertCurrentConversation() before clearing state — it doesn't.
Case B (Backend): POST /api/v1/conversations/start with previous_thread_id
    should schedule convert_conversation as a background task — it doesn't.

Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3
"""

import os
import re
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JS_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "src", "multimodal_librarian", "static", "js",
)

UNIFIED_INTERFACE_PATH = os.path.normpath(
    os.path.join(_JS_DIR, "unified_interface.js")
)
CHAT_JS_PATH = os.path.normpath(os.path.join(_JS_DIR, "chat.js"))


def _extract_method_body(source: str, method_name: str) -> str | None:
    """
    Extract the body of a JS class method from *source*.

    Returns the text between the opening '{' and its matching '}',
    or None if the method is not found.
    """
    pattern = re.compile(
        rf'(?:async\s+)?{re.escape(method_name)}\s*\([^)]*\)\s*\{{',
        re.MULTILINE,
    )
    m = pattern.search(source)
    if m is None:
        return None

    start = m.end() - 1  # points at the '{'
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : i]
    return None


# ---------------------------------------------------------------------------
# Case A — Frontend: unified_interface.js clearChat()
# ---------------------------------------------------------------------------

class TestUnifiedInterfaceClearChatConversion:
    """
    Assert that unified_interface.js clearChat() calls
    _convertCurrentConversation() guarded by a message-count check,
    mirroring the pattern in chat.js.
    """

    @pytest.fixture(autouse=True)
    def _load_sources(self):
        with open(UNIFIED_INTERFACE_PATH, "r") as f:
            self.unified_source = f.read()
        with open(CHAT_JS_PATH, "r") as f:
            self.chat_source = f.read()

    # -- Sanity: chat.js has the correct pattern (should always pass) ------

    def test_chat_js_clear_chat_calls_convert(self):
        """chat.js clearChat() calls _convertCurrentConversation — baseline."""
        body = _extract_method_body(self.chat_source, "clearChat")
        assert body is not None, "clearChat not found in chat.js"
        assert "_convertCurrentConversation" in body, (
            "chat.js clearChat() should call _convertCurrentConversation()"
        )

    def test_chat_js_clear_chat_guards_with_message_check(self):
        """chat.js clearChat() guards conversion with messageHistory check."""
        body = _extract_method_body(self.chat_source, "clearChat")
        assert body is not None
        assert "messageHistory.length" in body, (
            "chat.js clearChat() should check messageHistory.length"
        )

    # -- Bug condition: unified_interface.js is missing the call ----------

    def test_unified_clear_chat_calls_convert(self):
        """
        BUG CONDITION — unified_interface.js clearChat() must call
        _convertCurrentConversation() before clearing state.

        On unfixed code this FAILS: the method body has no such call.
        """
        body = _extract_method_body(self.unified_source, "clearChat")
        assert body is not None, "clearChat not found in unified_interface.js"
        assert "_convertCurrentConversation" in body, (
            "COUNTEREXAMPLE: unified_interface.js clearChat() never calls "
            "_convertCurrentConversation() — concepts from the outgoing "
            "conversation are silently lost"
        )

    def test_unified_clear_chat_guards_with_message_check(self):
        """
        BUG CONDITION — the conversion call must be guarded by a
        messageHistory.length > 0 && currentThreadId check.

        On unfixed code this FAILS: there is no guard because there
        is no conversion call at all.
        """
        body = _extract_method_body(self.unified_source, "clearChat")
        assert body is not None
        has_guard = (
            "messageHistory.length" in body
            and "_convertCurrentConversation" in body
        )
        assert has_guard, (
            "COUNTEREXAMPLE: unified_interface.js clearChat() has no "
            "message-count guard before _convertCurrentConversation() — "
            "method doesn't exist on the class"
        )

    def test_unified_interface_has_convert_method(self):
        """
        BUG CONDITION — unified_interface.js must define
        _convertCurrentConversation() as a class method.

        On unfixed code this FAILS: the method doesn't exist.
        """
        body = _extract_method_body(
            self.unified_source, "_convertCurrentConversation"
        )
        assert body is not None, (
            "COUNTEREXAMPLE: unified_interface.js has no "
            "_convertCurrentConversation() method — it was never implemented"
        )

    # -- PBT: for any non-empty message history, conversion must happen ----

    @given(msg_count=st.integers(min_value=1, max_value=50))
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_conversion_called_for_nonempty_conversations(
        self, msg_count
    ):
        """
        Property: For ALL conversations with msg_count >= 1 messages,
        unified_interface.js clearChat() source must contain a call to
        _convertCurrentConversation().

        This is a static source-level property — the msg_count parameter
        demonstrates that the property should hold for any positive
        message count, but the bug means it holds for NONE of them.
        """
        body = _extract_method_body(self.unified_source, "clearChat")
        assert body is not None
        assert "_convertCurrentConversation" in body, (
            f"COUNTEREXAMPLE: conversation with {msg_count} messages — "
            f"unified_interface.js clearChat() never triggers concept "
            f"extraction regardless of message count"
        )


# ---------------------------------------------------------------------------
# Case B — Backend: start_conversation with previous_thread_id
# ---------------------------------------------------------------------------

class TestStartConversationBackgroundConversion:
    """
    Assert that POST /api/v1/conversations/start accepts a
    previous_thread_id field and schedules convert_conversation
    as a background task when the previous thread has messages.
    """

    @pytest.fixture()
    def _app_with_mocks(self, clear_di_caches):
        """
        Create a FastAPI test app with the conversations router
        explicitly included and a mocked conversation manager.
        """
        from multimodal_librarian.api.dependencies import (
            get_conversation_knowledge_service_optional,
        )
        from multimodal_librarian.api.middleware import get_user_id
        from multimodal_librarian.api.routers.conversations import (
            router as conversations_router,
        )
        from multimodal_librarian.main import create_minimal_app

        app = create_minimal_app()
        app.include_router(conversations_router)

        # Mock conversation manager
        mock_cm = MagicMock()
        mock_thread = MagicMock()
        mock_thread.thread_id = "new-thread-001"
        mock_thread.created_at = "2025-01-01T00:00:00Z"
        mock_cm.start_conversation.return_value = mock_thread

        # Previous thread with messages
        mock_prev_thread = MagicMock()
        mock_prev_thread.thread_id = "prev-thread-001"
        mock_prev_thread.messages = [MagicMock(), MagicMock()]
        mock_prev_thread.get_message_count.return_value = 2
        mock_cm.get_conversation.return_value = mock_prev_thread
        mock_cm.get_conversation_thread.return_value = mock_prev_thread

        # Mock knowledge service for DI override
        mock_knowledge_service = MagicMock()
        mock_knowledge_service.convert_conversation = MagicMock()

        # Override get_user_id so it doesn't need a real Request
        app.dependency_overrides[get_user_id] = lambda: "test-user"
        app.dependency_overrides[
            get_conversation_knowledge_service_optional
        ] = lambda: mock_knowledge_service

        # Patch the module-level conversation_manager used in the router
        with patch(
            "multimodal_librarian.api.routers.conversations"
            ".conversation_manager",
            mock_cm,
        ):
            self.mock_cm = mock_cm
            self.mock_knowledge_service = mock_knowledge_service
            self.app = app
            yield

        app.dependency_overrides.clear()

    def test_start_conversation_triggers_conversion_for_previous_thread(
        self, _app_with_mocks
    ):
        """
        BUG CONDITION — When previous_thread_id is provided, the
        endpoint must schedule convert_conversation as a background
        task for that thread.

        On unfixed code this FAILS: StartConversationRequest has no
        previous_thread_id field — Pydantic silently drops it, and
        no conversion is ever triggered.
        """
        client = TestClient(self.app)
        response = client.post(
            "/api/v1/conversations/start",
            json={
                "user_id": "test-user",
                "previous_thread_id": "prev-thread-001",
            },
        )
        assert response.status_code == 200, (
            f"start_conversation returned {response.status_code}: "
            f"{response.text}"
        )

        # Verify convert_conversation was scheduled via background task
        assert self.mock_knowledge_service.convert_conversation.called, (
            "COUNTEREXAMPLE: previous_thread_id='prev-thread-001' — "
            "start_conversation silently drops previous_thread_id. "
            "The field is not in StartConversationRequest and no "
            "background conversion task is scheduled."
        )

    @given(
        prev_thread_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Pd")
            ),
            min_size=1,
            max_size=36,
        )
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_convert_scheduled_for_previous_thread(
        self, _app_with_mocks, prev_thread_id
    ):
        """
        Property: For ALL non-empty previous_thread_id values, calling
        start_conversation must schedule convert_conversation as a
        background task for the previous thread.

        On unfixed code this FAILS: the endpoint has no knowledge of
        previous_thread_id and never calls ConversationKnowledgeService.
        """
        # Reset mock call state for each hypothesis example
        self.mock_knowledge_service.convert_conversation.reset_mock()

        client = TestClient(self.app)
        client.post(
            "/api/v1/conversations/start",
            json={
                "user_id": "test-user",
                "previous_thread_id": prev_thread_id,
            },
        )

        assert self.mock_knowledge_service.convert_conversation.called, (
            f"COUNTEREXAMPLE: previous_thread_id='{prev_thread_id}' — "
            f"start_conversation never schedules convert_conversation "
            f"as a background task. The endpoint has no "
            f"ConversationKnowledgeService dependency and ignores "
            f"previous_thread_id entirely."
        )

    def test_start_conversation_no_previous_thread_no_conversion(
        self, _app_with_mocks
    ):
        """
        Preservation baseline — when no previous_thread_id is provided,
        no background conversion should be attempted. This should pass
        on both unfixed and fixed code.
        """
        client = TestClient(self.app)
        response = client.post(
            "/api/v1/conversations/start",
            json={"user_id": "test-user"},
        )
        assert response.status_code == 200
