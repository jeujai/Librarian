"""
Property-based tests for QLoRA trainer chat template formatting.

# Feature: medical-knowledge-finetuning, Property 10: Chat template formatting preserves content

Validates: Requirements 5.3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.models import (
    VALID_STRATEGIES,
    InstructionTuningPair,
    PairMetadata,
)
from multimodal_librarian.ml.qlora_trainer import (
    format_chat_message,
    format_chat_template_string,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies for generating valid model instances
# ---------------------------------------------------------------------------


def _non_empty_text() -> st.SearchStrategy[str]:
    """Generate non-empty strings with at least one non-whitespace character."""
    return st.text(min_size=1, max_size=500).filter(lambda s: s.strip())


def _confidence_score() -> st.SearchStrategy[float]:
    """Generate a float in [0.0, 1.0]."""
    return st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    )


def _strategy_name() -> st.SearchStrategy[str]:
    """Generate a valid strategy name."""
    return st.sampled_from(list(VALID_STRATEGIES))


def _pair_metadata_strategy() -> st.SearchStrategy[PairMetadata]:
    """Generate a valid PairMetadata instance."""
    return st.builds(
        PairMetadata,
        strategy=_strategy_name(),
        source_concepts=st.lists(st.text(min_size=1, max_size=50), max_size=5),
        confidence_score=_confidence_score(),
        source_document=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        chunk_ids=st.one_of(
            st.none(), st.lists(st.text(min_size=1, max_size=50), max_size=5)
        ),
        relationship_chain=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    )


def _instruction_tuning_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a valid InstructionTuningPair instance."""
    return st.builds(
        InstructionTuningPair,
        instruction=_non_empty_text(),
        context=_non_empty_text(),
        response=_non_empty_text(),
        metadata=_pair_metadata_strategy(),
    )


# ---------------------------------------------------------------------------
# Property 10: Chat template formatting preserves content
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestChatTemplateFormattingPreservesContent:
    """Property 10: Chat template formatting preserves content.

    For any valid InstructionTuningPair, formatting it into the Llama chat
    template SHALL produce a string that contains the original instruction
    text, context text, and response text.

    Validates: Requirements 5.3
    """

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_template_string_contains_instruction(
        self, pair: InstructionTuningPair
    ) -> None:
        """The formatted template string contains the original instruction."""
        formatted = format_chat_template_string(pair)
        assert pair.instruction in formatted, (
            f"Instruction text not found in formatted template.\n"
            f"Instruction: {pair.instruction!r}\n"
            f"Formatted: {formatted!r}"
        )

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_template_string_contains_context(
        self, pair: InstructionTuningPair
    ) -> None:
        """The formatted template string contains the original context."""
        formatted = format_chat_template_string(pair)
        assert pair.context in formatted, (
            f"Context text not found in formatted template.\n"
            f"Context: {pair.context!r}\n"
            f"Formatted: {formatted!r}"
        )

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_template_string_contains_response(
        self, pair: InstructionTuningPair
    ) -> None:
        """The formatted template string contains the original response."""
        formatted = format_chat_template_string(pair)
        assert pair.response in formatted, (
            f"Response text not found in formatted template.\n"
            f"Response: {pair.response!r}\n"
            f"Formatted: {formatted!r}"
        )

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_template_string_contains_all_fields(
        self, pair: InstructionTuningPair
    ) -> None:
        """The formatted template string contains instruction, context, and response."""
        formatted = format_chat_template_string(pair)
        assert pair.instruction in formatted
        assert pair.context in formatted
        assert pair.response in formatted

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_chat_message_contains_instruction(
        self, pair: InstructionTuningPair
    ) -> None:
        """The chat message user content contains the original instruction."""
        result = format_chat_message(pair)
        messages = result["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert pair.instruction in user_msg["content"], (
            f"Instruction not found in user message content.\n"
            f"Instruction: {pair.instruction!r}\n"
            f"User content: {user_msg['content']!r}"
        )

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_chat_message_contains_context(
        self, pair: InstructionTuningPair
    ) -> None:
        """The chat message user content contains the original context."""
        result = format_chat_message(pair)
        messages = result["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert pair.context in user_msg["content"], (
            f"Context not found in user message content.\n"
            f"Context: {pair.context!r}\n"
            f"User content: {user_msg['content']!r}"
        )

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_chat_message_contains_response(
        self, pair: InstructionTuningPair
    ) -> None:
        """The chat message assistant content contains the original response."""
        result = format_chat_message(pair)
        messages = result["messages"]
        assistant_msg = next(m for m in messages if m["role"] == "assistant")
        assert pair.response in assistant_msg["content"], (
            f"Response not found in assistant message content.\n"
            f"Response: {pair.response!r}\n"
            f"Assistant content: {assistant_msg['content']!r}"
        )

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_chat_message_has_system_user_assistant_roles(
        self, pair: InstructionTuningPair
    ) -> None:
        """The chat message contains exactly system, user, and assistant roles."""
        result = format_chat_message(pair)
        messages = result["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant"], (
            f"Expected roles ['system', 'user', 'assistant'], got {roles}"
        )

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_chat_message_returns_messages_key(
        self, pair: InstructionTuningPair
    ) -> None:
        """The chat message dict contains a 'messages' key."""
        result = format_chat_message(pair)
        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) == 3
