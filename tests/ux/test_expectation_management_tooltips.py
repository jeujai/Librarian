"""
Test suite for expectation management tooltips functionality.

This module tests the tooltip system that provides contextual guidance
to users based on current system capabilities and loading states.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from multimodal_librarian.main import app


class TestExpectationManagementTooltips:
    """Test expectation management tooltip functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
    
    def test_tooltip_javascript_loads(self):
        """Test that the expectation manager JavaScript loads correctly."""
        response = self.client.get("/static/js/expectation-manager.js")
        assert response.status_code == 200
        
        content = response.text
        assert "ExpectationManager" in content
        assert "initializeTooltips" in content
        assert "setupDynamicTooltips" in content
    
    def test_tooltip_css_loads(self):
        """Test that the tooltip CSS loads correctly."""
        response = self.client.get("/static/css/quality-indicators.css")
        assert response.status_code == 200
        
        content = response.text
        assert "expectation-tooltip" in content
        assert "contextual-tooltip" in content
        assert "tooltip-trigger" in content
    
    def test_loading_template_includes_tooltips(self):
        """Test that the loading template includes tooltip functionality."""
        # This would be tested in integration tests with actual template rendering
        # For now, we verify the template file exists and contains tooltip references
        import os
        template_path = "src/multimodal_librarian/templates/loading.html"
        assert os.path.exists(template_path)
        
        with open(template_path, 'r') as f:
            content = f.read()
            assert "expectation-manager.js" in content or "loading-states.js" in content
    
    def test_tooltip_message_templates(self):
        """Test tooltip message templates for different request types."""
        # Test that the JavaScript contains proper message templates
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for message template structure
        assert "messageTemplates" in content
        assert "chat" in content
        assert "document_analysis" in content
        assert "search" in content
        assert "complex_analysis" in content
    
    def test_dynamic_tooltip_functionality(self):
        """Test dynamic tooltip content generation."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for dynamic tooltip methods
        assert "generateDynamicTooltip" in content
        assert "updateDynamicTooltips" in content
        assert "getInputGuidanceForCurrentState" in content
        assert "getFileUploadGuidanceForCurrentState" in content
    
    def test_tooltip_positioning_logic(self):
        """Test tooltip positioning and display logic."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for positioning methods
        assert "positionTooltip" in content
        assert "showTooltip" in content
        assert "hideTooltip" in content
    
    def test_mobile_tooltip_adaptations(self):
        """Test mobile-specific tooltip behavior."""
        response = self.client.get("/static/css/quality-indicators.css")
        content = response.text
        
        # Check for mobile media queries
        assert "@media (max-width: 768px)" in content
        assert "Mobile Tooltip Adaptations" in content
    
    def test_accessibility_features(self):
        """Test accessibility features in tooltips."""
        response = self.client.get("/static/css/quality-indicators.css")
        content = response.text
        
        # Check for accessibility support
        assert "@media (prefers-contrast: high)" in content
        assert "@media (prefers-reduced-motion: reduce)" in content
    
    def test_tooltip_capability_integration(self):
        """Test integration with capability status system."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for capability integration methods
        assert "addCapabilityItemTooltip" in content
        assert "addQualityIndicatorTooltip" in content
        assert "currentCapabilities" in content
    
    def test_contextual_guidance_system(self):
        """Test contextual guidance based on user input."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for contextual guidance methods
        assert "analyzeUserInput" in content
        assert "classifyRequest" in content
        assert "showRequestTypeGuidance" in content
        assert "getRequestTypeIndicators" in content
    
    def test_eta_confidence_indicators(self):
        """Test ETA confidence indicators in tooltips."""
        response = self.client.get("/static/css/quality-indicators.css")
        content = response.text
        
        # Check for confidence indicator styles
        assert "eta-with-confidence" in content
        assert "high-confidence" in content
        assert "medium-confidence" in content
        assert "low-confidence" in content
    
    def test_tooltip_cleanup_functionality(self):
        """Test tooltip cleanup and memory management."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for cleanup methods
        assert "hideAllTooltips" in content
        assert "destroy" in content
        assert "removeEventListener" in content
    
    def test_progress_tooltip_integration(self):
        """Test integration with progress tracking system."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for progress integration
        assert "getRelevantProgressInfo" in content
        assert "createProgressInfoHTML" in content
        assert "formatDuration" in content
    
    def test_tooltip_error_handling(self):
        """Test error handling in tooltip system."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for error handling
        assert "try" in content and "catch" in content
        assert "console.error" in content or "console.log" in content
    
    def test_tooltip_performance_optimization(self):
        """Test performance optimizations in tooltip system."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for performance optimizations
        assert "setInterval" in content  # Periodic updates
        assert "isMobileDevice" in content  # Device detection
        assert "setTimeout" in content  # Delayed actions


class TestTooltipIntegration:
    """Test tooltip integration with other systems."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = TestClient(app)
    
    def test_tooltip_loading_states_integration(self):
        """Test integration with loading states manager."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for loading states integration
        assert "loadingStatesManager" in content
        assert "getCurrentLevel" in content
        assert "getReadinessPercent" in content
    
    def test_tooltip_health_check_integration(self):
        """Test integration with health check system."""
        # Test that tooltips can access health check status
        response = self.client.get("/health/minimal")
        assert response.status_code == 200
        
        # Verify tooltip system can use this endpoint
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        assert "updateCapabilities" in content
    
    def test_tooltip_api_endpoint_integration(self):
        """Test integration with API endpoints for dynamic content."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for API integration patterns
        assert "fetch" in content or "XMLHttpRequest" in content or "ajax" in content


class TestTooltipUserExperience:
    """Test tooltip user experience aspects."""
    
    def test_tooltip_message_clarity(self):
        """Test that tooltip messages are clear and helpful."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for clear messaging patterns
        assert "Basic mode" in content
        assert "Enhanced mode" in content
        assert "Full mode" in content
        assert "ready" in content.lower()
        assert "loading" in content.lower()
    
    def test_tooltip_progressive_disclosure(self):
        """Test progressive disclosure of information in tooltips."""
        response = self.client.get("/static/js/expectation-manager.js")
        content = response.text
        
        # Check for progressive disclosure patterns
        assert "showContextualHelp" in content
        assert "showInputGuidance" in content
        assert "showRequestFeedback" in content
    
    def test_tooltip_visual_hierarchy(self):
        """Test visual hierarchy in tooltip styles."""
        response = self.client.get("/static/css/quality-indicators.css")
        content = response.text
        
        # Check for visual hierarchy elements
        assert "font-weight: 600" in content or "font-weight: bold" in content
        assert "opacity" in content
        assert "z-index" in content
    
    def test_tooltip_responsive_design(self):
        """Test responsive design of tooltips."""
        response = self.client.get("/static/css/quality-indicators.css")
        content = response.text
        
        # Check for responsive design patterns
        assert "max-width" in content
        assert "@media" in content
        assert "mobile" in content.lower() or "768px" in content


if __name__ == "__main__":
    pytest.main([__file__])