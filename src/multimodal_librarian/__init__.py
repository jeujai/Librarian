"""
Multimodal Librarian - A conversational web-based knowledge management system.

This package provides a comprehensive system for processing PDF books with multimodal content,
storing them in a vector database, and enabling conversational queries with multimedia output.
"""

__version__ = "0.1.0"
__author__ = "Multimodal Librarian Team"
__email__ = "team@multimodal-librarian.com"

from .config import Settings, get_settings

__all__ = ["Settings", "get_settings"]# Cache bust: Wed Jan 21 00:02:34 MST 2026
