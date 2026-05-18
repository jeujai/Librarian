"""
Property-based tests for DeepSeekAIService._merge_context.

Feature: deepseek-chat-streaming
Task 4.2: Property-based test for context-merge

This module validates the context-merge helper
(``DeepSeekAIService._merge_context``) defined in
``src/multimodal_librarian/services/deepseek_ai_service.py``. The helper
mirrors the inline context-merge behavior inside ``generate_response`` so
that the streaming path (``generate_response_stream``) produces an
identical merged payload.

The helper's contract:

- When ``context`` is non-empty and the last message has ``role == "user"``,
  return a new list whose last entry has the same ``role`` and whose
  ``content`` is ``original + "\\n\\nAdditional context:\\n" + context``.
- When ``context`` is ``None`` or empty, return ``messages`` unchanged.
- Never mutate the input ``messages`` list or any of its dicts.
- Messages other than the last one are preserved.

Testing Framework: hypothesis (per design document)
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from multimodal_librarian.services.deepseek_ai_service import DeepSeekAIService

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def service() -> DeepSeekAIService:
    """Instantiate a ``DeepSeekAIService`` with a dummy API key.

    The context-merge helper is a pure method that does not touch the
    network or the cached HTTP client, so a dummy key is sufficient. The
    module-scoped fixture avoids re-reading environment variables for
    every example Hypothesis generates.
    """
    return DeepSeekAIService(api_key="test-key-not-used")


# A role for messages that precede the final user message. The helper's
# contract only pins down the last-message role, so earlier messages can be
# any of the standard chat roles.
_ROLES = st.sampled_from(["user", "assistant", "system"])


def _message(role: str, content: str) -> Dict[str, str]:
    return {"role": role, "content": content}


# Strategy: a non-empty list of chat messages whose final entry has
# ``role == "user"``. Earlier entries have arbitrary roles. Contents are
# arbitrary strings (including empty, unicode, and multi-line).
_messages_ending_in_user = st.lists(
    st.builds(_message, _ROLES, st.text()),
    min_size=0,
    max_size=8,
).flatmap(
    lambda prefix: st.builds(
        lambda last_content: [*prefix, _message("user", last_content)],
        st.text(),
    )
)


# ---------------------------------------------------------------------------
# Property 3: Context-merge rule
# ---------------------------------------------------------------------------
#
# Validates: Requirements 2.3
#
# For all message lists ``messages`` ending in ``role == "user"`` and for
# all non-empty strings ``context``, ``_merge_context(messages, context)``
# produces a new list identical to ``messages`` except that the last
# message's content equals ``original + "\n\nAdditional context:\n" +
# context`` and its role is unchanged. The input must not be mutated.


@given(
    messages=_messages_ending_in_user,
    context=st.text(min_size=1),
)
@settings(max_examples=200, deadline=None)
@example(
    messages=[{"role": "user", "content": ""}],
    context="extra",
)
@example(
    messages=[
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ],
    context="docs",
)
@example(
    messages=[{"role": "user", "content": "你好"}],
    context="🔥",
)
def test_merge_context_appends_suffix_and_preserves_role(
    service: DeepSeekAIService,
    messages: List[Dict[str, str]],
    context: str,
) -> None:
    """Context-merge appends the exact suffix and preserves all roles.

    **Validates: Requirements 2.3**
    """
    # Deep-copy the input so we can verify the helper never mutates it.
    original_snapshot = copy.deepcopy(messages)

    merged = service._merge_context(messages, context)

    # 1. Input is not mutated.
    assert messages == original_snapshot

    # 2. Length is preserved.
    assert len(merged) == len(messages)

    # 3. All messages preceding the last are structurally equal to input.
    for i in range(len(messages) - 1):
        assert merged[i] == original_snapshot[i]

    # 4. Last message's role is unchanged ("user").
    last_merged = merged[-1]
    last_original = original_snapshot[-1]
    assert last_merged["role"] == "user"
    assert last_merged["role"] == last_original["role"]

    # 5. Last message's content equals original + suffix (exact match).
    expected_suffix = "\n\nAdditional context:\n" + context
    assert last_merged["content"] == last_original["content"] + expected_suffix

    # 6. The original content is preserved as a prefix.
    assert last_merged["content"].startswith(last_original["content"])

    # 7. The content ends with the exact context suffix.
    assert last_merged["content"].endswith(expected_suffix)


# ---------------------------------------------------------------------------
# Secondary property: no-op when context is None or empty
# ---------------------------------------------------------------------------
#
# Validates: Requirements 2.3 (fallback clause — "When context is None /
# empty, return messages unchanged")


@given(messages=_messages_ending_in_user)
@settings(max_examples=100, deadline=None)
@pytest.mark.parametrize("context", [None, ""])
def test_merge_context_is_noop_when_context_is_empty_or_none(
    service: DeepSeekAIService,
    messages: List[Dict[str, str]],
    context: Optional[str],
) -> None:
    """When ``context`` is falsy, the helper returns ``messages`` unchanged.

    **Validates: Requirements 2.3**
    """
    original_snapshot = copy.deepcopy(messages)
    merged = service._merge_context(messages, context)

    # Structurally equal to the input (and per the docstring, the helper
    # returns the same reference, but we assert equality rather than
    # identity because equality is the user-observable contract).
    assert merged == original_snapshot

    # Input not mutated.
    assert messages == original_snapshot
