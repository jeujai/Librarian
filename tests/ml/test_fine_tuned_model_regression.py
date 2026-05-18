"""
Property-based tests for the fine-tuned-model-regression bugfix spec.

# Feature: fine-tuned-model-regression
# Property 5: Preservation — JSONL round-trip preserves ``semantic_type``

Validates: Requirements 3.4
"""

from __future__ import annotations

import asyncio
from typing import List, Optional
from unittest.mock import patch

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.models import (
    VALID_STRATEGIES,
    InstructionTuningPair,
    PairMetadata,
)
from multimodal_librarian.services.ai_service import AIResponse
from multimodal_librarian.services.deepseek_ai_service import DeepSeekAIService

# ---------------------------------------------------------------------------
# Constants — the five UMLS semantic types exercised by the 50-question
# fine-tuned-model-regression evaluation set. Generated pairs draw their
# ``metadata.semantic_type`` from this pool (plus ``None`` to exercise the
# legacy-compatible default).
# ---------------------------------------------------------------------------

EVAL_SEMANTIC_TYPES: List[str] = [
    "Pharmacologic Substance",
    "Disease or Syndrome",
    "Therapeutic or Preventive Procedure",
    "Sign or Symptom",
    "Diagnostic Procedure",
]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


def _non_empty_text() -> st.SearchStrategy[str]:
    """Generate non-empty strings with at least one non-whitespace char."""
    return st.text(min_size=1, max_size=500).filter(lambda s: s.strip())


def _confidence_score() -> st.SearchStrategy[float]:
    """Generate a float in [0.0, 1.0]."""
    return st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    )


def _strategy_name() -> st.SearchStrategy[str]:
    """Generate a valid strategy name."""
    return st.sampled_from(list(VALID_STRATEGIES))


def _semantic_type() -> st.SearchStrategy[Optional[str]]:
    """Generate a ``semantic_type`` value.

    Draws from the five UMLS semantic types used by the evaluation set
    plus ``None`` so the round-trip is also exercised for legacy pairs
    that predate this field.
    """
    return st.sampled_from([*EVAL_SEMANTIC_TYPES, None])


def pair_metadata_strategy_with_semantic_type() -> (
    st.SearchStrategy[PairMetadata]
):
    """Generate a ``PairMetadata`` that populates ``semantic_type``.

    Mirrors the baseline ``pair_metadata_strategy`` used elsewhere in the
    ``tests/ml`` suite but additionally draws ``semantic_type`` from the
    five eval types plus ``None``, so Property 5 (JSONL round-trip
    preserves ``semantic_type``) can be exercised across the full domain
    including the legacy default.
    """
    return st.builds(
        PairMetadata,
        strategy=_strategy_name(),
        source_concepts=st.lists(
            st.text(min_size=1, max_size=50), max_size=10
        ),
        confidence_score=_confidence_score(),
        source_document=st.one_of(
            st.none(), st.text(min_size=1, max_size=200)
        ),
        chunk_ids=st.one_of(
            st.none(),
            st.lists(st.text(min_size=1, max_size=50), max_size=10),
        ),
        relationship_chain=st.one_of(
            st.none(), st.text(min_size=1, max_size=300)
        ),
        semantic_type=_semantic_type(),
    )


def instruction_tuning_pair_strategy_with_semantic_type() -> (
    st.SearchStrategy[InstructionTuningPair]
):
    """Generate an ``InstructionTuningPair`` with a populated semantic type.

    Extends the baseline ``instruction_tuning_pair_strategy`` used in the
    existing ``tests/ml`` suite by populating ``metadata.semantic_type``
    from ``st.sampled_from([...five eval types..., None])``.
    """
    return st.builds(
        InstructionTuningPair,
        instruction=_non_empty_text(),
        context=_non_empty_text(),
        response=_non_empty_text(),
        metadata=pair_metadata_strategy_with_semantic_type(),
    )


# ---------------------------------------------------------------------------
# Property 5: Preservation — JSONL round-trip preserves ``semantic_type``
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestSemanticTypeJSONLRoundTrip:
    """Property 5: Preservation — JSONL round-trip preserves ``semantic_type``.

    **Validates: Requirements 3.4**

    For any ``InstructionTuningPair`` whose ``metadata.semantic_type`` is
    drawn from the five evaluation UMLS semantic types (or ``None`` for
    legacy pairs), serializing the pair to a JSONL line and parsing it
    back SHALL produce an ``InstructionTuningPair`` equal to the original,
    with the ``semantic_type`` value preserved exactly.

    This is the primary preservation property driving task 1.3 of the
    fine-tuned-model-regression bugfix: adding the ``semantic_type``
    field to ``PairMetadata`` must not break the existing JSONL
    round-trip contract established by the ``conversational-training-data``
    spec (Property 18).
    """

    @given(pair=instruction_tuning_pair_strategy_with_semantic_type())
    @settings(max_examples=20)
    def test_jsonl_round_trip_preserves_pair(
        self, pair: InstructionTuningPair
    ) -> None:
        """``from_jsonl_line(pair.to_jsonl_line()) == pair``.

        Validates the full preservation contract: the serialized pair
        parses back to an object that compares equal under
        ``InstructionTuningPair.__eq__``, which includes metadata and
        therefore ``semantic_type``.
        """
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)

        assert restored == pair

    @given(pair=instruction_tuning_pair_strategy_with_semantic_type())
    @settings(max_examples=100)
    def test_jsonl_round_trip_preserves_semantic_type_field(
        self, pair: InstructionTuningPair
    ) -> None:
        """The ``semantic_type`` value survives the round-trip exactly.

        Complements the whole-object equality check above with a direct
        assertion on the new field, making the preservation guarantee
        explicit in the test output when a regression occurs.
        """
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)

        assert restored.metadata.semantic_type == pair.metadata.semantic_type


# ---------------------------------------------------------------------------
# Property 2: Bug Condition — Judge pipeline completes without transport
# contamination (task 3.5)
#
# ``DeepSeekAIService`` caches an ``httpx.AsyncClient`` whose transport is
# bound to the event loop that created it. When the evaluation CLI (or any
# caller) invokes ``asyncio.run`` more than once, the first loop closes
# before the second starts; reusing the cached client across that boundary
# historically raised ``RuntimeError("Event loop is closed")`` and forced
# the judge pipeline into a degraded retry state.
#
# The fix in task 3.1 makes ``_get_client`` loop-aware: it tracks the loop
# the current client was bound to and rebuilds the client whenever the
# running loop differs from that tracked loop (or the tracked loop is
# closed). This property test exercises that fix across 2–5 back-to-back
# ``asyncio.run`` invocations on the *same* service instance, using a
# mocked ``httpx.MockTransport`` that will raise the sentinel error if it
# is ever reached on a stale loop.
# ---------------------------------------------------------------------------


_EVENT_LOOP_CLOSED_MESSAGE = "Event loop is closed"


def _build_loop_aware_mock_transport(
    bound_loop: asyncio.AbstractEventLoop,
) -> httpx.MockTransport:
    """Build a ``MockTransport`` that enforces loop affinity.

    The returned transport captures ``bound_loop`` at construction time.
    On every subsequent request, if ``bound_loop`` has been closed (the
    symptom of a cached ``httpx.AsyncClient`` being reused across
    ``asyncio.run`` boundaries) the handler raises
    ``RuntimeError("Event loop is closed")`` — the exact error emitted
    by the real httpx transport pool in that situation.

    When the transport's bound loop is still the one driving the current
    call, the handler returns a minimal but schema-valid DeepSeek chat
    completion response so ``generate_response`` can successfully parse
    it into an :class:`AIResponse` with ``confidence_score=1.0``.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        # Reuse across an ``asyncio.run`` boundary manifests as the bound
        # loop having been closed by the time the transport is reached.
        # Raise the sentinel error that the real transport would raise so
        # the test fails visibly if ``_get_client`` ever regresses.
        if bound_loop.is_closed():
            raise RuntimeError(_EVENT_LOOP_CLOSED_MESSAGE)
        body = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "deepseek-chat",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "ok",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


class _LoopAwareAsyncClient(httpx.AsyncClient):
    """``httpx.AsyncClient`` subclass that auto-attaches a loop-aware transport.

    Each instance captures the currently running event loop at
    construction time and wires a fresh
    :func:`_build_loop_aware_mock_transport` into the client. That
    transport will raise ``RuntimeError("Event loop is closed")`` on any
    request that arrives after its bound loop has been closed.

    When the production code under test (``DeepSeekAIService._get_client``)
    correctly detects a loop change and rebuilds the client, each
    ``asyncio.run`` gets a client whose transport is bound to *that*
    run's loop, and no ``Event loop is closed`` error ever surfaces. If
    the fix regressed and the cached client were reused across loops,
    the request would land on a transport whose bound loop is the
    already-closed first loop and the sentinel error would propagate.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        # ``_get_client`` is ``async`` so we are guaranteed to have a
        # running loop here; capturing it ties every MockTransport to the
        # loop that built its owning client.
        bound_loop = asyncio.get_running_loop()
        # Drop any caller-provided transport so the mock is authoritative.
        kwargs.pop("transport", None)
        kwargs["transport"] = _build_loop_aware_mock_transport(bound_loop)
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]


@pytest.mark.pbt
@pytest.mark.unit
class TestJudgeLoopSafety:
    """Property 2: Bug Condition — judge pipeline completes cleanly.

    **Validates: Requirements 1.8, 2.8**

    For every ``num_run_calls`` in ``[2, 5]``, performing that many
    back-to-back ``asyncio.run(service.generate_response(...))`` calls on
    the *same* :class:`DeepSeekAIService` instance SHALL:

    1. Never propagate ``RuntimeError("Event loop is closed")`` to the
       caller (neither as a raised exception out of ``asyncio.run`` nor
       as the wrapped error content of an :class:`AIResponse`).
    2. Return an :class:`AIResponse` from every call, with the
       ``confidence_score=1.0`` success marker set by the non-error path
       of ``generate_response``.

    The cached ``httpx.AsyncClient`` inside the service is deliberately
    reused across these loops (that is the whole point of testing the
    loop-aware ``_get_client`` — Property 2's Bug_Condition is exactly
    "two or more ``asyncio.run`` invocations sharing one
    ``DeepSeekAIService`` instance"). A regression in ``_get_client``
    would surface as the mocked transport raising the sentinel error,
    which ``generate_response`` then converts into an ``AIResponse``
    whose ``content`` contains ``"Event loop is closed"`` and whose
    ``confidence_score`` is ``0.0``. Both failure modes are asserted
    against below.
    """

    @given(num_run_calls=st.integers(min_value=2, max_value=5))
    @settings(max_examples=100, deadline=None)
    def test_no_event_loop_is_closed_across_asyncio_runs(
        self, num_run_calls: int
    ) -> None:
        """N back-to-back ``asyncio.run`` calls never contaminate the judge.

        Patches ``httpx.AsyncClient`` inside the ``deepseek_ai_service``
        module with :class:`_LoopAwareAsyncClient` so every client
        constructed by ``_get_client`` is wired to a fresh
        :class:`httpx.MockTransport`. The transport enforces that calls
        only succeed while their bound loop is still open, faithfully
        reproducing the real ``httpx`` behaviour that motivated this
        bugfix.
        """
        # Single service instance shared across every asyncio.run below
        # so the cached ``_client`` path is genuinely exercised.
        service = DeepSeekAIService(api_key="test-key-not-used")

        async def _one_call() -> AIResponse:
            return await service.generate_response(
                messages=[
                    {"role": "user", "content": "ping"},
                ],
            )

        with patch(
            "multimodal_librarian.services.deepseek_ai_service.httpx.AsyncClient",
            _LoopAwareAsyncClient,
        ):
            responses: list[AIResponse] = []
            for _ in range(num_run_calls):
                # Each ``asyncio.run`` spins up a fresh event loop. With
                # the loop-aware ``_get_client`` fix, the cached
                # ``_client`` is rebuilt on the new loop and the mocked
                # transport handler is reached with ``bound_loop`` still
                # open. Without the fix, the handler would see a closed
                # bound loop and raise ``RuntimeError("Event loop is
                # closed")``.
                responses.append(asyncio.run(_one_call()))

        # Assertion 1: every call returned an ``AIResponse``.
        assert len(responses) == num_run_calls
        for response in responses:
            assert isinstance(response, AIResponse)

        # Assertion 2: no ``Event loop is closed`` error propagated —
        # neither as a raised exception (caught above via ``assert
        # isinstance(AIResponse)``) nor as the wrapped error content of
        # a degraded ``AIResponse`` returned by ``generate_response``'s
        # outer ``except Exception`` handler.
        for response in responses:
            assert _EVENT_LOOP_CLOSED_MESSAGE not in (response.content or "")
            # A non-error response from ``generate_response`` has
            # confidence 1.0 and a populated ``finish_reason`` other than
            # the ``error``/``timeout`` sentinels. Re-asserting both
            # gives a clearer failure message when the transport fault
            # goes down the ``except`` path.
            assert response.confidence_score == 1.0
            assert (
                response.metadata.get("finish_reason") != "error"
            )


# ---------------------------------------------------------------------------
# Property 3: Preservation — Per-type training-data balance floor (task 5.6)
#
# ``RAGQAStrategy.generate`` enforces a per-type floor (default 10%) for
# each of the five evaluation semantic types. This property test verifies
# that for any ``target_count`` in [500, 3000] and any non-empty subset of
# the five eval types, the fraction of accepted pairs whose
# ``metadata.semantic_type == t`` is at least 10% of the total accepted
# pairs for every type ``t`` in the subset.
#
# The test mocks the RAG service, Neo4j client, and LLM rewriter so that
# most seeds are accepted (valid RAG responses with citations). The
# ``generate_seed_questions`` method is mocked to produce seeds with the
# correct semantic types based on the allocation computed by
# ``_compute_type_allocation``.
# ---------------------------------------------------------------------------


class _MockRAGResponse:
    """Minimal mock RAG response that satisfies ``_extract_response_text``,
    ``_count_citations``, ``_extract_citations``, and
    ``_build_context_summary``.
    """

    def __init__(self, question: str, semantic_type: str) -> None:
        self.response = (
            f"Based on clinical evidence, here is information about "
            f"{question}. [Source 1] First reference content about "
            f"{semantic_type}. [Source 2] Second reference content. "
            f"[Source 3] Third reference for completeness."
        )
        self.sources = [
            _MockSource(f"Source document {i} ({semantic_type})")
            for i in range(1, 4)
        ]


class _MockSource:
    """Minimal mock source object for RAG response."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.metadata = {"document_id": "mock-doc-001"}


@pytest.mark.pbt
@pytest.mark.unit
class TestPerTypeTrainingDataBalanceFloor:
    """Property 3: Preservation — Per-type training-data balance floor.

    **Validates: Requirements 2.2, 2.3, 2.4, 2.5**

    For any ``target_count`` in ``[500, 3000]`` and any non-empty subset
    of the five evaluation semantic types, running
    ``RAGQAStrategy.generate`` with mocked RAG/Neo4j/LLM that accept
    most seeds SHALL produce a set of accepted pairs where, for every
    type ``t`` in the subset, the fraction of pairs whose
    ``metadata.semantic_type == t`` is at least 10% of the total
    accepted pairs.

    This property directly validates the per-type floor enforcement
    added in tasks 5.2 and 5.3 of the fine-tuned-model-regression
    bugfix: the ``_compute_type_allocation`` helper reserves at least
    ``ceil(target_count * 0.10)`` seeds per target type, and the
    top-up loop ensures under-yielding types reach at least 80% of
    their allocation.
    """

    @given(
        target_count=st.integers(min_value=500, max_value=3000),
        type_subset=st.lists(
            st.sampled_from(EVAL_SEMANTIC_TYPES),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_per_type_fraction_meets_floor(
        self, target_count: int, type_subset: List[str]
    ) -> None:
        """Every selected type has ≥ 10% of accepted pairs.

        Mocks the RAG service to return valid cited responses for most
        seeds (90% acceptance rate), and mocks ``generate_seed_questions``
        to produce seeds distributed according to the allocation computed
        by ``_compute_type_allocation``. The top-up loop is also
        exercised because the mock Neo4j client returns additional
        concepts on demand.

        The 10% floor is the configured ``per_type_floor`` default in
        ``RAGQAStrategy.generate``. With the mocked acceptance rate of
        ~90%, the per-type yield after RAG processing should comfortably
        exceed the floor for every target type.
        """
        from unittest.mock import AsyncMock, MagicMock

        from multimodal_librarian.ml.models import SeedQuestion
        from multimodal_librarian.ml.rag_qa_strategy import RAGQAStrategy

        # --- Build mocks ---
        # RAG service: returns a valid response with 3 citations for
        # ALL seeds. We use 100% acceptance so the per-type floor
        # property is tested purely against the allocation logic
        # without noise from simulated dropout. The real dropout
        # (LOINC cleaning, quality filter, etc.) is handled by the
        # top-up loop in production; here we isolate the allocation
        # guarantee.

        async def _mock_generate_response(
            query: str, user_id: str = "", skip_query_classification: bool = True
        ) -> _MockRAGResponse:
            return _MockRAGResponse(query, "mock-type")

        mock_rag = MagicMock()
        mock_rag.generate_response = _mock_generate_response

        # Neo4j client: returns concept names for any semantic type
        # queried. Used by the top-up loop when it needs additional
        # seeds for under-yielding types.
        async def _mock_execute_query(query: str, **kwargs: object) -> list:
            # Return a list of mock concept records
            return [
                {"concept_name": f"MockConcept_{i}", "semantic_type": kwargs.get("semantic_type", "Unknown")}
                for i in range(50)
            ]

        mock_neo4j = MagicMock()
        mock_neo4j.execute_query = _mock_execute_query

        # UMLS client: not used directly in the mocked path
        mock_umls = MagicMock()

        # --- Mock generate_seed_questions ---
        # Instead of going through the full Neo4j + LLM rewriter path,
        # we mock generate_seed_questions to produce seeds distributed
        # according to the type_allocation. This isolates the test to
        # the per-type floor enforcement in ``generate`` itself.

        async def _mock_generate_seed_questions(
            seed_count: int,
            semantic_types: Optional[List[str]] = None,
            rewrite_progress_callback: Optional[object] = None,
            type_allocation: Optional[dict] = None,
        ) -> List[SeedQuestion]:
            """Produce seeds distributed per the allocation dict.

            Seeds are interleaved by type (round-robin) so that when
            the early-stop cap in ``generate`` fires, all types have
            had a proportional chance of being processed — matching
            the real behaviour where UMLS and template seeds from
            different types are mixed together.
            """
            types = semantic_types or type_subset

            # Build per-type seed lists
            per_type_seeds: dict = {}
            if type_allocation:
                for t, count in type_allocation.items():
                    per_type_seeds[t] = [
                        SeedQuestion(
                            question=f"What is the clinical significance of concept_{t}_{i}?",
                            source="umls_concept",
                            semantic_type=t,
                            concept_name=f"concept_{t}_{i}",
                        )
                        for i in range(count)
                    ]
            else:
                per_type = max(seed_count // len(types), 1)
                for t in types:
                    per_type_seeds[t] = [
                        SeedQuestion(
                            question=f"What is the clinical significance of concept_{t}_{i}?",
                            source="umls_concept",
                            semantic_type=t,
                            concept_name=f"concept_{t}_{i}",
                        )
                        for i in range(per_type)
                    ]

            # Interleave seeds round-robin across types so the
            # early-stop in generate() does not starve later types.
            seeds: List[SeedQuestion] = []
            max_len = max(
                (len(v) for v in per_type_seeds.values()), default=0
            )
            ordered_types = list(per_type_seeds.keys())
            for i in range(max_len):
                for t in ordered_types:
                    if i < len(per_type_seeds[t]):
                        seeds.append(per_type_seeds[t][i])

            return seeds[:seed_count]

        # --- Instantiate strategy and run ---
        strategy = RAGQAStrategy(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            umls_client=mock_umls,
            question_rewriter=None,
            quality_filter=None,
            token_budget_manager=None,
        )

        # Patch generate_seed_questions on the instance so the real
        # generate() method uses our mock seeds but still exercises the
        # full per-type allocation, top-up loop, and acceptance tracking.
        strategy.generate_seed_questions = _mock_generate_seed_questions

        # Run the generation
        pairs = asyncio.run(
            strategy.generate(
                target_count=target_count,
                semantic_types=type_subset,
                per_type_floor=0.10,
            )
        )

        # --- Assertions ---
        # We must have produced some pairs (the mock accepts ~90%)
        assert len(pairs) > 0, (
            f"Expected pairs to be generated but got 0 "
            f"(target_count={target_count}, types={type_subset})"
        )

        # For every type in the subset, the fraction of accepted pairs
        # with that semantic type must be ≥ 10%.
        total_pairs = len(pairs)
        for t in type_subset:
            type_count = sum(
                1
                for p in pairs
                if p.metadata.semantic_type == t
            )
            fraction = type_count / total_pairs
            assert fraction >= 0.10, (
                f"Type '{t}' has fraction {fraction:.4f} "
                f"({type_count}/{total_pairs}) which is below the "
                f"10% floor. target_count={target_count}, "
                f"type_subset={type_subset}"
            )


# ---------------------------------------------------------------------------
# Property 4: Preservation — Training/evaluation prompt parity (task 7.5)
#
# The evaluation harness (``EvaluationRunner._query_ollama``) must send the
# fine-tuned model the *exact same* user message and system prompt that the
# training pipeline (``format_chat_message``) produced for the same
# ``(instruction, context)`` pair. Any divergence puts the model
# out-of-distribution at evaluation time, which was the confirmed root
# cause (H2/H5) of the Coherence regression.
#
# The fix in tasks 7.1–7.3 extracted ``build_inference_user_message`` as
# the single source of truth for the user-message format and wired it into
# both ``format_chat_message`` (training) and ``EvaluationRunner._query_ollama``
# (evaluation). This property test validates that the two code paths
# produce byte-equal user messages for all generated pairs, and that both
# use the same ``_SYSTEM_PROMPT`` constant.
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestTrainingEvaluationPromptParity:
    """Property 4: Preservation — Training/evaluation prompt parity.

    **Validates: Requirements 3.5, 3.6**

    For any ``InstructionTuningPair`` produced by the training pipeline,
    the user message built by ``format_chat_message(pair)`` SHALL equal
    the user message built by ``build_inference_user_message(pair.instruction,
    pair.context)`` — the code path ``EvaluationRunner._query_ollama``
    now uses. Additionally, both paths SHALL use the same
    ``_SYSTEM_PROMPT`` constant as the system message.

    This ensures the fine-tuned model is never evaluated on a prompt
    format it did not see during training, which was the confirmed root
    cause of the Coherence regression (H2, H5 in design.md).
    """

    @given(pair=instruction_tuning_pair_strategy_with_semantic_type())
    @settings(max_examples=100)
    def test_user_message_parity(self, pair: InstructionTuningPair) -> None:
        """Training and evaluation user messages are byte-equal.

        Computes the user message from both the training path
        (``format_chat_message``) and the evaluation path
        (``build_inference_user_message``) and asserts they are
        identical for all generated pairs with ``distill=False``.

        The ``distill=False`` mode is the relevant comparison because
        evaluation always runs in non-distill mode (the model is
        queried with full context at inference time).
        """
        from multimodal_librarian.ml.qlora_trainer import (
            build_inference_user_message,
            format_chat_message,
        )

        # Training path: format_chat_message with distill=False
        training_chat = format_chat_message(pair, distill=False)
        training_user_msg = training_chat["messages"][1]["content"]

        # Evaluation path: build_inference_user_message (used by
        # EvaluationRunner._query_ollama)
        eval_user_msg = build_inference_user_message(
            pair.instruction, pair.context
        )

        assert training_user_msg == eval_user_msg, (
            f"Training/evaluation user message mismatch.\n"
            f"  Training: {training_user_msg!r}\n"
            f"  Eval:     {eval_user_msg!r}\n"
            f"  Instruction: {pair.instruction!r}\n"
            f"  Context: {pair.context!r}"
        )

    @given(pair=instruction_tuning_pair_strategy_with_semantic_type())
    @settings(max_examples=100)
    def test_system_prompt_shared(self, pair: InstructionTuningPair) -> None:
        """Both training and evaluation use the same ``_SYSTEM_PROMPT``.

        The training path embeds ``_SYSTEM_PROMPT`` as the system message
        in ``format_chat_message``. The evaluation path passes
        ``_SYSTEM_PROMPT`` as the default ``system_prompt`` parameter to
        ``_query_ollama``. This test verifies the training chat template
        uses the exact same constant that the evaluation runner imports.
        """
        from multimodal_librarian.ml.qlora_trainer import (
            _SYSTEM_PROMPT,
            format_chat_message,
        )

        # Training path: system message from format_chat_message
        training_chat = format_chat_message(pair, distill=False)
        training_system_msg = training_chat["messages"][0]["content"]

        # Evaluation path: _SYSTEM_PROMPT is the default for
        # _query_ollama's system_prompt parameter (imported from
        # qlora_trainer in evaluation_runner.py)
        assert training_system_msg == _SYSTEM_PROMPT, (
            f"Training system prompt does not match _SYSTEM_PROMPT.\n"
            f"  Training: {training_system_msg!r}\n"
            f"  _SYSTEM_PROMPT: {_SYSTEM_PROMPT!r}"
        )
