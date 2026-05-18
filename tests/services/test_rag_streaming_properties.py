"""
Property-based tests for RAGService.generate_response_stream.

Feature: deepseek-chat-streaming
Task 8.4: Property-based test for RAG order preservation

This module validates that ``RAGService.generate_response_stream``
forwards every delta yielded by the underlying
``ai_service.generate_response_stream`` as a content-bearing
``RAGStreamingChunk`` in the exact order produced by the AI service and
with byte-identical ``content`` strings.

The property mocks the underlying ``ai_service`` so the test exercises
only the RAG-side chunk forwarding (not DeepSeek SSE, retrieval, or the
knowledge-graph pipeline). The ``query_processor.process_query`` step is
short-circuited to the ``skip_retrieval=True`` branch so the test path is
the simplest one that reaches ``_generate_fallback_response_stream`` and
forwards AI deltas.

Testing Framework: hypothesis (per design document)
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from hypothesis import example, given, settings
from hypothesis import strategies as st

from multimodal_librarian.services.ai_service import AIResponse
from multimodal_librarian.services.rag_service import RAGService, RAGStreamingChunk

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_rag_service(deltas: List[str]) -> RAGService:
    """Build a ``RAGService`` whose ``ai_service`` yields the given deltas.

    The retrieval pipeline is short-circuited by patching
    ``query_processor.process_query`` to take the ``skip_retrieval``
    branch; in that branch ``RAGService.generate_response_stream`` calls
    ``_generate_fallback_response_stream`` which in turn iterates over
    ``self.ai_service.generate_response_stream(...)`` and forwards every
    ``AIResponse.content`` as a ``RAGStreamingChunk.content``.
    """
    # Minimal mock vector client — its only runtime requirement is that
    # it is not None (the RAGService constructor enforces that). It is
    # never called because we route via ``skip_retrieval``.
    mock_vector = MagicMock()
    mock_vector.is_connected = MagicMock(return_value=True)

    # Mock AI service. It needs ``generate_response_stream`` (async
    # generator forwarding the deltas) and ``provider_name`` /
    # ``get_available_providers`` for the final metadata chunk.
    mock_ai = MagicMock()
    mock_ai.provider_name = "mock-provider"
    mock_ai.get_available_providers = MagicMock(return_value=["mock-provider"])

    async def _fake_stream(
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        preferred_provider: Optional[Any] = None,
    ) -> AsyncGenerator[AIResponse, None]:
        # Yield one AIResponse per input delta, preserving order.
        cumulative_tokens = 0
        for i, delta in enumerate(deltas):
            # Rough token estimate mirrors real providers; the property
            # does not depend on the token count.
            cumulative_tokens += max(1, len(delta) // 4)
            yield AIResponse(
                content=delta,
                provider="mock-provider",
                model="mock-model",
                tokens_used=cumulative_tokens,
                processing_time_ms=0,
                metadata={"is_final": False, "chunk_index": i},
            )
        # Terminal chunk with empty content — the contract for the
        # underlying streaming API. RAGService treats this like any
        # other chunk (its empty content is simply forwarded and then
        # filtered out by the "content-bearing" predicate below).
        yield AIResponse(
            content="",
            provider="mock-provider",
            model="mock-model",
            tokens_used=cumulative_tokens,
            processing_time_ms=0,
            metadata={"is_final": True, "chunk_index": len(deltas)},
        )

    mock_ai.generate_response_stream = _fake_stream

    # Inject mock KG components to avoid their real constructors
    # (KnowledgeGraphBuilder calls ``asyncio.get_event_loop()`` at init
    # time, which raises outside a running loop when Hypothesis drives
    # the test synchronously via ``asyncio.run``).
    mock_kg_builder = MagicMock()
    mock_kg_query_engine = MagicMock()

    rag = RAGService(
        vector_client=mock_vector,
        ai_service=mock_ai,
        kg_builder=mock_kg_builder,
        kg_query_engine=mock_kg_query_engine,
    )

    # Short-circuit query processing to the skip_retrieval branch so we
    # exercise only the AI-chunk forwarding path without touching the
    # knowledge graph, vector search, or query classifier.
    async def _fake_process_query(
        query: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
    ):
        return query, [], {"skip_retrieval": True}

    rag.query_processor.process_query = _fake_process_query  # type: ignore[method-assign]

    return rag


async def _collect_rag_chunks(
    rag: RAGService,
    query: str = "hi",
    user_id: str = "test-user",
) -> List[RAGStreamingChunk]:
    """Drive ``RAGService.generate_response_stream`` and collect all chunks."""
    chunks: List[RAGStreamingChunk] = []
    async for chunk in rag.generate_response_stream(
        query=query,
        user_id=user_id,
    ):
        chunks.append(chunk)
    return chunks


def _content_bearing(chunks: List[RAGStreamingChunk]) -> List[RAGStreamingChunk]:
    """Filter to chunks that carry a non-empty content delta.

    Citation-only preamble chunks and the final metadata chunk both have
    ``content == ""``; content-bearing forwarded AI deltas have the
    original non-empty delta string.
    """
    return [c for c in chunks if c.content != ""]


# ---------------------------------------------------------------------------
# Property 5: RAG order preservation
# ---------------------------------------------------------------------------
#
# Validates: Requirements 3.3
#
# For any list of non-empty string deltas yielded in order by the
# underlying ``ai_service.generate_response_stream``,
# ``RAGService.generate_response_stream`` yields content-bearing
# ``RAGStreamingChunk`` objects whose ``content`` strings match the input
# deltas exactly, in the same order.


@given(deltas=st.lists(st.text(min_size=1), min_size=0, max_size=50))
@settings(max_examples=200, deadline=None)
@example(deltas=[])
@example(deltas=["hello"])
@example(deltas=["a", "b", "c"])
@example(deltas=["**bold**", " and ", "_italic_"])
@example(deltas=["🔥", "你好", "\u200b"])
@example(deltas=["line1\n", "line2\n", "\n"])
def test_rag_generate_response_stream_preserves_delta_order(
    deltas: List[str],
) -> None:
    """RAG forwards AI deltas verbatim, in arrival order.

    **Validates: Requirements 3.3**
    """
    rag = _build_rag_service(deltas)
    chunks = asyncio.run(_collect_rag_chunks(rag))

    # Filter to the content-bearing chunks (drop citation preamble and
    # final metadata chunks, both of which have empty content).
    content_chunks = _content_bearing(chunks)

    # 1. There is exactly one content-bearing chunk per input delta.
    assert len(content_chunks) == len(deltas), (
        f"Expected {len(deltas)} content-bearing chunks, got "
        f"{len(content_chunks)}"
    )

    # 2. Each content-bearing chunk matches the input delta at the same
    #    index — byte-identical, same order.
    for i, (chunk, delta) in enumerate(zip(content_chunks, deltas)):
        assert chunk.content == delta, (
            f"Chunk {i}: expected content={delta!r}, got {chunk.content!r}"
        )

    # 3. None of the content-bearing chunks are the terminal final
    #    metadata chunk (Requirement 3.3 mandates is_final=False for
    #    forwarded deltas).
    for chunk in content_chunks:
        assert chunk.is_final is False, (
            "Content-bearing chunks must have is_final=False"
        )

    # 4. Overall concatenation equality — a second, stronger phrasing of
    #    the order-preservation property.
    assert "".join(c.content for c in content_chunks) == "".join(deltas)
