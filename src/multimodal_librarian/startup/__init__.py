"""
Startup management module for the Multimodal Librarian application.

This module provides components for managing application startup phases,
progressive model loading, and health check optimization.
"""

from .phase_manager import StartupPhaseManager, StartupPhase

__all__ = ["StartupPhaseManager", "StartupPhase"]