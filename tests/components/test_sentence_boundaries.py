"""
Unit tests for sentence-boundary detection and bare capitalized-phrase lists.

Covers ``_find_sentence_boundaries`` and ``_is_standalone_capitalized_phrase``
on ``GenericMultiLevelChunkingFramework``.

The two behaviours under test are:

1. Abbreviation false positives — a period followed by a lowercase word is an
   abbreviation/decimal, not a sentence end ("p.o. twice daily", "neg. for").
2. Bare capitalized-phrase lists — runs of >=2 consecutive Title-Case /
   ALL-CAPS lines are list items and get split; a single isolated capitalized
   line is deliberately left alone (ambiguous with wrapped prose).
"""

import pytest

from src.multimodal_librarian.components.chunking_framework.framework import (
    GenericMultiLevelChunkingFramework,
)


@pytest.fixture
def framework():
    return GenericMultiLevelChunkingFramework()


class TestAbbreviationHandling:
    def test_unknown_abbreviation_lowercase_continuation_not_split(self, framework):
        """A period before a lowercase word is an abbreviation, not a boundary."""
        text = "The result was neg. for hepatitis. Treatment was started."
        assert framework._find_sentence_boundaries(text) == [6]

    def test_normal_sentence_end(self, framework):
        """A period before a capitalised word is a sentence end."""
        text = "The patient improved. Treatment was discontinued."
        assert framework._find_sentence_boundaries(text) == [3]

    def test_known_abbreviation_before_capital_not_split(self, framework):
        """A known abbreviation before a capitalised word stays unsplit.

        This is a deliberate tradeoff: "etc." at a sentence end will merge the
        following sentence rather than risk a spurious split on "Dr. Smith".
        """
        text = "This is an example, etc. The next sentence follows."
        assert framework._find_sentence_boundaries(text) == []

    def test_title_abbreviation_before_proper_noun_not_split(self, framework):
        text = "We saw Dr. Smith and Mr. Jones today."
        assert framework._find_sentence_boundaries(text) == []

    def test_medical_dosing_abbreviation_not_split(self, framework):
        text = "Give p.o. twice daily. Then reevaluate."
        assert framework._find_sentence_boundaries(text) == [4]

    def test_intravenous_abbreviation_before_capital_not_split(self, framework):
        text = "Start i.v. Vancomycin and monitor."
        assert framework._find_sentence_boundaries(text) == []

    def test_time_abbreviation_before_capital_not_split(self, framework):
        text = "Dose at 8 a.m. Patients then rest."
        assert framework._find_sentence_boundaries(text) == []

    def test_english_word_am_still_sentence_end(self, framework):
        """The dotted "a.m." guard must not suppress a sentence-final "I am."."""
        text = "Here I am. Now go."
        assert framework._find_sentence_boundaries(text) == [3]

    def test_number_abbreviation_no_not_split(self, framework):
        """'No. 5' (number) stays unsplit — only a numeral follows."""
        text = "See No. 5 for details."
        assert framework._find_sentence_boundaries(text) == []

    def test_english_word_no_still_sentence_end(self, framework):
        """A lowercase 'no.' before a capital is the word, not the number."""
        text = "The answer is no. Next question."
        assert framework._find_sentence_boundaries(text) == [4]

    def test_capitalized_word_no_still_sentence_end(self, framework):
        """A capitalized 'No.' followed by a letter is the word, not a number."""
        text = "No. I won't go."
        assert framework._find_sentence_boundaries(text) == [1]

    def test_figure_abbreviation_not_split(self, framework):
        """'Fig. 3' (figure) stays unsplit — a numeral follows."""
        text = "See Fig. 3 for details."
        assert framework._find_sentence_boundaries(text) == []

    def test_english_word_fig_still_sentence_end(self, framework):
        """A lowercase 'fig.' (the fruit) before a capital is a sentence end."""
        text = "He ate a fig. Then he left."
        assert framework._find_sentence_boundaries(text) == [4]

    def test_temperature_abbreviation_not_split(self, framework):
        """'Temp. 98.6' (temperature) stays unsplit — a numeral follows."""
        text = "Temp. 98.6 was elevated."
        assert framework._find_sentence_boundaries(text) == []

    def test_english_word_temp_still_sentence_end(self, framework):
        """A lowercase 'temp.' (temporary) before a capital is a sentence end."""
        text = "She hired a temp. The job ended."
        assert framework._find_sentence_boundaries(text) == [4]


class TestFusedSentences:
    def test_no_space_after_period_splits(self, framework):
        """A dropped-space period before an uppercase letter is a sentence end."""
        text = "The patient improved.Treatment was discontinued."
        assert framework._find_sentence_boundaries(text) == [3]

    def test_title_abbreviation_fused_to_name_not_split(self, framework):
        """A title abbreviation fused to a name stays unsplit ('Dr.Smith')."""
        text = "We saw Dr.Smith today."
        assert framework._find_sentence_boundaries(text) == []

    def test_question_mark_fused_splits(self, framework):
        text = "Was it tested?The result was negative."
        assert framework._find_sentence_boundaries(text) == [3]

    def test_decimal_not_split(self, framework):
        """A digit after a period is a decimal, not a fused sentence."""
        text = "The value was 3.14 units."
        assert framework._find_sentence_boundaries(text) == []


class TestCapitalizedPhraseLists:
    def test_run_of_three_splits_before_each_item(self, framework):
        text = (
            "Healthcare Personnel\n"
            "Post-Exposure Prophylaxis\n"
            "Management Guidelines"
        )
        assert framework._find_sentence_boundaries(text) == [2, 4]

    def test_single_capitalized_line_not_split(self, framework):
        """A lone capitalized line is ambiguous with wrapped prose."""
        text = "the patient was exposed to\nHepatitis B Virus\ninfection yesterday"
        assert framework._find_sentence_boundaries(text) == []


class TestIsStandaloneCapitalizedPhrase:
    @pytest.mark.parametrize(
        "line, expected",
        [
            ("Healthcare Personnel", True),
            ("Post-Exposure Prophylaxis", True),
            ("Management Guidelines and Work Restrictions", True),
            ("Hepatitis B Virus", True),
            ("Category III", True),
            ("hepatitis b surface antigen", False),
            ("the patient was exposed", False),
            ("Healthcare", False),
        ],
    )
    def test_phrase_detection(self, framework, line, expected):
        assert framework._is_standalone_capitalized_phrase(line) is expected


class TestDehyphenateSpaceWraps:
    """Soft-wrap folding for already-whitespace-collapsed chunk text.

    Stored chunks carry "word- word" (a typeset hyphen collapsed to a space).
    The fold is conservative: join only when the merged form is a known word,
    otherwise drop the space but keep the hyphen (a true compound).
    """

    def test_soft_wrap_join(self, framework):
        assert framework._dehyphenate_space_wraps("andro- gen") == "androgen"
        assert framework._dehyphenate_space_wraps("popula- tion") == "population"
        assert framework._dehyphenate_space_wraps("treat- ment") == "treatment"

    def test_all_caps_soft_wrap_join(self, framework):
        assert framework._dehyphenate_space_wraps("CON- FIRMED") == "CONFIRMED"
        assert framework._dehyphenate_space_wraps("PAREN- TERAL") == "PARENTERAL"

    def test_inflected_soft_wrap_join(self, framework):
        assert (
            framework._dehyphenate_space_wraps("recommen- dations")
            == "recommendations"
        )
        assert framework._dehyphenate_space_wraps("gene expres- sion") == "gene expression"

    def test_edropping_gerund_soft_wrap_join(self, framework):
        """'ing' after a silent 'e' restores the 'e' ("includ- ing" -> "including")."""
        assert framework._dehyphenate_space_wraps("includ- ing") == "including"
        assert framework._dehyphenate_space_wraps("imag- ing") == "imaging"
        assert framework._dehyphenate_space_wraps("mak- ing") == "making"

    def test_compound_keeps_hyphen(self, framework):
        assert framework._dehyphenate_space_wraps("B- cell") == "B-cell"
        assert framework._dehyphenate_space_wraps("T- cell") == "T-cell"
        assert (
            framework._dehyphenate_space_wraps("enzyme- inducing")
            == "enzyme-inducing"
        )
        assert framework._dehyphenate_space_wraps("FDA- approved") == "FDA-approved"
        assert (
            framework._dehyphenate_space_wraps("carbidopa- levodopa")
            == "carbidopa-levodopa"
        )

    def test_function_word_dash_untouched(self, framework):
        assert (
            framework._dehyphenate_space_wraps("pre- and post-operative")
            == "pre- and post-operative"
        )
        assert (
            framework._dehyphenate_space_wraps("low- and intermediate")
            == "low- and intermediate"
        )

    def test_extra_words_join_domain_terms(self, framework):
        extra = frozenset({"thromboembolism", "anticoagulation"})
        assert (
            framework._dehyphenate_space_wraps("thromboem- bolism", extra)
            == "thromboembolism"
        )
        assert (
            framework._dehyphenate_space_wraps("anti- coagulation", extra)
            == "anticoagulation"
        )

    def test_no_artifact_unchanged(self, framework):
        text = "The patient received extended-release metformin."
        assert framework._dehyphenate_space_wraps(text) == text
