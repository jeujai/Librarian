"""
PDF Processing Component.

This component handles extraction of text, images, charts, and metadata from PDF files
while preserving document structure and maintaining associations between text and media elements.
Includes comprehensive error handling and graceful degradation for corrupted or problematic PDFs.
"""

from .pdf_processor import (
    PDFProcessor,
    PDFProcessingError,
    PDFCorruptionError,
    PDFPartialReadError,
    PDFValidationError
)

__all__ = [
    "PDFProcessor",
    "PDFProcessingError", 
    "PDFCorruptionError",
    "PDFPartialReadError",
    "PDFValidationError"
]