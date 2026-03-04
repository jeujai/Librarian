"""Text utility functions for content processing.

This module provides utilities for text manipulation, including
truncation functions that preserve word boundaries.
"""

from typing import Tuple


def truncate_content(content: str, max_length: int = 1000) -> Tuple[str, bool]:
    """Truncate content at word boundaries when possible.
    
    This function truncates text content to a maximum length while attempting
    to preserve word boundaries. If the content is shorter than max_length,
    it is returned unchanged.
    
    Args:
        content: The text content to truncate
        max_length: Maximum length of the output string (default: 1000)
    
    Returns:
        A tuple of (truncated_content, was_truncated) where:
        - truncated_content: The possibly truncated string, ending with "..." if truncated
        - was_truncated: True if the content was truncated, False otherwise
    
    Examples:
        >>> truncate_content("Hello world", 100)
        ('Hello world', False)
        >>> truncate_content("Hello world", 8)
        ('Hello...', True)
    """
    if not content:
        return content, False
    
    if len(content) <= max_length:
        return content, False
    
    # Reserve space for ellipsis
    effective_max = max_length - 3
    
    if effective_max <= 0:
        # Edge case: max_length is too small for meaningful truncation
        return "...", True
    
    # Try to find a word boundary (space) to truncate at
    truncated = content[:effective_max]
    
    # Look for the last space within the truncated portion
    last_space = truncated.rfind(' ')
    
    if last_space > 0:
        # Truncate at word boundary
        truncated = truncated[:last_space]
    # else: no space found, truncate at character boundary
    
    return truncated + "...", True
