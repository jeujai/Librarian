"""Unit tests for the corpus-derived surface-form learner's pure helpers.

Covers ``normalize_text``, ``anchors_for``, ``cooccur_in_same_sentence``,
``cooccur_rate``, ``parse_json_list``, and the select gate ``evaluate_candidates``.
"""

from src.multimodal_librarian.components.kg_retrieval.surface_form_learner import (
    anchors_for,
    cooccur_in_same_sentence,
    cooccur_rate,
    evaluate_candidates,
    is_valid_surface_form,
    normalize_text,
    parse_json_list,
)


class TestNormalizeText:
    def test_collapses_linebreak_hyphenation(self):
        assert normalize_text("exposure-\nprone") == "exposure-prone"
        # A hyphen followed by a space (not a line break) is left alone.
        assert normalize_text("Exposure- Prone") == "exposure- prone"

    def test_lowercases(self):
        assert normalize_text("Category III") == "category iii"


class TestAnchorsFor:
    def test_known_type_uses_lexicon(self):
        anchors = anchors_for("RESTRICTION", "work restrictions")
        assert "restrict" in anchors
        assert "prohibit" in anchors
        assert "exposure-prone" in anchors

    def test_unknown_type_falls_back_to_name_words(self):
        anchors = anchors_for("UNKNOWN_TYPE", "work restrictions")
        assert "work" in anchors
        assert "restrictions" in anchors

    def test_process_anchors_are_co_text_not_name_synonyms(self):
        anchors = anchors_for("PROCESS", "management guidelines")
        assert "manage" not in anchors
        assert "guideline" not in anchors
        assert "protocol" not in anchors
        assert "follow" in anchors
        assert "algorithm" in anchors


class TestCooccurInSameSentence:
    def test_candidate_and_anchor_same_sentence(self):
        text = (
            "The general recommendation for practice restrictions addresses "
            "category III/exposure-prone procedures."
        )
        assert cooccur_in_same_sentence(
            text, "category III", ["exposure-prone", "prohibit"]
        )

    def test_candidate_and_anchor_different_sentence(self):
        text = (
            "The availability of safer devices that mitigate patient exposure "
            "risk is addressed. The recommendation for practice restrictions "
            "addresses category III procedures."
        )
        assert not cooccur_in_same_sentence(
            text, "safer devices", ["restrict", "prohibit", "exposure-prone"]
        )

    def test_no_anchor_present(self):
        text = "See Category III: Cardiac Magnetic Resonance Imaging."
        assert not cooccur_in_same_sentence(
            text, "category III", ["restrict", "exposure-prone"]
        )

    def test_linebreak_hyphenation_matches_anchor(self):
        text = "HCP who perform category III/exposure-\nprone procedures."
        assert cooccur_in_same_sentence(
            text, "category III", ["exposure-prone"]
        )


class TestCooccurRate:
    def test_fraction_of_chunks(self):
        chunks = [
            "category III/exposure-prone procedures are restricted.",
            "See Category III: Cardiac MRI.",  # no anchor
        ]
        assert cooccur_rate(chunks, "category III", ["restrict", "exposure-prone"]) == 0.5

    def test_empty_chunks_is_zero(self):
        assert cooccur_rate([], "x", ["y"]) == 0.0


class TestParseJsonList:
    def test_clean_array(self):
        assert parse_json_list('["a", "b"]') == ["a", "b"]

    def test_code_fence(self):
        assert parse_json_list('```json\n["category III"]\n```') == ["category III"]

    def test_surrounding_text(self):
        assert parse_json_list('here is the list ["x", "y"] done') == ["x", "y"]

    def test_truncated_returns_empty(self):
        assert parse_json_list('["a", "b"') == []

    def test_garbage_returns_empty(self):
        assert parse_json_list("not json at all") == []


class TestIsValidSurfaceForm:
    def test_accepts_noun_phrases(self):
        assert is_valid_surface_form("category III")
        assert is_valid_surface_form("exposure-prone procedures")
        assert is_valid_surface_form("management guidelines")

    def test_rejects_trailing_function_word(self):
        assert not is_valid_surface_form("guidelines for the management of")
        assert not is_valid_surface_form("recommendations for")

    def test_rejects_leading_verb(self):
        assert not is_valid_surface_form("prevent spread of illness")
        assert not is_valid_surface_form("adhere to work restrictions")


class TestEvaluateCandidates:
    def test_select_keeps_correct_and_drops_overgeneration(self):
        candidates = ["category III", "safer devices", "RESTRICTION", "absent"]
        anchors = ["restrict", "prohibit", "exposure-prone"]
        chunks_by_candidate = {
            "category III": [
                "The recommendation for practice restrictions addresses "
                "category III/exposure-prone procedures."
            ],
            # same chunk, different sentence -> co-occurrence gate drops it
            "safer devices": [
                "The availability of safer devices that mitigate patient "
                "exposure risk is addressed. The recommendation for practice "
                "restrictions addresses category III procedures."
            ],
            # co-occurs but cross-encoder below floor -> dropped
            "RESTRICTION": ["Restriction of activities is recommended."],
            "absent": [],
        }
        score_by_candidate = {
            "category III": 0.584,
            "safer devices": 0.542,
            "RESTRICTION": 0.503,
        }
        survivors = evaluate_candidates(
            candidates, anchors, chunks_by_candidate, score_by_candidate
        )
        assert survivors == ["category III"]

    def test_drops_malformed_shapes(self):
        candidates = ["management guidelines", "guidelines for the management of"]
        anchors = ["guideline", "manage"]
        chunks_by_candidate = {
            "management guidelines": ["Follow the management guidelines."],
            "guidelines for the management of": [
                "These guidelines for the management of HCP."
            ],
        }
        score_by_candidate = {
            "management guidelines": 0.9,
            "guidelines for the management of": 0.9,
        }
        survivors = evaluate_candidates(
            candidates, anchors, chunks_by_candidate, score_by_candidate
        )
        assert survivors == ["management guidelines"]
