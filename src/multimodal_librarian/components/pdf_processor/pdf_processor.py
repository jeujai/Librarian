"""
PDF Processing Component.

This module implements PyMuPDF-based text and image extraction, table detection using pdfplumber,
and document structure analysis for chapters and sections.

For large PDFs (50+ pages), uses streaming/page-by-page processing with explicit memory management
to avoid OOM errors.
"""

import gc
import io
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image

from ...models.core import (
    ContentType,
    DocumentContent,
    DocumentMetadata,
    DocumentStructure,
    MediaElement,
)

logger = logging.getLogger(__name__)


class PDFProcessingError(Exception):
    """Base exception for PDF processing errors."""
    pass


class PDFCorruptionError(PDFProcessingError):
    """Exception raised when PDF is corrupted or unreadable."""
    pass


class PDFPartialReadError(PDFProcessingError):
    """Exception raised when PDF is partially readable but has issues."""
    pass


class PDFValidationError(PDFProcessingError):
    """Exception raised when PDF fails validation checks."""
    pass


class PDFProcessor:
    """
    PDF processing component that extracts multimodal content from PDF files.
    
    Handles text extraction, image extraction, table detection, and document
    structure analysis while preserving associations between text and media elements.
    
    For large PDFs, uses streaming/page-by-page processing to avoid memory exhaustion.
    """
    
    def __init__(self, max_file_size: int = None):
        """
        Initialize PDF processor.
        
        Args:
            max_file_size: Maximum allowed file size in bytes (defaults to config setting)
        """
        if max_file_size is None:
            from ...config.config import get_settings
            max_file_size = get_settings().max_file_size
        self.max_file_size = max_file_size
        self.supported_image_formats = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}
        self.enable_graceful_degradation = True
        self.partial_read_threshold = 0.5  # Minimum fraction of pages that must be readable
        
        # Memory management settings
        self.batch_size = 10  # Process pages in batches of 10
        self.large_pdf_threshold = 50  # PDFs with more pages are considered "large"
        self.skip_images_for_large_pdfs = True  # Skip image extraction for large PDFs
        self.max_images_per_page = 5  # Limit images extracted per page
        self.gc_after_batch = True  # Run garbage collection after each batch
        
    def extract_content(self, pdf_file: Union[bytes, str, Path]) -> DocumentContent:
        """
        Extract multimodal content from PDF file with error handling and graceful degradation.
        
        Args:
            pdf_file: PDF file as bytes, file path string, or Path object
            
        Returns:
            DocumentContent: Extracted content with text, images, tables, and metadata
            
        Raises:
            PDFProcessingError: If PDF processing fails completely
            PDFCorruptionError: If PDF is corrupted and cannot be read
            PDFPartialReadError: If PDF is partially readable (when graceful degradation is disabled)
        """
        processing_errors = []
        
        try:
            # Handle different input types and validate
            pdf_bytes, file_size = self._prepare_pdf_input(pdf_file)
            
            # Comprehensive PDF validation
            validation_result = self._comprehensive_pdf_validation(pdf_bytes)
            if not validation_result['is_valid']:
                if validation_result['is_recoverable'] and self.enable_graceful_degradation:
                    logger.warning(f"PDF has issues but attempting graceful degradation: {validation_result['issues']}")
                    processing_errors.extend(validation_result['issues'])
                else:
                    raise PDFCorruptionError(f"PDF validation failed: {'; '.join(validation_result['issues'])}")
            
            # Extract content with error recovery
            doc_content = self._extract_with_error_recovery(pdf_bytes, processing_errors)
            
            # Enhance with pdfplumber for tables (with error handling)
            try:
                tables = self._extract_tables_with_pdfplumber(pdf_bytes)
                doc_content.tables.extend(tables)
            except Exception as e:
                error_msg = f"Table extraction failed: {str(e)}"
                processing_errors.append(error_msg)
                logger.warning(error_msg)
            
            # Analyze document structure (with error handling)
            try:
                structure = self.analyze_structure(doc_content)
                doc_content.structure = structure
            except Exception as e:
                error_msg = f"Structure analysis failed: {str(e)}"
                processing_errors.append(error_msg)
                logger.warning(error_msg)
            
            # Update metadata with file size and processing info
            if doc_content.metadata:
                doc_content.metadata.file_size = file_size
                if processing_errors:
                    doc_content.metadata.keywords.append("partial_extraction")
            
            # Log processing summary
            success_msg = (f"PDF processing completed: {len(doc_content.text)} chars, "
                          f"{len(doc_content.images)} images, {len(doc_content.tables)} tables")
            if processing_errors:
                success_msg += f" (with {len(processing_errors)} warnings)"
            logger.info(success_msg)
            
            # Raise partial read error if too many issues and graceful degradation is disabled
            if processing_errors and not self.enable_graceful_degradation:
                raise PDFPartialReadError(f"PDF partially readable with errors: {'; '.join(processing_errors)}")
            
            return doc_content
            
        except (PDFCorruptionError, PDFPartialReadError, PDFValidationError):
            # Re-raise our custom exceptions
            raise
        except fitz.FileDataError as e:
            raise PDFCorruptionError(f"PDF file is corrupted or unreadable: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected PDF processing error: {str(e)}")
            raise PDFProcessingError(f"Failed to process PDF: {str(e)}")
    
    def _prepare_pdf_input(self, pdf_file: Union[bytes, str, Path]) -> Tuple[bytes, int]:
        """
        Prepare and validate PDF input from various sources.
        
        Args:
            pdf_file: PDF file as bytes, file path string, or Path object
            
        Returns:
            Tuple of (pdf_bytes, file_size)
            
        Raises:
            PDFProcessingError: If input preparation fails
        """
        try:
            if isinstance(pdf_file, (str, Path)):
                pdf_path = Path(pdf_file)
                if not pdf_path.exists():
                    raise PDFProcessingError(f"PDF file not found: {pdf_path}")
                
                # Check file size
                file_size = pdf_path.stat().st_size
                if file_size == 0:
                    raise PDFProcessingError("PDF file is empty")
                if file_size > self.max_file_size:
                    raise PDFProcessingError(
                        f"PDF file too large: {file_size} bytes (max: {self.max_file_size})"
                    )
                
                pdf_bytes = pdf_path.read_bytes()
            else:
                pdf_bytes = pdf_file
                file_size = len(pdf_bytes)
                if file_size == 0:
                    raise PDFProcessingError("PDF data is empty")
                if file_size > self.max_file_size:
                    raise PDFProcessingError(
                        f"PDF data too large: {file_size} bytes (max: {self.max_file_size})"
                    )
            
            return pdf_bytes, file_size
            
        except Exception as e:
            if isinstance(e, PDFProcessingError):
                raise
            raise PDFProcessingError(f"Failed to prepare PDF input: {str(e)}")
    
    def _comprehensive_pdf_validation(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Perform comprehensive PDF validation with detailed error reporting.
        
        Args:
            pdf_bytes: PDF file content as bytes
            
        Returns:
            Dict with validation results: {'is_valid': bool, 'is_recoverable': bool, 'issues': List[str]}
        """
        issues = []
        is_valid = True
        is_recoverable = True
        
        # Check PDF header
        if not pdf_bytes.startswith(b'%PDF-'):
            issues.append("Invalid PDF format: missing PDF header")
            is_valid = False
            
            # Try to find PDF header within first 1024 bytes
            header_pos = pdf_bytes.find(b'%PDF-', 0, 1024)
            if header_pos > 0:
                issues.append(f"PDF header found at offset {header_pos}, attempting recovery")
                pdf_bytes = pdf_bytes[header_pos:]
            else:
                is_recoverable = False
                return {'is_valid': False, 'is_recoverable': False, 'issues': issues}
        
        # Check PDF version
        try:
            version_line = pdf_bytes[:20].decode('ascii', errors='ignore')
            if '%PDF-' in version_line:
                version = version_line.split('%PDF-')[1][:3]
                try:
                    version_num = float(version)
                    if version_num > 2.0:
                        issues.append(f"PDF version {version} may not be fully supported")
                except ValueError:
                    issues.append("Could not parse PDF version")
            else:
                issues.append("Could not determine PDF version")
        except Exception:
            issues.append("Failed to check PDF version")
        
        # Try to open with PyMuPDF for structural validation
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            if doc.page_count == 0:
                issues.append("PDF contains no pages")
                is_valid = False
                is_recoverable = False
            elif doc.page_count > 10000:
                issues.append(f"PDF has unusually high page count: {doc.page_count}")
            
            # Check if document is encrypted
            if doc.needs_pass:
                issues.append("PDF is password protected")
                is_valid = False
                is_recoverable = False
            
            # Test reading first few pages
            readable_pages = 0
            for i in range(min(5, doc.page_count)):
                try:
                    page = doc[i]
                    text = page.get_text()
                    if text or page.get_images():
                        readable_pages += 1
                except Exception as e:
                    issues.append(f"Cannot read page {i + 1}: {str(e)}")
            
            # Check if enough pages are readable
            if readable_pages == 0:
                issues.append("No pages are readable")
                is_valid = False
                is_recoverable = False
            elif readable_pages < min(3, doc.page_count * self.partial_read_threshold):
                issues.append(f"Only {readable_pages} of {doc.page_count} pages are readable")
                is_valid = False
                # Still recoverable if some pages work
            
            doc.close()
            
        except fitz.FileDataError as e:
            issues.append(f"PDF structure error: {str(e)}")
            is_valid = False
            is_recoverable = False
        except Exception as e:
            issues.append(f"PDF validation error: {str(e)}")
            is_valid = False
        
        return {
            'is_valid': is_valid,
            'is_recoverable': is_recoverable,
            'issues': issues
        }
    
    def get_error_description(self, error: Exception) -> Dict[str, str]:
        """
        Get detailed error description and recovery suggestions.
        
        Args:
            error: Exception that occurred during processing
            
        Returns:
            Dict with error details and suggestions
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        descriptions = {
            'PDFCorruptionError': {
                'description': 'The PDF file is corrupted, encrypted, or in an unsupported format.',
                'suggestions': [
                    'Try opening the PDF in a different PDF viewer to verify it works',
                    'If the PDF is password-protected, remove the password first',
                    'Convert the PDF to a newer format using a PDF editor',
                    'Check if the file was completely downloaded'
                ],
                'severity': 'high'
            },
            'PDFPartialReadError': {
                'description': 'The PDF could be partially read, but some pages or content failed to process.',
                'suggestions': [
                    'Enable graceful degradation to extract available content',
                    'Check if specific pages are corrupted',
                    'Try converting problematic pages to images first',
                    'Consider splitting the PDF into smaller sections'
                ],
                'severity': 'medium'
            },
            'PDFValidationError': {
                'description': 'The PDF failed validation checks but may still be processable.',
                'suggestions': [
                    'Try processing with graceful degradation enabled',
                    'Check PDF version compatibility',
                    'Verify the PDF is not truncated or incomplete'
                ],
                'severity': 'medium'
            },
            'PDFProcessingError': {
                'description': 'A general error occurred during PDF processing.',
                'suggestions': [
                    'Check if the file is a valid PDF',
                    'Ensure sufficient system memory is available',
                    'Try processing a smaller PDF first',
                    'Check file permissions and accessibility'
                ],
                'severity': 'medium'
            }
        }
        
        error_info = descriptions.get(error_type, {
            'description': f'An unexpected error occurred: {error_message}',
            'suggestions': [
                'Check the PDF file integrity',
                'Try with a different PDF file',
                'Contact support if the issue persists'
            ],
            'severity': 'unknown'
        })
        
        return {
            'error_type': error_type,
            'error_message': error_message,
            'description': error_info['description'],
            'suggestions': error_info['suggestions'],
            'severity': error_info['severity']
        }
    
    def enable_graceful_degradation_mode(self, enabled: bool = True) -> None:
        """
        Enable or disable graceful degradation for partially readable PDFs.
        
        Args:
            enabled: Whether to enable graceful degradation
        """
        self.enable_graceful_degradation = enabled
        logger.info(f"Graceful degradation {'enabled' if enabled else 'disabled'}")
    
    def set_partial_read_threshold(self, threshold: float) -> None:
        """
        Set the minimum fraction of pages that must be readable.
        
        Args:
            threshold: Minimum fraction (0.0 to 1.0) of pages that must be readable
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        
        self.partial_read_threshold = threshold
        logger.info(f"Partial read threshold set to {threshold}")
    
    def configure_memory_management(
        self,
        batch_size: int = 10,
        large_pdf_threshold: int = 50,
        skip_images_for_large_pdfs: bool = True,
        max_images_per_page: int = 5,
        gc_after_batch: bool = True
    ) -> None:
        """
        Configure memory management settings for processing large PDFs.
        
        Args:
            batch_size: Number of pages to process before garbage collection (default: 10)
            large_pdf_threshold: Page count above which PDF is considered "large" (default: 50)
            skip_images_for_large_pdfs: Whether to skip image extraction for large PDFs (default: True)
            max_images_per_page: Maximum images to extract per page (default: 5)
            gc_after_batch: Whether to run garbage collection after each batch (default: True)
        """
        self.batch_size = batch_size
        self.large_pdf_threshold = large_pdf_threshold
        self.skip_images_for_large_pdfs = skip_images_for_large_pdfs
        self.max_images_per_page = max_images_per_page
        self.gc_after_batch = gc_after_batch
        
        logger.info(f"Memory management configured: batch_size={batch_size}, "
                   f"large_pdf_threshold={large_pdf_threshold}, "
                   f"skip_images_for_large_pdfs={skip_images_for_large_pdfs}, "
                   f"max_images_per_page={max_images_per_page}, "
                   f"gc_after_batch={gc_after_batch}")
    @staticmethod
    def _extract_printed_page_number(page_text: str) -> Optional[str]:
        """
        Extract the printed page number from the first few lines of a page's text.

        Many PDFs have the printed page number as a standalone number on one of the
        first few lines (e.g. line 0 is chapter title, line 1 is "302").

        Args:
            page_text: Raw text extracted from a PDF page

        Returns:
            The printed page number as a string, or None if not found
        """
        import re
        lines = page_text.strip().split('\n')
        # Check the first 5 lines for a standalone number
        for line in lines[:5]:
            stripped = line.strip()
            if re.match(r'^\d+$', stripped) and len(stripped) <= 5:
                return stripped
        return None
    
    def validate_pdf_file(self, pdf_file: Union[bytes, str, Path]) -> Dict[str, Any]:
        """
        Validate PDF file without full processing.
        
        Args:
            pdf_file: PDF file as bytes, file path string, or Path object
            
        Returns:
            Dict with validation results and recommendations
        """
        try:
            pdf_bytes, file_size = self._prepare_pdf_input(pdf_file)
            validation_result = self._comprehensive_pdf_validation(pdf_bytes)
            
            return {
                'is_valid': validation_result['is_valid'],
                'is_recoverable': validation_result['is_recoverable'],
                'issues': validation_result['issues'],
                'file_size': file_size,
                'recommendations': self._get_processing_recommendations(validation_result)
            }
            
        except Exception as e:
            return {
                'is_valid': False,
                'is_recoverable': False,
                'issues': [str(e)],
                'file_size': 0,
                'recommendations': ['File cannot be accessed or read']
            }
    
    def _get_processing_recommendations(self, validation_result: Dict[str, Any]) -> List[str]:
        """
        Get processing recommendations based on validation results.
        
        Args:
            validation_result: Results from comprehensive validation
            
        Returns:
            List of processing recommendations
        """
        recommendations = []
        
        if validation_result['is_valid']:
            recommendations.append('PDF appears to be valid and should process normally')
        elif validation_result['is_recoverable']:
            recommendations.append('PDF has issues but may be processable with graceful degradation')
            recommendations.append('Consider enabling graceful degradation mode')
            if 'password protected' in ' '.join(validation_result['issues']).lower():
                recommendations.append('Remove password protection before processing')
        else:
            recommendations.append('PDF cannot be processed in current state')
            if 'header' in ' '.join(validation_result['issues']).lower():
                recommendations.append('File may not be a valid PDF')
            if 'no pages' in ' '.join(validation_result['issues']).lower():
                recommendations.append('PDF appears to be empty or severely corrupted')
        
        return recommendations
    
    def _extract_with_error_recovery(self, pdf_bytes: bytes, processing_errors: List[str]) -> DocumentContent:
        """
        Extract content with error recovery, graceful degradation, and memory-efficient
        page-by-page processing for large PDFs.
        
        Args:
            pdf_bytes: PDF file content as bytes
            processing_errors: List to collect processing errors
            
        Returns:
            DocumentContent: Extracted content (may be partial)
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        try:
            page_count = doc.page_count
            is_large_pdf = page_count > self.large_pdf_threshold
            
            if is_large_pdf:
                logger.info(f"Large PDF detected ({page_count} pages). Using streaming extraction with batch size {self.batch_size}")
            
            # Extract metadata with error handling
            try:
                metadata = self._extract_metadata(doc)
            except Exception as e:
                error_msg = f"Metadata extraction failed: {str(e)}"
                processing_errors.append(error_msg)
                logger.warning(error_msg)
                metadata = DocumentMetadata(title="Unknown Document")
            
            # Initialize accumulators
            full_text = []
            images = []
            charts = []
            successful_pages = 0
            
            # Process pages in batches for memory efficiency
            for batch_start in range(0, page_count, self.batch_size):
                batch_end = min(batch_start + self.batch_size, page_count)
                batch_num = (batch_start // self.batch_size) + 1
                total_batches = (page_count + self.batch_size - 1) // self.batch_size
                
                if is_large_pdf:
                    logger.info(f"Processing batch {batch_num}/{total_batches} (pages {batch_start + 1}-{batch_end})")
                
                # Process each page in the batch
                for page_num in range(batch_start, batch_end):
                    try:
                        page = doc[page_num]
                        
                        # Extract text first so we can inspect it for printed page number
                        try:
                            page_text = page.get_text()
                        except Exception as e:
                            page_text = ""
                            error_msg = f"Text extraction failed for page {page_num + 1}: {str(e)}"
                            processing_errors.append(error_msg)
                            logger.warning(error_msg)
                        
                        # Determine the display page number:
                        # 1. PDF page label (if the PDF defines them)
                        # 2. Printed page number extracted from page text
                        # 3. Physical page index + 1 as last resort
                        page_label = page.get_label() or None
                        if not page_label and page_text.strip():
                            page_label = self._extract_printed_page_number(page_text)
                        if not page_label:
                            page_label = str(page_num + 1)
                        
                        # Append text with page marker
                        try:
                            if page_text.strip():
                                full_text.append(f"[Page {page_label}]\n{page_text}")
                        except Exception as e:
                            error_msg = f"Text extraction failed for page {page_label}: {str(e)}"
                            processing_errors.append(error_msg)
                            logger.warning(error_msg)
                            # Try OCR as fallback (but skip for large PDFs to save memory)
                            if not is_large_pdf:
                                try:
                                    ocr_text = self._ocr_fallback(page, page_num + 1)
                                    if ocr_text:
                                        full_text.append(f"[Page {page_label} - OCR]\n{ocr_text}")
                                except Exception as ocr_e:
                                    processing_errors.append(f"OCR fallback failed for page {page_num + 1}: {str(ocr_e)}")
                        
                        # Extract images (skip for large PDFs if configured)
                        if not (is_large_pdf and self.skip_images_for_large_pdfs):
                            try:
                                page_images = self._extract_images_from_page(page, page_num + 1)
                                # Limit images per page
                                images.extend(page_images[:self.max_images_per_page])
                            except Exception as e:
                                error_msg = f"Image extraction failed for page {page_num + 1}: {str(e)}"
                                processing_errors.append(error_msg)
                                logger.warning(error_msg)
                        
                        # Skip chart extraction for large PDFs (memory intensive)
                        if not is_large_pdf:
                            try:
                                page_charts = self._extract_charts_from_page(page, page_num + 1)
                                charts.extend(page_charts)
                            except Exception as e:
                                error_msg = f"Chart extraction failed for page {page_num + 1}: {str(e)}"
                                processing_errors.append(error_msg)
                                logger.warning(error_msg)
                        
                        successful_pages += 1
                        
                        # Explicitly clear page reference
                        page = None
                        
                    except Exception as e:
                        error_msg = f"Complete page processing failed for page {page_num + 1}: {str(e)}"
                        processing_errors.append(error_msg)
                        logger.warning(error_msg)
                        continue
                
                # Force garbage collection after each batch for large PDFs
                if is_large_pdf and self.gc_after_batch:
                    gc.collect()
                    logger.debug(f"Garbage collection completed after batch {batch_num}")
            
            # Check if we have enough successful pages
            if successful_pages < page_count * self.partial_read_threshold:
                error_msg = f"Only {successful_pages} of {page_count} pages processed successfully"
                processing_errors.append(error_msg)
                if not self.enable_graceful_degradation:
                    raise PDFPartialReadError(error_msg)
            
            # Log summary for large PDFs
            if is_large_pdf:
                logger.info(f"Large PDF extraction complete: {successful_pages}/{page_count} pages, "
                           f"{len(full_text)} text blocks, {len(images)} images")
                if self.skip_images_for_large_pdfs:
                    processing_errors.append("Image extraction was skipped for this large PDF to conserve memory")
            
            # Combine all text
            combined_text = "\n\n".join(full_text) if full_text else "No text could be extracted"
            
            return DocumentContent(
                text=combined_text,
                images=images,
                tables=[],  # Will be filled by pdfplumber
                charts=charts,
                metadata=metadata,
                structure=None  # Will be analyzed separately
            )
            
        finally:
            doc.close()
            # Final garbage collection
            gc.collect()
    
    def _ocr_fallback(self, page: fitz.Page, page_num: int) -> str:
        """
        OCR fallback for pages where text extraction fails.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (1-indexed)
            
        Returns:
            Extracted text via OCR
        """
        try:
            # Render page as image
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            # Convert to PIL Image
            pil_img = Image.open(io.BytesIO(img_data))
            
            # Perform OCR
            ocr_text = pytesseract.image_to_string(pil_img, lang='eng')
            
            pix = None  # Free memory
            
            return ocr_text.strip()
            
        except Exception as e:
            logger.warning(f"OCR fallback failed for page {page_num}: {str(e)}")
            return ""
    
    def _validate_pdf(self, pdf_bytes: bytes) -> None:
        """
        Validate PDF file format and basic integrity.
        
        Args:
            pdf_bytes: PDF file content as bytes
            
        Raises:
            PDFCorruptionError: If PDF is invalid or corrupted
        """
        # Check PDF header
        if not pdf_bytes.startswith(b'%PDF-'):
            raise PDFCorruptionError("Invalid PDF format: missing PDF header")
        
        # Try to open with PyMuPDF for basic validation
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if doc.page_count == 0:
                raise PDFCorruptionError("PDF contains no pages")
            doc.close()
        except Exception as e:
            raise PDFCorruptionError(f"PDF validation failed: {str(e)}")
    
    def _extract_with_pymupdf(self, pdf_bytes: bytes) -> DocumentContent:
        """
        Extract content using PyMuPDF for high-performance processing.
        
        Args:
            pdf_bytes: PDF file content as bytes
            
        Returns:
            DocumentContent: Extracted content
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        try:
            # Extract metadata
            metadata = self._extract_metadata(doc)
            
            # Extract text and images from all pages
            full_text = []
            images = []
            charts = []
            
            for page_num in range(doc.page_count):
                page = doc[page_num]
                
                # Extract text first so we can inspect for printed page number
                page_text = page.get_text()
                
                # Determine display page number:
                # 1. PDF page label  2. Printed page number from text  3. index+1
                page_label = page.get_label() or None
                if not page_label and page_text.strip():
                    page_label = self._extract_printed_page_number(page_text)
                if not page_label:
                    page_label = str(page_num + 1)
                
                if page_text.strip():
                    full_text.append(f"[Page {page_label}]\n{page_text}")
                
                # Extract images
                page_images = self._extract_images_from_page(page, page_num + 1)
                images.extend(page_images)
                
                # Extract vector graphics (charts/diagrams)
                page_charts = self._extract_charts_from_page(page, page_num + 1)
                charts.extend(page_charts)
            
            # Combine all text
            combined_text = "\n\n".join(full_text)
            
            return DocumentContent(
                text=combined_text,
                images=images,
                tables=[],  # Will be filled by pdfplumber
                charts=charts,
                metadata=metadata,
                structure=None  # Will be analyzed separately
            )
            
        finally:
            doc.close()
    
    def _extract_metadata(self, doc: fitz.Document) -> DocumentMetadata:
        """
        Extract document metadata from PDF.
        
        Args:
            doc: PyMuPDF document object
            
        Returns:
            DocumentMetadata: Extracted metadata
        """
        meta = doc.metadata
        
        # Parse creation date
        creation_date = None
        if meta.get('creationDate'):
            try:
                # PyMuPDF returns dates in format "D:YYYYMMDDHHmmSSOHH'mm'"
                date_str = meta['creationDate']
                if date_str.startswith('D:'):
                    date_str = date_str[2:16]  # Extract YYYYMMDDHHMMSS
                    creation_date = datetime.strptime(date_str, '%Y%m%d%H%M%S')
            except (ValueError, TypeError):
                logger.warning(f"Could not parse creation date: {meta.get('creationDate')}")
        
        # Extract keywords
        keywords = []
        if meta.get('keywords'):
            keywords = [kw.strip() for kw in meta['keywords'].split(',') if kw.strip()]
        
        return DocumentMetadata(
            title=meta.get('title', 'Untitled Document'),
            author=meta.get('author'),
            creation_date=creation_date,
            page_count=doc.page_count,
            file_size=0,  # Will be set by caller
            language='en',  # Default, could be detected
            subject=meta.get('subject'),
            keywords=keywords
        )
    
    def _extract_images_from_page(self, page: fitz.Page, page_num: int) -> List[MediaElement]:
        """
        Extract images from a PDF page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (1-indexed)
            
        Returns:
            List of MediaElement objects for images
        """
        images = []
        image_list = page.get_images()
        
        for img_index, img in enumerate(image_list):
            try:
                # Get image data
                xref = img[0]
                pix = fitz.Pixmap(page.parent, xref)
                
                # Convert to PIL Image
                if pix.n - pix.alpha < 4:  # GRAY or RGB
                    img_data = pix.tobytes("png")
                    pil_img = Image.open(io.BytesIO(img_data))
                    
                    # Generate unique ID
                    element_id = f"img_{page_num}_{img_index}_{uuid.uuid4().hex[:8]}"
                    
                    # Create media element
                    media_element = MediaElement(
                        element_id=element_id,
                        element_type="image",
                        content_data=img_data,
                        caption=f"Image from page {page_num}",
                        alt_text=f"Image {img_index + 1} on page {page_num}",
                        metadata={
                            'page_number': page_num,
                            'image_index': img_index,
                            'width': pil_img.width,
                            'height': pil_img.height,
                            'format': 'PNG',
                            'xref': xref
                        }
                    )
                    
                    images.append(media_element)
                
                pix = None  # Free memory
                
            except Exception as e:
                logger.warning(f"Failed to extract image {img_index} from page {page_num}: {str(e)}")
                continue
        
        return images
    
    def _extract_charts_from_page(self, page: fitz.Page, page_num: int) -> List[MediaElement]:
        """
        Extract vector graphics (charts/diagrams) from a PDF page.
        
        Args:
            page: PyMuPDF page object
            page_num: Page number (1-indexed)
            
        Returns:
            List of MediaElement objects for charts/diagrams
        """
        charts = []
        
        try:
            # Get page as image to capture vector graphics
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            # Check if page has significant vector content (heuristic)
            drawings = page.get_drawings()
            if len(drawings) > 5:  # Threshold for considering it a chart/diagram
                element_id = f"chart_{page_num}_{uuid.uuid4().hex[:8]}"
                
                media_element = MediaElement(
                    element_id=element_id,
                    element_type="chart",
                    content_data=img_data,
                    caption=f"Chart/diagram from page {page_num}",
                    alt_text=f"Vector graphics on page {page_num}",
                    metadata={
                        'page_number': page_num,
                        'drawing_count': len(drawings),
                        'format': 'PNG',
                        'is_vector_graphics': True
                    }
                )
                
                charts.append(media_element)
            
            pix = None  # Free memory
            
        except Exception as e:
            logger.warning(f"Failed to extract charts from page {page_num}: {str(e)}")
        
        return charts
    
    def _extract_tables_with_pdfplumber(self, pdf_bytes: bytes) -> List[MediaElement]:
        """
        Extract tables using pdfplumber for detailed layout analysis.
        Uses batched processing for large PDFs to manage memory.
        
        Args:
            pdf_bytes: PDF file content as bytes
            
        Returns:
            List of MediaElement objects for tables
        """
        tables = []
        
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                page_count = len(pdf.pages)
                is_large_pdf = page_count > self.large_pdf_threshold
                
                if is_large_pdf:
                    logger.info(f"Large PDF: Limiting table extraction to first {self.large_pdf_threshold} pages")
                    # For large PDFs, only extract tables from first N pages
                    pages_to_process = pdf.pages[:self.large_pdf_threshold]
                else:
                    pages_to_process = pdf.pages
                
                for page_num, page in enumerate(pages_to_process, 1):
                    try:
                        page_tables = page.extract_tables()
                        
                        for table_index, table_data in enumerate(page_tables):
                            if table_data and len(table_data) > 1:  # Must have header + data
                                # Convert table to structured format
                                table_dict = {
                                    'headers': table_data[0] if table_data[0] else [],
                                    'rows': table_data[1:],
                                    'row_count': len(table_data) - 1,
                                    'col_count': len(table_data[0]) if table_data[0] else 0
                                }
                                
                                # Generate unique ID
                                element_id = f"table_{page_num}_{table_index}_{uuid.uuid4().hex[:8]}"
                                
                                # Serialize table data
                                import json
                                table_json = json.dumps(table_dict, ensure_ascii=False)
                                
                                media_element = MediaElement(
                                    element_id=element_id,
                                    element_type="table",
                                    content_data=table_json.encode('utf-8'),
                                    caption=f"Table from page {page_num}",
                                    alt_text=f"Table {table_index + 1} on page {page_num} "
                                             f"({table_dict['row_count']} rows, {table_dict['col_count']} columns)",
                                    metadata={
                                        'page_number': page_num,
                                        'table_index': table_index,
                                        'row_count': table_dict['row_count'],
                                        'col_count': table_dict['col_count'],
                                        'format': 'JSON'
                                    }
                                )
                                
                                tables.append(media_element)
                    except Exception as e:
                        logger.warning(f"Failed to extract tables from page {page_num}: {str(e)}")
                        continue
                    
                    # Garbage collection every batch_size pages for large PDFs
                    if is_large_pdf and page_num % self.batch_size == 0:
                        gc.collect()
        
        except Exception as e:
            logger.warning(f"Failed to extract tables with pdfplumber: {str(e)}")
        
        return tables
    
    def analyze_structure(self, content: DocumentContent) -> DocumentStructure:
        """
        Analyze document hierarchy and organization.
        
        Args:
            content: DocumentContent object with extracted text
            
        Returns:
            DocumentStructure: Analyzed document structure
        """
        text = content.text
        lines = text.split('\n')
        
        chapters = []
        sections = []
        paragraphs = []
        current_page = 1
        
        # Simple heuristic-based structure analysis
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Track page numbers
            if line.startswith('[Page ') and line.endswith(']'):
                try:
                    current_page = int(line[6:-1])
                except ValueError:
                    pass
                continue
            
            if not line:
                continue
            
            # Detect chapters (common patterns)
            if self._is_chapter_heading(line):
                chapters.append({
                    'title': line,
                    'page': current_page,
                    'line_number': i,
                    'level': 1
                })
            
            # Detect sections
            elif self._is_section_heading(line):
                sections.append({
                    'title': line,
                    'page': current_page,
                    'line_number': i,
                    'level': 2
                })
            
            # Detect paragraphs (non-empty lines that aren't headings)
            elif len(line) > 20 and not self._is_heading(line):
                paragraphs.append({
                    'content': line[:100] + '...' if len(line) > 100 else line,
                    'page': current_page,
                    'line_number': i,
                    'word_count': len(line.split())
                })
        
        # Check for table of contents
        has_toc = self._detect_table_of_contents(text)
        
        return DocumentStructure(
            chapters=chapters,
            sections=sections,
            paragraphs=paragraphs,
            page_count=content.metadata.page_count if content.metadata else 0,
            has_toc=has_toc
        )
    
    def _is_chapter_heading(self, line: str) -> bool:
        """Check if line is likely a chapter heading."""
        line_lower = line.lower()
        
        # Common chapter patterns
        chapter_patterns = [
            'chapter ', 'chap ', 'ch. ', 'ch ', 
            'part ', 'section ', 'unit ',
            'book ', 'volume ', 'vol '
        ]
        
        # Check for numbered chapters
        if any(line_lower.startswith(pattern) for pattern in chapter_patterns):
            return True
        
        # Check for Roman numerals or numbers at start
        import re
        if re.match(r'^[IVX]+\.?\s+', line) or re.match(r'^\d+\.?\s+', line):
            return len(line) < 100  # Headings are usually short
        
        # All caps and short (likely heading)
        if line.isupper() and 10 <= len(line) <= 80:
            return True
        
        return False
    
    def _is_section_heading(self, line: str) -> bool:
        """Check if line is likely a section heading."""
        # Numbered sections
        import re
        if re.match(r'^\d+\.\d+', line):
            return len(line) < 100
        
        # Subsection patterns
        if line.startswith(('A. ', 'B. ', 'C. ', 'a. ', 'b. ', 'c. ')):
            return len(line) < 100
        
        # Title case and reasonable length
        if line.istitle() and 10 <= len(line) <= 80:
            return True
        
        return False
    
    def _is_heading(self, line: str) -> bool:
        """Check if line is any type of heading."""
        return self._is_chapter_heading(line) or self._is_section_heading(line)
    
    def _detect_table_of_contents(self, text: str) -> bool:
        """Detect if document has a table of contents."""
        text_lower = text.lower()
        
        toc_indicators = [
            'table of contents',
            'contents',
            'index',
            'chapter 1',
            'page 1',
            '...........'  # Common TOC formatting
        ]
        
        # Look for multiple TOC indicators
        found_indicators = sum(1 for indicator in toc_indicators if indicator in text_lower)
        return found_indicators >= 2