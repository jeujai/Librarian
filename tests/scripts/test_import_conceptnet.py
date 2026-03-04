"""Unit tests for ConceptNet import script."""

import json
import os
import sys

import pytest

# Add scripts dir to path so we can import directly
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
)

from import_conceptnet import ConceptNetImporter, ImportStats


class TestParseConceptnetUri:
    """Tests for parse_conceptnet_uri."""

    def test_basic_underscore(self) -> None:
        result = ConceptNetImporter.parse_conceptnet_uri(
            "/c/en/machine_learning"
        )
        assert result == "machine learning"

    def test_basic_hyphen(self) -> None:
        result = ConceptNetImporter.parse_conceptnet_uri(
            "/c/en/New-York"
        )
        assert result == "new york"

    def test_with_pos_tag(self) -> None:
        result = ConceptNetImporter.parse_conceptnet_uri(
            "/c/en/machine_learning/n"
        )
        assert result == "machine learning"

    def test_simple_word(self) -> None:
        result = ConceptNetImporter.parse_conceptnet_uri(
            "/c/en/dog"
        )
        assert result == "dog"

    def test_uppercase_normalized(self) -> None:
        result = ConceptNetImporter.parse_conceptnet_uri(
            "/c/en/Python"
        )
        assert result == "python"


class TestParseRelationUri:
    """Tests for parse_relation_uri."""

    def test_isa(self) -> None:
        result = ConceptNetImporter.parse_relation_uri("/r/IsA")
        assert result == "IsA"

    def test_part_of(self) -> None:
        result = ConceptNetImporter.parse_relation_uri("/r/PartOf")
        assert result == "PartOf"

    def test_non_relation_uri(self) -> None:
        result = ConceptNetImporter.parse_relation_uri("SomeRel")
        assert result == "SomeRel"


class TestParseAssertionLine:
    """Tests for parse_assertion_line."""

    def setup_method(self) -> None:
        self.importer = ConceptNetImporter(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        )

    def test_valid_english_line(self) -> None:
        meta = json.dumps({"weight": 2.5})
        line = [
            "/a/[/r/IsA/,/c/en/dog/,/c/en/animal/]",
            "/r/IsA",
            "/c/en/dog",
            "/c/en/animal",
            meta,
        ]
        result = self.importer.parse_assertion_line(line)
        assert result is not None
        assert result["concept1_name"] == "dog"
        assert result["concept2_name"] == "animal"
        assert result["relation"] == "IsA"
        assert result["weight"] == 2.5

    def test_non_english_filtered(self) -> None:
        meta = json.dumps({"weight": 1.0})
        line = [
            "/a/[/r/IsA/,/c/fr/chien/,/c/fr/animal/]",
            "/r/IsA",
            "/c/fr/chien",
            "/c/fr/animal",
            meta,
        ]
        result = self.importer.parse_assertion_line(line)
        assert result is None

    def test_short_line_returns_none(self) -> None:
        result = self.importer.parse_assertion_line(
            ["too", "short"]
        )
        assert result is None

    def test_mixed_language_filtered(self) -> None:
        meta = json.dumps({"weight": 1.0})
        line = [
            "/a/test",
            "/r/IsA",
            "/c/en/dog",
            "/c/fr/animal",
            meta,
        ]
        result = self.importer.parse_assertion_line(line)
        assert result is None


class TestImportStats:
    """Tests for ImportStats dataclass."""

    def test_defaults(self) -> None:
        stats = ImportStats()
        assert stats.concepts_imported == 0
        assert stats.relationships_imported == 0
        assert stats.duplicates_skipped == 0
        assert stats.errors == 0
        assert stats.duration_seconds == 0.0
