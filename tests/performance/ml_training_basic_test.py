#!/usr/bin/env python3
"""
ML Training Performance Testing for AWS Learning Deployment

This module provides performance testing for ML training APIs and the
adaptive chunking framework. Designed for learning-oriented testing
with cost-optimized scenarios.

Test Scenarios:
- ML training API performance under load
- Chunking framework performance testing
- Document processing pipeline testing
- Vector database operations testing
- Knowledge graph operations testing
"""

import os
import sys
import asyncio
import aiohttp
import json
import time
import tempfile
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import io
import base64

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger


@dataclass
class MLPerformanceResult:
    """ML training performance test result."""
    test_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    total_operations: int
    successful_operations: int
    failed_operations: int
    avg_processing_time_ms: float
    max_processing_time_ms: float
    min_processing_time_ms: float
    throughput_ops_per_sec: float
    avg_response_size_kb: float
    success_rate_percent: float
    errors: List[str]


class MLTrainingLoadTester:
    """Performance tester for ML training and processing APIs."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.logger = get_logger("ml_training_load_tester")
        
        # Test tracking
        self.processing_times = []
        self.response_sizes = []
        self.errors = []
        
        self.logger.info(f"Initialized ML training load tester for {self.base_url}")
    
    async def run_ml_performance_tests(
        self, 
        concurrent_operations: int = 5, 
        operations_per_test: int = 10,
        test_duration: int = 120
    ) -> Dict[str, Any]:
        """Run comprehensive ML training performance tests."""
        
        self.logger.info("🚀 Starting ML training performance tests")
        
        test_results = {
            "start_time": datetime.now(),
            "config": {
                "concurrent_operations": concurrent_operations,
                "operations_per_test": operations_per_test,
                "test_duration_seconds": test_duration,
                "base_url": self.base_url
            },
            "test_results": [],
            "summary": {}
        }
        
        print("=" * 80)
        print("🤖 ML TRAINING PERFORMANCE TEST SUITE")
        print("=" * 80)
        print(f"📅 Started: {test_results['start_time'].isoformat()}")
        print(f"🎯 Target: {self.base_url}")
        print(f"⚙️  Concurrent Operations: {concurrent_operations}")
        print(f"📊 Operations per Test: {operations_per_test}")
        print()
        
        # Test scenarios
        test_scenarios = [
            {
                "name": "Document Processing Performance",
                "description": "Test document upload and processing performance",
                "test_func": self._test_document_processing,
                "params": {"concurrent_ops": concurrent_operations, "operations": operations_per_test}
            },
            {
                "name": "Chunking Framework Performance",
                "description": "Test adaptive chunking framework under load",
                "test_func": self._test_chunking_performance,
                "params": {"concurrent_ops": concurrent_operations, "operations": operations_per_test}
            },
            {
                "name": "Vector Search Performance",
                "description": "Test vector database search operations",
                "test_func": self._test_vector_search,
                "params": {"concurrent_ops": concurrent_operations, "operations": operations_per_test}
            },
            {
                "name": "Knowledge Graph Performance",
                "description": "Test knowledge graph operations",
                "test_func": self._test_knowledge_graph,
                "params": {"concurrent_ops": concurrent_operations, "operations": operations_per_test}
            },
            {
                "name": "ML Training API Performance",
                "description": "Test ML training API endpoints",
                "test_func": self._test_ml_training_api,
                "params": {"concurrent_ops": min(concurrent_operations, 3), "operations": operations_per_test}
            }
        ]
        
        # Run each test scenario
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"📋 [{i}/{len(test_scenarios)}] {scenario['name']}")
            print(f"   {scenario['description']}")
            print("-" * 60)
            
            try:
                # Reset metrics for each test
                self._reset_metrics()
                
                result = await scenario['test_func'](**scenario['params'])
                test_results["test_results"].append(result)
                
                # Print scenario summary
                self._print_ml_test_summary(result)
                
            except Exception as e:
                self.logger.error(f"Error in scenario {scenario['name']}: {e}")
                error_result = MLPerformanceResult(
                    test_name=scenario['name'],
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    duration_seconds=0,
                    total_operations=0,
                    successful_operations=0,
                    failed_operations=operations_per_test,
                    avg_processing_time_ms=0,
                    max_processing_time_ms=0,
                    min_processing_time_ms=0,
                    throughput_ops_per_sec=0,
                    avg_response_size_kb=0,
                    success_rate_percent=0,
                    errors=[str(e)]
                )
                test_results["test_results"].append(error_result)
            
            print()
        
        # Calculate final summary
        test_results["end_time"] = datetime.now()
        test_results["total_duration"] = (
            test_results["end_time"] - test_results["start_time"]
        ).total_seconds()
        test_results["summary"] = self._calculate_ml_suite_summary(test_results["test_results"])
        
        # Print final summary
        self._print_ml_suite_summary(test_results)
        
        return test_results
    
    def _reset_metrics(self):
        """Reset metrics for a new test."""
        self.processing_times = []
        self.response_sizes = []
        self.errors = []
    
    async def _test_document_processing(self, concurrent_ops: int, operations: int) -> MLPerformanceResult:
        """Test document processing performance."""
        self.logger.info(f"Testing document processing: {concurrent_ops} concurrent, {operations} operations")
        
        start_time = datetime.now()
        
        # Create test documents
        test_documents = self._create_test_documents(operations)
        
        # Create processing tasks
        tasks = []
        for i in range(concurrent_ops):
            docs_per_task = operations // concurrent_ops
            if i < operations % concurrent_ops:
                docs_per_task += 1
            
            start_idx = i * (operations // concurrent_ops)
            end_idx = start_idx + docs_per_task
            task_docs = test_documents[start_idx:end_idx]
            
            task = asyncio.create_task(
                self._process_documents_batch(task_docs, i)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful vs failed operations
        successful_operations = 0
        failed_operations = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_operations += operations // concurrent_ops
                self.errors.append(str(result))
            else:
                successful, failed = result
                successful_operations += successful
                failed_operations += failed
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return self._create_ml_result(
            "Document Processing Performance",
            start_time, end_time, duration,
            operations, successful_operations, failed_operations
        )
    
    def _create_test_documents(self, count: int) -> List[Dict[str, Any]]:
        """Create test documents for processing."""
        documents = []
        
        for i in range(count):
            # Create a simple text document
            content = f"""
            Test Document {i+1}
            
            This is a test document for performance testing of the ML training system.
            It contains multiple paragraphs to test the chunking framework.
            
            The document includes various types of content:
            - Text paragraphs
            - Lists and bullet points
            - Technical information
            
            This content will be processed by the adaptive chunking framework
            to test its performance under load conditions.
            
            Document ID: {i+1}
            Timestamp: {datetime.now().isoformat()}
            """
            
            # Encode as base64 for upload simulation
            content_bytes = content.encode('utf-8')
            content_b64 = base64.b64encode(content_bytes).decode('utf-8')
            
            documents.append({
                "filename": f"test_document_{i+1}.txt",
                "content": content_b64,
                "content_type": "text/plain",
                "size": len(content_bytes)
            })
        
        return documents
    
    async def _process_documents_batch(self, documents: List[Dict], batch_id: int) -> tuple:
        """Process a batch of documents."""
        successful = 0
        failed = 0
        
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for doc in documents:
                    try:
                        start_time = time.time()
                        
                        # Upload document
                        async with session.post(
                            f"{self.base_url}/api/documents/upload",
                            json=doc,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            response_data = await response.read()
                            processing_time = (time.time() - start_time) * 1000
                            
                            self.processing_times.append(processing_time)
                            self.response_sizes.append(len(response_data))
                            
                            if response.status < 400:
                                successful += 1
                            else:
                                failed += 1
                                self.errors.append(f"Upload failed: HTTP {response.status}")
                        
                        # Small delay between operations
                        await asyncio.sleep(0.1)
                        
                    except Exception as e:
                        failed += 1
                        self.errors.append(f"Document processing error: {str(e)}")
                
                return successful, failed
                
        except Exception as e:
            self.errors.append(f"Batch {batch_id} error: {str(e)}")
            return successful, len(documents) - successful
    
    async def _test_chunking_performance(self, concurrent_ops: int, operations: int) -> MLPerformanceResult:
        """Test chunking framework performance."""
        self.logger.info(f"Testing chunking performance: {concurrent_ops} concurrent, {operations} operations")
        
        start_time = datetime.now()
        
        # Create chunking tasks
        tasks = []
        for i in range(concurrent_ops):
            ops_per_task = operations // concurrent_ops
            if i < operations % concurrent_ops:
                ops_per_task += 1
            
            task = asyncio.create_task(
                self._test_chunking_operations(ops_per_task, i)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        successful_operations = 0
        failed_operations = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_operations += operations // concurrent_ops
                self.errors.append(str(result))
            else:
                successful, failed = result
                successful_operations += successful
                failed_operations += failed
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return self._create_ml_result(
            "Chunking Framework Performance",
            start_time, end_time, duration,
            operations, successful_operations, failed_operations
        )
    
    async def _test_chunking_operations(self, operations: int, task_id: int) -> tuple:
        """Test chunking framework operations."""
        successful = 0
        failed = 0
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for i in range(operations):
                    try:
                        start_time = time.time()
                        
                        # Test chunking configuration
                        chunking_config = {
                            "strategy": "adaptive",
                            "max_chunk_size": 1000,
                            "overlap": 100,
                            "content_type": "text"
                        }
                        
                        async with session.post(
                            f"{self.base_url}/api/chunking/configure",
                            json=chunking_config,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            response_data = await response.read()
                            processing_time = (time.time() - start_time) * 1000
                            
                            self.processing_times.append(processing_time)
                            self.response_sizes.append(len(response_data))
                            
                            if response.status < 400:
                                successful += 1
                            else:
                                failed += 1
                                self.errors.append(f"Chunking config failed: HTTP {response.status}")
                        
                        # Test chunking analysis
                        start_time = time.time()
                        
                        async with session.get(
                            f"{self.base_url}/api/chunking/analyze"
                        ) as response:
                            response_data = await response.read()
                            processing_time = (time.time() - start_time) * 1000
                            
                            self.processing_times.append(processing_time)
                            self.response_sizes.append(len(response_data))
                            
                            if response.status < 400:
                                successful += 1
                            else:
                                failed += 1
                                self.errors.append(f"Chunking analysis failed: HTTP {response.status}")
                        
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        failed += 2  # Two operations per iteration
                        self.errors.append(f"Chunking operation error: {str(e)}")
                
                return successful, failed
                
        except Exception as e:
            self.errors.append(f"Chunking task {task_id} error: {str(e)}")
            return successful, operations * 2 - successful
    
    async def _test_vector_search(self, concurrent_ops: int, operations: int) -> MLPerformanceResult:
        """Test vector database search performance."""
        self.logger.info(f"Testing vector search: {concurrent_ops} concurrent, {operations} operations")
        
        start_time = datetime.now()
        
        # Create search tasks
        tasks = []
        for i in range(concurrent_ops):
            ops_per_task = operations // concurrent_ops
            if i < operations % concurrent_ops:
                ops_per_task += 1
            
            task = asyncio.create_task(
                self._test_vector_search_operations(ops_per_task, i)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        successful_operations = 0
        failed_operations = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_operations += operations // concurrent_ops
                self.errors.append(str(result))
            else:
                successful, failed = result
                successful_operations += successful
                failed_operations += failed
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return self._create_ml_result(
            "Vector Search Performance",
            start_time, end_time, duration,
            operations, successful_operations, failed_operations
        )
    
    async def _test_vector_search_operations(self, operations: int, task_id: int) -> tuple:
        """Test vector search operations."""
        successful = 0
        failed = 0
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for i in range(operations):
                    try:
                        start_time = time.time()
                        
                        # Test vector search
                        search_query = {
                            "query": f"test search query {i+1} for performance testing",
                            "limit": 10,
                            "threshold": 0.7
                        }
                        
                        async with session.post(
                            f"{self.base_url}/api/search/vector",
                            json=search_query,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            response_data = await response.read()
                            processing_time = (time.time() - start_time) * 1000
                            
                            self.processing_times.append(processing_time)
                            self.response_sizes.append(len(response_data))
                            
                            if response.status < 400:
                                successful += 1
                            else:
                                failed += 1
                                self.errors.append(f"Vector search failed: HTTP {response.status}")
                        
                        await asyncio.sleep(0.1)
                        
                    except Exception as e:
                        failed += 1
                        self.errors.append(f"Vector search error: {str(e)}")
                
                return successful, failed
                
        except Exception as e:
            self.errors.append(f"Vector search task {task_id} error: {str(e)}")
            return successful, operations - successful
    
    async def _test_knowledge_graph(self, concurrent_ops: int, operations: int) -> MLPerformanceResult:
        """Test knowledge graph operations performance."""
        self.logger.info(f"Testing knowledge graph: {concurrent_ops} concurrent, {operations} operations")
        
        start_time = datetime.now()
        
        # Create knowledge graph tasks
        tasks = []
        for i in range(concurrent_ops):
            ops_per_task = operations // concurrent_ops
            if i < operations % concurrent_ops:
                ops_per_task += 1
            
            task = asyncio.create_task(
                self._test_knowledge_graph_operations(ops_per_task, i)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        successful_operations = 0
        failed_operations = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_operations += operations // concurrent_ops
                self.errors.append(str(result))
            else:
                successful, failed = result
                successful_operations += successful
                failed_operations += failed
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return self._create_ml_result(
            "Knowledge Graph Performance",
            start_time, end_time, duration,
            operations, successful_operations, failed_operations
        )
    
    async def _test_knowledge_graph_operations(self, operations: int, task_id: int) -> tuple:
        """Test knowledge graph operations."""
        successful = 0
        failed = 0
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for i in range(operations):
                    try:
                        start_time = time.time()
                        
                        # Test knowledge graph query
                        kg_query = {
                            "query": f"MATCH (n) RETURN count(n) as node_count",
                            "limit": 100
                        }
                        
                        async with session.post(
                            f"{self.base_url}/api/knowledge-graph/query",
                            json=kg_query,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            response_data = await response.read()
                            processing_time = (time.time() - start_time) * 1000
                            
                            self.processing_times.append(processing_time)
                            self.response_sizes.append(len(response_data))
                            
                            if response.status < 400:
                                successful += 1
                            else:
                                failed += 1
                                self.errors.append(f"KG query failed: HTTP {response.status}")
                        
                        await asyncio.sleep(0.2)
                        
                    except Exception as e:
                        failed += 1
                        self.errors.append(f"Knowledge graph error: {str(e)}")
                
                return successful, failed
                
        except Exception as e:
            self.errors.append(f"Knowledge graph task {task_id} error: {str(e)}")
            return successful, operations - successful
    
    async def _test_ml_training_api(self, concurrent_ops: int, operations: int) -> MLPerformanceResult:
        """Test ML training API performance."""
        self.logger.info(f"Testing ML training API: {concurrent_ops} concurrent, {operations} operations")
        
        start_time = datetime.now()
        
        # Create ML training tasks
        tasks = []
        for i in range(concurrent_ops):
            ops_per_task = operations // concurrent_ops
            if i < operations % concurrent_ops:
                ops_per_task += 1
            
            task = asyncio.create_task(
                self._test_ml_training_operations(ops_per_task, i)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        successful_operations = 0
        failed_operations = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_operations += operations // concurrent_ops
                self.errors.append(str(result))
            else:
                successful, failed = result
                successful_operations += successful
                failed_operations += failed
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return self._create_ml_result(
            "ML Training API Performance",
            start_time, end_time, duration,
            operations, successful_operations, failed_operations
        )
    
    async def _test_ml_training_operations(self, operations: int, task_id: int) -> tuple:
        """Test ML training API operations."""
        successful = 0
        failed = 0
        
        try:
            timeout = aiohttp.ClientTimeout(total=60)  # Longer timeout for training
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for i in range(operations):
                    try:
                        start_time = time.time()
                        
                        # Test training status
                        async with session.get(
                            f"{self.base_url}/api/ml-training/status"
                        ) as response:
                            response_data = await response.read()
                            processing_time = (time.time() - start_time) * 1000
                            
                            self.processing_times.append(processing_time)
                            self.response_sizes.append(len(response_data))
                            
                            if response.status < 400:
                                successful += 1
                            else:
                                failed += 1
                                self.errors.append(f"Training status failed: HTTP {response.status}")
                        
                        # Test training configuration
                        start_time = time.time()
                        
                        training_config = {
                            "model_type": "test",
                            "batch_size": 32,
                            "learning_rate": 0.001,
                            "epochs": 1
                        }
                        
                        async with session.post(
                            f"{self.base_url}/api/ml-training/configure",
                            json=training_config,
                            headers={"Content-Type": "application/json"}
                        ) as response:
                            response_data = await response.read()
                            processing_time = (time.time() - start_time) * 1000
                            
                            self.processing_times.append(processing_time)
                            self.response_sizes.append(len(response_data))
                            
                            if response.status < 400:
                                successful += 1
                            else:
                                failed += 1
                                self.errors.append(f"Training config failed: HTTP {response.status}")
                        
                        await asyncio.sleep(1.0)  # Longer delay for training operations
                        
                    except Exception as e:
                        failed += 2  # Two operations per iteration
                        self.errors.append(f"ML training error: {str(e)}")
                
                return successful, failed
                
        except Exception as e:
            self.errors.append(f"ML training task {task_id} error: {str(e)}")
            return successful, operations * 2 - successful
    
    def _create_ml_result(
        self, 
        test_name: str, 
        start_time: datetime, 
        end_time: datetime, 
        duration: float,
        total_ops: int, 
        successful_ops: int, 
        failed_ops: int
    ) -> MLPerformanceResult:
        """Create ML performance result from metrics."""
        
        if not self.processing_times:
            return MLPerformanceResult(
                test_name=test_name,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                total_operations=total_ops,
                successful_operations=successful_ops,
                failed_operations=failed_ops,
                avg_processing_time_ms=0,
                max_processing_time_ms=0,
                min_processing_time_ms=0,
                throughput_ops_per_sec=0,
                avg_response_size_kb=0,
                success_rate_percent=0,
                errors=list(set(self.errors[:10]))
            )
        
        avg_processing_time = sum(self.processing_times) / len(self.processing_times)
        max_processing_time = max(self.processing_times)
        min_processing_time = min(self.processing_times)
        
        avg_response_size = sum(self.response_sizes) / max(len(self.response_sizes), 1) / 1024  # KB
        
        return MLPerformanceResult(
            test_name=test_name,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            total_operations=total_ops,
            successful_operations=successful_ops,
            failed_operations=failed_ops,
            avg_processing_time_ms=avg_processing_time,
            max_processing_time_ms=max_processing_time,
            min_processing_time_ms=min_processing_time,
            throughput_ops_per_sec=total_ops / max(duration, 0.001),
            avg_response_size_kb=avg_response_size,
            success_rate_percent=(successful_ops / max(total_ops, 1)) * 100,
            errors=list(set(self.errors[:10]))
        )
    
    def _calculate_ml_suite_summary(self, test_results: List[MLPerformanceResult]) -> Dict[str, Any]:
        """Calculate summary statistics for ML test suite."""
        if not test_results:
            return {}
        
        total_operations = sum(r.total_operations for r in test_results)
        total_successful = sum(r.successful_operations for r in test_results)
        total_failed = sum(r.failed_operations for r in test_results)
        
        avg_success_rate = sum(r.success_rate_percent for r in test_results) / len(test_results)
        avg_processing_time = sum(r.avg_processing_time_ms for r in test_results if r.avg_processing_time_ms > 0) / max(1, len([r for r in test_results if r.avg_processing_time_ms > 0]))
        avg_throughput = sum(r.throughput_ops_per_sec for r in test_results) / len(test_results)
        
        return {
            "total_test_scenarios": len(test_results),
            "successful_scenarios": len([r for r in test_results if r.success_rate_percent > 80]),
            "total_operations": total_operations,
            "successful_operations": total_successful,
            "failed_operations": total_failed,
            "overall_success_rate": avg_success_rate,
            "average_processing_time_ms": avg_processing_time,
            "average_throughput_ops_per_sec": avg_throughput,
            "max_processing_time_ms": max([r.max_processing_time_ms for r in test_results], default=0),
            "total_response_size_kb": sum(r.avg_response_size_kb * r.total_operations for r in test_results)
        }
    
    def _print_ml_test_summary(self, result: MLPerformanceResult):
        """Print summary for a single ML test."""
        status_icon = "✅" if result.success_rate_percent > 90 else "⚠️" if result.success_rate_percent > 70 else "❌"
        
        print(f"{status_icon} {result.test_name}")
        print(f"   Duration: {result.duration_seconds:.1f}s")
        print(f"   Operations: {result.total_operations} ({result.successful_operations} success, {result.failed_operations} failed)")
        print(f"   Success Rate: {result.success_rate_percent:.1f}%")
        print(f"   Throughput: {result.throughput_ops_per_sec:.1f} ops/sec")
        print(f"   Avg Processing: {result.avg_processing_time_ms:.1f}ms")
        print(f"   Max Processing: {result.max_processing_time_ms:.1f}ms")
        print(f"   Avg Response: {result.avg_response_size_kb:.1f} KB")
        
        if result.errors:
            print(f"   Top Errors: {', '.join(result.errors[:3])}")
    
    def _print_ml_suite_summary(self, test_results: Dict[str, Any]):
        """Print final ML test suite summary."""
        summary = test_results["summary"]
        
        print("=" * 80)
        print("🤖 ML TRAINING PERFORMANCE SUMMARY")
        print("=" * 80)
        print(f"⏱️  Total Duration: {test_results['total_duration']:.1f} seconds")
        print()
        
        print("📋 Test Scenarios:")
        print(f"   Total: {summary.get('total_test_scenarios', 0)}")
        print(f"   ✅ Successful: {summary.get('successful_scenarios', 0)}")
        print(f"   ❌ Failed: {summary.get('total_test_scenarios', 0) - summary.get('successful_scenarios', 0)}")
        print()
        
        print("⚙️  Operations:")
        print(f"   Total: {summary.get('total_operations', 0)}")
        print(f"   ✅ Successful: {summary.get('successful_operations', 0)}")
        print(f"   ❌ Failed: {summary.get('failed_operations', 0)}")
        print(f"   📈 Success Rate: {summary.get('overall_success_rate', 0):.1f}%")
        print()
        
        print("⚡ Performance:")
        print(f"   Average Throughput: {summary.get('average_throughput_ops_per_sec', 0):.1f} ops/sec")
        print(f"   Average Processing Time: {summary.get('average_processing_time_ms', 0):.1f}ms")
        print(f"   Max Processing Time: {summary.get('max_processing_time_ms', 0):.1f}ms")
        print(f"   Total Data Processed: {summary.get('total_response_size_kb', 0):.1f} KB")
        print()
        
        # Overall result
        success_rate = summary.get('overall_success_rate', 0)
        avg_processing = summary.get('average_processing_time_ms', 0)
        
        if success_rate >= 95 and avg_processing < 2000:
            print("🎉 EXCELLENT ML PERFORMANCE - System handled ML operations very well!")
        elif success_rate >= 90 and avg_processing < 5000:
            print("✅ GOOD ML PERFORMANCE - ML system performed well under load")
        elif success_rate >= 80 and avg_processing < 10000:
            print("⚠️  ACCEPTABLE ML PERFORMANCE - Some ML performance issues detected")
        else:
            print("❌ POOR ML PERFORMANCE - ML system struggled under load")
        
        print("=" * 80)


async def run_ml_performance_test(
    base_url: str = "http://localhost:8000",
    concurrent_operations: int = 5,
    operations_per_test: int = 10,
    test_duration: int = 120,
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """Run ML training performance test."""
    
    # Create ML performance tester
    tester = MLTrainingLoadTester(base_url)
    
    # Run tests
    results = await tester.run_ml_performance_tests(
        concurrent_operations=concurrent_operations,
        operations_per_test=operations_per_test,
        test_duration=test_duration
    )
    
    # Save results if requested
    if output_file:
        try:
            # Convert datetime objects to strings for JSON serialization
            results_copy = json.loads(json.dumps(results, default=str))
            
            with open(output_file, 'w') as f:
                json.dump(results_copy, f, indent=2)
            
            print(f"📄 Results saved to: {output_file}")
            
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")
    
    return results


def main():
    """Main ML performance test runner function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run ML Training Performance Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base URL for testing')
    parser.add_argument('--concurrent', type=int, default=5,
                       help='Number of concurrent operations')
    parser.add_argument('--operations', type=int, default=10,
                       help='Operations per test scenario')
    parser.add_argument('--duration', type=int, default=120,
                       help='Test duration in seconds')
    parser.add_argument('--output', type=str,
                       help='Output file for results (JSON)')
    
    args = parser.parse_args()
    
    # Run ML performance test
    results = asyncio.run(run_ml_performance_test(
        base_url=args.url,
        concurrent_operations=args.concurrent,
        operations_per_test=args.operations,
        test_duration=args.duration,
        output_file=args.output
    ))
    
    # Exit with appropriate code
    summary = results.get("summary", {})
    success_rate = summary.get("overall_success_rate", 0)
    
    if success_rate >= 90:
        exit(0)  # Success
    elif success_rate >= 80:
        exit(1)  # Warning
    else:
        exit(2)  # Failure


if __name__ == "__main__":
    main()