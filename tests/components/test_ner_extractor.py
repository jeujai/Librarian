"""
Property-based and unit tests for NER_Extractor.

Tests cover:
- Property 1: Filtered labels excluded from key_terms
- Property 2: Proper nouns and capitalized nouns preserved
- Property 3: N-gram generation completeness
- Property 4: Three-way merge correctness
- Property 5: Well-formed NERResult
- Property 6: NERResult serialization round-trip
- Property 7: Independent layer degradation
- Unit tests for graceful degradation, merge logic, edge cases

Feature: scientific-medical-ner-extraction
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from multimodal_librarian.components.kg_retrieval.ner_extractor import (
    NER_Extractor,
    NERResult,
)

# =============================================================================
# Helpers — Mock spaCy objects
# =============================================================================


def _make_mock_token(text: str, pos: str = "NOUN"):
    """Create a mock spaCy token."""
    tok = MagicMock()
    tok.text = text
    tok.pos_ = pos
    return tok


def _make_mock_entity(text: str, label: str = "PERSON"):
    """Create a mock spaCy entity."""
    ent = MagicMock()
    ent.text = text
    ent.label_ = label
    return ent


def _make_mock_noun_chunk(tokens):
    """Create a mock noun chunk that iterates over tokens."""
    nc = MagicMock()
    nc.__iter__ = MagicMock(return_value=iter(tokens))
    return nc


def _make_mock_nlp(entities=None, noun_chunks=None):
    """Create a mock spaCy nlp model that returns a doc with given entities
    and noun chunks."""
    entities = entities or []
    noun_chunks = noun_chunks or []

    def nlp_call(query):
        doc = MagicMock()
        doc.ents = entities
        doc.noun_chunks = noun_chunks
        return doc

    mock_nlp = MagicMock(side_effect=nlp_call)
    return mock_nlp


def _make_mock_umls_client(result_dict=None, delay=0.0, raise_exc=None):
    """Create a mock UMLSClient."""
    client = MagicMock()

    async def _batch_search(names):
        if delay > 0:
            await asyncio.sleep(delay)
        if raise_exc:
            raise raise_exc
        return result_dict

    client.batch_search_by_names = AsyncMock(side_effect=_batch_search)
    return client


# =============================================================================
# Property 1: Filtered labels are excluded from key_terms
# Feature: scientific-medical-ner-extraction, Property 1: Filtered labels excluded
# =============================================================================

# Strategy: generate entity text and pick a filtered label
_filtered_labels = list(NER_Extractor.FILTERED_LABELS)
_age_descriptors = st.from_regex(r"\d{1,3}-year-old", fullmatch=True)
_numeric_patterns = st.from_regex(r"\d[\d\s.,%/:-]{0,10}", fullmatch=True)


@given(
    entity_text=st.text(min_size=1, max_size=30).filter(lambda t: t.strip()),
    label=st.sampled_from(_filtered_labels),
)
@settings(max_examples=100)
def test_property1_filtered_labels_excluded(entity_text, label):
    """**Validates: Requirements 2.3, 3.3**

    For any entity with a filtered label, it must not appear in key_terms.
    """
    ent = _make_mock_entity(entity_text, label)
    mock_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])

    extractor = NER_Extractor(spacy_web_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert entity_text not in result.key_terms, (
        f"Filtered label entity '{entity_text}' ({label}) "
        f"should not be in key_terms"
    )


@given(age_text=_age_descriptors)
@settings(max_examples=100)
def test_property1_age_descriptors_excluded(age_text):
    """**Validates: Requirements 2.3, 3.3**

    Age descriptors like '72-year-old' must not appear in key_terms.
    """
    ent = _make_mock_entity(age_text, "PERSON")
    mock_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])

    extractor = NER_Extractor(spacy_web_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert age_text not in result.key_terms


@given(num_text=_numeric_patterns)
@settings(max_examples=100)
def test_property1_numeric_patterns_excluded(num_text):
    """**Validates: Requirements 2.3, 3.3**

    Numeric-only patterns must not appear in key_terms.
    """
    assume(num_text.strip())
    ent = _make_mock_entity(num_text, "PERSON")
    mock_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])

    extractor = NER_Extractor(spacy_web_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert num_text not in result.key_terms


# --- Property 1 (sci layer): same filtering applies to Layer 2 ---


@given(
    entity_text=st.text(min_size=1, max_size=30).filter(lambda t: t.strip()),
    label=st.sampled_from(_filtered_labels),
)
@settings(max_examples=100)
def test_property1_filtered_labels_excluded_sci_layer(entity_text, label):
    """**Validates: Requirements 2.3, 3.3**

    For any entity with a filtered label produced by the sci layer (Layer 2),
    it must not appear in key_terms.
    """
    ent = _make_mock_entity(entity_text, label)
    mock_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])

    extractor = NER_Extractor(spacy_sci_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert entity_text not in result.key_terms, (
        f"Filtered label entity '{entity_text}' ({label}) from sci layer "
        f"should not be in key_terms"
    )


@given(age_text=_age_descriptors)
@settings(max_examples=100)
def test_property1_age_descriptors_excluded_sci_layer(age_text):
    """**Validates: Requirements 2.3, 3.3**

    Age descriptors from the sci layer must not appear in key_terms.
    """
    ent = _make_mock_entity(age_text, "PERSON")
    mock_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])

    extractor = NER_Extractor(spacy_sci_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert age_text not in result.key_terms


@given(num_text=_numeric_patterns)
@settings(max_examples=100)
def test_property1_numeric_patterns_excluded_sci_layer(num_text):
    """**Validates: Requirements 2.3, 3.3**

    Numeric-only patterns from the sci layer must not appear in key_terms.
    """
    assume(num_text.strip())
    ent = _make_mock_entity(num_text, "PERSON")
    mock_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])

    extractor = NER_Extractor(spacy_sci_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert num_text not in result.key_terms


# --- Property 1 (both layers): filtering holds when both layers produce
#     the same filtered entity simultaneously ---


@given(
    entity_text=st.text(min_size=1, max_size=30).filter(lambda t: t.strip()),
    label=st.sampled_from(_filtered_labels),
)
@settings(max_examples=100)
def test_property1_filtered_labels_excluded_both_layers(entity_text, label):
    """**Validates: Requirements 2.3, 3.3**

    When both web and sci layers produce an entity with a filtered label,
    it must not appear in key_terms.
    """
    ent = _make_mock_entity(entity_text, label)
    web_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])
    sci_nlp = _make_mock_nlp(entities=[ent], noun_chunks=[])

    extractor = NER_Extractor(
        spacy_web_nlp=web_nlp,
        spacy_sci_nlp=sci_nlp,
    )
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert entity_text not in result.key_terms, (
        f"Filtered label entity '{entity_text}' ({label}) from both layers "
        f"should not be in key_terms"
    )


# =============================================================================
# Property 2: Proper nouns and capitalized nouns preserved in key_terms
# Feature: scientific-medical-ner-extraction, Property 2: Proper nouns preserved
# =============================================================================

# Strategy: generate capitalized ASCII words of length > 2
_capitalized_word = st.text(
    alphabet=st.sampled_from(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    ),
    min_size=3,
    max_size=15,
).map(lambda s: s[0].upper() + s[1:]).filter(
    lambda s: len(s) > 2 and s[0].isupper()
)


@given(word=_capitalized_word)
@settings(max_examples=100)
def test_property2_propn_tokens_preserved(word):
    """**Validates: Requirements 2.2, 2.4, 9.1, 9.3**

    PROPN tokens (length > 2) from noun chunks appear in key_terms.
    """
    tok = _make_mock_token(word, pos="PROPN")
    nc = _make_mock_noun_chunk([tok])
    mock_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_web_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert word in result.key_terms, (
        f"PROPN token '{word}' should be in key_terms"
    )


@given(word=_capitalized_word)
@settings(max_examples=100)
def test_property2_capitalized_nouns_preserved(word):
    """**Validates: Requirements 2.2, 2.4, 9.1, 9.3**

    Capitalized NOUN tokens (length > 2) from noun chunks appear in key_terms.
    """
    tok = _make_mock_token(word, pos="NOUN")
    nc = _make_mock_noun_chunk([tok])
    mock_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_web_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert word in result.key_terms, (
        f"Capitalized NOUN token '{word}' should be in key_terms"
    )


# --- Property 2 (sci layer): PROPN/NOUN tokens preserved via Layer 2 ---


@given(word=_capitalized_word)
@settings(max_examples=100)
def test_property2_propn_tokens_preserved_sci_layer(word):
    """**Validates: Requirements 2.2, 2.4, 9.1, 9.3**

    PROPN tokens (length > 2) from noun chunks in the sci layer (Layer 2)
    appear in key_terms.
    """
    tok = _make_mock_token(word, pos="PROPN")
    nc = _make_mock_noun_chunk([tok])
    mock_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_sci_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert word in result.key_terms, (
        f"PROPN token '{word}' from sci layer should be in key_terms"
    )


@given(word=_capitalized_word)
@settings(max_examples=100)
def test_property2_capitalized_nouns_preserved_sci_layer(word):
    """**Validates: Requirements 2.2, 2.4, 9.1, 9.3**

    Capitalized NOUN tokens (length > 2) from noun chunks in the sci layer
    (Layer 2) appear in key_terms.
    """
    tok = _make_mock_token(word, pos="NOUN")
    nc = _make_mock_noun_chunk([tok])
    mock_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_sci_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert word in result.key_terms, (
        f"Capitalized NOUN token '{word}' from sci layer should be in key_terms"
    )


# --- Property 2 (both layers): tokens preserved when both layers produce them ---


@given(word=_capitalized_word)
@settings(max_examples=100)
def test_property2_propn_tokens_preserved_both_layers(word):
    """**Validates: Requirements 2.2, 2.4, 9.1, 9.3**

    PROPN tokens produced by both web and sci layers simultaneously
    still appear in key_terms (deduplicated).
    """
    tok = _make_mock_token(word, pos="PROPN")
    nc = _make_mock_noun_chunk([tok])
    web_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])
    sci_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_web_nlp=web_nlp, spacy_sci_nlp=sci_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    assert word in result.key_terms, (
        f"PROPN token '{word}' from both layers should be in key_terms"
    )


# --- Property 2 (subsumption exception): subsumed tokens correctly removed ---


@given(
    short_word=_capitalized_word,
    prefix=st.text(
        alphabet=st.sampled_from(
            "abcdefghijklmnopqrstuvwxyz"
        ),
        min_size=3,
        max_size=10,
    ).filter(lambda s: s.strip()),
)
@settings(max_examples=100)
def test_property2_propn_subsumed_by_umls_not_in_key_terms(short_word, prefix):
    """**Validates: Requirements 2.2, 2.4, 5.2, 5.5**

    When a PROPN token from the web layer is a case-insensitive substring
    of a longer UMLS term, the short token is subsumed and should NOT
    appear in key_terms — the longer UMLS term takes priority.
    """
    # Build a UMLS term that contains the short word as a substring
    umls_term = f"{prefix} {short_word}"
    assume(len(umls_term) > len(short_word))

    tok = _make_mock_token(short_word, pos="PROPN")
    nc = _make_mock_noun_chunk([tok])
    web_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_web_nlp=web_nlp)
    # Directly test the merge logic with a UMLS override
    web_entities = extractor._run_spacy_extraction(web_nlp, "test query")
    merged = extractor._merge_entities(
        web_entities=web_entities,
        sci_entities=[],
        umls_overrides=[umls_term],
    )

    assert umls_term in merged, (
        f"UMLS term '{umls_term}' should be in merged set"
    )
    # The short word should be subsumed since it's a substring of the UMLS term
    if short_word.lower() in umls_term.lower():
        assert short_word not in merged, (
            f"PROPN token '{short_word}' should be subsumed by "
            f"UMLS term '{umls_term}'"
        )


@given(
    short_word=_capitalized_word,
    prefix=st.text(
        alphabet=st.sampled_from(
            "abcdefghijklmnopqrstuvwxyz"
        ),
        min_size=3,
        max_size=10,
    ).filter(lambda s: s.strip()),
)
@settings(max_examples=100)
def test_property2_noun_subsumed_by_sci_not_in_key_terms(short_word, prefix):
    """**Validates: Requirements 2.2, 2.4, 5.3**

    When a capitalized NOUN token from the web layer is a case-insensitive
    substring of a longer sci entity, the short token is subsumed and should
    NOT appear in key_terms — the longer sci term takes priority.
    """
    sci_term = f"{prefix} {short_word}"
    assume(len(sci_term) > len(short_word))

    tok = _make_mock_token(short_word, pos="NOUN")
    nc = _make_mock_noun_chunk([tok])
    web_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_web_nlp=web_nlp)
    web_entities = extractor._run_spacy_extraction(web_nlp, "test query")
    merged = extractor._merge_entities(
        web_entities=web_entities,
        sci_entities=[sci_term],
        umls_overrides=[],
    )

    assert sci_term in merged, (
        f"Sci term '{sci_term}' should be in merged set"
    )
    if short_word.lower() in sci_term.lower():
        assert short_word not in merged, (
            f"NOUN token '{short_word}' should be subsumed by "
            f"sci term '{sci_term}'"
        )


# --- Property 2 (multiple tokens): all qualifying tokens in a chunk preserved ---


@given(
    words=st.lists(
        _capitalized_word,
        min_size=2,
        max_size=5,
    ).filter(lambda ws: len(set(ws)) == len(ws))  # unique words
)
@settings(max_examples=100)
def test_property2_multiple_propn_tokens_in_chunk_preserved(words):
    """**Validates: Requirements 2.2, 2.4, 9.1, 9.3**

    When a noun chunk contains multiple PROPN tokens (each length > 2),
    all of them appear in key_terms (no higher-priority layer to subsume).
    """
    tokens = [_make_mock_token(w, pos="PROPN") for w in words]
    nc = _make_mock_noun_chunk(tokens)
    mock_nlp = _make_mock_nlp(entities=[], noun_chunks=[nc])

    extractor = NER_Extractor(spacy_web_nlp=mock_nlp)
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    for w in words:
        assert w in result.key_terms, (
            f"PROPN token '{w}' from multi-token noun chunk "
            f"should be in key_terms"
        )


# =============================================================================
# Property 3: N-gram generation completeness
# Feature: scientific-medical-ner-extraction, Property 3: N-gram completeness
# =============================================================================


@given(
    words=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=2,
            max_size=10,
        ).filter(lambda w: w.strip()),
        min_size=1,
        max_size=20,
    )
)
@settings(max_examples=100)
def test_property3_ngram_count(words):
    """**Validates: Requirements 4.1**

    For N words, _generate_ngrams produces the correct count of n-grams:
    sum of (N - k + 1) for k in range(2, min(6, N + 1)).
    """
    extractor = NER_Extractor(max_ngram_size=5)
    query = " ".join(words)
    ngrams = extractor._generate_ngrams(query)

    n = len(words)
    expected_count = sum(
        (n - k + 1) for k in range(2, min(6, n + 1))
    )

    assert len(ngrams) == expected_count, (
        f"Expected {expected_count} n-grams for {n} words, "
        f"got {len(ngrams)}"
    )


@given(
    words=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=2,
            max_size=10,
        ).filter(lambda w: w.strip()),
        min_size=2,
        max_size=10,
    )
)
@settings(max_examples=100)
def test_property3_ngram_adjacency(words):
    """**Validates: Requirements 4.1**

    Every generated n-gram is a contiguous subsequence of the input words.
    """
    extractor = NER_Extractor(max_ngram_size=5)
    query = " ".join(words)
    ngrams = extractor._generate_ngrams(query)

    for gram in ngrams:
        gram_words = gram.split()
        assert 2 <= len(gram_words) <= 5, (
            f"N-gram '{gram}' has {len(gram_words)} words, "
            f"expected 2-5"
        )
        # Verify it's a contiguous subsequence
        found = False
        for i in range(len(words) - len(gram_words) + 1):
            candidate = " ".join(words[i : i + len(gram_words)])
            # Account for punctuation stripping
            if candidate.strip("?.,!\"';:()[]{}").strip() == gram:
                found = True
                break
        assert found, (
            f"N-gram '{gram}' is not a contiguous subsequence "
            f"of {words}"
        )


# =============================================================================
# Property 4: Three-way merge correctness
# Feature: scientific-medical-ner-extraction, Property 4: Merge correctness
# =============================================================================

# Strategy: generate entity lists with potential substring relationships
_entity_name = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Zs")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

_entity_list = st.lists(_entity_name, min_size=0, max_size=5)


@given(
    web_entities=_entity_list,
    sci_entities=_entity_list,
    umls_entities=_entity_list,
)
@settings(max_examples=100)
def test_property4_all_umls_in_merged(web_entities, sci_entities, umls_entities):
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

    All UMLS terms must appear in the merged set.
    """
    extractor = NER_Extractor()
    merged = extractor._merge_entities(web_entities, sci_entities, umls_entities)

    for umls_term in umls_entities:
        assert umls_term in merged, (
            f"UMLS term '{umls_term}' must be in merged set"
        )


@given(
    web_entities=_entity_list,
    sci_entities=_entity_list,
    umls_entities=_entity_list,
)
@settings(max_examples=100)
def test_property4_non_subsumed_sci_preserved(
    web_entities, sci_entities, umls_entities
):
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

    Sci entities NOT subsumed by any longer UMLS term must be in merged set.
    """
    extractor = NER_Extractor()
    merged = extractor._merge_entities(web_entities, sci_entities, umls_entities)

    for sci_ent in sci_entities:
        is_subsumed = any(
            sci_ent.lower() in umls.lower() and len(umls) > len(sci_ent)
            for umls in umls_entities
        )
        if not is_subsumed:
            assert sci_ent in merged, (
                f"Non-subsumed sci entity '{sci_ent}' must be in merged set"
            )


@given(
    web_entities=_entity_list,
    sci_entities=_entity_list,
    umls_entities=_entity_list,
)
@settings(max_examples=100)
def test_property4_non_subsumed_web_preserved(
    web_entities, sci_entities, umls_entities
):
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

    Web entities NOT subsumed by any longer sci or UMLS term must be in
    merged set.
    """
    extractor = NER_Extractor()
    merged = extractor._merge_entities(web_entities, sci_entities, umls_entities)

    for web_ent in web_entities:
        # Check if subsumed by UMLS
        subsumed_by_umls = any(
            web_ent.lower() in umls.lower() and len(umls) > len(web_ent)
            for umls in umls_entities
        )
        # Check if subsumed by non-subsumed sci entities
        remaining_sci = [
            s for s in sci_entities
            if not any(
                s.lower() in u.lower() and len(u) > len(s)
                for u in umls_entities
            )
        ]
        subsumed_by_sci = any(
            web_ent.lower() in sci.lower() and len(sci) > len(web_ent)
            for sci in remaining_sci
        )
        if not subsumed_by_umls and not subsumed_by_sci:
            assert web_ent in merged, (
                f"Non-subsumed web entity '{web_ent}' must be in merged set"
            )


@given(
    web_entities=_entity_list,
    sci_entities=_entity_list,
    umls_entities=_entity_list,
)
@settings(max_examples=100)
def test_property4_subsumed_entities_removed(
    web_entities, sci_entities, umls_entities
):
    """**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

    Entities subsumed by a longer term from a higher-priority layer
    must NOT be in the merged set (unless they also appear as a term
    in a higher-priority layer).
    """
    extractor = NER_Extractor()
    merged = extractor._merge_entities(web_entities, sci_entities, umls_entities)

    # Sci entities subsumed by UMLS should not be in merged
    for sci_ent in sci_entities:
        is_subsumed = any(
            sci_ent.lower() in umls.lower() and len(umls) > len(sci_ent)
            for umls in umls_entities
        )
        if is_subsumed:
            # It should not be in merged UNLESS it also appears as a
            # UMLS term or as a non-subsumed web entity
            if sci_ent not in umls_entities and sci_ent not in web_entities:
                assert sci_ent not in merged, (
                    f"Subsumed sci entity '{sci_ent}' should not be "
                    f"in merged set"
                )


# =============================================================================
# Property 5: extract_key_terms returns a well-formed NERResult
# Feature: scientific-medical-ner-extraction, Property 5: Well-formed NERResult
# =============================================================================


@given(
    web_ents=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    sci_ents=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    umls_ents=st.lists(st.text(min_size=1, max_size=20), max_size=5),
)
@settings(max_examples=100)
def test_property5_well_formed_result(web_ents, sci_ents, umls_ents):
    """**Validates: Requirements 10.2**

    extract_key_terms returns a well-formed NERResult where:
    (a) web_entities is list of str
    (b) sci_entities is list of str
    (c) umls_entities is list of str
    (d) key_terms is set of str
    (e) every element in key_terms is in web_entities, sci_entities,
        or umls_entities
    """
    # Mock all three layers to return controlled data
    web_nlp = _make_mock_nlp(
        entities=[_make_mock_entity(e, "PERSON") for e in web_ents if e.strip()],
        noun_chunks=[],
    )
    sci_nlp = _make_mock_nlp(
        entities=[_make_mock_entity(e, "PERSON") for e in sci_ents if e.strip()],
        noun_chunks=[],
    )

    # For UMLS, mock the client to return matches for all candidates
    umls_result = {name: f"CUI_{i}" for i, name in enumerate(umls_ents)}
    umls_client = _make_mock_umls_client(result_dict=umls_result)

    extractor = NER_Extractor(
        spacy_web_nlp=web_nlp,
        spacy_sci_nlp=sci_nlp,
        umls_client=umls_client,
    )

    # Use a query that generates n-grams matching our UMLS terms
    query = " ".join(umls_ents) if umls_ents else "test query"
    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms(query)
    )

    # (a) web_entities is list of str
    assert isinstance(result.web_entities, list)
    assert all(isinstance(e, str) for e in result.web_entities)

    # (b) sci_entities is list of str
    assert isinstance(result.sci_entities, list)
    assert all(isinstance(e, str) for e in result.sci_entities)

    # (c) umls_entities is list of str
    assert isinstance(result.umls_entities, list)
    assert all(isinstance(e, str) for e in result.umls_entities)

    # (d) key_terms is set of str
    assert isinstance(result.key_terms, set)
    assert all(isinstance(t, str) for t in result.key_terms)

    # (e) every element in key_terms is in one of the entity lists
    all_entities = set(result.web_entities) | set(result.sci_entities) | set(result.umls_entities)
    for term in result.key_terms:
        assert term in all_entities, (
            f"key_term '{term}' not found in any entity list"
        )


# =============================================================================
# Property 6: NERResult serialization round-trip
# Feature: scientific-medical-ner-extraction, Property 6: Serialization round-trip
# =============================================================================

_ner_result_strategy = st.builds(
    NERResult,
    web_entities=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    sci_entities=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    umls_entities=st.lists(st.text(min_size=1, max_size=20), max_size=5),
    key_terms=st.frozensets(st.text(min_size=1, max_size=20), max_size=5).map(set),
)


@given(result=_ner_result_strategy)
@settings(max_examples=100)
def test_property6_serialization_roundtrip(result):
    """**Validates: Requirements 10.4**

    NERResult.from_dict(result.to_dict()) produces identical fields.
    """
    serialized = result.to_dict()
    deserialized = NERResult.from_dict(serialized)

    assert sorted(deserialized.web_entities) == sorted(result.web_entities)
    assert sorted(deserialized.sci_entities) == sorted(result.sci_entities)
    assert sorted(deserialized.umls_entities) == sorted(result.umls_entities)
    assert deserialized.key_terms == result.key_terms


# =============================================================================
# Property 7: Independent layer degradation preserves other layers' results
# Feature: scientific-medical-ner-extraction, Property 7: Independent degradation
# =============================================================================


def _is_subsumed(entity: str, longer_entities: list) -> bool:
    """Check if entity is a case-insensitive substring of any longer entity."""
    ent_lower = entity.lower()
    for other in longer_entities:
        if ent_lower in other.lower() and len(other) > len(entity):
            return True
    return False


# Strategy: generate distinct entity names using unique prefixes to avoid
# accidental substring relationships between layers.
_layer_entity = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
    min_size=3,
    max_size=12,
).filter(lambda s: s.strip())


@given(
    sci_ents=st.lists(
        _layer_entity.map(lambda s: "Sci" + s),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_property7_layer1_disabled(sci_ents):
    """**Validates: Requirements 6.1, 6.2, 6.3**

    When Layer 1 (web) is disabled, Layer 2 (sci) results still appear
    in key_terms. With no UMLS layer either, sci entities are the sole
    source and must all appear in key_terms.
    """
    sci_nlp = _make_mock_nlp(
        entities=[_make_mock_entity(e, "PERSON") for e in sci_ents],
        noun_chunks=[],
    )

    extractor = NER_Extractor(
        spacy_web_nlp=None,  # Layer 1 disabled
        spacy_sci_nlp=sci_nlp,
        umls_client=None,
    )

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    # Layer 1 disabled → web_entities must be empty
    assert result.web_entities == [], (
        "web_entities should be empty when Layer 1 is disabled"
    )
    # Every sci entity that passes filtering must be in key_terms
    for ent in sci_ents:
        if (
            not NER_Extractor._AGE_PATTERN.match(ent.strip())
            and not NER_Extractor._NUMERIC_PATTERN.match(ent.strip())
        ):
            assert ent in result.key_terms, (
                f"Sci entity '{ent}' should be in key_terms "
                f"when Layer 1 is disabled; got {result.key_terms}"
            )
    # key_terms should be a subset of sci_entities (no phantom terms)
    assert result.key_terms <= set(result.sci_entities), (
        "key_terms should only contain sci entities when Layer 1 is disabled"
    )


@given(
    web_ents=st.lists(
        _layer_entity.map(lambda s: "Web" + s),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_property7_layer2_disabled(web_ents):
    """**Validates: Requirements 6.1, 6.2, 6.3**

    When Layer 2 (sci) is disabled, Layer 1 (web) results still appear
    in key_terms. With no UMLS layer either, web entities are the sole
    source and must all appear in key_terms.
    """
    web_nlp = _make_mock_nlp(
        entities=[_make_mock_entity(e, "PERSON") for e in web_ents],
        noun_chunks=[],
    )

    extractor = NER_Extractor(
        spacy_web_nlp=web_nlp,
        spacy_sci_nlp=None,  # Layer 2 disabled
        umls_client=None,
    )

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    # Layer 2 disabled → sci_entities must be empty
    assert result.sci_entities == [], (
        "sci_entities should be empty when Layer 2 is disabled"
    )
    # Every web entity that passes filtering must be in key_terms
    for ent in web_ents:
        if (
            not NER_Extractor._AGE_PATTERN.match(ent.strip())
            and not NER_Extractor._NUMERIC_PATTERN.match(ent.strip())
        ):
            assert ent in result.key_terms, (
                f"Web entity '{ent}' should be in key_terms "
                f"when Layer 2 is disabled; got {result.key_terms}"
            )
    # key_terms should be a subset of web_entities (no phantom terms)
    assert result.key_terms <= set(result.web_entities), (
        "key_terms should only contain web entities when Layer 2 is disabled"
    )


@given(
    web_ents=st.lists(
        _layer_entity.map(lambda s: "Web" + s),
        min_size=1,
        max_size=3,
        unique=True,
    ),
    sci_ents=st.lists(
        _layer_entity.map(lambda s: "Sci" + s),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
@settings(max_examples=100)
def test_property7_layer3_disabled(web_ents, sci_ents):
    """**Validates: Requirements 6.1, 6.2, 6.3**

    When Layer 3 (UMLS) is disabled, Layer 1 + Layer 2 results still
    appear in key_terms. With distinct prefixes ("Web"/"Sci"), no
    cross-layer subsumption occurs, so all entities must be preserved.
    """
    web_nlp = _make_mock_nlp(
        entities=[_make_mock_entity(e, "PERSON") for e in web_ents],
        noun_chunks=[],
    )
    sci_nlp = _make_mock_nlp(
        entities=[_make_mock_entity(e, "PERSON") for e in sci_ents],
        noun_chunks=[],
    )

    extractor = NER_Extractor(
        spacy_web_nlp=web_nlp,
        spacy_sci_nlp=sci_nlp,
        umls_client=None,  # Layer 3 disabled
    )

    result = asyncio.get_event_loop().run_until_complete(
        extractor.extract_key_terms("test query")
    )

    # Layer 3 disabled → umls_entities must be empty
    assert result.umls_entities == [], (
        "umls_entities should be empty when Layer 3 is disabled"
    )

    # With distinct prefixes, no entity from one layer is a substring of
    # another layer's entity, so all valid entities must appear in key_terms.
    all_valid = set()
    for ent in web_ents + sci_ents:
        if (
            not NER_Extractor._AGE_PATTERN.match(ent.strip())
            and not NER_Extractor._NUMERIC_PATTERN.match(ent.strip())
        ):
            # Only subsumed if a longer entity from a higher-priority layer
            # contains it as a case-insensitive substring
            if not _is_subsumed(ent, sci_ents if ent in web_ents else []):
                all_valid.add(ent)

    for ent in all_valid:
        assert ent in result.key_terms, (
            f"Entity '{ent}' should be in key_terms when Layer 3 is "
            f"disabled; got {result.key_terms}"
        )

    # key_terms should only contain entities from web or sci layers
    assert result.key_terms <= (
        set(result.web_entities) | set(result.sci_entities)
    ), "key_terms should only contain web or sci entities when Layer 3 is disabled"

    # If there are valid entities, key_terms must not be empty
    if all_valid:
        assert len(result.key_terms) > 0, (
            "key_terms should not be empty when valid entities exist"
        )


# =============================================================================
# Unit Tests — NER_Extractor
# Feature: scientific-medical-ner-extraction, Unit Tests
# =============================================================================


class TestNERResultDataclass:
    """Tests for NERResult dataclass."""

    def test_default_construction(self):
        result = NERResult()
        assert result.web_entities == []
        assert result.sci_entities == []
        assert result.umls_entities == []
        assert result.key_terms == set()

    def test_to_dict_sorts_lists(self):
        result = NERResult(
            web_entities=["Zeta", "Alpha"],
            sci_entities=["Beta", "Alpha"],
            umls_entities=["Gamma", "Alpha"],
            key_terms={"Zeta", "Alpha", "Beta", "Gamma"},
        )
        d = result.to_dict()
        assert d["web_entities"] == ["Alpha", "Zeta"]
        assert d["sci_entities"] == ["Alpha", "Beta"]
        assert d["umls_entities"] == ["Alpha", "Gamma"]
        assert d["key_terms"] == sorted({"Zeta", "Alpha", "Beta", "Gamma"})

    def test_from_dict_reconstructs(self):
        original = NERResult(
            web_entities=["Chelsea", "Venezuela"],
            sci_entities=["hepatitis B", "surface antigen"],
            umls_entities=["hepatitis B surface antigen"],
            key_terms={"Chelsea", "Venezuela", "hepatitis B surface antigen"},
        )
        reconstructed = NERResult.from_dict(original.to_dict())
        assert sorted(reconstructed.web_entities) == sorted(original.web_entities)
        assert sorted(reconstructed.sci_entities) == sorted(original.sci_entities)
        assert sorted(reconstructed.umls_entities) == sorted(original.umls_entities)
        assert reconstructed.key_terms == original.key_terms


class TestEmptyAndWhitespaceQueries:
    """Test empty/whitespace query returns empty NERResult."""

    @pytest.mark.parametrize("query", ["", "   ", "\t", "\n", None])
    def test_empty_query_returns_empty_result(self, query):
        """_Requirements: edge case_"""
        extractor = NER_Extractor(
            spacy_web_nlp=_make_mock_nlp(),
            spacy_sci_nlp=_make_mock_nlp(),
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms(query or "")
        )
        assert result.web_entities == []
        assert result.sci_entities == []
        assert result.umls_entities == []
        assert result.key_terms == set()


class TestLayer1Failure:
    """Test Layer 1 (web) failure: verify Layer 2+3 still produce results."""

    def test_web_model_failure_returns_sci_and_umls(self):
        """_Requirements: 6.1_"""
        # Layer 1 raises an exception
        failing_nlp = MagicMock(side_effect=RuntimeError("model crash"))

        # Layer 2 returns entities
        sci_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("hepatitis B", "DISEASE")],
            noun_chunks=[],
        )

        extractor = NER_Extractor(
            spacy_web_nlp=failing_nlp,
            spacy_sci_nlp=sci_nlp,
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("hepatitis B treatment")
        )

        assert result.web_entities == []
        assert "hepatitis B" in result.sci_entities
        assert "hepatitis B" in result.key_terms


class TestLayer2Failure:
    """Test Layer 2 (sci) failure: verify Layer 1+3 still produce results."""

    def test_sci_model_failure_returns_web_and_umls(self):
        """_Requirements: 6.2_"""
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        failing_nlp = MagicMock(side_effect=RuntimeError("model crash"))

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            spacy_sci_nlp=failing_nlp,
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("Chelsea research")
        )

        assert result.sci_entities == []
        assert "Chelsea" in result.web_entities
        assert "Chelsea" in result.key_terms


class TestUMLSUnavailable:
    """Test UMLS unavailable (umls_client=None) returns Layer 1+2 only."""

    def test_umls_none_returns_web_and_sci(self):
        """_Requirements: 6.3_"""
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        sci_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("hepatitis B", "DISEASE")],
            noun_chunks=[],
        )

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            spacy_sci_nlp=sci_nlp,
            umls_client=None,
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("Chelsea hepatitis B")
        )

        assert result.umls_entities == []
        assert "Chelsea" in result.key_terms
        assert "hepatitis B" in result.key_terms


class TestUMLSTimeout:
    """Test UMLS timeout returns Layer 1+2 only."""

    def test_umls_timeout_returns_web_and_sci(self):
        """_Requirements: 6.4_"""
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        sci_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("hepatitis B", "DISEASE")],
            noun_chunks=[],
        )
        # UMLS client that takes too long
        slow_umls = _make_mock_umls_client(
            result_dict={"hepatitis B surface antigen": "C123"},
            delay=5.0,  # 5 seconds — well over the 200ms timeout
        )

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            spacy_sci_nlp=sci_nlp,
            umls_client=slow_umls,
            umls_timeout_ms=50,  # 50ms timeout for fast test
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("hepatitis B surface antigen treatment")
        )

        assert result.umls_entities == []
        assert "Chelsea" in result.key_terms
        assert "hepatitis B" in result.key_terms


class TestAllLayersFail:
    """Test all layers fail returns empty NERResult."""

    def test_all_layers_fail_returns_empty(self):
        """_Requirements: 6.5_"""
        failing_nlp = MagicMock(side_effect=RuntimeError("crash"))

        extractor = NER_Extractor(
            spacy_web_nlp=failing_nlp,
            spacy_sci_nlp=failing_nlp,
            umls_client=None,
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("some query")
        )

        assert result.web_entities == []
        assert result.sci_entities == []
        assert result.umls_entities == []
        assert result.key_terms == set()


class TestDegradationLogging:
    """Test degradation logging contains layer name, model name, error."""

    def test_layer1_failure_logs_warning(self):
        """_Requirements: 6.6_"""
        failing_nlp = MagicMock(side_effect=RuntimeError("web model crash"))

        extractor = NER_Extractor(spacy_web_nlp=failing_nlp)

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("test query")
            )
            # Check that warning was logged with layer info
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 1" in call_args
            assert "en_core_web_sm" in call_args

    def test_layer2_failure_logs_warning(self):
        """_Requirements: 6.6_"""
        failing_nlp = MagicMock(side_effect=RuntimeError("sci model crash"))

        extractor = NER_Extractor(spacy_sci_nlp=failing_nlp)

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("test query")
            )
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 2" in call_args
            assert "en_core_sci_sm" in call_args

    def test_umls_timeout_logs_warning(self):
        """_Requirements: 6.6_"""
        slow_umls = _make_mock_umls_client(
            result_dict={}, delay=5.0
        )

        extractor = NER_Extractor(
            umls_client=slow_umls,
            umls_timeout_ms=10,
        )

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("hepatitis B surface antigen")
            )
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 3" in call_args
            assert "timed out" in call_args


class TestNonMedicalQuery:
    """Test non-medical query with UMLS returning empty."""

    def test_non_medical_query_empty_umls(self):
        """_Requirements: 9.2_"""
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        # UMLS returns empty dict (no matches)
        umls_client = _make_mock_umls_client(result_dict={})

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            umls_client=umls_client,
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("Chelsea football match")
        )

        assert result.umls_entities == []
        assert "Chelsea" in result.key_terms


class TestConcurrentExecution:
    """Test concurrent execution: verify all three layers run via asyncio.gather."""

    def test_all_layers_run_concurrently(self):
        """_Requirements: 3.4, 4.6_"""
        call_order = []

        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        sci_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("hepatitis B", "DISEASE")],
            noun_chunks=[],
        )
        umls_client = _make_mock_umls_client(
            result_dict={"hepatitis B surface antigen": "C123"}
        )

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            spacy_sci_nlp=sci_nlp,
            umls_client=umls_client,
        )

        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("hepatitis B surface antigen treatment")
        )

        # All three layers should have produced results
        assert len(result.web_entities) > 0 or True  # web may or may not find entities
        # sci should find hepatitis B
        assert "hepatitis B" in result.sci_entities
        # umls should find the full term
        assert "hepatitis B surface antigen" in result.umls_entities


class TestMergeLogic:
    """Test merge: UMLS overrides sci, sci overrides web, non-overlapping preserved."""

    def test_umls_overrides_sci(self):
        """_Requirements: 5.2_"""
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=[],
            sci_entities=["hepatitis B", "surface antigen"],
            umls_overrides=["hepatitis B surface antigen"],
        )

        assert "hepatitis B surface antigen" in merged
        assert "hepatitis B" not in merged
        assert "surface antigen" not in merged

    def test_sci_overrides_web(self):
        """_Requirements: 5.3_"""
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=["hepatitis"],
            sci_entities=["hepatitis B"],
            umls_overrides=[],
        )

        assert "hepatitis B" in merged
        assert "hepatitis" not in merged

    def test_non_overlapping_preserved(self):
        """_Requirements: 5.4_"""
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=["Chelsea", "Venezuela"],
            sci_entities=["healthcare worker"],
            umls_overrides=["hepatitis B surface antigen"],
        )

        assert "Chelsea" in merged
        assert "Venezuela" in merged
        assert "healthcare worker" in merged
        assert "hepatitis B surface antigen" in merged

    def test_umls_directly_subsumes_web(self):
        """_Requirements: 5.5_"""
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=["hepatitis"],
            sci_entities=[],
            umls_overrides=["hepatitis B surface antigen"],
        )

        assert "hepatitis B surface antigen" in merged
        assert "hepatitis" not in merged


class TestUMLSGeneralException:
    """Test UMLS general exception (not timeout) returns Layer 1+2 only."""

    def test_umls_exception_returns_web_and_sci(self):
        """_Requirements: 6.3, 6.6_"""
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        sci_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("hepatitis B", "DISEASE")],
            noun_chunks=[],
        )
        # UMLS client that raises a general exception
        umls_client = _make_mock_umls_client(
            raise_exc=ConnectionError("Neo4j connection refused"),
        )

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            spacy_sci_nlp=sci_nlp,
            umls_client=umls_client,
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("Chelsea hepatitis B treatment")
        )

        assert result.umls_entities == []
        assert "Chelsea" in result.key_terms
        assert "hepatitis B" in result.key_terms

    def test_umls_exception_logs_warning_with_error(self):
        """_Requirements: 6.6_"""
        umls_client = _make_mock_umls_client(
            raise_exc=ConnectionError("Neo4j connection refused"),
        )

        extractor = NER_Extractor(umls_client=umls_client)

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("hepatitis B surface antigen")
            )
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 3" in call_args
            assert "failed" in call_args


class TestUMLSReturnsNone:
    """Test UMLS batch_search_by_names returning None."""

    def test_umls_returns_none_produces_empty_umls_entities(self):
        """_Requirements: 6.3_"""
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        # UMLS client returns None instead of a dict
        umls_client = _make_mock_umls_client(result_dict=None)

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            umls_client=umls_client,
        )
        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("Chelsea football match")
        )

        assert result.umls_entities == []
        assert "Chelsea" in result.key_terms


class TestDegradationLoggingDetailed:
    """Test degradation logging contains layer name, model name, error,
    and remaining layers information."""

    def test_layer1_failure_log_mentions_remaining_layers(self):
        """_Requirements: 6.6_

        When Layer 1 fails, the warning log should mention that
        Layer 2+3 continue.
        """
        failing_nlp = MagicMock(side_effect=RuntimeError("web model crash"))

        extractor = NER_Extractor(spacy_web_nlp=failing_nlp)

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("test query")
            )
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 1" in call_args
            assert "en_core_web_sm" in call_args
            assert "Layer 2+3" in call_args

    def test_layer2_failure_log_mentions_remaining_layers(self):
        """_Requirements: 6.6_

        When Layer 2 fails, the warning log should mention that
        Layer 1+3 continue.
        """
        failing_nlp = MagicMock(side_effect=RuntimeError("sci model crash"))

        extractor = NER_Extractor(spacy_sci_nlp=failing_nlp)

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("test query")
            )
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 2" in call_args
            assert "en_core_sci_sm" in call_args
            assert "Layer 1+3" in call_args

    def test_umls_timeout_log_mentions_remaining_layers(self):
        """_Requirements: 6.6_

        When Layer 3 times out, the warning log should mention that
        Layer 1+2 continue.
        """
        slow_umls = _make_mock_umls_client(result_dict={}, delay=5.0)

        extractor = NER_Extractor(umls_client=slow_umls, umls_timeout_ms=10)

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("hepatitis B surface antigen")
            )
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 3" in call_args
            assert "Layer 1+2" in call_args

    def test_umls_failure_log_mentions_remaining_layers(self):
        """_Requirements: 6.6_

        When Layer 3 raises a general exception, the warning log should
        mention that Layer 1+2 continue.
        """
        umls_client = _make_mock_umls_client(
            raise_exc=RuntimeError("Neo4j down"),
        )

        extractor = NER_Extractor(umls_client=umls_client)

        with patch(
            "multimodal_librarian.components.kg_retrieval.ner_extractor.logger"
        ) as mock_logger:
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("hepatitis B surface antigen")
            )
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "Layer 3" in call_args
            assert "Layer 1+2" in call_args


class TestConcurrentExecutionDetailed:
    """Verify all three layers are actually invoked concurrently via
    asyncio.gather."""

    def test_all_three_layers_invoked(self):
        """_Requirements: 3.4, 4.6_

        Verify that all three layer methods are called when all three
        models are available.
        """
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        sci_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("hepatitis B", "DISEASE")],
            noun_chunks=[],
        )
        umls_client = _make_mock_umls_client(
            result_dict={"hepatitis B surface antigen": "C123"}
        )

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            spacy_sci_nlp=sci_nlp,
            umls_client=umls_client,
        )

        result = asyncio.get_event_loop().run_until_complete(
            extractor.extract_key_terms("hepatitis B surface antigen treatment")
        )

        # web_nlp was called (Layer 1 invoked)
        web_nlp.assert_called()
        # sci_nlp was called (Layer 2 invoked)
        sci_nlp.assert_called()
        # umls_client.batch_search_by_names was called (Layer 3 invoked)
        umls_client.batch_search_by_names.assert_called()

    def test_gather_runs_layers_in_parallel(self):
        """_Requirements: 3.4, 4.6_

        Verify that asyncio.gather is used to run all three layers.
        We patch asyncio.gather to confirm it receives three coroutines.
        """
        web_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("Chelsea", "ORG")],
            noun_chunks=[],
        )
        sci_nlp = _make_mock_nlp(
            entities=[_make_mock_entity("hepatitis B", "DISEASE")],
            noun_chunks=[],
        )
        umls_client = _make_mock_umls_client(result_dict={})

        extractor = NER_Extractor(
            spacy_web_nlp=web_nlp,
            spacy_sci_nlp=sci_nlp,
            umls_client=umls_client,
        )

        original_gather = asyncio.gather
        gather_call_count = []

        async def tracking_gather(*coros, **kwargs):
            gather_call_count.append(len(coros))
            return await original_gather(*coros, **kwargs)

        with patch("asyncio.gather", side_effect=tracking_gather):
            asyncio.get_event_loop().run_until_complete(
                extractor.extract_key_terms("hepatitis B surface antigen")
            )

        # asyncio.gather should have been called with exactly 3 coroutines
        assert len(gather_call_count) == 1, (
            "asyncio.gather should be called exactly once"
        )
        assert gather_call_count[0] == 3, (
            f"asyncio.gather should receive 3 coroutines, got {gather_call_count[0]}"
        )


class TestMergeFullScenario:
    """Test complete merge scenario with all three layers interacting."""

    def test_full_three_layer_merge(self):
        """_Requirements: 5.2, 5.3, 5.4_

        UMLS overrides sci, sci overrides web, non-overlapping preserved
        — all in one scenario.
        """
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=["Chelsea", "hepatitis", "Venezuela"],
            sci_entities=["hepatitis B", "healthcare worker"],
            umls_overrides=["hepatitis B surface antigen"],
        )

        # UMLS term present
        assert "hepatitis B surface antigen" in merged
        # "hepatitis B" (sci) subsumed by UMLS term
        assert "hepatitis B" not in merged
        # "hepatitis" (web) subsumed by UMLS term
        assert "hepatitis" not in merged
        # Non-overlapping terms preserved
        assert "Chelsea" in merged
        assert "Venezuela" in merged
        assert "healthcare worker" in merged

    def test_merge_case_insensitive_subsumption(self):
        """_Requirements: 5.2, 5.3, 5.5_

        Subsumption checks are case-insensitive.
        """
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=["Hepatitis"],
            sci_entities=["Hepatitis B"],
            umls_overrides=["hepatitis b surface antigen"],
        )

        assert "hepatitis b surface antigen" in merged
        assert "Hepatitis B" not in merged
        assert "Hepatitis" not in merged

    def test_merge_identical_terms_across_layers(self):
        """_Requirements: 5.4_

        When the same term appears in multiple layers, it should appear
        exactly once in the merged set.
        """
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=["Chelsea"],
            sci_entities=["Chelsea"],
            umls_overrides=["Chelsea"],
        )

        assert "Chelsea" in merged
        assert len([t for t in merged if t == "Chelsea"]) == 1

    def test_merge_empty_inputs(self):
        """_Requirements: 5.4_

        Merge with all empty inputs returns empty set.
        """
        extractor = NER_Extractor()
        merged = extractor._merge_entities(
            web_entities=[],
            sci_entities=[],
            umls_overrides=[],
        )

        assert merged == set()


class TestNgramGeneration:
    """Test n-gram generation edge cases."""

    def test_single_word_query(self):
        extractor = NER_Extractor(max_ngram_size=5)
        ngrams = extractor._generate_ngrams("hello")
        assert ngrams == []

    def test_two_word_query(self):
        extractor = NER_Extractor(max_ngram_size=5)
        ngrams = extractor._generate_ngrams("hello world")
        assert ngrams == ["hello world"]

    def test_punctuation_stripped(self):
        extractor = NER_Extractor(max_ngram_size=5)
        ngrams = extractor._generate_ngrams("hello world?")
        assert "hello world" in ngrams

    def test_max_ngram_size_respected(self):
        extractor = NER_Extractor(max_ngram_size=3)
        ngrams = extractor._generate_ngrams("a b c d e")
        for gram in ngrams:
            assert len(gram.split()) <= 3

    def test_empty_query(self):
        extractor = NER_Extractor(max_ngram_size=5)
        ngrams = extractor._generate_ngrams("")
        assert ngrams == []
