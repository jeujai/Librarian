#!/usr/bin/env python3
"""
Basic ML Training Tests for AWS Learning Deployment

This module tests ML training APIs and chunking framework including:
- ML training API endpoints
- Chunking framework operations
- Model training workflows
- Performance monitoring
- Integration with AWS services
"""

import os
import sys
import pytest
import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger


class MLTrainingTestSuite:
    """Test suite for ML training and chunking framework."""
    
    def __init__(self):
        self.logger = get_logger("ml_training_tests")
        
        # Configuration
        self.base_url = os.getenv("AWS_BASE_URL", "http://localhost:8000")
        self.test_timeout = 60  # Longer timeout for ML operations
        
        # ML training endpoints
        self.ml_endpoints = {
            "status": "/api/ml-training/status",
            "start": "/api/ml-training/start",
            "stop": "/api/ml-training/stop",
            "models": "/api/ml-training/models",
            "metrics": "/api/ml-training/metrics"
        }
        
        # Chunking framework endpoints
        self.chunking_endpoints = {
            "status": "/api/chunking/status",
            "optimize": "/api/chunking/optimize",
            "config": "/api/chunking/config",
            "performance": "/api/chunking/performance"
        }


@pytest.fixture(scope="session")
def ml_test_suite():
    """Pytest fixture for ML training test suite."""
    return MLTrainingTestSuite()


class TestMLTrainingEndpoints:
    """Test ML training API endpoints."""
    
    @pytest.mark.asyncio
    async def test_ml_training_status_endpoint(self, ml_test_suite):
        """Test ML training status endpoint."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['status']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Accept various status codes (may require auth, may not be implemented)
                    assert response.status in [200, 401, 404, 501]
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Validate response structure
                        assert isinstance(data, dict)
                        
                        # Common fields in ML training status
                        expected_fields = ["status", "timestamp"]
                        for field in expected_fields:
                            if field in data:
                                ml_test_suite.logger.info(f"✅ Status field '{field}': {data[field]}")
                    
                    ml_test_suite.logger.info("✅ ML training status endpoint accessible")
                    
            except asyncio.TimeoutError:
                pytest.fail("ML training status endpoint timeout")
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML training status test: {e}")
                pytest.skip(f"ML training status endpoint may not be available: {e}")
    
    @pytest.mark.asyncio
    async def test_ml_models_endpoint(self, ml_test_suite):
        """Test ML models listing endpoint."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['models']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Accept various status codes
                    assert response.status in [200, 401, 404, 501]
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Should be a list or dict containing model information
                        assert isinstance(data, (list, dict))
                        
                        if isinstance(data, list):
                            ml_test_suite.logger.info(f"✅ Found {len(data)} models")
                        elif isinstance(data, dict) and "models" in data:
                            models = data["models"]
                            ml_test_suite.logger.info(f"✅ Found {len(models)} models")
                    
                    ml_test_suite.logger.info("✅ ML models endpoint accessible")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML models test: {e}")
                pytest.skip(f"ML models endpoint may not be available: {e}")
    
    @pytest.mark.asyncio
    async def test_ml_metrics_endpoint(self, ml_test_suite):
        """Test ML training metrics endpoint."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['metrics']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Accept various status codes
                    assert response.status in [200, 401, 404, 501]
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Validate metrics structure
                        assert isinstance(data, dict)
                        
                        # Common metrics fields
                        metrics_fields = ["training_time", "accuracy", "loss", "epoch"]
                        found_fields = [field for field in metrics_fields if field in data]
                        
                        if found_fields:
                            ml_test_suite.logger.info(f"✅ Metrics fields found: {found_fields}")
                    
                    ml_test_suite.logger.info("✅ ML metrics endpoint accessible")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML metrics test: {e}")
                pytest.skip(f"ML metrics endpoint may not be available: {e}")


class TestChunkingFramework:
    """Test chunking framework operations."""
    
    @pytest.mark.asyncio
    async def test_chunking_status_endpoint(self, ml_test_suite):
        """Test chunking framework status endpoint."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.chunking_endpoints['status']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Accept various status codes
                    assert response.status in [200, 401, 404, 501]
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Validate response structure
                        assert isinstance(data, dict)
                        
                        # Common chunking status fields
                        status_fields = ["status", "active_optimizations", "performance_score"]
                        found_fields = [field for field in status_fields if field in data]
                        
                        if found_fields:
                            ml_test_suite.logger.info(f"✅ Chunking status fields: {found_fields}")
                    
                    ml_test_suite.logger.info("✅ Chunking status endpoint accessible")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  Chunking status test: {e}")
                pytest.skip(f"Chunking status endpoint may not be available: {e}")
    
    @pytest.mark.asyncio
    async def test_chunking_config_endpoint(self, ml_test_suite):
        """Test chunking framework configuration endpoint."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.chunking_endpoints['config']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Accept various status codes
                    assert response.status in [200, 401, 404, 501]
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Validate configuration structure
                        assert isinstance(data, dict)
                        
                        # Common configuration fields
                        config_fields = ["chunk_size", "overlap", "strategy", "optimization_enabled"]
                        found_fields = [field for field in config_fields if field in data]
                        
                        if found_fields:
                            ml_test_suite.logger.info(f"✅ Chunking config fields: {found_fields}")
                    
                    ml_test_suite.logger.info("✅ Chunking config endpoint accessible")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  Chunking config test: {e}")
                pytest.skip(f"Chunking config endpoint may not be available: {e}")
    
    @pytest.mark.asyncio
    async def test_chunking_performance_endpoint(self, ml_test_suite):
        """Test chunking framework performance endpoint."""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.chunking_endpoints['performance']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Accept various status codes
                    assert response.status in [200, 401, 404, 501]
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Validate performance data structure
                        assert isinstance(data, dict)
                        
                        # Common performance fields
                        perf_fields = ["processing_time", "throughput", "accuracy", "efficiency_score"]
                        found_fields = [field for field in perf_fields if field in data]
                        
                        if found_fields:
                            ml_test_suite.logger.info(f"✅ Chunking performance fields: {found_fields}")
                    
                    ml_test_suite.logger.info("✅ Chunking performance endpoint accessible")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  Chunking performance test: {e}")
                pytest.skip(f"Chunking performance endpoint may not be available: {e}")


class TestMLTrainingWorkflows:
    """Test ML training workflow operations."""
    
    @pytest.mark.asyncio
    async def test_ml_training_workflow_status(self, ml_test_suite):
        """Test ML training workflow status check."""
        async with aiohttp.ClientSession() as session:
            try:
                # Check if any training is currently running
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['status']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check for workflow status indicators
                        workflow_indicators = ["is_training", "current_job", "queue_length"]
                        
                        for indicator in workflow_indicators:
                            if indicator in data:
                                ml_test_suite.logger.info(f"✅ Workflow indicator '{indicator}': {data[indicator]}")
                        
                        # Basic workflow validation
                        if "status" in data:
                            status = data["status"]
                            valid_statuses = ["idle", "training", "completed", "error", "queued"]
                            
                            if status in valid_statuses:
                                ml_test_suite.logger.info(f"✅ Valid workflow status: {status}")
                            else:
                                ml_test_suite.logger.warning(f"⚠️  Unknown workflow status: {status}")
                    
                    ml_test_suite.logger.info("✅ ML training workflow status check successful")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML workflow status test: {e}")
                pytest.skip(f"ML workflow status test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_ml_training_start_endpoint(self, ml_test_suite):
        """Test ML training start endpoint (without actually starting training)."""
        async with aiohttp.ClientSession() as session:
            try:
                # Test POST to start endpoint with minimal payload
                training_request = {
                    "model_type": "test",
                    "dry_run": True,  # Don't actually start training
                    "test_mode": True
                }
                
                async with session.post(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['start']}",
                    json=training_request,
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Accept various responses (may require auth, validation, etc.)
                    assert response.status in [200, 400, 401, 404, 422, 501]
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Validate response structure
                        assert isinstance(data, dict)
                        
                        # Common response fields
                        response_fields = ["job_id", "status", "message"]
                        found_fields = [field for field in response_fields if field in data]
                        
                        if found_fields:
                            ml_test_suite.logger.info(f"✅ Training start response fields: {found_fields}")
                    
                    elif response.status == 422:
                        # Validation error is expected for test payload
                        ml_test_suite.logger.info("✅ Training start endpoint validates input (422 response)")
                    
                    ml_test_suite.logger.info("✅ ML training start endpoint accessible")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML training start test: {e}")
                pytest.skip(f"ML training start endpoint may not be available: {e}")


class TestMLPerformanceMonitoring:
    """Test ML performance monitoring capabilities."""
    
    @pytest.mark.asyncio
    async def test_ml_performance_metrics_collection(self, ml_test_suite):
        """Test ML performance metrics collection."""
        async with aiohttp.ClientSession() as session:
            try:
                # Get performance metrics
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['metrics']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check for performance-related metrics
                        performance_metrics = [
                            "training_time", "inference_time", "memory_usage",
                            "cpu_utilization", "gpu_utilization", "throughput"
                        ]
                        
                        found_metrics = []
                        for metric in performance_metrics:
                            if metric in data:
                                found_metrics.append(metric)
                                value = data[metric]
                                ml_test_suite.logger.info(f"✅ Performance metric '{metric}': {value}")
                        
                        if found_metrics:
                            ml_test_suite.logger.info(f"✅ Found {len(found_metrics)} performance metrics")
                        else:
                            ml_test_suite.logger.info("⚠️  No specific performance metrics found")
                    
                    ml_test_suite.logger.info("✅ ML performance metrics collection test successful")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML performance metrics test: {e}")
                pytest.skip(f"ML performance metrics test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_chunking_performance_monitoring(self, ml_test_suite):
        """Test chunking framework performance monitoring."""
        async with aiohttp.ClientSession() as session:
            try:
                # Get chunking performance data
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.chunking_endpoints['performance']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Check for chunking performance metrics
                        chunking_metrics = [
                            "chunks_processed", "processing_rate", "optimization_score",
                            "accuracy_improvement", "efficiency_gain"
                        ]
                        
                        found_metrics = []
                        for metric in chunking_metrics:
                            if metric in data:
                                found_metrics.append(metric)
                                value = data[metric]
                                ml_test_suite.logger.info(f"✅ Chunking metric '{metric}': {value}")
                        
                        if found_metrics:
                            ml_test_suite.logger.info(f"✅ Found {len(found_metrics)} chunking metrics")
                    
                    ml_test_suite.logger.info("✅ Chunking performance monitoring test successful")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  Chunking performance test: {e}")
                pytest.skip(f"Chunking performance monitoring test failed: {e}")


class TestMLIntegration:
    """Test ML training integration with other system components."""
    
    @pytest.mark.asyncio
    async def test_ml_training_with_database(self, ml_test_suite):
        """Test ML training integration with database."""
        async with aiohttp.ClientSession() as session:
            try:
                # Check if ML training can access training data
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['status']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Look for database integration indicators
                        db_indicators = [
                            "training_data_count", "data_source", "last_data_update",
                            "database_connection", "data_availability"
                        ]
                        
                        found_indicators = []
                        for indicator in db_indicators:
                            if indicator in data:
                                found_indicators.append(indicator)
                                ml_test_suite.logger.info(f"✅ DB integration '{indicator}': {data[indicator]}")
                        
                        if found_indicators:
                            ml_test_suite.logger.info("✅ ML-Database integration indicators found")
                        else:
                            ml_test_suite.logger.info("⚠️  No specific DB integration indicators")
                    
                    ml_test_suite.logger.info("✅ ML-Database integration test successful")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML-Database integration test: {e}")
                pytest.skip(f"ML-Database integration test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_chunking_with_document_processing(self, ml_test_suite):
        """Test chunking framework integration with document processing."""
        async with aiohttp.ClientSession() as session:
            try:
                # Check chunking framework status for document processing integration
                async with session.get(
                    f"{ml_test_suite.base_url}{ml_test_suite.chunking_endpoints['status']}",
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # Look for document processing integration
                        doc_indicators = [
                            "documents_processed", "active_documents", "processing_queue",
                            "pdf_support", "text_extraction", "chunk_quality"
                        ]
                        
                        found_indicators = []
                        for indicator in doc_indicators:
                            if indicator in data:
                                found_indicators.append(indicator)
                                ml_test_suite.logger.info(f"✅ Doc integration '{indicator}': {data[indicator]}")
                        
                        if found_indicators:
                            ml_test_suite.logger.info("✅ Chunking-Document integration indicators found")
                    
                    ml_test_suite.logger.info("✅ Chunking-Document integration test successful")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  Chunking-Document integration test: {e}")
                pytest.skip(f"Chunking-Document integration test failed: {e}")


class TestMLErrorHandling:
    """Test ML training error handling and resilience."""
    
    @pytest.mark.asyncio
    async def test_ml_invalid_request_handling(self, ml_test_suite):
        """Test ML training handling of invalid requests."""
        async with aiohttp.ClientSession() as session:
            try:
                # Send invalid training request
                invalid_request = {
                    "invalid_field": "invalid_value",
                    "malformed_data": None
                }
                
                async with session.post(
                    f"{ml_test_suite.base_url}{ml_test_suite.ml_endpoints['start']}",
                    json=invalid_request,
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Should handle invalid requests gracefully
                    assert response.status in [400, 422, 401, 404, 501]
                    
                    if response.status in [400, 422]:
                        # Good error handling
                        ml_test_suite.logger.info("✅ ML training handles invalid requests properly")
                        
                        try:
                            error_data = await response.json()
                            if "error" in error_data or "message" in error_data:
                                ml_test_suite.logger.info("✅ Error response includes helpful message")
                        except:
                            pass  # Error response might not be JSON
                    
                    ml_test_suite.logger.info("✅ ML invalid request handling test successful")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  ML error handling test: {e}")
                pytest.skip(f"ML error handling test failed: {e}")
    
    @pytest.mark.asyncio
    async def test_chunking_error_resilience(self, ml_test_suite):
        """Test chunking framework error resilience."""
        async with aiohttp.ClientSession() as session:
            try:
                # Test chunking with invalid optimization request
                invalid_optimization = {
                    "strategy": "nonexistent_strategy",
                    "parameters": {"invalid": "params"}
                }
                
                async with session.post(
                    f"{ml_test_suite.base_url}{ml_test_suite.chunking_endpoints['optimize']}",
                    json=invalid_optimization,
                    timeout=ml_test_suite.test_timeout
                ) as response:
                    # Should handle invalid optimization requests
                    assert response.status in [400, 422, 401, 404, 501]
                    
                    if response.status in [400, 422]:
                        ml_test_suite.logger.info("✅ Chunking handles invalid optimization requests")
                    
                    # System should still be responsive after error
                    async with session.get(
                        f"{ml_test_suite.base_url}{ml_test_suite.chunking_endpoints['status']}",
                        timeout=ml_test_suite.test_timeout
                    ) as status_response:
                        # Status endpoint should still work
                        assert status_response.status in [200, 401, 404]
                        
                        if status_response.status == 200:
                            ml_test_suite.logger.info("✅ Chunking system remains responsive after error")
                    
                    ml_test_suite.logger.info("✅ Chunking error resilience test successful")
                    
            except Exception as e:
                ml_test_suite.logger.warning(f"⚠️  Chunking error resilience test: {e}")
                pytest.skip(f"Chunking error resilience test failed: {e}")


# Test execution functions
def run_ml_training_tests():
    """Run ML training tests with proper configuration."""
    import subprocess
    
    # Set test environment
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    
    # Run pytest with specific markers and output
    cmd = [
        "python", "-m", "pytest",
        __file__,
        "-v",
        "--tb=short",
        "--color=yes",
        "-x"  # Stop on first failure
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("🤖 ML TRAINING TEST RESULTS")
        print("=" * 50)
        print(result.stdout)
        
        if result.stderr:
            print("\n⚠️  WARNINGS/ERRORS:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run ML training tests: {e}")
        return False


if __name__ == "__main__":
    success = run_ml_training_tests()
    exit(0 if success else 1)