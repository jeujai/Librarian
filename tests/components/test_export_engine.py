"""
Tests for the export engine component.

This module contains tests for the multi-format export functionality,
ensuring proper export to various formats with multimedia content preservation.
"""

import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import Mock, patch
import io

from src.multimodal_librarian.components.export_engine import ExportEngine
from src.multimodal_librarian.models.core import (
    MultimediaResponse, Visualization, AudioFile, VideoFile, 
    KnowledgeCitation, SourceType, ExportMetadata
)


class TestExportEngine:
    """Test cases for the ExportEngine class."""
    
    @pytest.fixture
    def export_engine(self):
        """Create an ExportEngine instance for testing."""
        return ExportEngine()
    
    @pytest.fixture
    def sample_response(self):
        """Create a sample MultimediaResponse for testing."""
        # Create sample visualization
        viz_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
        visualization = Visualization(
            viz_id="viz_1",
            viz_type="chart",
            content_data=viz_data,
            caption="Sample Chart",
            alt_text="A sample chart for testing"
        )
        
        # Create sample audio
        audio = AudioFile(
            audio_id="audio_1",
            content_data=b"fake_audio_data",
            duration_seconds=30.5,
            format="mp3"
        )
        
        # Create sample video
        video = VideoFile(
            video_id="video_1",
            content_data=b"fake_video_data",
            duration_seconds=120.0,
            format="mp4",
            resolution="1920x1080"
        )
        
        # Create sample citations
        citation = KnowledgeCitation(
            source_type=SourceType.BOOK,
            source_title="Test Book",
            location_reference="Page 42",
            chunk_id="chunk_123",
            relevance_score=0.85
        )
        
        return MultimediaResponse(
            text_content="This is a sample response with multimedia content for testing export functionality.",
            visualizations=[visualization],
            audio_content=audio,
            video_content=video,
            knowledge_citations=[citation]
        )
    
    def test_export_engine_initialization(self, export_engine):
        """Test that ExportEngine initializes correctly."""
        assert export_engine is not None
        assert len(export_engine.supported_formats) == 6
        assert 'txt' in export_engine.supported_formats
        assert 'docx' in export_engine.supported_formats
        assert 'pdf' in export_engine.supported_formats
        assert 'rtf' in export_engine.supported_formats
        assert 'pptx' in export_engine.supported_formats
        assert 'xlsx' in export_engine.supported_formats
    
    def test_get_supported_formats(self, export_engine):
        """Test getting supported formats."""
        formats = export_engine.get_supported_formats()
        expected_formats = ['txt', 'docx', 'pdf', 'rtf', 'pptx', 'xlsx']
        assert set(formats) == set(expected_formats)
    
    def test_validate_response_valid(self, export_engine, sample_response):
        """Test validation of valid response."""
        assert export_engine.validate_response(sample_response) is True
    
    def test_validate_response_invalid(self, export_engine):
        """Test validation of invalid response."""
        # Test with None
        assert export_engine.validate_response(None) is False
        
        # Test with empty text content
        empty_response = MultimediaResponse(text_content="")
        assert export_engine.validate_response(empty_response) is False
    
    def test_export_to_txt(self, export_engine, sample_response):
        """Test export to TXT format."""
        result = export_engine.export_to_format(sample_response, 'txt')
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Decode and check content
        content = result.decode('utf-8')
        assert "MULTIMODAL LIBRARIAN EXPORT" in content
        assert "This is a sample response" in content
        assert "VISUALIZATIONS:" in content
        assert "Sample Chart" in content
        assert "CITATIONS:" in content
        assert "Test Book" in content
        assert "Page 42" in content
    
    def test_export_to_docx(self, export_engine, sample_response):
        """Test export to DOCX format."""
        result = export_engine.export_to_format(sample_response, 'docx')
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Check that it's a valid DOCX file by checking the header
        assert result.startswith(b'PK')  # ZIP file signature (DOCX is a ZIP)
    
    def test_export_to_pdf(self, export_engine, sample_response):
        """Test export to PDF format."""
        result = export_engine.export_to_format(sample_response, 'pdf')
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Check that it's a valid PDF file
        assert result.startswith(b'%PDF')
    
    def test_export_to_rtf(self, export_engine, sample_response):
        """Test export to RTF format."""
        result = export_engine.export_to_format(sample_response, 'rtf')
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Check that it contains RTF content
        content = result.decode('utf-8')
        assert content.startswith('{\\rtf')
    
    def test_export_to_pptx(self, export_engine, sample_response):
        """Test export to PPTX format."""
        result = export_engine.export_to_format(sample_response, 'pptx')
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Check that it's a valid PPTX file by checking the header
        assert result.startswith(b'PK')  # ZIP file signature (PPTX is a ZIP)
    
    def test_export_to_xlsx(self, export_engine, sample_response):
        """Test export to XLSX format."""
        result = export_engine.export_to_format(sample_response, 'xlsx')
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Check that it's a valid XLSX file by checking the header
        assert result.startswith(b'PK')  # ZIP file signature (XLSX is a ZIP)
    
    def test_export_unsupported_format(self, export_engine, sample_response):
        """Test export to unsupported format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported format"):
            export_engine.export_to_format(sample_response, 'unsupported')
    
    def test_export_format_case_insensitive(self, export_engine, sample_response):
        """Test that format specification is case insensitive."""
        result_lower = export_engine.export_to_format(sample_response, 'txt')
        result_upper = export_engine.export_to_format(sample_response, 'TXT')
        result_mixed = export_engine.export_to_format(sample_response, 'Txt')
        
        # All should produce the same result
        assert result_lower == result_upper == result_mixed
    
    def test_export_format_with_dot(self, export_engine, sample_response):
        """Test that format with dot prefix works."""
        result_with_dot = export_engine.export_to_format(sample_response, '.txt')
        result_without_dot = export_engine.export_to_format(sample_response, 'txt')
        
        # Should produce the same result
        assert result_with_dot == result_without_dot
    
    def test_export_updates_metadata(self, export_engine, sample_response):
        """Test that export updates the response metadata."""
        # Initially no export metadata
        assert sample_response.export_metadata is None
        
        result = export_engine.export_to_format(sample_response, 'txt')
        
        # Should now have export metadata
        assert sample_response.export_metadata is not None
        assert sample_response.export_metadata.export_format == 'txt'
        assert sample_response.export_metadata.file_size == len(result)
        assert sample_response.export_metadata.includes_media is True
        assert isinstance(sample_response.export_metadata.created_at, datetime)
    
    def test_export_minimal_response(self, export_engine):
        """Test export with minimal response (text only)."""
        minimal_response = MultimediaResponse(
            text_content="Just some text content."
        )
        
        result = export_engine.export_to_format(minimal_response, 'txt')
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        content = result.decode('utf-8')
        assert "Just some text content." in content
    
    def test_export_response_without_multimedia(self, export_engine):
        """Test export with response that has no multimedia content."""
        text_only_response = MultimediaResponse(
            text_content="Text only response for testing.",
            knowledge_citations=[
                KnowledgeCitation(
                    source_type=SourceType.CONVERSATION,
                    source_title="Test Conversation",
                    location_reference="2023-12-01 10:30",
                    chunk_id="conv_456",
                    relevance_score=0.75
                )
            ]
        )
        
        # Test multiple formats
        for format_type in ['txt', 'docx', 'pdf']:
            result = export_engine.export_to_format(text_only_response, format_type)
            assert isinstance(result, bytes)
            assert len(result) > 0
    
    @patch('tempfile.NamedTemporaryFile')
    @patch('os.unlink')
    def test_export_handles_image_errors(self, mock_unlink, mock_tempfile, export_engine, sample_response):
        """Test that export handles image processing errors gracefully."""
        # Mock tempfile to raise an exception
        mock_tempfile.side_effect = Exception("Temp file error")
        
        # Should still complete export without crashing
        result = export_engine.export_to_format(sample_response, 'docx')
        assert isinstance(result, bytes)
        assert len(result) > 0
    
    def test_preserve_formatting(self, export_engine):
        """Test the preserve_formatting method."""
        test_content = "Test content"
        result = export_engine.preserve_formatting(test_content, 'txt')
        assert result == test_content
    
    def test_export_performance(self, export_engine, sample_response):
        """Test that export completes within reasonable time."""
        import time
        
        start_time = time.time()
        result = export_engine.export_to_format(sample_response, 'txt')
        end_time = time.time()
        
        # Should complete within 5 seconds (generous for testing)
        assert (end_time - start_time) < 5.0
        assert len(result) > 0


class TestExportEngineIntegration:
    """Integration tests for the ExportEngine."""
    
    @pytest.fixture
    def export_engine(self):
        """Create an ExportEngine instance for testing."""
        return ExportEngine()
    
    def test_export_all_formats(self, export_engine):
        """Test exporting to all supported formats."""
        response = MultimediaResponse(
            text_content="Integration test content with comprehensive data.",
            visualizations=[
                Visualization(
                    viz_id="test_viz",
                    viz_type="bar_chart",
                    content_data=b"fake_chart_data",
                    caption="Test Chart Caption"
                )
            ],
            knowledge_citations=[
                KnowledgeCitation(
                    source_type=SourceType.BOOK,
                    source_title="Integration Test Book",
                    location_reference="Chapter 5",
                    chunk_id="test_chunk",
                    relevance_score=0.9
                )
            ]
        )
        
        formats = export_engine.get_supported_formats()
        results = {}
        
        for format_type in formats:
            result = export_engine.export_to_format(response, format_type)
            results[format_type] = result
            
            # Basic validation
            assert isinstance(result, bytes)
            assert len(result) > 0
        
        # Ensure all formats produced different results (except where they might be identical)
        assert len(set(len(result) for result in results.values())) > 1
    
    def test_export_large_content(self, export_engine):
        """Test export with large content."""
        large_text = "This is a test sentence. " * 1000  # ~25KB of text
        
        large_response = MultimediaResponse(
            text_content=large_text,
            knowledge_citations=[
                KnowledgeCitation(
                    source_type=SourceType.BOOK,
                    source_title=f"Large Book {i}",
                    location_reference=f"Page {i}",
                    chunk_id=f"chunk_{i}",
                    relevance_score=0.8
                )
                for i in range(50)  # 50 citations
            ]
        )
        
        # Test with a few formats
        for format_type in ['txt', 'docx', 'pdf']:
            result = export_engine.export_to_format(large_response, format_type)
            assert isinstance(result, bytes)
            assert len(result) > 0
            
            # Should handle large content without issues
            assert len(result) > 1000  # Should be substantial