#!/usr/bin/env python3
"""
Search-related models and data structures.

This module contains models used across the search and vector store components
to avoid circular import issues.

DEPRECATED: This module is kept for backward compatibility.
New code should import from search_types.py instead.
"""

# Import from the new search_types module for backward compatibility
from .search_types import SearchResult, SearchQuery, SearchResponse

# Re-export for backward compatibility
__all__ = ['SearchResult', 'SearchQuery', 'SearchResponse']