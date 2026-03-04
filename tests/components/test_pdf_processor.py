"""
Tests for PDF processing component.

Tests the core PDF processing functionality including content extraction,
error handling, and document structure analysis.
"""

import pytest
import io
from pathlib import Path
from unittest.mock import Mock, patch

from multimodal_librarian.components.pdf_processor.pdf_processor import (
    PDFProcessor,
    PDFProcessingError,
    PDFCorruptionError,
    PDFPartialReadError,
    PDFValidationError
)
from multimodal_librarian.models.core import DocumentContent, DocumentMetadata


class TestPDFProcessor:
    """Test cases for PDFProcessor class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = PDFProcessor()
        
    def test_processor_initialization(self):
        """Test PDFProcessor initialization with default settings."""
        assert self.processor.max_file_size == 100 * 1024 * 1024  # 100MB
        assert self.processor.enable_graceful_degradation is True
        assert self.processor.partial_read_threshold == 0.5
        
    def test_processor_initialization_custom_size(self):
        """Test PDFProcessor initialization with custom max file size."""
        custom_processor = PDFProcessor(max_file_size=50 * 1024 * 1024)
        assert custom_processor.max_file_size == 50 * 1024 * 1024
        
    def test_empty_pdf_bytes_raises_error(self):
        """Test that empty PDF bytes raise PDFProcessingError."""
        with pytest.raises(PDFProcessingError, match="PDF data is empty"):
            self.processor.extract_content(b"")
            
    def test_oversized_pdf_raises_error(self):
        """Test that oversized PDF raises PDFProcessingError."""
        # Create oversized data
        oversized_data = b"x" * (self.processor.max_file_size + 1)
        
        with pytest.raises(PDFProcessingError, match="PDF data too large"):
            self.processor.extract_content(oversized_data)
            
    def test_invalid_pdf_header_raises_corruption_error(self):
        """Test that invalid PDF header raises PDFCorruptionError."""
        invalid_pdf = b"Not a PDF file"
        
        with pytest.raises(PDFCorruptionError, match="Invalid PDF format"):
            self.processor.extract_content(invalid_pdf)
            
    def test_graceful_degradation_toggle(self):
        """Test enabling and disabling graceful degradation."""
        # Test enabling
        self.processor.enable_graceful_degradation_mode(True)
        assert self.processor.enable_graceful_degradation is True
        
        # Test disabling
        self.processor.enable_graceful_degradation_mode(False)
        assert self.processor.enable_graceful_degradation is False
        
    def test_partial_read_threshold_setting(self):
        """Test setting partial read threshold."""
        self.processor.set_partial_read_threshold(0.8)
        assert self.processor.partial_read_threshold == 0.8
        
    def test_invalid_threshold_raises_error(self):
        """Test that invalid threshold values raise ValueError."""
        with pytest.raises(ValueError, match="Threshold must be between 0.0 and 1.0"):
            self.processor.set_partial_read_threshold(1.5)
            
        with pytest.raises(ValueError, match="Threshold must be between 0.0 and 1.0"):
            self.processor.set_partial_read_threshold(-0.1)
            
    def test_error_description_corruption_error(self):
        """Test error description for PDFCorruptionError."""
        error = PDFCorruptionError("Test corruption error")
        description = self.processor.get_error_description(error)
        
        assert description['error_type'] == 'PDFCorruptionError'
        assert description['severity'] == 'high'
        assert 'corrupted' in description['description'].lower()
        assert len(description['suggestions']) > 0
        
    def test_error_description_partial_read_error(self):
        """Test error description for PDFPartialReadError."""
        error = PDFPartialReadError("Test partial read error")
        description = self.processor.get_error_description(error)
        
        assert description['error_type'] == 'PDFPartialReadError'
        assert description['severity'] == 'medium'
        assert 'partially' in description['description'].lower()
        
    def test_error_description_unknown_error(self):
        """Test error description for unknown error types."""
        error = ValueError("Unknown error")
        description = self.processor.get_error_description(error)
        
        assert description['error_type'] == 'ValueError'
        assert description['severity'] == 'unknown'
        assert 'unexpected error' in description['description'].lower()
        
    @patch('multimodal_librarian.components.pdf_processor.pdf_processor.fitz')
    def test_validate_pdf_file_valid(self, mock_fitz):
        """Test PDF validation for valid file."""
        # Mock a valid PDF document
        mock_doc = Mock()
        mock_doc.page_count = 5
        mock_doc.needs_pass = False
        mock_doc.close = Mock()
        
        # Mock page that can be read
        mock_page = Mock()
        mock_page.get_text.return_value = "Sample text"
        mock_page.get_images.return_value = []
        
        # Properly mock the __getitem__ method for document indexing
        def mock_getitem(index):
            return mock_page
        mock_doc.__getitem__ = Mock(side_effect=mock_getitem)
        
        mock_fitz.open.return_value = mock_doc
        
        # Create valid PDF bytes
        pdf_bytes = b"%PDF-1.4\nSample PDF content"
        
        result = self.processor.validate_pdf_file(pdf_bytes)
        
        assert result['is_valid'] is True
        assert result['is_recoverable'] is True
        assert result['file_size'] == len(pdf_bytes)
        assert len(result['recommendations']) > 0
        
    @patch('multimodal_librarian.components.pdf_processor.pdf_processor.fitz')
    def test_validate_pdf_file_encrypted(self, mock_fitz):
        """Test PDF validation for encrypted file."""
        # Mock an encrypted PDF document
        mock_doc = Mock()
        mock_doc.page_count = 5
        mock_doc.needs_pass = True  # Password protected
        mock_doc.close = Mock()
        
        mock_fitz.open.return_value = mock_doc
        
        pdf_bytes = b"%PDF-1.4\nEncrypted PDF content"
        
        result = self.processor.validate_pdf_file(pdf_bytes)
        
        assert result['is_valid'] is False
        assert result['is_recoverable'] is False
        assert 'password protected' in ' '.join(result['issues']).lower()
        
    def test_validate_pdf_file_invalid_input(self):
        """Test PDF validation for invalid input."""
        result = self.processor.validate_pdf_file(b"Not a PDF")
        
        assert result['is_valid'] is False
        assert result['is_recoverable'] is False
        assert result['file_size'] == len(b"Not a PDF")  # File size should be actual size
        
    @patch('multimodal_librarian.components.pdf_processor.pdf_processor.fitz')
    def test_extract_content_basic_functionality(self, mock_fitz):
        """Test basic content extraction functionality."""
        # Mock a simple PDF document
        mock_doc = Mock()
        mock_doc.page_count = 2
        mock_doc.needs_pass = False
        mock_doc.close = Mock()
        
        # Mock metadata
        mock_doc.metadata = {
            'title': 'Test Document',
            'author': 'Test Author',
            'creationDate': 'D:20230101120000',
            'subject': 'Test Subject',
            'keywords': 'test, pdf'
        }
        
        # Mock pages
        mock_page1 = Mock()
        mock_page1.get_text.return_value = "Page 1 content"
        mock_page1.get_images.return_value = []
        mock_page1.get_drawings.return_value = []
        
        mock_page2 = Mock()
        mock_page2.get_text.return_value = "Page 2 content"
        mock_page2.get_images.return_value = []
        mock_page2.get_drawings.return_value = []
        
        # Properly mock the __getitem__ method for document indexing
        def mock_getitem(index):
            if index == 0:
                return mock_page1
            elif index == 1:
                return mock_page2
            else:
                raise IndexError("Page index out of range")
        mock_doc.__getitem__ = Mock(side_effect=mock_getitem)
        
        mock_fitz.open.return_value = mock_doc
        
        # Mock pdfplumber for table extraction
        with patch('multimodal_librarian.components.pdf_processor.pdf_processor.pdfplumber') as mock_pdfplumber:
            mock_pdf = Mock()
            mock_page_plumber = Mock()
            mock_page_plumber.extract_tables.return_value = []
            mock_pdf.pages = [mock_page_plumber, mock_page_plumber]
            mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
            
            pdf_bytes = b"%PDF-1.4\nTest PDF content"
            result = self.processor.extract_content(pdf_bytes)
            
            assert isinstance(result, DocumentContent)
            assert "Page 1 content" in result.text
            assert "Page 2 content" in result.text
            assert result.metadata.title == "Test Document"
            assert result.metadata.author == "Test Author"
            assert result.metadata.page_count == 2
            
    @patch('multimodal_librarian.components.pdf_processor.pdf_processor.fitz')
    def test_extract_content_with_images(self, mock_fitz):
        """Test content extraction with images."""
        # Mock document with images
        mock_doc = Mock()
        mock_doc.page_count = 1
        mock_doc.needs_pass = False
        mock_doc.close = Mock()
        mock_doc.metadata = {'title': 'Test Document'}
        
        # Mock image data
        mock_pixmap = Mock()
        mock_pixmap.n = 3  # RGB
        mock_pixmap.alpha = 0
        mock_pixmap.tobytes.return_value = b"fake_png_data"
        
        # Mock page with images
        mock_page = Mock()
        mock_page.get_text.return_value = "Page with image"
        mock_page.get_images.return_value = [(123, 0, 100, 100, 8, 'DeviceRGB', '', 'Im1', 'DCTDecode')]
        mock_page.get_drawings.return_value = []
        mock_page.parent = mock_doc
        
        # Properly mock the __getitem__ method for document indexing
        def mock_getitem(index):
            if index == 0:
                return mock_page
            else:
                raise IndexError("Page index out of range")
        mock_doc.__getitem__ = Mock(side_effect=mock_getitem)
        
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Pixmap.return_value = mock_pixmap
        
        # Mock PIL Image
        with patch('multimodal_librarian.components.pdf_processor.pdf_processor.Image') as mock_pil:
            mock_img = Mock()
            mock_img.width = 100
            mock_img.height = 100
            mock_pil.open.return_value = mock_img
            
            # Mock pdfplumber
            with patch('multimodal_librarian.components.pdf_processor.pdf_processor.pdfplumber') as mock_pdfplumber:
                mock_pdf = Mock()
                mock_page_plumber = Mock()
                mock_page_plumber.extract_tables.return_value = []
                mock_pdf.pages = [mock_page_plumber]
                mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
                
                pdf_bytes = b"%PDF-1.4\nTest PDF with images"
                result = self.processor.extract_content(pdf_bytes)
                
                assert len(result.images) == 1
                assert result.images[0].element_type == "image"
                assert result.images[0].metadata['width'] == 100
                assert result.images[0].metadata['height'] == 100
                
    def test_structure_analysis_basic(self):
        """Test basic document structure analysis."""
        # Create mock document content
        text = """[Page 1]
Chapter 1: Introduction
This is the introduction paragraph.

1.1 Overview
This is an overview section.

[Page 2]
Chapter 2: Methods
This is the methods chapter.
"""
        
        mock_content = Mock()
        mock_content.text = text
        mock_content.metadata = Mock()
        mock_content.metadata.page_count = 2
        
        structure = self.processor.analyze_structure(mock_content)
        
        assert len(structure.chapters) >= 1
        assert len(structure.sections) >= 1
        assert structure.page_count == 2
        
    def test_chapter_heading_detection(self):
        """Test chapter heading detection."""
        assert self.processor._is_chapter_heading("Chapter 1: Introduction")
        assert self.processor._is_chapter_heading("CHAPTER ONE")
        assert self.processor._is_chapter_heading("1. First Chapter")
        assert not self.processor._is_chapter_heading("This is a regular paragraph.")
        
    def test_section_heading_detection(self):
        """Test section heading detection."""
        assert self.processor._is_section_heading("1.1 Overview")
        assert self.processor._is_section_heading("A. First Section")
        assert not self.processor._is_section_heading("This is a regular paragraph with more text.")
        
    def test_table_of_contents_detection(self):
        """Test table of contents detection."""
        toc_text = """
Table of Contents
Chapter 1 ............... Page 1
Chapter 2 ............... Page 15
Index ................... Page 200
"""
        assert self.processor._detect_table_of_contents(toc_text)
        
        no_toc_text = "This is just regular content."
        assert not self.processor._detect_table_of_contents(no_toc_text)


class TestPDFProcessorIntegration:
    """Integration tests for PDF processor with sample data."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = PDFProcessor()
        
    def test_sample_pdf_content_fixture(self, sample_pdf_content):
        """Test processing with sample PDF content fixture."""
        # This should raise a corruption error since it's minimal PDF content
        with pytest.raises(PDFCorruptionError):
            self.processor.extract_content(sample_pdf_content)
            
    def test_processing_recommendations(self):
        """Test processing recommendations for different validation results."""
        # Valid PDF
        valid_result = {'is_valid': True, 'is_recoverable': True, 'issues': []}
        recommendations = self.processor._get_processing_recommendations(valid_result)
        assert any('valid' in rec.lower() for rec in recommendations)
        
        # Recoverable PDF
        recoverable_result = {'is_valid': False, 'is_recoverable': True, 'issues': ['minor issue']}
        recommendations = self.processor._get_processing_recommendations(recoverable_result)
        assert any('graceful degradation' in rec.lower() for rec in recommendations)
        
        # Unrecoverable PDF
        unrecoverable_result = {'is_valid': False, 'is_recoverable': False, 'issues': ['no pages']}
        recommendations = self.processor._get_processing_recommendations(unrecoverable_result)
        assert any('cannot be processed' in rec.lower() for rec in recommendations)