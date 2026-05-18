"""
Property-based tests for the conversational training data pipeline.

# Feature: conversational-training-data
# Property 1: LOINC cleaning removes all coded patterns

Validates: Requirements 1.3, 4.2
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.loinc_cleaner import (
    _CODED_SUFFIX_PATTERN,
    _HTML_ENTITY_PATTERN,
    _LOINC_PIPE_PATTERN,
    clean_concept_name,
    is_loinc_coded,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies for generating LOINC-coded concept names
# ---------------------------------------------------------------------------

# Known LOINC coded suffixes used in UMLS concept names.
_CODED_SUFFIXES: list[str] = [
    "ANYProp",
    "ANYTm",
    "ANYSys",
    "ANYMeth",
    "Pt",
    "Bld",
    "Ser",
    "Plas",
    "Urine",
    "CSF",
    "LC/MS/MS",
    "IA",
    "Qn",
    "Ord",
    "Nom",
]


def _html_entity() -> st.SearchStrategy[str]:
    """Generate a random HTML hex entity like ``&#xNN;`` or ``&#x7C;``."""
    return st.integers(min_value=0x00, max_value=0xFF).map(
        lambda n: f"&#x{n:02X};"
    )


def _pipe_field() -> st.SearchStrategy[str]:
    """Generate a pipe-separated field segment (``|<content>``)."""
    return st.text(
        alphabet=st.characters(blacklist_characters="|"),
        min_size=0,
        max_size=20,
    ).map(lambda t: f"|{t}")


def _coded_suffix() -> st.SearchStrategy[str]:
    """Generate a single LOINC coded suffix token."""
    return st.sampled_from(_CODED_SUFFIXES)


def _base_concept_name() -> st.SearchStrategy[str]:
    """Generate a plausible base concept name (human-readable portion).

    Uses printable text that does *not* contain LOINC patterns so we can
    verify the cleaner preserves it.
    """
    return (
        st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
                blacklist_characters="|&#;",
            ),
            min_size=1,
            max_size=60,
        )
        .filter(lambda s: s.strip())
        .filter(lambda s: not _CODED_SUFFIX_PATTERN.search(s))
    )


def _loinc_coded_name_with_pipes() -> st.SearchStrategy[str]:
    """Generate a concept name with pipe-separated LOINC fields.

    Example output: ``cycloSPORINE|Pt|Bld|LC/MS/MS``
    """
    return st.tuples(
        _base_concept_name(),
        st.lists(_pipe_field(), min_size=1, max_size=5),
    ).map(lambda t: t[0] + "".join(t[1]))


def _loinc_coded_name_with_html() -> st.SearchStrategy[str]:
    """Generate a concept name with HTML entities injected.

    Example output: ``aspirin&#x7C;Pt&#x3B;Bld``
    """
    return st.tuples(
        _base_concept_name(),
        st.lists(_html_entity(), min_size=1, max_size=4),
    ).map(lambda t: t[0] + " ".join(t[1]))


def _loinc_coded_name_with_suffixes() -> st.SearchStrategy[str]:
    """Generate a concept name with coded suffix tokens appended.

    Example output: ``metformin Pt Bld Qn``
    """
    return st.tuples(
        _base_concept_name(),
        st.lists(_coded_suffix(), min_size=1, max_size=4),
    ).map(lambda t: t[0] + " " + " ".join(t[1]))


def _loinc_coded_name_mixed() -> st.SearchStrategy[str]:
    """Generate a concept name combining pipes, HTML entities, and suffixes."""
    return st.tuples(
        _base_concept_name(),
        st.lists(_pipe_field(), min_size=0, max_size=3),
        st.lists(_html_entity(), min_size=0, max_size=2),
        st.lists(_coded_suffix(), min_size=0, max_size=2),
    ).filter(
        # Ensure at least one LOINC pattern is present
        lambda t: len(t[1]) + len(t[2]) + len(t[3]) > 0
    ).map(
        lambda t: t[0]
        + "".join(t[1])
        + (" " + " ".join(t[2]) if t[2] else "")
        + (" " + " ".join(t[3]) if t[3] else "")
    )


def loinc_coded_concept_strategy() -> st.SearchStrategy[str]:
    """Generate any style of LOINC-coded concept name."""
    return st.one_of(
        _loinc_coded_name_with_pipes(),
        _loinc_coded_name_with_html(),
        _loinc_coded_name_with_suffixes(),
        _loinc_coded_name_mixed(),
    )


# ---------------------------------------------------------------------------
# Property 1: LOINC cleaning removes all coded patterns
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestLOINCCleaningRemovesAllCodedPatterns:
    """Property 1: LOINC cleaning removes all coded patterns.

    For any UMLS concept name string containing LOINC-coded patterns
    (pipe-separated fields, HTML entities like ``&#x7C;``, or coded
    suffixes like ``ANYProp``, ``ANYTm``, ``ANYSys``, ``ANYMeth``),
    ``clean_concept_name()`` SHALL return a string that contains none
    of those patterns, and ``is_loinc_coded()`` applied to the cleaned
    output SHALL return False.

    Validates: Requirements 1.3, 4.2
    """

    # -- Core property: is_loinc_coded(clean_concept_name(raw)) == False ----

    @given(raw=loinc_coded_concept_strategy())
    @settings(max_examples=100)
    def test_cleaned_output_is_not_loinc_coded(self, raw: str) -> None:
        """After cleaning, ``is_loinc_coded`` must return False."""
        # Feature: conversational-training-data, Property 1: LOINC cleaning removes all coded patterns
        cleaned = clean_concept_name(raw)
        assert not is_loinc_coded(cleaned), (
            f"is_loinc_coded() returned True on cleaned output.\n"
            f"  raw   = {raw!r}\n"
            f"  clean = {cleaned!r}"
        )

    # -- No pipe-separated fields remain ------------------------------------

    @given(raw=loinc_coded_concept_strategy())
    @settings(max_examples=100)
    def test_cleaned_output_has_no_pipe_fields(self, raw: str) -> None:
        """Cleaned output must not contain pipe-separated fields."""
        # Feature: conversational-training-data, Property 1: LOINC cleaning removes all coded patterns
        cleaned = clean_concept_name(raw)
        assert not _LOINC_PIPE_PATTERN.search(cleaned), (
            f"Pipe-separated field found in cleaned output.\n"
            f"  raw   = {raw!r}\n"
            f"  clean = {cleaned!r}"
        )

    # -- No HTML entities remain --------------------------------------------

    @given(raw=loinc_coded_concept_strategy())
    @settings(max_examples=100)
    def test_cleaned_output_has_no_html_entities(self, raw: str) -> None:
        """Cleaned output must not contain HTML hex entities."""
        # Feature: conversational-training-data, Property 1: LOINC cleaning removes all coded patterns
        cleaned = clean_concept_name(raw)
        assert not _HTML_ENTITY_PATTERN.search(cleaned), (
            f"HTML entity found in cleaned output.\n"
            f"  raw   = {raw!r}\n"
            f"  clean = {cleaned!r}"
        )

    # -- No coded suffixes remain -------------------------------------------

    @given(raw=loinc_coded_concept_strategy())
    @settings(max_examples=100)
    def test_cleaned_output_has_no_coded_suffixes(self, raw: str) -> None:
        """Cleaned output must not contain LOINC coded suffix tokens."""
        # Feature: conversational-training-data, Property 1: LOINC cleaning removes all coded patterns
        cleaned = clean_concept_name(raw)
        assert not _CODED_SUFFIX_PATTERN.search(cleaned), (
            f"Coded suffix found in cleaned output.\n"
            f"  raw   = {raw!r}\n"
            f"  clean = {cleaned!r}"
        )

    # -- Cleaning is idempotent ---------------------------------------------

    @given(raw=loinc_coded_concept_strategy())
    @settings(max_examples=100)
    def test_cleaning_is_idempotent(self, raw: str) -> None:
        """Applying ``clean_concept_name`` twice yields the same result."""
        # Feature: conversational-training-data, Property 1: LOINC cleaning removes all coded patterns
        once = clean_concept_name(raw)
        twice = clean_concept_name(once)
        assert once == twice, (
            f"Cleaning is not idempotent.\n"
            f"  raw   = {raw!r}\n"
            f"  once  = {once!r}\n"
            f"  twice = {twice!r}"
        )

    # -- Arbitrary text (no injected patterns) stays clean ------------------

    @given(raw=st.text(min_size=0, max_size=200))
    @settings(max_examples=100)
    def test_clean_of_clean_is_not_loinc_coded(self, raw: str) -> None:
        """For any text, the cleaned result must not be flagged as LOINC-coded."""
        # Feature: conversational-training-data, Property 1: LOINC cleaning removes all coded patterns
        cleaned = clean_concept_name(raw)
        assert not is_loinc_coded(cleaned), (
            f"is_loinc_coded() returned True on cleaned arbitrary text.\n"
            f"  raw   = {raw!r}\n"
            f"  clean = {cleaned!r}"
        )

    # -- Empty / whitespace-only input returns empty string -----------------

    @given(raw=st.from_regex(r"^\s*$", fullmatch=True))
    @settings(max_examples=50)
    def test_whitespace_only_input_returns_empty(self, raw: str) -> None:
        """Whitespace-only input must clean to an empty string."""
        # Feature: conversational-training-data, Property 1: LOINC cleaning removes all coded patterns
        assert clean_concept_name(raw) == ""


# ---------------------------------------------------------------------------
# Property 2: Textbook style classification correctness
# ---------------------------------------------------------------------------

# Import the quality filter and its internal stem/pattern lists so we can
# generate inputs that are guaranteed to match (or guaranteed not to match).
from multimodal_librarian.ml.quality_filter import _TEXTBOOK_STEMS, QualityFilter

# Stems that do NOT contain a ``{concept_name}`` placeholder.
# These can be used directly as question prefixes.
_PLAIN_STEMS: list[str] = [
    s for s in _TEXTBOOK_STEMS if "{concept_name}" not in s
]

# Stems that DO contain a ``{concept_name}`` placeholder.
# The compiled patterns replace the placeholder with empty string and
# collapse whitespace, so these match when the placeholder position
# contains only whitespace.
_TEMPLATE_STEMS: list[str] = [
    s for s in _TEXTBOOK_STEMS if "{concept_name}" in s
]

# Exam-style prefixes that match ``_EXAM_STYLE_PATTERNS``.
_EXAM_PREFIXES: list[str] = [
    "Which of the following is true about",
    "All of the following EXCEPT",
    "A 45-year-old male presents with",
    "A 32-year-old female presents with",
    "The most likely diagnosis is",
    "Select the best answer for",
]


def _filled_template_stems() -> list[str]:
    """Return template stems with ``{concept_name}`` removed.

    The compiled patterns match when the placeholder position is
    whitespace, so we remove the placeholder to produce strings that
    the classifier will actually match.
    """
    return [s.replace("{concept_name}", "") for s in _TEMPLATE_STEMS]


# All concrete textbook-style prefixes (plain stems + filled templates).
_ALL_TEXTBOOK_PREFIXES: list[str] = _PLAIN_STEMS + _filled_template_stems()


def _textbook_question_from_stem() -> st.SearchStrategy[str]:
    """Generate a question that starts with a known textbook stem.

    Picks a plain stem and appends arbitrary trailing text so the
    question is a complete sentence.
    """
    return st.tuples(
        st.sampled_from(_PLAIN_STEMS),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=1,
            max_size=80,
        ),
    ).map(lambda t: t[0] + " " + t[1] + "?")


def _textbook_question_from_template_stem() -> st.SearchStrategy[str]:
    """Generate a question from a template stem with the placeholder removed.

    The compiled ``_TEXTBOOK_STEM_PATTERNS`` replace ``{concept_name}``
    with empty string and collapse whitespace, so the resulting regex
    matches when the placeholder position contains only whitespace.
    We generate questions that match this compiled pattern by removing
    the placeholder (leaving a double space) and appending trailing text.
    """
    return st.tuples(
        st.sampled_from(_TEMPLATE_STEMS),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=0,
            max_size=60,
        ),
    ).map(
        lambda t: t[0].replace("{concept_name}", "")
        + (" " + t[1] if t[1] else "")
        + "?"
    )


def _exam_style_question() -> st.SearchStrategy[str]:
    """Generate a question matching an exam-style structural pattern."""
    return st.tuples(
        st.sampled_from(_EXAM_PREFIXES),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=1,
            max_size=80,
        ),
    ).map(lambda t: t[0] + " " + t[1] + "?")


def _textbook_question_with_leading_whitespace() -> st.SearchStrategy[str]:
    """Generate a textbook question with optional leading whitespace.

    The classifier strips leading whitespace before matching, so
    textbook questions with leading spaces/tabs should still be
    classified as ``"textbook"``.
    """
    return st.tuples(
        st.text(
            alphabet=st.sampled_from(" \t"),
            min_size=1,
            max_size=5,
        ),
        st.one_of(
            _textbook_question_from_stem(),
            _exam_style_question(),
        ),
    ).map(lambda t: t[0] + t[1])


def textbook_question_strategy() -> st.SearchStrategy[str]:
    """Generate any style of textbook/exam question."""
    return st.one_of(
        _textbook_question_from_stem(),
        _textbook_question_from_template_stem(),
        _exam_style_question(),
        _textbook_question_with_leading_whitespace(),
    )


# Conversational question prefixes that should NOT match any textbook
# stem or exam pattern.  These are phrased as a real user would type
# in a chat interface.
_CONVERSATIONAL_PREFIXES: list[str] = [
    "Can you tell me about",
    "I was wondering about",
    "Hey, what do you know about",
    "My doctor mentioned",
    "I just got prescribed",
    "Is it safe to take",
    "How long does it take for",
    "What should I expect when taking",
    "I have a question about",
    "Could you explain",
    "Tell me more about",
    "Why would someone need",
    "What happens if I miss a dose of",
    "Are there any side effects of",
    "How does this compare to",
]


def _conversational_question() -> st.SearchStrategy[str]:
    """Generate a conversational question that should NOT match textbook patterns.

    Uses known conversational prefixes combined with arbitrary trailing
    text.  The prefixes are chosen to avoid accidentally matching any
    textbook stem or exam pattern.
    """
    return st.tuples(
        st.sampled_from(_CONVERSATIONAL_PREFIXES),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=1,
            max_size=80,
        ),
    ).map(lambda t: t[0] + " " + t[1] + "?")


@pytest.mark.pbt
@pytest.mark.unit
class TestTextbookStyleClassificationCorrectness:
    """Property 2: Textbook style classification correctness.

    For any question string that begins with a known textbook stem,
    ``classify_question_style()`` SHALL return ``"textbook"``.
    Conversely, for any question string that does not begin with any
    banned textbook stem and does not match exam-style structural
    patterns, ``classify_question_style()`` SHALL return
    ``"conversational"``.

    Validates: Requirements 1.1, 1.5, 4.5
    """

    def setup_method(self) -> None:
        """Create a fresh QualityFilter for each test method."""
        self._filter = QualityFilter()

    # -- Textbook stems are classified as "textbook" -----------------------

    @given(question=_textbook_question_from_stem())
    @settings(max_examples=100)
    def test_plain_stem_classified_as_textbook(self, question: str) -> None:
        """Questions starting with a plain textbook stem must be 'textbook'."""
        # Feature: conversational-training-data, Property 2: Textbook style classification correctness
        result = self._filter.classify_question_style(question)
        assert result == "textbook", (
            f"Expected 'textbook' but got '{result}' for:\n"
            f"  question = {question!r}"
        )

    # -- Template stems (with concept name filled in) are "textbook" -------

    @given(question=_textbook_question_from_template_stem())
    @settings(max_examples=100)
    def test_template_stem_classified_as_textbook(
        self, question: str
    ) -> None:
        """Questions from template stems with concept names must be 'textbook'."""
        # Feature: conversational-training-data, Property 2: Textbook style classification correctness
        result = self._filter.classify_question_style(question)
        assert result == "textbook", (
            f"Expected 'textbook' but got '{result}' for:\n"
            f"  question = {question!r}"
        )

    # -- Exam-style patterns are classified as "textbook" ------------------

    @given(question=_exam_style_question())
    @settings(max_examples=100)
    def test_exam_style_classified_as_textbook(self, question: str) -> None:
        """Questions matching exam-style patterns must be 'textbook'."""
        # Feature: conversational-training-data, Property 2: Textbook style classification correctness
        result = self._filter.classify_question_style(question)
        assert result == "textbook", (
            f"Expected 'textbook' but got '{result}' for:\n"
            f"  question = {question!r}"
        )

    # -- Leading whitespace does not prevent textbook classification -------

    @given(question=_textbook_question_with_leading_whitespace())
    @settings(max_examples=100)
    def test_leading_whitespace_still_textbook(self, question: str) -> None:
        """Textbook questions with leading whitespace must still be 'textbook'."""
        # Feature: conversational-training-data, Property 2: Textbook style classification correctness
        result = self._filter.classify_question_style(question)
        assert result == "textbook", (
            f"Expected 'textbook' but got '{result}' for:\n"
            f"  question = {question!r}"
        )

    # -- Conversational questions are classified as "conversational" -------

    @given(question=_conversational_question())
    @settings(max_examples=100)
    def test_conversational_classified_as_conversational(
        self, question: str
    ) -> None:
        """Questions with conversational phrasing must be 'conversational'."""
        # Feature: conversational-training-data, Property 2: Textbook style classification correctness
        result = self._filter.classify_question_style(question)
        assert result == "conversational", (
            f"Expected 'conversational' but got '{result}' for:\n"
            f"  question = {question!r}"
        )

    # -- Classification is deterministic -----------------------------------

    @given(question=st.one_of(textbook_question_strategy(), _conversational_question()))
    @settings(max_examples=100)
    def test_classification_is_deterministic(self, question: str) -> None:
        """Calling classify_question_style twice yields the same result."""
        # Feature: conversational-training-data, Property 2: Textbook style classification correctness
        first = self._filter.classify_question_style(question)
        second = self._filter.classify_question_style(question)
        assert first == second, (
            f"Non-deterministic classification for:\n"
            f"  question = {question!r}\n"
            f"  first    = {first!r}\n"
            f"  second   = {second!r}"
        )

    # -- Return value is always one of the two valid labels ----------------

    @given(question=st.text(min_size=0, max_size=300))
    @settings(max_examples=100)
    def test_return_value_is_valid_label(self, question: str) -> None:
        """classify_question_style must return 'textbook' or 'conversational'."""
        # Feature: conversational-training-data, Property 2: Textbook style classification correctness
        result = self._filter.classify_question_style(question)
        assert result in ("textbook", "conversational"), (
            f"Unexpected classification label '{result}' for:\n"
            f"  question = {question!r}"
        )


# ---------------------------------------------------------------------------
# Property 3: MCQ marker detection and rejection
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.models import (  # noqa: E402
    InstructionTuningPair,
    PairMetadata,
)
from multimodal_librarian.ml.quality_filter import _MCQ_THRESHOLD  # noqa: E402

# The nine distinct MCQ marker strings.  Each must be followed by a
# space (or, for "correct answer is", can appear anywhere) to match
# the compiled ``_MCQ_PATTERNS`` regexes in ``quality_filter.py``.
_MCQ_MARKER_STRINGS: list[str] = [
    "A. ",
    "B. ",
    "C. ",
    "D. ",
    "(a) ",
    "(b) ",
    "(c) ",
    "(d) ",
    "correct answer is",
]


def _safe_filler() -> st.SearchStrategy[str]:
    """Filler text that cannot accidentally contain MCQ markers.

    Uses only lowercase letters that avoid the patterns ``A.``,
    ``B.``, ``C.``, ``D.``, ``(a)``, ``(b)``, ``(c)``, ``(d)``
    and the phrase ``correct answer is``.
    """
    return st.text(
        alphabet=st.sampled_from("efghijklmnopqrstuvwxyz "),
        min_size=10,
        max_size=120,
    )


def _response_with_n_mcq_markers(
    n: int,
) -> st.SearchStrategy[str]:
    """Build a response containing exactly *n* distinct MCQ markers.

    Markers are drawn without replacement from
    ``_MCQ_MARKER_STRINGS`` and interleaved with safe filler text
    so the response looks realistic.
    """
    if n == 0:
        return _safe_filler()

    return st.tuples(
        # Pick exactly n distinct markers
        st.lists(
            st.sampled_from(_MCQ_MARKER_STRINGS),
            min_size=n,
            max_size=n,
            unique=True,
        ),
        # Filler segments (one more than markers to surround them)
        st.lists(
            _safe_filler(),
            min_size=n + 1,
            max_size=n + 1,
        ),
    ).map(
        lambda t: _interleave(t[1], t[0])
    )


def _interleave(
    fillers: list[str], markers: list[str]
) -> str:
    """Interleave filler segments with marker strings.

    Given fillers ``[f0, f1, f2]`` and markers ``[m0, m1]``,
    produces ``f0 + m0 + f1 + m1 + f2``.
    """
    parts: list[str] = []
    for i, filler in enumerate(fillers):
        parts.append(filler)
        if i < len(markers):
            parts.append(markers[i])
    return " ".join(parts)


def _make_pair(response: str) -> InstructionTuningPair:
    """Build a minimal ``InstructionTuningPair`` with the given response.

    The instruction and context are innocuous conversational text
    so they do not trigger other filter checks (textbook style,
    LOINC instruction, etc.).
    """
    return InstructionTuningPair(
        instruction="Can you tell me about this medication?",
        context="Some relevant medical context here.",
        response=response,
        metadata=PairMetadata(
            strategy="rag",
            confidence_score=0.8,
        ),
    )


@pytest.mark.pbt
@pytest.mark.unit
class TestMCQMarkerDetectionAndRejection:
    """Property 3: MCQ marker detection and rejection.

    For any response string, if it contains three or more
    multiple-choice markers from the set {``A.``, ``B.``,
    ``C.``, ``D.``, ``(a)``, ``(b)``, ``(c)``, ``(d)``,
    ``"correct answer is"``}, the ``QualityFilter`` SHALL reject
    the pair with reason ``"mcq_markers"``.  If the response
    contains fewer than three such markers, the filter SHALL NOT
    reject for this reason.

    Validates: Requirements 4.1
    """

    def setup_method(self) -> None:
        self._filter = QualityFilter()

    # -- 3+ markers → rejection with "mcq_markers" -----------------------

    @given(
        n=st.integers(
            min_value=_MCQ_THRESHOLD,
            max_value=len(_MCQ_MARKER_STRINGS),
        ),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_three_or_more_markers_rejected(
        self, n: int, data: st.DataObject
    ) -> None:
        """Responses with 3+ MCQ markers must be rejected."""
        # Feature: conversational-training-data,
        # Property 3: MCQ marker detection and rejection
        response = data.draw(
            _response_with_n_mcq_markers(n),
            label=f"response_with_{n}_markers",
        )
        pair = _make_pair(response)
        result = self._filter.evaluate(pair)
        assert "mcq_markers" in result.rejection_reasons, (
            f"Expected 'mcq_markers' rejection for {n} markers.\n"
            f"  response = {response!r}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- <3 markers → no "mcq_markers" rejection --------------------------

    @given(
        n=st.integers(min_value=0, max_value=_MCQ_THRESHOLD - 1),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_fewer_than_three_markers_not_rejected(
        self, n: int, data: st.DataObject
    ) -> None:
        """Responses with <3 MCQ markers must NOT be rejected for mcq."""
        # Feature: conversational-training-data,
        # Property 3: MCQ marker detection and rejection
        response = data.draw(
            _response_with_n_mcq_markers(n),
            label=f"response_with_{n}_markers",
        )
        pair = _make_pair(response)
        result = self._filter.evaluate(pair)
        assert "mcq_markers" not in result.rejection_reasons, (
            f"Unexpected 'mcq_markers' rejection for {n} markers.\n"
            f"  response = {response!r}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Exactly at threshold boundary ------------------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_exactly_at_threshold_rejected(
        self, data: st.DataObject
    ) -> None:
        """Responses with exactly 3 MCQ markers must be rejected."""
        # Feature: conversational-training-data,
        # Property 3: MCQ marker detection and rejection
        response = data.draw(
            _response_with_n_mcq_markers(_MCQ_THRESHOLD),
            label="response_at_threshold",
        )
        pair = _make_pair(response)
        result = self._filter.evaluate(pair)
        assert "mcq_markers" in result.rejection_reasons, (
            f"Expected rejection at threshold ({_MCQ_THRESHOLD}).\n"
            f"  response = {response!r}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- One below threshold → no rejection --------------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_one_below_threshold_not_rejected(
        self, data: st.DataObject
    ) -> None:
        """Responses with threshold-1 MCQ markers must NOT be rejected."""
        # Feature: conversational-training-data,
        # Property 3: MCQ marker detection and rejection
        response = data.draw(
            _response_with_n_mcq_markers(_MCQ_THRESHOLD - 1),
            label="response_below_threshold",
        )
        pair = _make_pair(response)
        result = self._filter.evaluate(pair)
        assert "mcq_markers" not in result.rejection_reasons, (
            f"Unexpected rejection below threshold.\n"
            f"  response = {response!r}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Zero markers → clean pass (no mcq reason) ------------------------

    @given(response=_safe_filler())
    @settings(max_examples=100)
    def test_zero_markers_no_mcq_rejection(
        self, response: str
    ) -> None:
        """Responses with zero MCQ markers must not trigger mcq rejection."""
        # Feature: conversational-training-data,
        # Property 3: MCQ marker detection and rejection
        pair = _make_pair(response)
        result = self._filter.evaluate(pair)
        assert "mcq_markers" not in result.rejection_reasons, (
            f"Unexpected 'mcq_markers' for marker-free response.\n"
            f"  response = {response!r}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Detection is deterministic ----------------------------------------

    @given(
        n=st.integers(
            min_value=0,
            max_value=len(_MCQ_MARKER_STRINGS),
        ),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_mcq_detection_is_deterministic(
        self, n: int, data: st.DataObject
    ) -> None:
        """Evaluating the same response twice yields same mcq result."""
        # Feature: conversational-training-data,
        # Property 3: MCQ marker detection and rejection
        response = data.draw(
            _response_with_n_mcq_markers(n),
            label=f"response_with_{n}_markers",
        )
        pair = _make_pair(response)
        r1 = self._filter.evaluate(pair)
        # Use a fresh filter to avoid counter side-effects
        fresh = QualityFilter()
        r2 = fresh.evaluate(pair)
        mcq_in_r1 = "mcq_markers" in r1.rejection_reasons
        mcq_in_r2 = "mcq_markers" in r2.rejection_reasons
        assert mcq_in_r1 == mcq_in_r2, (
            f"Non-deterministic MCQ detection.\n"
            f"  response = {response!r}\n"
            f"  first    = {r1.rejection_reasons}\n"
            f"  second   = {r2.rejection_reasons}"
        )


# ---------------------------------------------------------------------------
# Property 4: Refusal detection identifies refusal phrases
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.refusal_formatter import (  # noqa: E402
    REFUSAL_INDICATORS,
    is_refusal_response,
)


def _safe_text_no_refusal() -> st.SearchStrategy[str]:
    """Generate text that cannot accidentally contain any refusal indicator.

    Uses a restricted alphabet of lowercase letters and spaces that
    avoids forming any substring matching the phrases in
    ``REFUSAL_INDICATORS``.  The indicators contain words like
    "could", "find", "information", "mentioned", "documents",
    "available", "relevant", "sources", "don't", "have" — so we
    use a small set of letters that cannot spell those words.
    """
    # Using only digits and a few consonants that don't form refusal words
    return st.text(
        alphabet=st.sampled_from("0123456789bkqxz "),
        min_size=0,
        max_size=200,
    )


def _response_with_refusal_indicator() -> st.SearchStrategy[str]:
    """Generate a response containing at least one refusal indicator phrase.

    Picks a random indicator from ``REFUSAL_INDICATORS`` and embeds it
    between safe prefix and suffix text.
    """
    return st.tuples(
        _safe_text_no_refusal(),
        st.sampled_from(REFUSAL_INDICATORS),
        _safe_text_no_refusal(),
    ).map(lambda t: t[0] + " " + t[1] + " " + t[2])


def _response_with_case_varied_indicator() -> st.SearchStrategy[str]:
    """Generate a response with a case-varied refusal indicator.

    Applies random case transformations (upper, title, swapcase) to
    the indicator phrase to verify case-insensitive matching.
    """
    case_fn = st.sampled_from([str.upper, str.title, str.swapcase, str.lower])
    return st.tuples(
        _safe_text_no_refusal(),
        st.sampled_from(REFUSAL_INDICATORS),
        case_fn,
        _safe_text_no_refusal(),
    ).map(lambda t: t[0] + " " + t[2](t[1]) + " " + t[3])


def _response_without_refusal_indicator() -> st.SearchStrategy[str]:
    """Generate a response guaranteed to contain no refusal indicator phrase.

    Uses a restricted alphabet that cannot form any of the indicator
    phrases, ensuring ``is_refusal_response`` returns False.
    """
    return _safe_text_no_refusal()


@pytest.mark.pbt
@pytest.mark.unit
class TestRefusalDetectionIdentifiesRefusalPhrases:
    """Property 4: Refusal detection identifies refusal phrases.

    For any response string containing at least one phrase from the
    ``REFUSAL_INDICATORS`` list (e.g., "could not find any
    information", "not mentioned in any of the given documents"),
    ``is_refusal_response()`` SHALL return True.  For any response
    string that does not contain any refusal indicator phrase,
    ``is_refusal_response()`` SHALL return False.

    Validates: Requirements 2.2
    """

    # -- Responses with an indicator → True --------------------------------

    @given(response=_response_with_refusal_indicator())
    @settings(max_examples=100)
    def test_response_with_indicator_detected(self, response: str) -> None:
        """Responses containing a refusal indicator must be detected."""
        # Feature: conversational-training-data,
        # Property 4: Refusal detection identifies refusal phrases
        assert is_refusal_response(response) is True, (
            f"Expected is_refusal_response() to return True.\n"
            f"  response = {response!r}"
        )

    # -- Responses with case-varied indicator → True -----------------------

    @given(response=_response_with_case_varied_indicator())
    @settings(max_examples=100)
    def test_case_insensitive_detection(self, response: str) -> None:
        """Refusal detection must be case-insensitive."""
        # Feature: conversational-training-data,
        # Property 4: Refusal detection identifies refusal phrases
        assert is_refusal_response(response) is True, (
            f"Expected case-insensitive detection to return True.\n"
            f"  response = {response!r}"
        )

    # -- Responses without any indicator → False ---------------------------

    @given(response=_response_without_refusal_indicator())
    @settings(max_examples=100)
    def test_response_without_indicator_not_detected(
        self, response: str
    ) -> None:
        """Responses without any refusal indicator must not be detected."""
        # Feature: conversational-training-data,
        # Property 4: Refusal detection identifies refusal phrases
        assert is_refusal_response(response) is False, (
            f"Expected is_refusal_response() to return False.\n"
            f"  response = {response!r}"
        )

    # -- Each individual indicator is detected -----------------------------

    @given(indicator=st.sampled_from(REFUSAL_INDICATORS))
    @settings(max_examples=len(REFUSAL_INDICATORS))
    def test_each_indicator_detected_alone(self, indicator: str) -> None:
        """Each indicator phrase by itself must be detected as a refusal."""
        # Feature: conversational-training-data,
        # Property 4: Refusal detection identifies refusal phrases
        assert is_refusal_response(indicator) is True, (
            f"Indicator not detected when used alone.\n"
            f"  indicator = {indicator!r}"
        )

    # -- Empty string → False ----------------------------------------------

    def test_empty_string_not_refusal(self) -> None:
        """An empty string must not be detected as a refusal."""
        # Feature: conversational-training-data,
        # Property 4: Refusal detection identifies refusal phrases
        assert is_refusal_response("") is False

    # -- Detection is deterministic ----------------------------------------

    @given(response=st.one_of(
        _response_with_refusal_indicator(),
        _response_without_refusal_indicator(),
    ))
    @settings(max_examples=100)
    def test_detection_is_deterministic(self, response: str) -> None:
        """Calling is_refusal_response twice yields the same result."""
        # Feature: conversational-training-data,
        # Property 4: Refusal detection identifies refusal phrases
        first = is_refusal_response(response)
        second = is_refusal_response(response)
        assert first == second, (
            f"Non-deterministic refusal detection.\n"
            f"  response = {response!r}\n"
            f"  first    = {first}\n"
            f"  second   = {second}"
        )

    # -- Indicator embedded in longer text still detected ------------------

    @given(
        prefix=st.text(min_size=50, max_size=300),
        indicator=st.sampled_from(REFUSAL_INDICATORS),
        suffix=st.text(min_size=50, max_size=300),
    )
    @settings(max_examples=100)
    def test_indicator_in_longer_text_detected(
        self, prefix: str, indicator: str, suffix: str
    ) -> None:
        """An indicator embedded in a longer response must still be detected."""
        # Feature: conversational-training-data,
        # Property 4: Refusal detection identifies refusal phrases
        response = prefix + " " + indicator + " " + suffix
        assert is_refusal_response(response) is True, (
            f"Indicator not detected in longer text.\n"
            f"  indicator = {indicator!r}\n"
            f"  response  = {response[:100]!r}..."
        )


# ---------------------------------------------------------------------------
# Property 5: Refusal formatting produces bounded, non-fabricating responses
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.refusal_formatter import (  # noqa: E402
    _DOSAGE_PATTERN,
    _DRUG_INTERACTION_PATTERN,
    _TREATMENT_REGIMEN_PATTERN,
    format_refusal,
)

# Token estimation heuristic: chars / 4.0 (same as used throughout the
# pipeline).  format_refusal() output must be under 200 estimated tokens.
_REFUSAL_MAX_TOKENS: int = 200

# Phrases that indicate the refusal acknowledges information is unavailable.
# At least one of these must appear in every formatted refusal.
_UNAVAILABILITY_PHRASES: list[str] = [
    "don't have information",
    "wasn't able to find",
    "don't cover",
    "couldn't locate",
    "not available",
    "not in the available sources",
    "don't have access",
    "no information",
]


def _estimate_tokens(text: str) -> int:
    """Estimate token count using the chars / 4.0 heuristic."""
    return int(len(text) / 4.0)


def _question_text() -> st.SearchStrategy[str]:
    """Generate question strings for refusal formatting.

    Uses ``st.text(min_size=5, max_size=200)`` as specified in the
    task, with printable characters to produce realistic questions.
    """
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Z", "P"),
            blacklist_characters="\x00",
        ),
        min_size=5,
        max_size=200,
    ).filter(lambda s: s.strip())


@pytest.mark.pbt
@pytest.mark.unit
class TestRefusalFormattingBounds:
    """Property 5: Refusal formatting produces bounded, non-fabricating responses.

    For any question string, the output of
    ``format_refusal(question, response)`` SHALL have an estimated
    token count under 200 (using the chars / 4 heuristic), SHALL
    contain a phrase indicating the information is not available,
    and SHALL NOT contain medical dosage numbers, treatment regimen
    details, or drug interaction specifics.

    Validates: Requirements 2.4
    """

    # -- Output is under 200 estimated tokens -----------------------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_output_under_200_tokens(self, question: str) -> None:
        """format_refusal() output must be under 200 estimated tokens."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, "No information found.")
        token_count = _estimate_tokens(result)
        assert token_count < _REFUSAL_MAX_TOKENS, (
            f"Refusal output exceeds 200 estimated tokens.\n"
            f"  question    = {question!r}\n"
            f"  result      = {result!r}\n"
            f"  len(result) = {len(result)}\n"
            f"  est_tokens  = {token_count}"
        )

    # -- Output contains an unavailability phrase -------------------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_output_contains_unavailability_phrase(
        self, question: str
    ) -> None:
        """format_refusal() output must indicate information is not available."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, "No information found.")
        lower_result = result.lower()
        has_phrase = any(
            phrase in lower_result for phrase in _UNAVAILABILITY_PHRASES
        )
        assert has_phrase, (
            f"Refusal output does not contain any unavailability phrase.\n"
            f"  question = {question!r}\n"
            f"  result   = {result!r}\n"
            f"  checked  = {_UNAVAILABILITY_PHRASES}"
        )

    # -- Output does not contain medical dosage numbers -------------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_output_has_no_dosage_numbers(self, question: str) -> None:
        """format_refusal() output must not contain medical dosage patterns."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, "No information found.")
        assert not _DOSAGE_PATTERN.search(result), (
            f"Refusal output contains dosage pattern.\n"
            f"  question = {question!r}\n"
            f"  result   = {result!r}\n"
            f"  match    = {_DOSAGE_PATTERN.search(result).group()!r}"  # type: ignore[union-attr]
        )

    # -- Output does not contain treatment regimen details ----------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_output_has_no_treatment_regimen(self, question: str) -> None:
        """format_refusal() output must not contain treatment regimen patterns."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, "No information found.")
        assert not _TREATMENT_REGIMEN_PATTERN.search(result), (
            f"Refusal output contains treatment regimen pattern.\n"
            f"  question = {question!r}\n"
            f"  result   = {result!r}\n"
            f"  match    = {_TREATMENT_REGIMEN_PATTERN.search(result).group()!r}"  # type: ignore[union-attr]
        )

    # -- Output does not contain drug interaction specifics ----------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_output_has_no_drug_interactions(self, question: str) -> None:
        """format_refusal() output must not contain drug interaction patterns."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, "No information found.")
        assert not _DRUG_INTERACTION_PATTERN.search(result), (
            f"Refusal output contains drug interaction pattern.\n"
            f"  question = {question!r}\n"
            f"  result   = {result!r}\n"
            f"  match    = {_DRUG_INTERACTION_PATTERN.search(result).group()!r}"  # type: ignore[union-attr]
        )

    # -- Output is non-empty ----------------------------------------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_output_is_non_empty(self, question: str) -> None:
        """format_refusal() must return a non-empty string."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, "No information found.")
        assert result.strip(), (
            f"Refusal output is empty.\n"
            f"  question = {question!r}"
        )

    # -- Formatting is deterministic --------------------------------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_formatting_is_deterministic(self, question: str) -> None:
        """Calling format_refusal() twice with the same input yields
        the same output."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        r1 = format_refusal(question, "No information found.")
        r2 = format_refusal(question, "No information found.")
        assert r1 == r2, (
            f"Non-deterministic refusal formatting.\n"
            f"  question = {question!r}\n"
            f"  first    = {r1!r}\n"
            f"  second   = {r2!r}"
        )

    # -- Token bound holds with varied response_text ----------------------

    @given(
        question=_question_text(),
        response_text=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=100)
    def test_token_bound_with_varied_response_text(
        self, question: str, response_text: str
    ) -> None:
        """Token bound must hold regardless of the original response_text."""
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, response_text)
        token_count = _estimate_tokens(result)
        assert token_count < _REFUSAL_MAX_TOKENS, (
            f"Refusal output exceeds 200 tokens with varied response_text.\n"
            f"  question      = {question!r}\n"
            f"  response_text = {response_text[:50]!r}...\n"
            f"  result        = {result!r}\n"
            f"  est_tokens    = {token_count}"
        )

    # -- No fabrication beyond question content --------------------------

    @given(question=_question_text())
    @settings(max_examples=100)
    def test_no_new_fabricated_medical_content(
        self, question: str
    ) -> None:
        """The refusal must not introduce medical content that was not
        already present in the question.

        ``format_refusal()`` may echo the topic from the question
        (e.g., "metformin dosage"), but it must not fabricate *new*
        dosage numbers, treatment regimens, or drug interaction
        details beyond what the question already contained.
        """
        # Feature: conversational-training-data,
        # Property 5: Refusal formatting produces bounded, non-fabricating responses
        result = format_refusal(question, "No information found.")

        # Remove the question text from the result to isolate the
        # template portion.  The refusal templates embed a "topic"
        # extracted from the question, so we strip that out before
        # checking for fabricated medical content.
        # We check the template text (result minus any substring
        # that appears in the question) for medical patterns.
        result_lower = result.lower()
        question_lower = question.lower()

        # Find dosage matches in the result that are NOT in the question
        for match in _DOSAGE_PATTERN.finditer(result):
            matched_text = match.group().lower()
            assert matched_text in question_lower, (
                f"Fabricated dosage not from question.\n"
                f"  question = {question!r}\n"
                f"  result   = {result!r}\n"
                f"  match    = {match.group()!r}"
            )

        # Find treatment regimen matches not in the question
        for match in _TREATMENT_REGIMEN_PATTERN.finditer(result):
            matched_text = match.group().lower()
            assert matched_text in question_lower, (
                f"Fabricated treatment regimen not from question.\n"
                f"  question = {question!r}\n"
                f"  result   = {result!r}\n"
                f"  match    = {match.group()!r}"
            )

        # Find drug interaction matches not in the question
        for match in _DRUG_INTERACTION_PATTERN.finditer(result):
            matched_text = match.group().lower()
            assert matched_text in question_lower, (
                f"Fabricated drug interaction not from question.\n"
                f"  question = {question!r}\n"
                f"  result   = {result!r}\n"
                f"  match    = {match.group()!r}"
            )


# ---------------------------------------------------------------------------
# Property 8: Quality filter rejects uncited long responses
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.quality_filter import estimate_tokens  # noqa: E402

# Characters per token ratio used by the heuristic estimator.
_CHARS_PER_TOKEN: float = 4.0

# Default max uncited token threshold from QualityFilter.
_MAX_UNCITED_TOKENS: int = 800

# Minimum character length that produces an estimated token count
# strictly greater than _MAX_UNCITED_TOKENS.
# estimate_tokens(text) = int(len(text) / 4.0), so we need
# int(n / 4.0) > 800  ⟺  n / 4.0 >= 801  ⟺  n >= 3204.
_MIN_CHARS_OVER_BUDGET: int = int((_MAX_UNCITED_TOKENS + 1) * _CHARS_PER_TOKEN)

# Maximum character length that produces an estimated token count
# at most _MAX_UNCITED_TOKENS.
# int(n / 4.0) <= 800  ⟺  n <= 3203  (since int(3203/4.0) = 800).
_MAX_CHARS_WITHIN_BUDGET: int = _MIN_CHARS_OVER_BUDGET - 1

# Safe alphabet that avoids MCQ markers, textbook stems, LOINC patterns,
# production-divergent patterns ("student", "exam"), and citation markers.
_SAFE_ALPHABET = st.sampled_from("efghijklmnopqrtuvwxyz ")


def _long_uncited_response() -> st.SearchStrategy[str]:
    """Generate a response exceeding 800 estimated tokens with no citations.

    Uses safe characters that cannot accidentally contain ``[Source N]``
    markers, MCQ markers, textbook stems, or production-divergent phrases.
    """
    return st.text(
        alphabet=_SAFE_ALPHABET,
        min_size=_MIN_CHARS_OVER_BUDGET,
        max_size=_MIN_CHARS_OVER_BUDGET + 2000,
    ).filter(lambda s: s.strip())


def _short_uncited_response() -> st.SearchStrategy[str]:
    """Generate a response at or below 800 estimated tokens with no citations.

    The response is long enough to avoid the ``response_too_short``
    rejection (≥50 estimated tokens → ≥200 chars) but short enough
    to stay within the uncited threshold.
    """
    # 50 tokens * 4 chars/token = 200 chars minimum to avoid
    # "response_too_short" rejection.
    min_chars = 200
    return st.text(
        alphabet=_SAFE_ALPHABET,
        min_size=min_chars,
        max_size=_MAX_CHARS_WITHIN_BUDGET,
    ).filter(lambda s: s.strip())


def _citation_marker() -> st.SearchStrategy[str]:
    """Generate a ``[Source N]`` citation marker."""
    return st.integers(min_value=1, max_value=20).map(
        lambda n: f"[Source {n}]"
    )


def _long_cited_response() -> st.SearchStrategy[str]:
    """Generate a response exceeding 800 estimated tokens WITH citations.

    Injects one or more ``[Source N]`` markers into a long safe-text
    response so the citation check passes.
    """
    return st.tuples(
        # Body text (long enough to exceed threshold even after
        # accounting for citation marker length)
        st.text(
            alphabet=_SAFE_ALPHABET,
            min_size=_MIN_CHARS_OVER_BUDGET,
            max_size=_MIN_CHARS_OVER_BUDGET + 1000,
        ).filter(lambda s: s.strip()),
        # One or more citation markers
        st.lists(
            _citation_marker(),
            min_size=1,
            max_size=5,
        ),
    ).map(
        lambda t: t[0] + " " + " ".join(t[1])
    )


@pytest.mark.pbt
@pytest.mark.unit
class TestUncitedLongResponseRejection:
    """Property 8: Quality filter rejects uncited long responses.

    For any ``InstructionTuningPair`` where the response has an
    estimated token count exceeding 800 and contains no
    ``[Source N]`` citation pattern, the ``QualityFilter`` SHALL
    reject the pair with reason ``"uncited_long_response"``.
    For any pair where the response is 800 tokens or fewer, or
    contains at least one citation, the filter SHALL NOT reject
    for this reason.

    Validates: Requirements 4.3
    """

    def setup_method(self) -> None:
        self._filter = QualityFilter()

    # -- Long uncited responses → rejection with "uncited_long_response" --

    @given(response=_long_uncited_response())
    @settings(max_examples=100)
    def test_long_uncited_response_rejected(self, response: str) -> None:
        """Responses >800 tokens without citations must be rejected."""
        # Feature: conversational-training-data,
        # Property 8: Quality filter rejects uncited long responses
        pair = _make_pair(response)
        # Sanity: confirm the response actually exceeds the threshold
        assert estimate_tokens(response) > _MAX_UNCITED_TOKENS, (
            f"Test setup error: response is not over budget.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair)
        assert "uncited_long_response" in result.rejection_reasons, (
            f"Expected 'uncited_long_response' rejection.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Short uncited responses → no "uncited_long_response" rejection ---

    @given(response=_short_uncited_response())
    @settings(max_examples=100)
    def test_short_uncited_response_not_rejected(
        self, response: str
    ) -> None:
        """Responses ≤800 tokens without citations must NOT be rejected
        for uncited_long_response."""
        # Feature: conversational-training-data,
        # Property 8: Quality filter rejects uncited long responses
        pair = _make_pair(response)
        assert estimate_tokens(response) <= _MAX_UNCITED_TOKENS, (
            f"Test setup error: response exceeds budget.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair)
        assert "uncited_long_response" not in result.rejection_reasons, (
            f"Unexpected 'uncited_long_response' rejection.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Long cited responses → no "uncited_long_response" rejection ------

    @given(response=_long_cited_response())
    @settings(max_examples=100)
    def test_long_cited_response_not_rejected(
        self, response: str
    ) -> None:
        """Responses >800 tokens WITH citations must NOT be rejected
        for uncited_long_response."""
        # Feature: conversational-training-data,
        # Property 8: Quality filter rejects uncited long responses
        pair = _make_pair(response)
        assert estimate_tokens(response) > _MAX_UNCITED_TOKENS, (
            f"Test setup error: response is not over budget.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair)
        assert "uncited_long_response" not in result.rejection_reasons, (
            f"Unexpected 'uncited_long_response' for cited response.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Boundary: exactly at 800 tokens → no rejection -------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_exactly_at_threshold_not_rejected(
        self, data: st.DataObject
    ) -> None:
        """Responses with exactly 800 estimated tokens must NOT be rejected.

        The check is strictly greater than (``>``), so 800 is within budget.
        """
        # Feature: conversational-training-data,
        # Property 8: Quality filter rejects uncited long responses
        # Generate text of exactly _MAX_UNCITED_TOKENS * _CHARS_PER_TOKEN
        # = 3200 chars → estimate_tokens = int(3200/4.0) = 800.
        exact_len = int(_MAX_UNCITED_TOKENS * _CHARS_PER_TOKEN)
        response = data.draw(
            st.text(
                alphabet=_SAFE_ALPHABET,
                min_size=exact_len,
                max_size=exact_len,
            ).filter(lambda s: s.strip()),
            label="response_at_boundary",
        )
        pair = _make_pair(response)
        assert estimate_tokens(response) == _MAX_UNCITED_TOKENS, (
            f"Test setup error: expected exactly {_MAX_UNCITED_TOKENS} tokens.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair)
        assert "uncited_long_response" not in result.rejection_reasons, (
            f"Unexpected rejection at exact threshold.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Boundary: one token over → rejection -----------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_one_token_over_threshold_rejected(
        self, data: st.DataObject
    ) -> None:
        """Responses with 801 estimated tokens (no citations) must be rejected.

        This is the smallest token count that triggers the check.
        """
        # Feature: conversational-training-data,
        # Property 8: Quality filter rejects uncited long responses
        # 801 tokens → need int(n/4.0) = 801 → n = 3204 chars.
        exact_len = _MIN_CHARS_OVER_BUDGET
        response = data.draw(
            st.text(
                alphabet=_SAFE_ALPHABET,
                min_size=exact_len,
                max_size=exact_len,
            ).filter(lambda s: s.strip()),
            label="response_one_over",
        )
        pair = _make_pair(response)
        assert estimate_tokens(response) > _MAX_UNCITED_TOKENS, (
            f"Test setup error: expected > {_MAX_UNCITED_TOKENS} tokens.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair)
        assert "uncited_long_response" in result.rejection_reasons, (
            f"Expected rejection one token over threshold.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Detection is deterministic ----------------------------------------

    @given(response=_long_uncited_response())
    @settings(max_examples=100)
    def test_uncited_detection_is_deterministic(
        self, response: str
    ) -> None:
        """Evaluating the same long uncited response twice yields same result."""
        # Feature: conversational-training-data,
        # Property 8: Quality filter rejects uncited long responses
        pair = _make_pair(response)
        r1 = self._filter.evaluate(pair)
        fresh = QualityFilter()
        r2 = fresh.evaluate(pair)
        in_r1 = "uncited_long_response" in r1.rejection_reasons
        in_r2 = "uncited_long_response" in r2.rejection_reasons
        assert in_r1 == in_r2, (
            f"Non-deterministic uncited long response detection.\n"
            f"  response = {response[:100]!r}...\n"
            f"  first    = {r1.rejection_reasons}\n"
            f"  second   = {r2.rejection_reasons}"
        )


# ---------------------------------------------------------------------------
# Property 9: Quality filter exempts refusals from minimum length
# ---------------------------------------------------------------------------

# Default minimum response token threshold from QualityFilter.
_MIN_RESPONSE_TOKENS: int = 50

# Maximum character length that produces an estimated token count
# strictly below _MIN_RESPONSE_TOKENS.
# estimate_tokens(text) = int(len(text) / 4.0), so we need
# int(n / 4.0) < 50  ⟺  n < 200.
_MAX_CHARS_SHORT: int = int(_MIN_RESPONSE_TOKENS * _CHARS_PER_TOKEN) - 1  # 199


def _short_response() -> st.SearchStrategy[str]:
    """Generate a response with <50 estimated tokens.

    Uses safe characters that avoid MCQ markers, textbook stems,
    LOINC patterns, production-divergent patterns, and citation
    markers.  The response is non-empty (min 1 char) and short
    enough that ``estimate_tokens(response) < 50``.
    """
    return st.text(
        alphabet=_SAFE_ALPHABET,
        min_size=1,
        max_size=_MAX_CHARS_SHORT,
    ).filter(lambda s: s.strip())


@pytest.mark.pbt
@pytest.mark.unit
class TestRefusalLengthExemption:
    """Property 9: Quality filter exempts refusals from minimum length.

    For any ``InstructionTuningPair`` flagged as a refusal
    (``is_refusal=True``), the ``QualityFilter`` SHALL NOT reject
    the pair with reason ``"response_too_short"`` regardless of
    response length.  For any non-refusal pair where the response
    has an estimated token count below 50, the filter SHALL reject
    with reason ``"response_too_short"``.

    Validates: Requirements 4.4
    """

    def setup_method(self) -> None:
        self._filter = QualityFilter()

    # -- Short refusal → no "response_too_short" rejection ----------------

    @given(response=_short_response())
    @settings(max_examples=100)
    def test_short_refusal_not_rejected_for_length(
        self, response: str
    ) -> None:
        """Short responses flagged as refusals must NOT be rejected
        for response_too_short."""
        # Feature: conversational-training-data,
        # Property 9: Quality filter exempts refusals from minimum length
        pair = _make_pair(response)
        assert estimate_tokens(response) < _MIN_RESPONSE_TOKENS, (
            f"Test setup error: response is not short enough.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair, is_refusal=True)
        assert "response_too_short" not in result.rejection_reasons, (
            f"Unexpected 'response_too_short' rejection for refusal.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Short non-refusal → "response_too_short" rejection ---------------

    @given(response=_short_response())
    @settings(max_examples=100)
    def test_short_non_refusal_rejected_for_length(
        self, response: str
    ) -> None:
        """Short responses NOT flagged as refusals must be rejected
        for response_too_short."""
        # Feature: conversational-training-data,
        # Property 9: Quality filter exempts refusals from minimum length
        pair = _make_pair(response)
        assert estimate_tokens(response) < _MIN_RESPONSE_TOKENS, (
            f"Test setup error: response is not short enough.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair, is_refusal=False)
        assert "response_too_short" in result.rejection_reasons, (
            f"Expected 'response_too_short' rejection for non-refusal.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Boundary: exactly at 49 tokens → rejection for non-refusal ------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_one_below_threshold_rejected_non_refusal(
        self, data: st.DataObject
    ) -> None:
        """Responses with 49 estimated tokens (non-refusal) must be rejected.

        This is the largest token count below the threshold.
        """
        # Feature: conversational-training-data,
        # Property 9: Quality filter exempts refusals from minimum length
        # 49 tokens → int(n/4.0) = 49 → n = 196 chars.
        exact_len = int((_MIN_RESPONSE_TOKENS - 1) * _CHARS_PER_TOKEN)
        response = data.draw(
            st.text(
                alphabet=_SAFE_ALPHABET,
                min_size=exact_len,
                max_size=exact_len,
            ).filter(lambda s: s.strip()),
            label="response_one_below_threshold",
        )
        pair = _make_pair(response)
        assert estimate_tokens(response) < _MIN_RESPONSE_TOKENS, (
            f"Test setup error: expected < {_MIN_RESPONSE_TOKENS} tokens.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair, is_refusal=False)
        assert "response_too_short" in result.rejection_reasons, (
            f"Expected rejection one below threshold.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Boundary: exactly at 50 tokens → no rejection --------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_exactly_at_threshold_not_rejected(
        self, data: st.DataObject
    ) -> None:
        """Responses with exactly 50 estimated tokens must NOT be rejected
        for response_too_short (the check is strictly less than)."""
        # Feature: conversational-training-data,
        # Property 9: Quality filter exempts refusals from minimum length
        # 50 tokens → int(n/4.0) = 50 → n = 200 chars.
        exact_len = int(_MIN_RESPONSE_TOKENS * _CHARS_PER_TOKEN)
        response = data.draw(
            st.text(
                alphabet=_SAFE_ALPHABET,
                min_size=exact_len,
                max_size=exact_len,
            ).filter(lambda s: s.strip()),
            label="response_at_threshold",
        )
        pair = _make_pair(response)
        assert estimate_tokens(response) == _MIN_RESPONSE_TOKENS, (
            f"Test setup error: expected exactly {_MIN_RESPONSE_TOKENS} tokens.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair, is_refusal=False)
        assert "response_too_short" not in result.rejection_reasons, (
            f"Unexpected rejection at exact threshold.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Refusal exemption holds at boundary too --------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_boundary_refusal_still_exempt(
        self, data: st.DataObject
    ) -> None:
        """Even at 49 tokens, refusals must NOT be rejected for length."""
        # Feature: conversational-training-data,
        # Property 9: Quality filter exempts refusals from minimum length
        exact_len = int((_MIN_RESPONSE_TOKENS - 1) * _CHARS_PER_TOKEN)
        response = data.draw(
            st.text(
                alphabet=_SAFE_ALPHABET,
                min_size=exact_len,
                max_size=exact_len,
            ).filter(lambda s: s.strip()),
            label="response_boundary_refusal",
        )
        pair = _make_pair(response)
        assert estimate_tokens(response) < _MIN_RESPONSE_TOKENS, (
            f"Test setup error: expected < {_MIN_RESPONSE_TOKENS} tokens.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}"
        )
        result = self._filter.evaluate(pair, is_refusal=True)
        assert "response_too_short" not in result.rejection_reasons, (
            f"Unexpected 'response_too_short' for boundary refusal.\n"
            f"  len      = {len(response)}\n"
            f"  est_tok  = {estimate_tokens(response)}\n"
            f"  reasons  = {result.rejection_reasons}"
        )

    # -- Same short response: refusal vs non-refusal yields different -----

    @given(response=_short_response())
    @settings(max_examples=100)
    def test_refusal_flag_changes_outcome(
        self, response: str
    ) -> None:
        """The same short response must be rejected as non-refusal but
        accepted (for length) as refusal."""
        # Feature: conversational-training-data,
        # Property 9: Quality filter exempts refusals from minimum length
        pair = _make_pair(response)
        assert estimate_tokens(response) < _MIN_RESPONSE_TOKENS

        filter_refusal = QualityFilter()
        filter_non_refusal = QualityFilter()

        result_refusal = filter_refusal.evaluate(pair, is_refusal=True)
        result_non_refusal = filter_non_refusal.evaluate(
            pair, is_refusal=False
        )

        assert "response_too_short" not in result_refusal.rejection_reasons, (
            f"Refusal should not be rejected for length.\n"
            f"  reasons = {result_refusal.rejection_reasons}"
        )
        assert "response_too_short" in result_non_refusal.rejection_reasons, (
            f"Non-refusal should be rejected for length.\n"
            f"  reasons = {result_non_refusal.rejection_reasons}"
        )

    # -- Detection is deterministic ----------------------------------------

    @given(response=_short_response())
    @settings(max_examples=100)
    def test_refusal_exemption_is_deterministic(
        self, response: str
    ) -> None:
        """Evaluating the same short response twice yields same result
        for both refusal and non-refusal flags."""
        # Feature: conversational-training-data,
        # Property 9: Quality filter exempts refusals from minimum length
        pair = _make_pair(response)

        f1 = QualityFilter()
        f2 = QualityFilter()

        r1_refusal = f1.evaluate(pair, is_refusal=True)
        r2_refusal = f2.evaluate(pair, is_refusal=True)
        assert (
            ("response_too_short" in r1_refusal.rejection_reasons)
            == ("response_too_short" in r2_refusal.rejection_reasons)
        ), "Non-deterministic refusal exemption"

        f3 = QualityFilter()
        f4 = QualityFilter()

        r1_non = f3.evaluate(pair, is_refusal=False)
        r2_non = f4.evaluate(pair, is_refusal=False)
        assert (
            ("response_too_short" in r1_non.rejection_reasons)
            == ("response_too_short" in r2_non.rejection_reasons)
        ), "Non-deterministic non-refusal length check"


# ---------------------------------------------------------------------------
# Property 10: Quality filter summary count invariant
# ---------------------------------------------------------------------------


def _instruction_tuning_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate ``InstructionTuningPair`` objects with varied characteristics.

    Produces a mix of pairs that will pass or fail different quality
    checks so the summary counters exercise all code paths:

    - **Passing pairs**: conversational instruction, adequately long
      response with citations, no MCQ markers.
    - **MCQ-rejected pairs**: response with 3+ MCQ markers.
    - **Short-rejected pairs**: response under 50 estimated tokens.
    - **Uncited-long-rejected pairs**: response over 800 tokens with
      no citations.
    - **Textbook-rejected pairs**: instruction starting with a known
      textbook stem.

    The strategy uses ``st.one_of`` so Hypothesis explores all
    categories across the 100 examples.
    """
    return st.one_of(
        _passing_pair(),
        _mcq_rejected_pair(),
        _short_rejected_pair(),
        _uncited_long_rejected_pair(),
        _textbook_rejected_pair(),
    )


def _passing_pair() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair that should pass all quality checks.

    - Conversational instruction (no textbook stems, no LOINC)
    - Response between 50 and 800 estimated tokens
    - Contains at least one ``[Source N]`` citation
    - No MCQ markers
    - No production-divergent patterns
    """
    # 50 tokens * 4 chars = 200 chars minimum
    # 800 tokens * 4 chars = 3200 chars maximum
    return st.tuples(
        st.sampled_from(_CONVERSATIONAL_PREFIXES),
        st.text(
            alphabet=_SAFE_ALPHABET,
            min_size=1,
            max_size=60,
        ).filter(lambda s: s.strip()),
        st.text(
            alphabet=_SAFE_ALPHABET,
            min_size=200,
            max_size=3100,
        ).filter(lambda s: s.strip()),
        _citation_marker(),
    ).map(
        lambda t: InstructionTuningPair(
            instruction=t[0] + " " + t[1] + "?",
            context="Some relevant medical context here.",
            response=t[2] + " " + t[3],
            metadata=PairMetadata(
                strategy="rag",
                confidence_score=0.8,
            ),
        )
    )


def _mcq_rejected_pair() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair rejected for MCQ markers (3+ markers in response)."""
    return _response_with_n_mcq_markers(3).map(
        lambda resp: InstructionTuningPair(
            instruction="Can you tell me about this medication?",
            context="Some relevant medical context here.",
            response=resp,
            metadata=PairMetadata(
                strategy="rag",
                confidence_score=0.8,
            ),
        )
    )


def _short_rejected_pair() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair rejected for response_too_short (<50 tokens)."""
    return _short_response().map(
        lambda resp: InstructionTuningPair(
            instruction="Can you tell me about this medication?",
            context="Some relevant medical context here.",
            response=resp,
            metadata=PairMetadata(
                strategy="rag",
                confidence_score=0.8,
            ),
        )
    )


def _uncited_long_rejected_pair() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair rejected for uncited_long_response (>800 tokens, no citations)."""
    return _long_uncited_response().map(
        lambda resp: InstructionTuningPair(
            instruction="Can you tell me about this medication?",
            context="Some relevant medical context here.",
            response=resp,
            metadata=PairMetadata(
                strategy="rag",
                confidence_score=0.8,
            ),
        )
    )


def _textbook_rejected_pair() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair rejected for textbook_style instruction."""
    return st.tuples(
        st.sampled_from(_PLAIN_STEMS),
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
            min_size=1,
            max_size=60,
        ).filter(lambda s: s.strip()),
        # Response long enough to avoid response_too_short, with citation
        st.text(
            alphabet=_SAFE_ALPHABET,
            min_size=200,
            max_size=3100,
        ).filter(lambda s: s.strip()),
        _citation_marker(),
    ).map(
        lambda t: InstructionTuningPair(
            instruction=t[0] + " " + t[1] + "?",
            context="Some relevant medical context here.",
            response=t[2] + " " + t[3],
            metadata=PairMetadata(
                strategy="rag",
                confidence_score=0.8,
            ),
        )
    )


@pytest.mark.pbt
@pytest.mark.unit
class TestFilterSummaryCountInvariant:
    """Property 10: Quality filter summary count invariant.

    For any sequence of ``evaluate()`` calls on a ``QualityFilter``
    instance, the resulting ``FilterSummary`` SHALL satisfy:

    - ``total_evaluated == total_passed + total_rejected``
    - ``pass_rate == total_passed / total_evaluated``
      (when ``total_evaluated > 0``)
    - The sum of all values in ``rejections_by_reason`` SHALL be
      greater than or equal to ``total_rejected`` (a pair with
      multiple rejection reasons increments each reason counter).

    Validates: Requirements 4.7
    """

    # -- Core invariant: total_evaluated == total_passed + total_rejected --

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_total_evaluated_equals_passed_plus_rejected(
        self, pairs: list[InstructionTuningPair]
    ) -> None:
        """total_evaluated must equal total_passed + total_rejected."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        for pair in pairs:
            qf.evaluate(pair)

        summary = qf.summarize()
        assert summary.total_evaluated == summary.total_passed + summary.total_rejected, (
            f"Count invariant violated.\n"
            f"  total_evaluated = {summary.total_evaluated}\n"
            f"  total_passed    = {summary.total_passed}\n"
            f"  total_rejected  = {summary.total_rejected}"
        )

    # -- Pass rate invariant: pass_rate == total_passed / total_evaluated --

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_pass_rate_equals_passed_over_evaluated(
        self, pairs: list[InstructionTuningPair]
    ) -> None:
        """pass_rate must equal total_passed / total_evaluated."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        for pair in pairs:
            qf.evaluate(pair)

        summary = qf.summarize()
        assert summary.total_evaluated > 0, "Expected at least one evaluation"
        expected_rate = summary.total_passed / summary.total_evaluated
        assert summary.pass_rate == pytest.approx(expected_rate), (
            f"Pass rate invariant violated.\n"
            f"  pass_rate        = {summary.pass_rate}\n"
            f"  expected         = {expected_rate}\n"
            f"  total_passed     = {summary.total_passed}\n"
            f"  total_evaluated  = {summary.total_evaluated}"
        )

    # -- Rejection reason sum invariant ------------------------------------

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_rejection_reason_sum_gte_total_rejected(
        self, pairs: list[InstructionTuningPair]
    ) -> None:
        """Sum of rejections_by_reason values must be >= total_rejected.

        A pair with multiple rejection reasons increments each reason
        counter, so the sum can exceed total_rejected.
        """
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        for pair in pairs:
            qf.evaluate(pair)

        summary = qf.summarize()
        reason_sum = sum(summary.rejections_by_reason.values())
        assert reason_sum >= summary.total_rejected, (
            f"Rejection reason sum invariant violated.\n"
            f"  sum(rejections_by_reason) = {reason_sum}\n"
            f"  total_rejected            = {summary.total_rejected}\n"
            f"  rejections_by_reason      = {summary.rejections_by_reason}"
        )

    # -- total_evaluated matches the number of evaluate() calls -----------

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_total_evaluated_matches_call_count(
        self, pairs: list[InstructionTuningPair]
    ) -> None:
        """total_evaluated must equal the number of evaluate() calls."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        for pair in pairs:
            qf.evaluate(pair)

        summary = qf.summarize()
        assert summary.total_evaluated == len(pairs), (
            f"total_evaluated does not match call count.\n"
            f"  total_evaluated = {summary.total_evaluated}\n"
            f"  len(pairs)      = {len(pairs)}"
        )

    # -- Empty filter: all counters are zero ------------------------------

    def test_empty_filter_summary(self) -> None:
        """A filter with no evaluations must have all-zero counters."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        summary = qf.summarize()
        assert summary.total_evaluated == 0
        assert summary.total_passed == 0
        assert summary.total_rejected == 0
        assert summary.rejections_by_reason == {}
        assert summary.pass_rate == 0.0

    # -- Rejection reasons are a subset of known reason codes -------------

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_rejection_reasons_are_known_codes(
        self, pairs: list[InstructionTuningPair]
    ) -> None:
        """All rejection reason codes must be from the known set."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        known_reasons = {
            "mcq_markers",
            "loinc_instruction",
            "uncited_long_response",
            "response_too_short",
            "textbook_style",
            "production_divergent",
            "refusal_then_fabrication",
            "token_budget_exceeded",
        }
        qf = QualityFilter()
        for pair in pairs:
            qf.evaluate(pair)

        summary = qf.summarize()
        for reason in summary.rejections_by_reason:
            assert reason in known_reasons, (
                f"Unknown rejection reason code: {reason!r}\n"
                f"  known = {known_reasons}"
            )

    # -- Summarize is idempotent (calling twice yields same result) -------

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_summarize_is_idempotent(
        self, pairs: list[InstructionTuningPair]
    ) -> None:
        """Calling summarize() twice without new evaluations yields
        the same result."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        for pair in pairs:
            qf.evaluate(pair)

        s1 = qf.summarize()
        s2 = qf.summarize()
        assert s1.total_evaluated == s2.total_evaluated
        assert s1.total_passed == s2.total_passed
        assert s1.total_rejected == s2.total_rejected
        assert s1.rejections_by_reason == s2.rejections_by_reason
        assert s1.pass_rate == pytest.approx(s2.pass_rate)

    # -- Incremental evaluation: counters grow monotonically --------------

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=2,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_counters_grow_monotonically(
        self, pairs: list[InstructionTuningPair]
    ) -> None:
        """After each evaluate() call, total_evaluated must increase by 1
        and either total_passed or total_rejected must increase by 1."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        prev = qf.summarize()

        for pair in pairs:
            qf.evaluate(pair)
            curr = qf.summarize()

            assert curr.total_evaluated == prev.total_evaluated + 1, (
                f"total_evaluated did not increase by 1.\n"
                f"  prev = {prev.total_evaluated}\n"
                f"  curr = {curr.total_evaluated}"
            )
            passed_delta = curr.total_passed - prev.total_passed
            rejected_delta = curr.total_rejected - prev.total_rejected
            assert (passed_delta, rejected_delta) in ((1, 0), (0, 1)), (
                f"Expected exactly one of passed/rejected to increase by 1.\n"
                f"  passed_delta   = {passed_delta}\n"
                f"  rejected_delta = {rejected_delta}"
            )
            prev = curr

    # -- Mixed refusal/non-refusal evaluations preserve invariant ---------

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(),
            min_size=1,
            max_size=20,
        ),
        refusal_flags=st.lists(
            st.booleans(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_invariant_holds_with_mixed_refusal_flags(
        self,
        pairs: list[InstructionTuningPair],
        refusal_flags: list[bool],
    ) -> None:
        """The count invariant holds regardless of is_refusal flag values."""
        # Feature: conversational-training-data,
        # Property 10: Quality filter summary count invariant
        qf = QualityFilter()
        # Zip pairs with refusal flags (truncate to shorter list)
        for pair, is_refusal in zip(pairs, refusal_flags):
            qf.evaluate(pair, is_refusal=is_refusal)

        summary = qf.summarize()
        n_evaluated = min(len(pairs), len(refusal_flags))

        assert summary.total_evaluated == n_evaluated, (
            f"total_evaluated mismatch.\n"
            f"  expected = {n_evaluated}\n"
            f"  actual   = {summary.total_evaluated}"
        )
        assert summary.total_evaluated == summary.total_passed + summary.total_rejected, (
            f"Count invariant violated with mixed refusal flags.\n"
            f"  total_evaluated = {summary.total_evaluated}\n"
            f"  total_passed    = {summary.total_passed}\n"
            f"  total_rejected  = {summary.total_rejected}"
        )
        reason_sum = sum(summary.rejections_by_reason.values())
        assert reason_sum >= summary.total_rejected, (
            f"Rejection reason sum invariant violated.\n"
            f"  sum(rejections_by_reason) = {reason_sum}\n"
            f"  total_rejected            = {summary.total_rejected}"
        )


# ---------------------------------------------------------------------------
# Property 6: Token budget estimation consistency
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.token_budget import (  # noqa: E402
    _CHAT_TEMPLATE_OVERHEAD_TOKENS,
    TokenBudgetManager,
)


def _system_prompt_strategy() -> st.SearchStrategy[str]:
    """Generate system prompt strings for token budget testing.

    Uses printable text of varying lengths to exercise the token
    estimation across different system prompt sizes.
    """
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Z", "P"),
            blacklist_characters="\x00",
        ),
        min_size=0,
        max_size=500,
    )


def _token_budget_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate ``InstructionTuningPair`` objects for token budget testing.

    Produces pairs with varied instruction, context, and response
    lengths so the budget estimation exercises different code paths
    (short pairs that fit, long pairs that exceed budget, pairs with
    empty-ish context, etc.).
    """
    return st.builds(
        InstructionTuningPair,
        instruction=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z", "P"),
                blacklist_characters="\x00",
            ),
            min_size=1,
            max_size=500,
        ).filter(lambda s: s.strip()),
        context=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z", "P"),
                blacklist_characters="\x00",
            ),
            min_size=1,
            max_size=2000,
        ).filter(lambda s: s.strip()),
        response=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z", "P"),
                blacklist_characters="\x00",
            ),
            min_size=1,
            max_size=2000,
        ).filter(lambda s: s.strip()),
        metadata=st.just(
            PairMetadata(
                strategy="rag",
                confidence_score=0.8,
            )
        ),
    )


@pytest.mark.pbt
@pytest.mark.unit
class TestTokenBudgetEstimationConsistency:
    """Property 6: Token budget estimation consistency.

    For any ``InstructionTuningPair`` and system prompt string,
    ``fits_budget(pair, system_prompt)`` SHALL return True if and
    only if ``estimate_pair_tokens(pair, system_prompt) <= max_tokens``.
    Additionally, ``estimate_tokens(s)`` SHALL be monotonically
    non-decreasing with respect to ``len(s)`` — that is, for any
    two strings where ``len(a) <= len(b)``,
    ``estimate_tokens(a) <= estimate_tokens(b)``.

    Validates: Requirements 3.1, 3.2
    """

    # -- Core property: fits_budget ↔ estimate_pair_tokens <= max_tokens --

    @given(
        pair=_token_budget_pair_strategy(),
        system_prompt=_system_prompt_strategy(),
        max_tokens=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=100)
    def test_fits_budget_iff_estimate_within_max(
        self,
        pair: InstructionTuningPair,
        system_prompt: str,
        max_tokens: int,
    ) -> None:
        """fits_budget() must return True iff estimate_pair_tokens() <= max_tokens."""
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        manager = TokenBudgetManager(max_tokens=max_tokens)
        estimated = manager.estimate_pair_tokens(pair, system_prompt)
        fits = manager.fits_budget(pair, system_prompt)

        if estimated <= max_tokens:
            assert fits is True, (
                f"fits_budget() returned False but estimate <= max_tokens.\n"
                f"  estimated  = {estimated}\n"
                f"  max_tokens = {max_tokens}"
            )
        else:
            assert fits is False, (
                f"fits_budget() returned True but estimate > max_tokens.\n"
                f"  estimated  = {estimated}\n"
                f"  max_tokens = {max_tokens}"
            )

    # -- Monotonicity: estimate_tokens is non-decreasing with len(s) ------

    @given(
        a=st.text(min_size=0, max_size=500),
        b=st.text(min_size=0, max_size=500),
    )
    @settings(max_examples=100)
    def test_estimate_tokens_monotonically_non_decreasing(
        self, a: str, b: str
    ) -> None:
        """For len(a) <= len(b), estimate_tokens(a) <= estimate_tokens(b)."""
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        manager = TokenBudgetManager()

        # Ensure a is the shorter (or equal) string
        if len(a) > len(b):
            a, b = b, a

        est_a = manager.estimate_tokens(a)
        est_b = manager.estimate_tokens(b)

        assert est_a <= est_b, (
            f"estimate_tokens is not monotonically non-decreasing.\n"
            f"  len(a)          = {len(a)}\n"
            f"  len(b)          = {len(b)}\n"
            f"  estimate_tokens(a) = {est_a}\n"
            f"  estimate_tokens(b) = {est_b}"
        )

    # -- estimate_tokens returns non-negative for any input ----------------

    @given(text=st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_estimate_tokens_non_negative(self, text: str) -> None:
        """estimate_tokens() must return a non-negative integer."""
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        manager = TokenBudgetManager()
        result = manager.estimate_tokens(text)
        assert isinstance(result, int), (
            f"estimate_tokens() did not return an int.\n"
            f"  type = {type(result)}"
        )
        assert result >= 0, (
            f"estimate_tokens() returned negative value.\n"
            f"  result = {result}\n"
            f"  text   = {text!r}"
        )

    # -- Empty string yields zero tokens -----------------------------------

    def test_empty_string_yields_zero_tokens(self) -> None:
        """estimate_tokens('') must return 0."""
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        manager = TokenBudgetManager()
        assert manager.estimate_tokens("") == 0

    # -- estimate_pair_tokens accounts for all components ------------------

    @given(
        pair=_token_budget_pair_strategy(),
        system_prompt=_system_prompt_strategy(),
    )
    @settings(max_examples=100)
    def test_estimate_pair_tokens_accounts_for_all_components(
        self,
        pair: InstructionTuningPair,
        system_prompt: str,
    ) -> None:
        """estimate_pair_tokens must be >= sum of individual component estimates.

        The pair token estimate includes system prompt, user content
        (instruction + context), response, and chat template overhead.
        It must be at least as large as the sum of the individual
        estimates plus the overhead constant.
        """
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        manager = TokenBudgetManager()

        system_tokens = manager.estimate_tokens(system_prompt)
        response_tokens = manager.estimate_tokens(pair.response)

        # Build user content the same way as estimate_pair_tokens
        user_content = pair.instruction
        if pair.context and pair.context.strip():
            user_content = f"{pair.instruction}\n\nContext:\n{pair.context}"
        user_tokens = manager.estimate_tokens(user_content)

        expected_total = (
            system_tokens
            + user_tokens
            + response_tokens
            + _CHAT_TEMPLATE_OVERHEAD_TOKENS
        )

        actual_total = manager.estimate_pair_tokens(pair, system_prompt)

        assert actual_total == expected_total, (
            f"estimate_pair_tokens does not match component sum.\n"
            f"  system_tokens   = {system_tokens}\n"
            f"  user_tokens     = {user_tokens}\n"
            f"  response_tokens = {response_tokens}\n"
            f"  overhead        = {_CHAT_TEMPLATE_OVERHEAD_TOKENS}\n"
            f"  expected_total  = {expected_total}\n"
            f"  actual_total    = {actual_total}"
        )

    # -- fits_budget with default max_tokens (5000) -----------------------

    @given(
        pair=_token_budget_pair_strategy(),
        system_prompt=_system_prompt_strategy(),
    )
    @settings(max_examples=100)
    def test_fits_budget_default_max_tokens(
        self,
        pair: InstructionTuningPair,
        system_prompt: str,
    ) -> None:
        """fits_budget with default max_tokens (5000) must be consistent."""
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        manager = TokenBudgetManager()  # default max_tokens=5000
        estimated = manager.estimate_pair_tokens(pair, system_prompt)
        fits = manager.fits_budget(pair, system_prompt)

        assert fits == (estimated <= 5000), (
            f"fits_budget inconsistent with default max_tokens.\n"
            f"  estimated = {estimated}\n"
            f"  fits      = {fits}"
        )

    # -- fits_budget is deterministic --------------------------------------

    @given(
        pair=_token_budget_pair_strategy(),
        system_prompt=_system_prompt_strategy(),
    )
    @settings(max_examples=100)
    def test_fits_budget_is_deterministic(
        self,
        pair: InstructionTuningPair,
        system_prompt: str,
    ) -> None:
        """Calling fits_budget twice with the same inputs yields the same result."""
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        manager = TokenBudgetManager()
        first = manager.fits_budget(pair, system_prompt)
        second = manager.fits_budget(pair, system_prompt)
        assert first == second, (
            f"Non-deterministic fits_budget result.\n"
            f"  first  = {first}\n"
            f"  second = {second}"
        )

    # -- Custom chars_per_token ratio is respected -------------------------

    @given(
        text=st.text(min_size=1, max_size=500),
        chars_per_token=st.floats(
            min_value=1.0, max_value=10.0,
            allow_nan=False, allow_infinity=False,
        ),
    )
    @settings(max_examples=100)
    def test_custom_chars_per_token_respected(
        self, text: str, chars_per_token: float
    ) -> None:
        """estimate_tokens must use the configured chars_per_token ratio."""
        # Feature: conversational-training-data,
        # Property 6: Token budget estimation consistency
        import math

        manager = TokenBudgetManager(chars_per_token=chars_per_token)
        result = manager.estimate_tokens(text)

        if not text:
            assert result == 0
        else:
            expected = math.ceil(len(text) / chars_per_token)
            assert result == expected, (
                f"estimate_tokens does not match expected calculation.\n"
                f"  len(text)        = {len(text)}\n"
                f"  chars_per_token  = {chars_per_token}\n"
                f"  expected         = {expected}\n"
                f"  actual           = {result}"
            )


# ---------------------------------------------------------------------------
# Property 7: Citation preservation through summarization
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from multimodal_librarian.ml.token_budget import (  # noqa: E402
    _CITATION_PATTERN as _TB_CITATION_PATTERN,
)


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine synchronously.

    Uses ``asyncio.new_event_loop()`` to avoid the deprecated
    ``get_event_loop()`` warning on Python 3.10+.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _citation_marker(n: int) -> str:
    """Return a ``[Source N]`` citation marker for the given integer."""
    return f"[Source {n}]"


def _response_with_citations_strategy() -> st.SearchStrategy[tuple[str, list[str]]]:
    """Generate a (response_text, citations) pair.

    The response contains between 1 and 8 unique ``[Source N]`` markers
    interleaved with prose-like filler text.  The second element is the
    sorted list of citation markers present in the response.

    Returns
    -------
    tuple[str, list[str]]
        ``(response_text, sorted_citation_markers)``
    """
    return st.tuples(
        # Number of unique citations to inject
        st.integers(min_value=1, max_value=8),
        # Filler segments (medical-ish prose without brackets)
        st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "Z"),
                    blacklist_characters="[]",
                ),
                min_size=10,
                max_size=120,
            ).filter(lambda s: s.strip()),
            min_size=2,
            max_size=10,
        ),
    ).map(lambda t: _build_cited_response(t[0], t[1]))


def _build_cited_response(
    n_citations: int,
    fillers: list[str],
) -> tuple[str, list[str]]:
    """Assemble a response string with *n_citations* unique ``[Source N]`` markers.

    Citations are distributed across the filler segments.  Returns
    ``(response_text, sorted_citation_markers)``.
    """
    citations = [_citation_marker(i) for i in range(1, n_citations + 1)]

    parts: list[str] = []
    for i, filler in enumerate(fillers):
        parts.append(filler)
        if i < len(citations):
            parts.append(citations[i])

    # If there are more citations than fillers, append the rest at the end.
    for c in citations[len(fillers):]:
        parts.append(c)

    response_text = " ".join(parts)
    return response_text, sorted(citations)


def _mock_llm_client_preserving_citations(
    response_text: str,
) -> MagicMock:
    """Create a mock LLM client whose ``generate`` returns a summarized
    version of *response_text* that preserves all ``[Source N]`` markers.

    The mock simply returns the original text (which by construction
    contains all citations).  This simulates a well-behaved LLM that
    preserves citations during summarization.
    """
    client = MagicMock()
    client.generate = AsyncMock(return_value=response_text)
    return client


def _mock_llm_client_dropping_citations(
    response_text: str,
    citations_to_drop: list[str],
) -> MagicMock:
    """Create a mock LLM client that drops specific citations.

    Returns a version of *response_text* with the specified citation
    markers removed, simulating a poorly-behaved summarizer.
    """
    stripped = response_text
    for c in citations_to_drop:
        stripped = stripped.replace(c, "")
    client = MagicMock()
    client.generate = AsyncMock(return_value=stripped)
    return client


@pytest.mark.pbt
@pytest.mark.unit
class TestCitationPreservationThroughSummarization:
    """Property 7: Citation preservation through summarization.

    For any response string containing ``[Source N]`` citation markers,
    if ``summarize_response()`` succeeds (returns a non-None result),
    the summarized output SHALL contain every ``[Source N]`` marker
    that was present in the original response.

    Validates: Requirements 3.4
    """

    # -- Core property: successful summarization preserves all citations --

    @given(data=st.data())
    @settings(max_examples=100)
    def test_successful_summarization_preserves_all_citations(
        self, data: st.DataObject
    ) -> None:
        """When the LLM preserves citations, summarize_response must
        return a result containing every original ``[Source N]`` marker.
        """
        # Feature: conversational-training-data,
        # Property 7: Citation preservation through summarization
        response_text, citations = data.draw(
            _response_with_citations_strategy(),
            label="response_with_citations",
        )
        target_tokens = data.draw(
            st.integers(min_value=50, max_value=2000),
            label="target_tokens",
        )

        client = _mock_llm_client_preserving_citations(response_text)
        manager = TokenBudgetManager(llm_client=client)

        result = _run_async(
            manager.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
            )
        )

        # The mock preserves all citations, so result must not be None.
        assert result is not None, (
            "summarize_response returned None despite LLM preserving "
            "all citations."
        )

        # Every original citation must appear in the summarized output.
        result_citations = set(_TB_CITATION_PATTERN.findall(result))
        for citation in citations:
            assert citation in result_citations, (
                f"Citation {citation!r} missing from summarized output.\n"
                f"  original_citations = {citations}\n"
                f"  result_citations   = {sorted(result_citations)}\n"
                f"  summarized_text    = {result!r}"
            )

    # -- Summarization returns None when citations are dropped ------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_summarization_returns_none_when_citations_dropped(
        self, data: st.DataObject
    ) -> None:
        """When the LLM drops one or more citations, summarize_response
        must return None (rejecting the summarization).
        """
        # Feature: conversational-training-data,
        # Property 7: Citation preservation through summarization
        response_text, citations = data.draw(
            _response_with_citations_strategy(),
            label="response_with_citations",
        )
        target_tokens = data.draw(
            st.integers(min_value=50, max_value=2000),
            label="target_tokens",
        )

        # Drop at least one citation.
        n_to_drop = data.draw(
            st.integers(min_value=1, max_value=len(citations)),
            label="n_citations_to_drop",
        )
        to_drop = data.draw(
            st.lists(
                st.sampled_from(citations),
                min_size=n_to_drop,
                max_size=n_to_drop,
                unique=True,
            ),
            label="citations_to_drop",
        )

        client = _mock_llm_client_dropping_citations(
            response_text, to_drop
        )
        manager = TokenBudgetManager(llm_client=client)

        result = _run_async(
            manager.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
            )
        )

        assert result is None, (
            f"summarize_response should return None when citations are "
            f"dropped, but got a result.\n"
            f"  dropped_citations = {to_drop}\n"
            f"  result            = {result!r}"
        )

    # -- No LLM client → always returns None ------------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_no_llm_client_returns_none(
        self, data: st.DataObject
    ) -> None:
        """Without an LLM client, summarize_response must return None."""
        # Feature: conversational-training-data,
        # Property 7: Citation preservation through summarization
        response_text, _ = data.draw(
            _response_with_citations_strategy(),
            label="response_with_citations",
        )
        target_tokens = data.draw(
            st.integers(min_value=50, max_value=2000),
            label="target_tokens",
        )

        manager = TokenBudgetManager(llm_client=None)

        result = _run_async(
            manager.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
            )
        )

        assert result is None, (
            "summarize_response should return None when no LLM client "
            "is configured."
        )

    # -- LLM failure → returns None ---------------------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_llm_failure_returns_none(
        self, data: st.DataObject
    ) -> None:
        """When the LLM call raises an exception, summarize_response
        must return None.
        """
        # Feature: conversational-training-data,
        # Property 7: Citation preservation through summarization
        response_text, _ = data.draw(
            _response_with_citations_strategy(),
            label="response_with_citations",
        )
        target_tokens = data.draw(
            st.integers(min_value=50, max_value=2000),
            label="target_tokens",
        )

        client = MagicMock()
        client.generate = AsyncMock(
            side_effect=RuntimeError("LLM service unavailable")
        )
        manager = TokenBudgetManager(llm_client=client)

        result = _run_async(
            manager.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
            )
        )

        assert result is None, (
            "summarize_response should return None when LLM call fails."
        )

    # -- LLM returns empty string → returns None --------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_llm_empty_response_returns_none(
        self, data: st.DataObject
    ) -> None:
        """When the LLM returns an empty string, summarize_response
        must return None.
        """
        # Feature: conversational-training-data,
        # Property 7: Citation preservation through summarization
        response_text, _ = data.draw(
            _response_with_citations_strategy(),
            label="response_with_citations",
        )
        target_tokens = data.draw(
            st.integers(min_value=50, max_value=2000),
            label="target_tokens",
        )

        client = MagicMock()
        client.generate = AsyncMock(return_value="")
        manager = TokenBudgetManager(llm_client=client)

        result = _run_async(
            manager.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
            )
        )

        assert result is None, (
            "summarize_response should return None when LLM returns "
            "empty string."
        )

    # -- Pre-extracted citations are respected -----------------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_pre_extracted_citations_are_used(
        self, data: st.DataObject
    ) -> None:
        """When citations are passed explicitly, summarize_response must
        verify those specific citations are preserved (not re-extract).
        """
        # Feature: conversational-training-data,
        # Property 7: Citation preservation through summarization
        response_text, citations = data.draw(
            _response_with_citations_strategy(),
            label="response_with_citations",
        )
        target_tokens = data.draw(
            st.integers(min_value=50, max_value=2000),
            label="target_tokens",
        )

        client = _mock_llm_client_preserving_citations(response_text)
        manager = TokenBudgetManager(llm_client=client)

        result = _run_async(
            manager.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
                citations=citations,
            )
        )

        assert result is not None, (
            "summarize_response returned None despite LLM preserving "
            "all pre-extracted citations."
        )

        result_citations = set(_TB_CITATION_PATTERN.findall(result))
        for citation in citations:
            assert citation in result_citations, (
                f"Pre-extracted citation {citation!r} missing from "
                f"summarized output.\n"
                f"  passed_citations = {citations}\n"
                f"  result_citations = {sorted(result_citations)}\n"
                f"  summarized_text  = {result!r}"
            )

    # -- Summarization is deterministic for same mock ---------------------

    @given(data=st.data())
    @settings(max_examples=100)
    def test_summarization_deterministic_with_same_mock(
        self, data: st.DataObject
    ) -> None:
        """Calling summarize_response twice with the same mock yields
        the same result.
        """
        # Feature: conversational-training-data,
        # Property 7: Citation preservation through summarization
        response_text, citations = data.draw(
            _response_with_citations_strategy(),
            label="response_with_citations",
        )
        target_tokens = data.draw(
            st.integers(min_value=50, max_value=2000),
            label="target_tokens",
        )

        client1 = _mock_llm_client_preserving_citations(response_text)
        manager1 = TokenBudgetManager(llm_client=client1)
        result1 = _run_async(
            manager1.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
            )
        )

        client2 = _mock_llm_client_preserving_citations(response_text)
        manager2 = TokenBudgetManager(llm_client=client2)
        result2 = _run_async(
            manager2.summarize_response(
                response=response_text,
                target_tokens=target_tokens,
            )
        )

        assert result1 == result2, (
            f"Non-deterministic summarization.\n"
            f"  result1 = {result1!r}\n"
            f"  result2 = {result2!r}"
        )

# ---------------------------------------------------------------------------
# Property 11: Confidence score is bounded and monotonic
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.rag_qa_strategy import (  # noqa: E402
    compute_confidence_score,
)


@pytest.mark.pbt
@pytest.mark.unit
class TestConfidenceScoreBoundsAndMonotonicity:
    """Property 11: Confidence score is bounded and monotonic.

    # Feature: conversational-training-data, Property 11: Confidence score is bounded and monotonic

    *For any* non-negative integer ``citation_count`` and positive
    integer ``min_citations``, the computed confidence score SHALL be
    in the range [0.0, 1.0].  Additionally, *for any* two citation
    counts where ``a < b`` (with the same ``min_citations``), the
    confidence score for ``b`` SHALL be greater than or equal to the
    confidence score for ``a``.

    **Validates: Requirements 5.4**
    """

    # -- Confidence score is in [0.0, 1.0] for all inputs -----------------

    @given(
        citation_count=st.integers(min_value=0, max_value=100),
        min_citations=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_confidence_bounded_zero_to_one(
        self, citation_count: int, min_citations: int
    ) -> None:
        """Confidence score must be in [0.0, 1.0] for all valid inputs."""
        # Feature: conversational-training-data,
        # Property 11: Confidence score is bounded and monotonic
        score = compute_confidence_score(citation_count, min_citations)
        assert 0.0 <= score <= 1.0, (
            f"Confidence score out of bounds.\n"
            f"  citation_count = {citation_count}\n"
            f"  min_citations  = {min_citations}\n"
            f"  score          = {score}"
        )

    # -- Monotonicity: a < b → confidence(a) <= confidence(b) -------------

    @given(
        a=st.integers(min_value=0, max_value=99),
        min_citations=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_confidence_monotonically_non_decreasing(
        self, a: int, min_citations: int
    ) -> None:
        """For a < b (same min_citations), confidence(a) <= confidence(b)."""
        # Feature: conversational-training-data,
        # Property 11: Confidence score is bounded and monotonic
        b = a + 1
        score_a = compute_confidence_score(a, min_citations)
        score_b = compute_confidence_score(b, min_citations)
        assert score_a <= score_b, (
            f"Confidence is not monotonically non-decreasing.\n"
            f"  a              = {a}\n"
            f"  b              = {b}\n"
            f"  min_citations  = {min_citations}\n"
            f"  score(a)       = {score_a}\n"
            f"  score(b)       = {score_b}"
        )

    # -- Monotonicity across wider gaps -----------------------------------

    @given(
        a=st.integers(min_value=0, max_value=50),
        gap=st.integers(min_value=1, max_value=50),
        min_citations=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_confidence_monotonic_with_larger_gap(
        self, a: int, gap: int, min_citations: int
    ) -> None:
        """For a < b with arbitrary gap, confidence(a) <= confidence(b)."""
        # Feature: conversational-training-data,
        # Property 11: Confidence score is bounded and monotonic
        b = a + gap
        score_a = compute_confidence_score(a, min_citations)
        score_b = compute_confidence_score(b, min_citations)
        assert score_a <= score_b, (
            f"Confidence is not monotonic with gap.\n"
            f"  a              = {a}\n"
            f"  b              = {b}\n"
            f"  min_citations  = {min_citations}\n"
            f"  score(a)       = {score_a}\n"
            f"  score(b)       = {score_b}"
        )

    # -- Zero citations → low confidence ----------------------------------

    @given(min_citations=st.integers(min_value=1, max_value=10))
    @settings(max_examples=100)
    def test_zero_citations_low_confidence(
        self, min_citations: int
    ) -> None:
        """Zero citations must produce a confidence of 0.0."""
        # Feature: conversational-training-data,
        # Property 11: Confidence score is bounded and monotonic
        score = compute_confidence_score(0, min_citations)
        assert score == 0.0, (
            f"Expected 0.0 for zero citations.\n"
            f"  min_citations = {min_citations}\n"
            f"  score         = {score}"
        )

    # -- At or above min_citations → confidence >= 0.7 --------------------

    @given(
        min_citations=st.integers(min_value=1, max_value=10),
        extra=st.integers(min_value=0, max_value=90),
    )
    @settings(max_examples=100)
    def test_at_or_above_min_citations_high_confidence(
        self, min_citations: int, extra: int
    ) -> None:
        """When citation_count >= min_citations, confidence >= 0.7."""
        # Feature: conversational-training-data,
        # Property 11: Confidence score is bounded and monotonic
        citation_count = min_citations + extra
        score = compute_confidence_score(citation_count, min_citations)
        assert score >= 0.7, (
            f"Expected confidence >= 0.7 when at/above min_citations.\n"
            f"  citation_count = {citation_count}\n"
            f"  min_citations  = {min_citations}\n"
            f"  score          = {score}"
        )

    # -- Computation is deterministic -------------------------------------

    @given(
        citation_count=st.integers(min_value=0, max_value=100),
        min_citations=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_confidence_is_deterministic(
        self, citation_count: int, min_citations: int
    ) -> None:
        """Calling compute_confidence_score twice yields the same result."""
        # Feature: conversational-training-data,
        # Property 11: Confidence score is bounded and monotonic
        s1 = compute_confidence_score(citation_count, min_citations)
        s2 = compute_confidence_score(citation_count, min_citations)
        assert s1 == s2, (
            f"Non-deterministic confidence computation.\n"
            f"  citation_count = {citation_count}\n"
            f"  min_citations  = {min_citations}\n"
            f"  first          = {s1}\n"
            f"  second         = {s2}"
        )


# ---------------------------------------------------------------------------
# Property 12: JSONL round-trip preservation for new pipeline output
# ---------------------------------------------------------------------------

from multimodal_librarian.ml.models import VALID_STRATEGIES  # noqa: E402

# Refusal phrases used to generate refusal-formatted responses.
_REFUSAL_RESPONSE_TEMPLATES: list[str] = [
    "I don't have information on {topic} in the available sources.",
    "I wasn't able to find details about {topic} in the documents I have access to.",
    "The sources I have don't cover {topic}. You might want to consult a healthcare professional.",
    "I couldn't locate information about {topic} in the available materials.",
]


def _unicode_text_for_roundtrip() -> st.SearchStrategy[str]:
    """Generate non-empty strings with arbitrary Unicode content.

    Includes characters from the full Unicode BMP: Latin, CJK,
    Cyrillic, Arabic, emoji, mathematical symbols, etc.
    Filters out strings that are only whitespace.
    """
    return st.text(
        alphabet=st.characters(
            codec="utf-8",
            categories=(
                "L",  # Letters
                "N",  # Numbers
                "P",  # Punctuation
                "S",  # Symbols
                "Z",  # Separators
            ),
            exclude_characters="\x00",
        ),
        min_size=1,
        max_size=300,
    ).filter(lambda s: s.strip())


def _confidence_score_strategy() -> st.SearchStrategy[float]:
    """Generate a float in [0.0, 1.0]."""
    return st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    )


def _pipeline_pair_metadata_strategy() -> st.SearchStrategy[PairMetadata]:
    """Generate PairMetadata representative of the conversational pipeline.

    Includes ``"rag"`` strategy (the primary strategy for this pipeline)
    and ``"llm_rewritten"`` in source_concepts to represent rewritten
    seed questions.
    """
    return st.builds(
        PairMetadata,
        strategy=st.just("rag"),
        source_concepts=st.one_of(
            # Standard source concepts
            st.lists(_unicode_text_for_roundtrip(), max_size=3),
            # Include "llm_rewritten" marker in source concepts
            st.lists(
                _unicode_text_for_roundtrip(), min_size=0, max_size=2
            ).map(lambda lst: ["llm_rewritten"] + lst),
        ),
        confidence_score=_confidence_score_strategy(),
        source_document=st.one_of(
            st.none(), _unicode_text_for_roundtrip()
        ),
        chunk_ids=st.one_of(
            st.none(),
            st.lists(_unicode_text_for_roundtrip(), max_size=5),
        ),
        relationship_chain=st.one_of(
            st.none(), _unicode_text_for_roundtrip()
        ),
    )


def _refusal_response_strategy() -> st.SearchStrategy[str]:
    """Generate a refusal-formatted response string."""
    return st.tuples(
        st.sampled_from(_REFUSAL_RESPONSE_TEMPLATES),
        _unicode_text_for_roundtrip(),
    ).map(lambda t: t[0].format(topic=t[1][:50]))


def _pipeline_instruction_tuning_pair_strategy() -> (
    st.SearchStrategy[InstructionTuningPair]
):
    """Generate InstructionTuningPair objects representative of the
    conversational training data pipeline.

    Includes:
    - Standard RAG pairs with Unicode content
    - Pairs with ``"llm_rewritten"`` in source_concepts
    - Pairs with refusal-formatted responses
    """
    # Standard pipeline pair with arbitrary response
    standard_pair = st.builds(
        InstructionTuningPair,
        instruction=_unicode_text_for_roundtrip(),
        context=_unicode_text_for_roundtrip(),
        response=_unicode_text_for_roundtrip(),
        metadata=_pipeline_pair_metadata_strategy(),
    )

    # Pair with refusal-formatted response
    refusal_pair = st.builds(
        InstructionTuningPair,
        instruction=_unicode_text_for_roundtrip(),
        context=_unicode_text_for_roundtrip(),
        response=_refusal_response_strategy(),
        metadata=_pipeline_pair_metadata_strategy(),
    )

    return st.one_of(standard_pair, refusal_pair)


@pytest.mark.pbt
@pytest.mark.unit
class TestJSONLRoundTripPreservation:
    """Property 12: JSONL round-trip preservation for new pipeline output.

    # Feature: conversational-training-data, Property 12: JSONL round-trip preservation

    *For any* valid ``InstructionTuningPair`` produced by the
    conversational training data pipeline (including pairs with
    ``source="llm_rewritten"`` seed questions and refusal-formatted
    responses), serializing to JSONL and deserializing back SHALL
    produce an equivalent pair.

    **Validates: Requirements 7.1, 7.2**
    """

    # -- Core round-trip: parse(print(x)) == x ----------------------------

    @given(pair=_pipeline_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_equality(
        self, pair: InstructionTuningPair
    ) -> None:
        """parse(print(x)) == x for any pipeline-produced pair."""
        # Feature: conversational-training-data,
        # Property 12: JSONL round-trip preservation
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored == pair, (
            f"Round-trip failed.\n"
            f"  original = {pair!r}\n"
            f"  restored = {restored!r}"
        )

    # -- Refusal-formatted responses survive round-trip --------------------

    @given(
        pair=st.builds(
            InstructionTuningPair,
            instruction=_unicode_text_for_roundtrip(),
            context=_unicode_text_for_roundtrip(),
            response=_refusal_response_strategy(),
            metadata=_pipeline_pair_metadata_strategy(),
        )
    )
    @settings(max_examples=100)
    def test_refusal_response_round_trip(
        self, pair: InstructionTuningPair
    ) -> None:
        """Refusal-formatted responses survive JSONL round-trip."""
        # Feature: conversational-training-data,
        # Property 12: JSONL round-trip preservation
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored == pair, (
            f"Refusal response round-trip failed.\n"
            f"  original_response = {pair.response!r}\n"
            f"  restored_response = {restored.response!r}"
        )

    # -- Pairs with llm_rewritten source survive round-trip ----------------

    @given(
        pair=st.builds(
            InstructionTuningPair,
            instruction=_unicode_text_for_roundtrip(),
            context=_unicode_text_for_roundtrip(),
            response=_unicode_text_for_roundtrip(),
            metadata=st.builds(
                PairMetadata,
                strategy=st.just("rag"),
                source_concepts=st.lists(
                    _unicode_text_for_roundtrip(),
                    min_size=0,
                    max_size=2,
                ).map(lambda lst: ["llm_rewritten"] + lst),
                confidence_score=_confidence_score_strategy(),
                source_document=st.one_of(
                    st.none(), _unicode_text_for_roundtrip()
                ),
                chunk_ids=st.one_of(
                    st.none(),
                    st.lists(
                        _unicode_text_for_roundtrip(), max_size=3
                    ),
                ),
                relationship_chain=st.none(),
            ),
        )
    )
    @settings(max_examples=100)
    def test_llm_rewritten_source_round_trip(
        self, pair: InstructionTuningPair
    ) -> None:
        """Pairs with 'llm_rewritten' in source_concepts survive round-trip."""
        # Feature: conversational-training-data,
        # Property 12: JSONL round-trip preservation
        assert "llm_rewritten" in pair.metadata.source_concepts
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored == pair, (
            f"llm_rewritten source round-trip failed.\n"
            f"  original_concepts = {pair.metadata.source_concepts!r}\n"
            f"  restored_concepts = {restored.metadata.source_concepts!r}"
        )

    # -- All metadata fields preserved ------------------------------------

    @given(pair=_pipeline_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_all_metadata(
        self, pair: InstructionTuningPair
    ) -> None:
        """All metadata fields survive serialization round-trip."""
        # Feature: conversational-training-data,
        # Property 12: JSONL round-trip preservation
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored.metadata.strategy == pair.metadata.strategy
        assert (
            restored.metadata.confidence_score
            == pair.metadata.confidence_score
        )
        assert (
            restored.metadata.source_concepts
            == pair.metadata.source_concepts
        )
        assert (
            restored.metadata.source_document
            == pair.metadata.source_document
        )
        assert restored.metadata.chunk_ids == pair.metadata.chunk_ids
        assert (
            restored.metadata.relationship_chain
            == pair.metadata.relationship_chain
        )

    # -- Double round-trip (idempotence) ----------------------------------

    @given(pair=_pipeline_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_double_round_trip_idempotent(
        self, pair: InstructionTuningPair
    ) -> None:
        """Two consecutive round-trips produce the same result."""
        # Feature: conversational-training-data,
        # Property 12: JSONL round-trip preservation
        line1 = pair.to_jsonl_line()
        restored1 = InstructionTuningPair.from_jsonl_line(line1)
        line2 = restored1.to_jsonl_line()
        restored2 = InstructionTuningPair.from_jsonl_line(line2)
        assert restored2 == pair
        assert line1 == line2
