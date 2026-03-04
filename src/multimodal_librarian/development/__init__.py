"""
Development optimization module for Multimodal Librarian.

This module provides development-specific optimizations that enhance
the local development experience.
"""

from .dev_optimizer import (
    DevelopmentOptimizer,
    get_development_optimizer,
    apply_development_optimizations,
    is_development_optimization_enabled,
    get_optimization_recommendations
)

__all__ = [
    'DevelopmentOptimizer',
    'get_development_optimizer', 
    'apply_development_optimizations',
    'is_development_optimization_enabled',
    'get_optimization_recommendations'
]