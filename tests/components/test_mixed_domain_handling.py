"""
Unit tests for mixed-domain document handling (Tasks 9.1-9.4).

Tests cover:
- _split_into_sections with markdown headings
- _split_into_sections with chapter markers
- _split_into_sections with no markers (returns single section)
- classify_sections with mixed-domain content
- classify_sections with short section inheritance
- Per-section chunking in chunk_with_smart_bridges
"""

import pytest

from src.multimodal_librarian.components.chunking_framework.content_analyzer import (
    AutomatedContentAnalyzer,
)
from src.multimodal_librarian.components.chunking_framework.framework import (
    GenericMultiLevelChunkingFramework,
    SectionClassification,
)
from src.multimodal_librarian.models.chunking import ChunkingRequirements
from src.multimodal_librarian.models.core import ContentType, DocumentContent


class TestSplitIntoSections:
    """Tests for _split_into_sections method."""

    def setup_method(self):
        self.analyzer = AutomatedContentAnalyzer()

    def test_split_markdown_headings(self):
        """Sections split at markdown heading boundaries."""
        text = (
            "Introduction paragraph here.\n"
            "## First Section\n"
            "Content of first section.\n"
            "## Second Section\n"
            "Content of second section."
        )
        sections = self.analyzer._split_into_sections(text)
        assert len(sections) >= 2
        # Each section after the first should start with a heading
        heading_sections = [s for s in sections if s.startswith("##")]
        assert len(heading_sections) >= 2

    def test_split_chapter_markers(self):
        """Sections split at chapter markers."""
        text = (
            "Preface content here.\n"
            "Chapter 1\n"
            "Content of chapter one with enough text.\n"
            "Chapter 2\n"
            "Content of chapter two with enough text."
        )
        sections = self.analyzer._split_into_sections(text)
        assert len(sections) >= 2
        chapter_sections = [s for s in sections if "Chapter" in s]
        assert len(chapter_sections) >= 2

    def test_split_section_markers(self):
        """Sections split at Section markers."""
        text = (
            "Overview content.\n"
            "Section 1\n"
            "First section content.\n"
            "Section 2\n"
            "Second section content."
        )
        sections = self.analyzer._split_into_sections(text)
        assert len(sections) >= 2

    def test_no_markers_returns_single_section(self):
        """Text without structural markers returns as single section."""
        text = "This is a plain paragraph with no headings or chapters."
        sections = self.analyzer._split_into_sections(text)
        assert len(sections) == 1
        assert sections[0] == text

    def test_empty_text(self):
        """Empty text returns empty list."""
        sections = self.analyzer._split_into_sections("")
        assert sections == []

    def test_whitespace_only(self):
        """Whitespace-only text returns empty list."""
        sections = self.analyzer._split_into_sections("   \n\n  ")
        assert sections == []

    def test_multiple_heading_levels(self):
        """Splits on h1, h2, and h3 headings."""
        text = (
            "Intro.\n"
            "# Top Level\n"
            "Top content.\n"
            "## Sub Level\n"
            "Sub content.\n"
            "### Sub Sub Level\n"
            "Deep content."
        )
        sections = self.analyzer._split_into_sections(text)
        assert len(sections) >= 3


class TestClassifySections:
    """Tests for classify_sections method."""

    def setup_method(self):
        self.analyzer = AutomatedContentAnalyzer()

    def test_single_section_document(self):
        """Document with no structural markers returns one classification."""
        doc = DocumentContent(
            text="A simple document with no sections.",
            images=[], tables=[], metadata={}, structure=None
        )
        results = self.analyzer.classify_sections(doc)
        assert len(results) == 1
        section_text, content_type, reqs = results[0]
        assert isinstance(content_type, ContentType)
        assert isinstance(reqs, ChunkingRequirements)

    def test_short_section_inherits_classification(self):
        """Sections shorter than 100 tokens inherit previous classification."""
        # Build a document with a long section followed by a short one
        long_section = " ".join(["word"] * 150)
        short_section = "Brief note."
        text = f"{long_section}\n## Short Part\n{short_section}"
        doc = DocumentContent(
            text=text, images=[], tables=[], metadata={}, structure=None
        )
        results = self.analyzer.classify_sections(doc)
        assert len(results) >= 2
        # The short section should inherit the previous classification
        if len(results) >= 2:
            _, prev_type, _ = results[0]
            _, short_type, _ = results[1]
            assert short_type == prev_type

    def test_classify_returns_tuples(self):
        """Each result is a (text, ContentType, ChunkingRequirements) tuple."""
        text = (
            "First section content.\n"
            "## Second Section\n"
            "Second section content."
        )
        doc = DocumentContent(
            text=text, images=[], tables=[], metadata={}, structure=None
        )
        results = self.analyzer.classify_sections(doc)
        for section_text, content_type, reqs in results:
            assert isinstance(section_text, str)
            assert isinstance(content_type, ContentType)
            assert isinstance(reqs, ChunkingRequirements)

    def test_first_short_section_defaults_to_general(self):
        """If the first section is short, it defaults to GENERAL."""
        text = "Short.\n## Long Section\n" + " ".join(["word"] * 150)
        doc = DocumentContent(
            text=text, images=[], tables=[], metadata={}, structure=None
        )
        results = self.analyzer.classify_sections(doc)
        _, first_type, _ = results[0]
        assert first_type == ContentType.GENERAL


class TestSectionClassificationDataclass:
    """Tests for SectionClassification dataclass."""

    def test_creation(self):
        """SectionClassification can be created with all fields."""
        sc = SectionClassification(
            section_text="Test section",
            content_type=ContentType.TECHNICAL,
            chunking_requirements=ChunkingRequirements(),
            start_offset=0,
            end_offset=100,
        )
        assert sc.section_text == "Test section"
        assert sc.content_type == ContentType.TECHNICAL
        assert sc.start_offset == 0
        assert sc.end_offset == 100


class TestPerSectionChunking:
    """Tests for per-section chunking in chunk_with_smart_bridges."""

    def setup_method(self):
        self.framework = GenericMultiLevelChunkingFramework()

    def test_single_section_uses_existing_behavior(self):
        """Single-section document uses document-level profile."""
        doc = DocumentContent(
            text="A simple document without any section markers at all.",
            images=[], tables=[], metadata={}, structure=None
        )
        profile = self.framework.generate_content_profile(doc)
        domain_config = self.framework.get_or_create_domain_config(profile)
        result = self.framework.chunk_with_smart_bridges(
            doc, profile, domain_config, document_id="test-single"
        )
        assert len(result.chunks) >= 1

    def test_multi_section_produces_chunks(self):
        """Multi-section document produces chunks from each section."""
        # Build a document with two distinct sections, each long enough
        section1 = " ".join(["algorithm"] * 200)
        section2 = " ".join(["patient"] * 200)
        text = f"{section1}\n## Medical Section\n{section2}"
        doc = DocumentContent(
            text=text, images=[], tables=[], metadata={}, structure=None
        )
        profile = self.framework.generate_content_profile(doc)
        domain_config = self.framework.get_or_create_domain_config(profile)
        result = self.framework.chunk_with_smart_bridges(
            doc, profile, domain_config, document_id="test-multi"
        )
        assert len(result.chunks) >= 2

    def test_backward_compatible_with_document_id(self):
        """Per-section chunking works with and without document_id."""
        doc = DocumentContent(
            text="Simple text for backward compatibility test.",
            images=[], tables=[], metadata={}, structure=None
        )
        profile = self.framework.generate_content_profile(doc)
        domain_config = self.framework.get_or_create_domain_config(profile)
        # Without document_id
        result1 = self.framework.chunk_with_smart_bridges(
            doc, profile, domain_config
        )
        # With document_id
        result2 = self.framework.chunk_with_smart_bridges(
            doc, profile, domain_config, document_id="test-compat"
        )
        assert len(result1.chunks) >= 1
        assert len(result2.chunks) >= 1
