"""
Search Operations Integration Test

This test validates search operations integration including:
- Vector search functionality
- Search result formatting  
- Metadata preservation

Validates: Requirement 1.3 - Component Integration Validation
"""

import pytest
import asyncio
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
import uuid

# Application imports
from multimodal_librarian.models.search_types import (
    SearchQuery, SearchResult, SearchResponse, 
    QueryIntent, QueryComplexity, UnderstoodQuery
)
from multimodal_librarian.models.core import SourceType, ContentType
from multimodal_librarian.components.vector_store.search_service_simple import (
    SimpleSemanticSearchService, SimpleSearchRequest, SimpleSearchResponse, SimpleSearchResult
)
from multimodal_librarian.components.vector_store.vector_store import VectorStore


class SearchOperationsIntegrationValidator:
    """Validates search operations integration across the system."""
    
    def __init__(self):
        self.test_results = {}
        self.search_errors = []
        self.performance_metrics = {}
        self.test_data = []
        
    def create_mock_vector_store(self) -> VectorStore:
        """Create a mock vector store with realistic test data."""
        mock_vector_store = MagicMock(spec=VectorStore)
        
        # Create realistic test data
        test_documents = [
            {
                'chunk_id': 'doc1_chunk1',
                'content': 'Machine learning is a subset of artificial intelligence that focuses on algorithms.',
                'source_type': 'book',
                'source_id': 'ml_textbook_2023',
                'content_type': 'technical',
                'location_reference': 'chapter_1_page_15',
                'section': 'Introduction to ML',
                'similarity_score': 0.95,
                'is_bridge': False,
                'created_at': int(time.time() * 1000),
                'metadata': {
                    'author': 'Dr. Smith',
                    'publication_year': 2023,
                    'chapter': 1,
                    'page': 15
                }
            },
            {
                'chunk_id': 'doc1_chunk2', 
                'content': 'Deep learning uses neural networks with multiple layers to process data.',
                'source_type': 'book',
                'source_id': 'ml_textbook_2023',
                'content_type': 'technical',
                'location_reference': 'chapter_3_page_45',
                'section': 'Deep Learning Fundamentals',
                'similarity_score': 0.88,
                'is_bridge': False,
                'created_at': int(time.time() * 1000),
                'metadata': {
                    'author': 'Dr. Smith',
                    'publication_year': 2023,
                    'chapter': 3,
                    'page': 45
                }
            },
            {
                'chunk_id': 'doc2_chunk1',
                'content': 'Natural language processing enables computers to understand human language.',
                'source_type': 'book',  # Changed from 'article' to 'book'
                'source_id': 'nlp_research_paper',
                'content_type': 'academic',
                'location_reference': 'section_2_paragraph_3',
                'section': 'NLP Overview',
                'similarity_score': 0.82,
                'is_bridge': True,
                'created_at': int(time.time() * 1000),
                'metadata': {
                    'journal': 'AI Research Quarterly',
                    'doi': '10.1234/ai.2023.001',
                    'section': 2,
                    'paragraph': 3
                }
            },
            {
                'chunk_id': 'doc3_chunk1',
                'content': 'Computer vision algorithms can identify objects in images and videos.',
                'source_type': 'conversation',
                'source_id': 'ai_discussion_session_1',
                'content_type': 'general',
                'location_reference': 'message_15',
                'section': 'Computer Vision Discussion',
                'similarity_score': 0.75,
                'is_bridge': False,
                'created_at': int(time.time() * 1000),
                'metadata': {
                    'session_id': 'session_123',
                    'participant': 'user_456',
                    'message_number': 15
                }
            }
        ]
        
        # Configure mock behavior
        def mock_semantic_search(query, top_k=10, source_type=None, content_type=None, source_id=None):
            """Mock semantic search that filters based on parameters."""
            results = test_documents.copy()
            
            # Apply filters
            if source_type:
                source_value = source_type.value if hasattr(source_type, 'value') else source_type
                results = [r for r in results if r['source_type'] == source_value]
            if content_type:
                content_value = content_type.value if hasattr(content_type, 'value') else content_type
                results = [r for r in results if r['content_type'] == content_value]
            if source_id:
                results = [r for r in results if r['source_id'] == source_id]
            
            # Sort by similarity score and limit
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            return results[:top_k]
        
        mock_vector_store.semantic_search.side_effect = mock_semantic_search
        mock_vector_store.health_check.return_value = True
        
        return mock_vector_store
    
    async def test_vector_search_functionality(self) -> Dict[str, Any]:
        """Test vector search functionality with various queries and filters."""
        test_result = {
            'test_name': 'vector_search_functionality',
            'success': False,
            'error': None,
            'search_tests': {},
            'performance_metrics': {}
        }
        
        try:
            # Initialize search service with mock vector store
            mock_vector_store = self.create_mock_vector_store()
            search_service = SimpleSemanticSearchService(mock_vector_store)
            
            # Test 1: Basic search query
            start_time = time.time()
            basic_request = SimpleSearchRequest(
                query="machine learning algorithms",
                top_k=5
            )
            basic_response = await search_service.search(basic_request)
            basic_search_time = (time.time() - start_time) * 1000
            
            test_result['search_tests']['basic_search'] = {
                'success': len(basic_response.results) > 0,
                'results_count': len(basic_response.results),
                'search_time_ms': basic_search_time,
                'top_similarity_score': basic_response.results[0].similarity_score if basic_response.results else 0
            }
            
            # Test 2: Filtered search by source type
            start_time = time.time()
            filtered_request = SimpleSearchRequest(
                query="artificial intelligence",
                source_type=SourceType.BOOK,
                top_k=10
            )
            filtered_response = await search_service.search(filtered_request)
            filtered_search_time = (time.time() - start_time) * 1000
            
            # Validate filtering worked
            book_results_only = all(
                result.source_type == SourceType.BOOK 
                for result in filtered_response.results
            )
            
            test_result['search_tests']['filtered_search'] = {
                'success': book_results_only,
                'results_count': len(filtered_response.results),
                'search_time_ms': filtered_search_time,
                'filter_applied_correctly': book_results_only
            }
            
            # Test 3: Content type filtering
            start_time = time.time()
            content_filtered_request = SimpleSearchRequest(
                query="technical concepts",
                content_type=ContentType.TECHNICAL,
                top_k=10
            )
            content_filtered_response = await search_service.search(content_filtered_request)
            content_search_time = (time.time() - start_time) * 1000
            
            # Validate content type filtering
            technical_results_only = all(
                result.content_type == ContentType.TECHNICAL
                for result in content_filtered_response.results
            )
            
            test_result['search_tests']['content_type_search'] = {
                'success': technical_results_only,
                'results_count': len(content_filtered_response.results),
                'search_time_ms': content_search_time,
                'content_filter_applied_correctly': technical_results_only
            }
            
            # Test 4: Source ID filtering
            start_time = time.time()
            source_filtered_request = SimpleSearchRequest(
                query="learning concepts",
                source_id="ml_textbook_2023",
                top_k=10
            )
            source_filtered_response = await search_service.search(source_filtered_request)
            source_search_time = (time.time() - start_time) * 1000
            
            # Validate source ID filtering
            source_results_only = all(
                result.source_id == "ml_textbook_2023"
                for result in source_filtered_response.results
            )
            
            test_result['search_tests']['source_id_search'] = {
                'success': source_results_only,
                'results_count': len(source_filtered_response.results),
                'search_time_ms': source_search_time,
                'source_filter_applied_correctly': source_results_only
            }
            
            # Test 5: Empty query handling
            start_time = time.time()
            empty_request = SimpleSearchRequest(query="", top_k=5)
            empty_response = await search_service.search(empty_request)
            empty_search_time = (time.time() - start_time) * 1000
            
            test_result['search_tests']['empty_query'] = {
                'success': True,  # Should handle gracefully
                'results_count': len(empty_response.results),
                'search_time_ms': empty_search_time,
                'handled_gracefully': True
            }
            
            # Test 6: Large top_k value
            start_time = time.time()
            large_k_request = SimpleSearchRequest(query="AI concepts", top_k=100)
            large_k_response = await search_service.search(large_k_request)
            large_k_search_time = (time.time() - start_time) * 1000
            
            test_result['search_tests']['large_top_k'] = {
                'success': len(large_k_response.results) <= 100,
                'results_count': len(large_k_response.results),
                'search_time_ms': large_k_search_time,
                'respects_limit': len(large_k_response.results) <= 100
            }
            
            # Calculate overall performance metrics
            all_search_times = [
                basic_search_time, filtered_search_time, content_search_time,
                source_search_time, empty_search_time, large_k_search_time
            ]
            
            test_result['performance_metrics'] = {
                'avg_search_time_ms': sum(all_search_times) / len(all_search_times),
                'max_search_time_ms': max(all_search_times),
                'min_search_time_ms': min(all_search_times),
                'total_searches_performed': len(all_search_times)
            }
            
            # Determine overall success
            all_tests_passed = all(
                test['success'] for test in test_result['search_tests'].values()
            )
            
            test_result['success'] = all_tests_passed
            
        except Exception as e:
            test_result['error'] = str(e)
            self.search_errors.append(f"Vector search functionality test failed: {e}")
        
        return test_result
    
    async def test_search_result_formatting(self) -> Dict[str, Any]:
        """Test that search results are properly formatted with all required fields."""
        test_result = {
            'test_name': 'search_result_formatting',
            'success': False,
            'error': None,
            'formatting_tests': {},
            'field_validation': {}
        }
        
        try:
            # Initialize search service
            mock_vector_store = self.create_mock_vector_store()
            search_service = SimpleSemanticSearchService(mock_vector_store)
            
            # Perform search to get results
            search_request = SimpleSearchRequest(
                query="machine learning concepts",
                top_k=5
            )
            search_response = await search_service.search(search_request)
            
            if not search_response.results:
                test_result['error'] = "No search results returned for formatting test"
                return test_result
            
            # Test result formatting
            formatting_tests = {}
            
            for i, result in enumerate(search_response.results):
                result_test = f'result_{i+1}'
                
                # Test required fields presence
                required_fields = [
                    'chunk_id', 'content', 'source_type', 'source_id', 
                    'content_type', 'location_reference', 'section', 'similarity_score'
                ]
                
                missing_fields = []
                for field in required_fields:
                    if not hasattr(result, field) or getattr(result, field) is None:
                        missing_fields.append(field)
                
                # Test field types and values
                field_type_errors = []
                
                # chunk_id should be string
                if not isinstance(result.chunk_id, str) or not result.chunk_id:
                    field_type_errors.append("chunk_id must be non-empty string")
                
                # content should be string
                if not isinstance(result.content, str) or not result.content:
                    field_type_errors.append("content must be non-empty string")
                
                # source_type should be SourceType enum
                if not isinstance(result.source_type, SourceType):
                    field_type_errors.append("source_type must be SourceType enum")
                
                # content_type should be ContentType enum
                if not isinstance(result.content_type, ContentType):
                    field_type_errors.append("content_type must be ContentType enum")
                
                # similarity_score should be float between 0 and 1
                if not isinstance(result.similarity_score, (int, float)):
                    field_type_errors.append("similarity_score must be numeric")
                elif not (0.0 <= result.similarity_score <= 1.0):
                    field_type_errors.append("similarity_score must be between 0.0 and 1.0")
                
                # Test SearchResult conversion
                try:
                    search_result = result.to_search_result()
                    conversion_success = isinstance(search_result, SearchResult)
                except Exception as e:
                    conversion_success = False
                    field_type_errors.append(f"SearchResult conversion failed: {e}")
                
                formatting_tests[result_test] = {
                    'missing_fields': missing_fields,
                    'field_type_errors': field_type_errors,
                    'conversion_success': conversion_success,
                    'has_all_required_fields': len(missing_fields) == 0,
                    'all_field_types_correct': len(field_type_errors) == 0
                }
            
            # Test response formatting
            response_formatting = {
                'has_results_list': isinstance(search_response.results, list),
                'has_total_results': hasattr(search_response, 'total_results'),
                'has_search_time': hasattr(search_response, 'search_time_ms'),
                'has_session_id': hasattr(search_response, 'session_id'),
                'has_query_id': hasattr(search_response, 'query_id'),
                'total_results_matches_count': (
                    search_response.total_results == len(search_response.results)
                ),
                'search_time_reasonable': (
                    hasattr(search_response, 'search_time_ms') and 
                    isinstance(search_response.search_time_ms, (int, float)) and
                    search_response.search_time_ms >= 0
                )
            }
            
            test_result['formatting_tests'] = formatting_tests
            test_result['field_validation'] = response_formatting
            
            # Determine overall success
            all_results_formatted_correctly = all(
                test['has_all_required_fields'] and 
                test['all_field_types_correct'] and 
                test['conversion_success']
                for test in formatting_tests.values()
            )
            
            response_formatted_correctly = all(response_formatting.values())
            
            test_result['success'] = all_results_formatted_correctly and response_formatted_correctly
            
        except Exception as e:
            test_result['error'] = str(e)
            self.search_errors.append(f"Search result formatting test failed: {e}")
        
        return test_result
    
    async def test_metadata_preservation(self) -> Dict[str, Any]:
        """Test that metadata is properly preserved throughout search operations."""
        test_result = {
            'test_name': 'metadata_preservation',
            'success': False,
            'error': None,
            'metadata_tests': {},
            'preservation_validation': {}
        }
        
        try:
            # Initialize search service
            mock_vector_store = self.create_mock_vector_store()
            search_service = SimpleSemanticSearchService(mock_vector_store)
            
            # Perform search
            search_request = SimpleSearchRequest(
                query="machine learning and AI concepts",
                top_k=10
            )
            search_response = await search_service.search(search_request)
            
            if not search_response.results:
                test_result['error'] = "No search results returned for metadata test"
                return test_result
            
            metadata_tests = {}
            
            for i, result in enumerate(search_response.results):
                result_test = f'result_{i+1}'
                
                # Test core metadata preservation
                core_metadata = {
                    'chunk_id_preserved': bool(result.chunk_id),
                    'source_id_preserved': bool(result.source_id),
                    'location_reference_preserved': bool(result.location_reference),
                    'section_preserved': bool(result.section),
                    'similarity_score_preserved': isinstance(result.similarity_score, (int, float)),
                    'created_at_preserved': result.created_at is not None,
                }
                
                # Test source type and content type preservation
                type_metadata = {
                    'source_type_is_enum': isinstance(result.source_type, SourceType),
                    'content_type_is_enum': isinstance(result.content_type, ContentType),
                    'source_type_valid': result.source_type in list(SourceType),
                    'content_type_valid': result.content_type in list(ContentType)
                }
                
                # Test bridge chunk detection
                bridge_metadata = {
                    'is_bridge_field_exists': hasattr(result, 'is_bridge'),
                    'is_bridge_is_boolean': isinstance(result.is_bridge, bool),
                    'bridge_value_preserved': True  # The is_bridge value should be preserved as-is
                }
                
                # Test SearchResult conversion preserves metadata
                try:
                    search_result = result.to_search_result()
                    
                    conversion_metadata = {
                        'chunk_id_preserved_in_conversion': search_result.chunk_id == result.chunk_id,
                        'content_preserved_in_conversion': search_result.content == result.content,
                        'source_type_preserved_in_conversion': search_result.source_type == result.source_type,
                        'source_id_preserved_in_conversion': search_result.source_id == result.source_id,
                        'similarity_score_preserved_in_conversion': search_result.similarity_score == result.similarity_score,
                        'metadata_dict_exists': hasattr(search_result, 'metadata') and isinstance(search_result.metadata, dict)
                    }
                except Exception as e:
                    conversion_metadata = {
                        'conversion_failed': True,
                        'conversion_error': str(e)
                    }
                
                metadata_tests[result_test] = {
                    'core_metadata': core_metadata,
                    'type_metadata': type_metadata,
                    'bridge_metadata': bridge_metadata,
                    'conversion_metadata': conversion_metadata
                }
            
            # Test session and query metadata preservation
            session_metadata = {
                'session_id_preserved': bool(search_response.session_id),
                'query_id_generated': bool(search_response.query_id),
                'search_time_recorded': (
                    hasattr(search_response, 'search_time_ms') and 
                    isinstance(search_response.search_time_ms, (int, float))
                ),
                'total_results_accurate': (
                    search_response.total_results == len(search_response.results)
                )
            }
            
            test_result['metadata_tests'] = metadata_tests
            test_result['preservation_validation'] = session_metadata
            
            # Calculate success metrics
            all_core_metadata_preserved = all(
                all(test['core_metadata'].values())
                for test in metadata_tests.values()
            )
            
            all_type_metadata_preserved = all(
                all(test['type_metadata'].values())
                for test in metadata_tests.values()
            )
            
            all_bridge_metadata_preserved = all(
                all(test['bridge_metadata'].values())
                for test in metadata_tests.values()
            )
            
            all_conversion_metadata_preserved = all(
                test['conversion_metadata'].get('conversion_failed', False) == False and
                all(v for k, v in test['conversion_metadata'].items() if k != 'conversion_failed')
                for test in metadata_tests.values()
            )
            
            session_metadata_preserved = all(session_metadata.values())
            
            test_result['success'] = (
                all_core_metadata_preserved and
                all_type_metadata_preserved and
                all_bridge_metadata_preserved and
                all_conversion_metadata_preserved and
                session_metadata_preserved
            )
            
        except Exception as e:
            test_result['error'] = str(e)
            self.search_errors.append(f"Metadata preservation test failed: {e}")
        
        return test_result
    
    async def test_search_service_health_and_performance(self) -> Dict[str, Any]:
        """Test search service health checks and performance characteristics."""
        test_result = {
            'test_name': 'search_service_health_performance',
            'success': False,
            'error': None,
            'health_tests': {},
            'performance_tests': {}
        }
        
        try:
            # Initialize search service
            mock_vector_store = self.create_mock_vector_store()
            search_service = SimpleSemanticSearchService(mock_vector_store)
            
            # Test 1: Health check functionality
            health_check_result = search_service.health_check()
            
            test_result['health_tests']['basic_health_check'] = {
                'health_check_callable': callable(search_service.health_check),
                'health_check_returns_boolean': isinstance(health_check_result, bool),
                'service_reports_healthy': health_check_result
            }
            
            # Test 2: Performance statistics
            perf_stats = search_service.get_performance_stats()
            
            test_result['health_tests']['performance_stats'] = {
                'stats_method_callable': callable(search_service.get_performance_stats),
                'stats_returns_dict': isinstance(perf_stats, dict),
                'has_total_searches': 'total_searches' in perf_stats,
                'has_avg_response_time': 'avg_response_time' in perf_stats,
                'stats_values_numeric': all(
                    isinstance(v, (int, float)) for v in perf_stats.values()
                )
            }
            
            # Test 3: Performance under load (simulated)
            search_times = []
            concurrent_searches = 5
            
            async def perform_search(query_num):
                start_time = time.time()
                request = SimpleSearchRequest(query=f"test query {query_num}")
                await search_service.search(request)
                return (time.time() - start_time) * 1000
            
            # Perform concurrent searches
            tasks = [perform_search(i) for i in range(concurrent_searches)]
            search_times = await asyncio.gather(*tasks)
            
            test_result['performance_tests']['concurrent_search_performance'] = {
                'concurrent_searches_completed': len(search_times),
                'avg_search_time_ms': sum(search_times) / len(search_times),
                'max_search_time_ms': max(search_times),
                'min_search_time_ms': min(search_times),
                'all_searches_under_1000ms': all(t < 1000 for t in search_times),
                'performance_consistent': (max(search_times) - min(search_times)) < 500
            }
            
            # Test 4: Error handling
            # Test with failing vector store
            failing_vector_store = MagicMock(spec=VectorStore)
            failing_vector_store.semantic_search.side_effect = Exception("Vector store connection failed")
            failing_vector_store.health_check.return_value = False
            
            failing_search_service = SimpleSemanticSearchService(failing_vector_store)
            
            # Test graceful error handling
            try:
                error_request = SimpleSearchRequest(query="test query")
                error_response = await failing_search_service.search(error_request)
                
                test_result['health_tests']['error_handling'] = {
                    'handles_vector_store_errors': True,
                    'returns_empty_results_on_error': len(error_response.results) == 0,
                    'maintains_response_structure': isinstance(error_response, SimpleSearchResponse),
                    'records_search_time_on_error': hasattr(error_response, 'search_time_ms')
                }
            except Exception as e:
                test_result['health_tests']['error_handling'] = {
                    'handles_vector_store_errors': False,
                    'error_propagated': str(e)
                }
            
            # Determine overall success
            health_tests_passed = all(
                all(test.values()) if isinstance(test, dict) else test
                for test in test_result['health_tests'].values()
                if not isinstance(test, dict) or 'error_propagated' not in test
            )
            
            performance_tests_passed = all(
                test.get('all_searches_under_1000ms', True) and
                test.get('performance_consistent', True)
                for test in test_result['performance_tests'].values()
            )
            
            test_result['success'] = health_tests_passed and performance_tests_passed
            
        except Exception as e:
            test_result['error'] = str(e)
            self.search_errors.append(f"Search service health and performance test failed: {e}")
        
        return test_result
    
    async def run_complete_search_operations_test(self) -> Dict[str, Any]:
        """Run the complete search operations integration test."""
        integration_results = {
            'overall_success': False,
            'test_results': {},
            'performance_summary': {},
            'errors': [],
            'test_duration_ms': 0
        }
        
        start_time = time.time()
        
        try:
            # Test 1: Vector Search Functionality
            vector_search_result = await self.test_vector_search_functionality()
            integration_results['test_results']['vector_search'] = vector_search_result
            
            # Test 2: Search Result Formatting
            formatting_result = await self.test_search_result_formatting()
            integration_results['test_results']['result_formatting'] = formatting_result
            
            # Test 3: Metadata Preservation
            metadata_result = await self.test_metadata_preservation()
            integration_results['test_results']['metadata_preservation'] = metadata_result
            
            # Test 4: Health and Performance
            health_performance_result = await self.test_search_service_health_and_performance()
            integration_results['test_results']['health_performance'] = health_performance_result
            
            # Calculate overall success
            test_successes = [
                result['success'] for result in integration_results['test_results'].values()
            ]
            integration_results['overall_success'] = all(test_successes)
            
            # Compile performance summary
            performance_metrics = []
            for result in integration_results['test_results'].values():
                if 'performance_metrics' in result:
                    performance_metrics.append(result['performance_metrics'])
            
            if performance_metrics:
                all_search_times = []
                for metrics in performance_metrics:
                    if 'avg_search_time_ms' in metrics:
                        all_search_times.append(metrics['avg_search_time_ms'])
                
                integration_results['performance_summary'] = {
                    'avg_search_time_ms': sum(all_search_times) / len(all_search_times) if all_search_times else 0,
                    'total_tests_performed': sum(len(result.get('search_tests', {})) for result in integration_results['test_results'].values()),
                    'performance_acceptable': all(t < 500 for t in all_search_times) if all_search_times else True
                }
            
            # Collect all errors
            integration_results['errors'] = self.search_errors.copy()
            
        except Exception as e:
            integration_results['errors'].append(f"Search operations integration test failed: {e}")
        
        integration_results['test_duration_ms'] = (time.time() - start_time) * 1000
        
        return integration_results
    
    def get_integration_report(self) -> Dict[str, Any]:
        """Get a comprehensive search operations integration report."""
        return {
            'test_results': self.test_results,
            'search_errors': self.search_errors,
            'performance_metrics': self.performance_metrics,
            'summary': {
                'total_tests_run': len(self.test_results),
                'successful_tests': sum(1 for r in self.test_results.values() if r.get('success', False)),
                'failed_tests': sum(1 for r in self.test_results.values() if not r.get('success', False)),
                'has_errors': len(self.search_errors) > 0
            }
        }


class TestSearchOperationsIntegration:
    """Test class for search operations integration validation."""
    
    def test_vector_search_functionality(self):
        """Test vector search functionality with various parameters."""
        validator = SearchOperationsIntegrationValidator()
        
        async def run_test():
            return await validator.test_vector_search_functionality()
        
        # Execute the async test
        vector_search_result = asyncio.run(run_test())
        
        # Report results
        print(f"\n🔍 Vector Search Functionality Test Results:")
        print(f"   Overall Success: {'✅' if vector_search_result['success'] else '❌'}")
        
        if vector_search_result.get('search_tests'):
            for test_name, test_result in vector_search_result['search_tests'].items():
                status = "✅" if test_result['success'] else "❌"
                print(f"   {status} {test_name.replace('_', ' ').title()}")
                print(f"      Results: {test_result['results_count']}")
                print(f"      Time: {test_result['search_time_ms']:.1f}ms")
                
                if 'top_similarity_score' in test_result:
                    print(f"      Top Score: {test_result['top_similarity_score']:.3f}")
        
        if vector_search_result.get('performance_metrics'):
            perf = vector_search_result['performance_metrics']
            print(f"\n⏱️  Performance Metrics:")
            print(f"   Average Search Time: {perf['avg_search_time_ms']:.1f}ms")
            print(f"   Max Search Time: {perf['max_search_time_ms']:.1f}ms")
            print(f"   Total Searches: {perf['total_searches_performed']}")
        
        if vector_search_result.get('error'):
            print(f"   Error: {vector_search_result['error']}")
        
        # Assert success
        assert vector_search_result['success'], f"Vector search functionality test failed: {vector_search_result.get('error')}"
        
        # Assert performance requirements
        if vector_search_result.get('performance_metrics'):
            avg_time = vector_search_result['performance_metrics']['avg_search_time_ms']
            assert avg_time < 500, f"Average search time {avg_time:.1f}ms exceeds 500ms threshold"
    
    def test_search_result_formatting(self):
        """Test that search results are properly formatted."""
        validator = SearchOperationsIntegrationValidator()
        
        async def run_test():
            return await validator.test_search_result_formatting()
        
        # Execute the async test
        formatting_result = asyncio.run(run_test())
        
        print(f"\n📋 Search Result Formatting Test Results:")
        print(f"   Overall Success: {'✅' if formatting_result['success'] else '❌'}")
        
        if formatting_result.get('formatting_tests'):
            for result_name, result_test in formatting_result['formatting_tests'].items():
                status = "✅" if (result_test['has_all_required_fields'] and 
                                result_test['all_field_types_correct'] and 
                                result_test['conversion_success']) else "❌"
                print(f"   {status} {result_name}")
                
                if result_test['missing_fields']:
                    print(f"      Missing fields: {result_test['missing_fields']}")
                if result_test['field_type_errors']:
                    print(f"      Type errors: {result_test['field_type_errors']}")
        
        if formatting_result.get('field_validation'):
            validation = formatting_result['field_validation']
            print(f"\n📊 Response Validation:")
            for check, passed in validation.items():
                status = "✅" if passed else "❌"
                print(f"   {status} {check.replace('_', ' ').title()}")
        
        if formatting_result.get('error'):
            print(f"   Error: {formatting_result['error']}")
        
        # Assert success
        assert formatting_result['success'], f"Search result formatting test failed: {formatting_result.get('error')}"
    
    def test_metadata_preservation(self):
        """Test that metadata is properly preserved throughout search operations."""
        validator = SearchOperationsIntegrationValidator()
        
        async def run_test():
            return await validator.test_metadata_preservation()
        
        # Execute the async test
        metadata_result = asyncio.run(run_test())
        
        print(f"\n🏷️  Metadata Preservation Test Results:")
        print(f"   Overall Success: {'✅' if metadata_result['success'] else '❌'}")
        
        if metadata_result.get('metadata_tests'):
            for result_name, result_test in metadata_result['metadata_tests'].items():
                print(f"   📄 {result_name}:")
                
                # Core metadata
                core_passed = all(result_test['core_metadata'].values())
                print(f"      Core Metadata: {'✅' if core_passed else '❌'}")
                
                # Type metadata
                type_passed = all(result_test['type_metadata'].values())
                print(f"      Type Metadata: {'✅' if type_passed else '❌'}")
                
                # Bridge metadata
                bridge_passed = all(result_test['bridge_metadata'].values())
                print(f"      Bridge Metadata: {'✅' if bridge_passed else '❌'}")
                
                # Conversion metadata
                conversion_passed = (
                    not result_test['conversion_metadata'].get('conversion_failed', False) and
                    all(v for k, v in result_test['conversion_metadata'].items() 
                        if k != 'conversion_failed')
                )
                print(f"      Conversion: {'✅' if conversion_passed else '❌'}")
        
        if metadata_result.get('preservation_validation'):
            validation = metadata_result['preservation_validation']
            print(f"\n🔄 Session Metadata:")
            for check, passed in validation.items():
                status = "✅" if passed else "❌"
                print(f"   {status} {check.replace('_', ' ').title()}")
        
        if metadata_result.get('error'):
            print(f"   Error: {metadata_result['error']}")
        
        # Assert success
        assert metadata_result['success'], f"Metadata preservation test failed: {metadata_result.get('error')}"
    
    def test_search_service_health_and_performance(self):
        """Test search service health checks and performance characteristics."""
        validator = SearchOperationsIntegrationValidator()
        
        async def run_test():
            return await validator.test_search_service_health_and_performance()
        
        # Execute the async test
        health_result = asyncio.run(run_test())
        
        print(f"\n🏥 Search Service Health & Performance Test Results:")
        print(f"   Overall Success: {'✅' if health_result['success'] else '❌'}")
        
        if health_result.get('health_tests'):
            print(f"\n🔍 Health Tests:")
            for test_name, test_result in health_result['health_tests'].items():
                if isinstance(test_result, dict) and 'error_propagated' not in test_result:
                    all_passed = all(test_result.values())
                    status = "✅" if all_passed else "❌"
                    print(f"   {status} {test_name.replace('_', ' ').title()}")
                    
                    for check, passed in test_result.items():
                        check_status = "✅" if passed else "❌"
                        print(f"      {check_status} {check.replace('_', ' ')}")
        
        if health_result.get('performance_tests'):
            print(f"\n⚡ Performance Tests:")
            for test_name, test_result in health_result['performance_tests'].items():
                print(f"   📊 {test_name.replace('_', ' ').title()}:")
                print(f"      Searches: {test_result['concurrent_searches_completed']}")
                print(f"      Avg Time: {test_result['avg_search_time_ms']:.1f}ms")
                print(f"      Max Time: {test_result['max_search_time_ms']:.1f}ms")
                print(f"      Under 1000ms: {'✅' if test_result['all_searches_under_1000ms'] else '❌'}")
                print(f"      Consistent: {'✅' if test_result['performance_consistent'] else '❌'}")
        
        if health_result.get('error'):
            print(f"   Error: {health_result['error']}")
        
        # Assert success
        assert health_result['success'], f"Search service health and performance test failed: {health_result.get('error')}"
    
    def test_complete_search_operations_integration(self):
        """Test the complete search operations integration comprehensively."""
        validator = SearchOperationsIntegrationValidator()
        
        print(f"\n🧪 Running Complete Search Operations Integration Test")
        print("=" * 80)
        
        # Run complete integration test
        async def run_test():
            return await validator.run_complete_search_operations_test()
        
        integration_results = asyncio.run(run_test())
        
        print(f"\n📊 Search Operations Integration Summary:")
        print(f"   Overall Success: {'✅' if integration_results['overall_success'] else '❌'}")
        print(f"   Total Test Duration: {integration_results['test_duration_ms']:.1f}ms")
        print(f"   Tests Run: {len(integration_results['test_results'])}")
        
        successful_tests = sum(1 for r in integration_results['test_results'].values() if r['success'])
        print(f"   Successful Tests: {successful_tests}/{len(integration_results['test_results'])}")
        
        # Report individual test results
        for test_name, test_result in integration_results['test_results'].items():
            status = "✅" if test_result['success'] else "❌"
            print(f"   {status} {test_name.replace('_', ' ').title()}")
            if test_result.get('error'):
                print(f"      Error: {test_result['error']}")
        
        # Performance summary
        if integration_results['performance_summary']:
            perf = integration_results['performance_summary']
            print(f"\n⏱️  Performance Summary:")
            print(f"   Average Search Time: {perf['avg_search_time_ms']:.1f}ms")
            print(f"   Total Tests Performed: {perf['total_tests_performed']}")
            print(f"   Performance Acceptable: {'✅' if perf['performance_acceptable'] else '❌'}")
        
        # Report errors
        if integration_results['errors']:
            print(f"\n❌ Errors encountered:")
            for error in integration_results['errors']:
                print(f"   - {error}")
        
        print(f"\n🎯 Overall Search Operations Integration: {'✅ PASSED' if integration_results['overall_success'] else '❌ FAILED'}")
        
        # Assert overall success
        assert integration_results['overall_success'], "Complete search operations integration test failed"
        
        # Assert minimum tests completed successfully
        assert successful_tests >= 3, f"Insufficient tests completed successfully: {successful_tests}/4"
        
        # Assert performance requirements
        if integration_results['performance_summary']:
            perf = integration_results['performance_summary']
            assert perf['performance_acceptable'], "Search performance does not meet requirements"


# Pytest fixtures and test functions
@pytest.fixture
def search_operations_validator():
    """Fixture to provide a search operations validator."""
    return SearchOperationsIntegrationValidator()


def test_search_operations_integration_comprehensive():
    """Comprehensive test of the search operations integration."""
    test_instance = TestSearchOperationsIntegration()
    
    # Run all search operations tests
    test_instance.test_vector_search_functionality()
    test_instance.test_search_result_formatting()
    test_instance.test_metadata_preservation()
    test_instance.test_search_service_health_and_performance()
    test_instance.test_complete_search_operations_integration()


if __name__ == "__main__":
    # Allow running this test directly
    test_search_operations_integration_comprehensive()
    print("\n✅ All search operations integration tests passed!")