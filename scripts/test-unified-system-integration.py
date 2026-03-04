#!/usr/bin/env python3
"""
Comprehensive integration tests for the unified system.

This script validates the complete workflow from document upload through
RAG-enhanced chat responses, ensuring all system components work together.

Task 7.2: Integration Tests for Unified System
Property 7: Cross-Feature Integration (Requirements 6.1, 6.2)
"""

import asyncio
import aiohttp
import json
import websockets
import sys
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from uuid import uuid4

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

class UnifiedSystemTester:
    """Comprehensive tester for the unified system integration."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.websocket_url = f"ws://localhost:8000/ws/chat"
        self.test_results = {}
        self.uploaded_documents = []
        
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration tests and return comprehensive results."""
        
        print("🧪 Unified System Integration Test Suite")
        print("=" * 60)
        print("Testing complete workflow: Upload → Process → Chat with documents")
        print("Validating Property 7: Cross-Feature Integration")
        print()
        
        # Test phases
        test_phases = [
            ("Infrastructure", self.test_infrastructure),
            ("Document Upload API", self.test_document_upload_api),
            ("Unified Interface", self.test_unified_interface),
            ("WebSocket Chat", self.test_websocket_chat),
            ("RAG Integration", self.test_rag_integration),
            ("Cross-Feature Integration", self.test_cross_feature_integration),
            ("Error Handling", self.test_error_handling),
            ("Performance", self.test_performance_metrics)
        ]
        
        overall_success = True
        
        for phase_name, test_function in test_phases:
            print(f"\n📋 Phase: {phase_name}")
            print("-" * 40)
            
            try:
                phase_result = await test_function()
                self.test_results[phase_name] = phase_result
                
                if phase_result.get('success', False):
                    print(f"✅ {phase_name}: PASSED")
                else:
                    print(f"❌ {phase_name}: FAILED")
                    overall_success = False
                    
            except Exception as e:
                print(f"❌ {phase_name}: ERROR - {e}")
                self.test_results[phase_name] = {
                    'success': False,
                    'error': str(e)
                }
                overall_success = False
        
        # Generate final report
        self.test_results['overall_success'] = overall_success
        self.test_results['test_timestamp'] = time.time()
        
        return self.test_results
    
    async def test_infrastructure(self) -> Dict[str, Any]:
        """Test basic infrastructure and service availability."""
        
        results = {
            'success': True,
            'tests': {},
            'services_available': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Health endpoint
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        results['tests']['health_endpoint'] = True
                        results['services_available']['overall'] = health_data.get('overall_status')
                        print(f"✅ Health endpoint: {health_data.get('overall_status', 'unknown')}")
                    else:
                        results['tests']['health_endpoint'] = False
                        results['success'] = False
                        print(f"❌ Health endpoint failed: {response.status}")
            except Exception as e:
                results['tests']['health_endpoint'] = False
                results['success'] = False
                print(f"❌ Health endpoint error: {e}")
            
            # Test 2: Features endpoint
            try:
                async with session.get(f"{self.base_url}/features") as response:
                    if response.status == 200:
                        features_data = await response.json()
                        results['tests']['features_endpoint'] = True
                        results['services_available']['features'] = features_data.get('features', {})
                        
                        features = features_data.get('features', {})
                        print(f"✅ Features endpoint available")
                        print(f"   - Chat: {features.get('chat', False)}")
                        print(f"   - Document upload: {features.get('document_upload', False)}")
                        print(f"   - RAG integration: {features.get('rag_integration', False)}")
                    else:
                        results['tests']['features_endpoint'] = False
                        results['success'] = False
                        print(f"❌ Features endpoint failed: {response.status}")
            except Exception as e:
                results['tests']['features_endpoint'] = False
                results['success'] = False
                print(f"❌ Features endpoint error: {e}")
            
            # Test 3: Document service health
            try:
                async with session.get(f"{self.base_url}/api/documents/health") as response:
                    if response.status == 200:
                        doc_health = await response.json()
                        results['tests']['document_service_health'] = True
                        results['services_available']['document_service'] = doc_health.get('status')
                        print(f"✅ Document service: {doc_health.get('status', 'unknown')}")
                    else:
                        results['tests']['document_service_health'] = False
                        print(f"⚠️  Document service health: {response.status}")
            except Exception as e:
                results['tests']['document_service_health'] = False
                print(f"⚠️  Document service health error: {e}")
        
        return results
    
    async def test_document_upload_api(self) -> Dict[str, Any]:
        """Test document upload API functionality."""
        
        results = {
            'success': True,
            'tests': {},
            'uploaded_documents': []
        }
        
        # Create test document content
        test_content = b"""This is a test document for integration testing.
        
        It contains information about machine learning concepts including:
        - Supervised learning algorithms
        - Neural networks and deep learning
        - Natural language processing
        - Computer vision applications
        
        This document will be used to test the RAG integration functionality."""
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Document upload
            try:
                form_data = aiohttp.FormData()
                form_data.add_field('file', test_content, 
                                  filename='test_integration_document.txt',
                                  content_type='text/plain')
                form_data.add_field('title', 'Integration Test Document')
                form_data.add_field('description', 'Test document for unified system integration')
                form_data.add_field('user_id', 'test_user')
                
                async with session.post(f"{self.base_url}/api/documents/upload", 
                                      data=form_data) as response:
                    if response.status == 200:
                        upload_result = await response.json()
                        results['tests']['document_upload'] = True
                        results['uploaded_documents'].append(upload_result)
                        self.uploaded_documents.append(upload_result)
                        
                        print(f"✅ Document upload successful")
                        print(f"   - Document ID: {upload_result.get('document_id')}")
                        print(f"   - Title: {upload_result.get('title')}")
                        print(f"   - Status: {upload_result.get('status')}")
                    else:
                        results['tests']['document_upload'] = False
                        results['success'] = False
                        error_text = await response.text()
                        print(f"❌ Document upload failed: {response.status}")
                        print(f"   Error: {error_text}")
            except Exception as e:
                results['tests']['document_upload'] = False
                results['success'] = False
                print(f"❌ Document upload error: {e}")
            
            # Test 2: Document listing
            try:
                async with session.get(f"{self.base_url}/api/documents/") as response:
                    if response.status == 200:
                        doc_list = await response.json()
                        results['tests']['document_listing'] = True
                        
                        print(f"✅ Document listing successful")
                        print(f"   - Total documents: {doc_list.get('total_count', 0)}")
                        print(f"   - Documents in page: {len(doc_list.get('documents', []))}")
                    else:
                        results['tests']['document_listing'] = False
                        results['success'] = False
                        print(f"❌ Document listing failed: {response.status}")
            except Exception as e:
                results['tests']['document_listing'] = False
                results['success'] = False
                print(f"❌ Document listing error: {e}")
            
            # Test 3: Document retrieval (if we have uploaded documents)
            if self.uploaded_documents:
                try:
                    doc_id = self.uploaded_documents[0].get('document_id')
                    async with session.get(f"{self.base_url}/api/documents/{doc_id}") as response:
                        if response.status == 200:
                            doc_details = await response.json()
                            results['tests']['document_retrieval'] = True
                            print(f"✅ Document retrieval successful")
                            print(f"   - Retrieved document: {doc_details.get('title')}")
                        else:
                            results['tests']['document_retrieval'] = False
                            results['success'] = False
                            print(f"❌ Document retrieval failed: {response.status}")
                except Exception as e:
                    results['tests']['document_retrieval'] = False
                    results['success'] = False
                    print(f"❌ Document retrieval error: {e}")
        
        return results
    
    async def test_unified_interface(self) -> Dict[str, Any]:
        """Test unified interface availability and functionality."""
        
        results = {
            'success': True,
            'tests': {},
            'interface_components': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Unified interface HTML
            try:
                async with session.get(f"{self.base_url}/app") as response:
                    if response.status == 200:
                        html_content = await response.text()
                        results['tests']['unified_interface_html'] = True
                        
                        # Check for key components
                        components = {
                            'css_reference': 'unified_interface.css' in html_content,
                            'js_reference': 'unified_interface.js' in html_content,
                            'chat_section': 'chat-section' in html_content,
                            'document_section': 'document-section' in html_content,
                            'sidebar_navigation': 'sidebar' in html_content
                        }
                        
                        results['interface_components'] = components
                        
                        print(f"✅ Unified interface HTML served")
                        for component, present in components.items():
                            status = "✅" if present else "❌"
                            print(f"   {status} {component}: {present}")
                    else:
                        results['tests']['unified_interface_html'] = False
                        results['success'] = False
                        print(f"❌ Unified interface HTML failed: {response.status}")
            except Exception as e:
                results['tests']['unified_interface_html'] = False
                results['success'] = False
                print(f"❌ Unified interface HTML error: {e}")
            
            # Test 2: Static assets
            static_assets = [
                ('CSS', '/static/css/unified_interface.css'),
                ('JavaScript', '/static/js/unified_interface.js')
            ]
            
            for asset_name, asset_path in static_assets:
                try:
                    async with session.get(f"{self.base_url}{asset_path}") as response:
                        if response.status == 200:
                            results['tests'][f'{asset_name.lower()}_asset'] = True
                            print(f"✅ {asset_name} asset available")
                        else:
                            results['tests'][f'{asset_name.lower()}_asset'] = False
                            results['success'] = False
                            print(f"❌ {asset_name} asset failed: {response.status}")
                except Exception as e:
                    results['tests'][f'{asset_name.lower()}_asset'] = False
                    results['success'] = False
                    print(f"❌ {asset_name} asset error: {e}")
        
        return results
    
    async def test_websocket_chat(self) -> Dict[str, Any]:
        """Test WebSocket chat functionality."""
        
        results = {
            'success': True,
            'tests': {},
            'chat_features': {}
        }
        
        try:
            print("📡 Testing WebSocket connection...")
            
            async with websockets.connect(self.websocket_url) as websocket:
                results['tests']['websocket_connection'] = True
                print("✅ WebSocket connection established")
                
                # Test 1: Start conversation
                start_message = {"type": "start_conversation"}
                await websocket.send(json.dumps(start_message))
                
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                start_response = json.loads(response)
                
                if start_response.get('type') == 'conversation_started':
                    results['tests']['conversation_start'] = True
                    thread_id = start_response.get('thread_id')
                    features = start_response.get('features', {})
                    
                    results['chat_features'] = features
                    
                    print("✅ Conversation started successfully")
                    print(f"   - Thread ID: {thread_id}")
                    print(f"   - RAG enabled: {features.get('rag_enabled', False)}")
                    print(f"   - Document-aware responses: {features.get('document_aware_responses', False)}")
                else:
                    results['tests']['conversation_start'] = False
                    results['success'] = False
                    print(f"❌ Conversation start failed: {start_response}")
                
                # Test 2: Send chat message
                test_message = "Hello! Can you help me understand machine learning concepts?"
                chat_message = {
                    "type": "chat_message",
                    "message": test_message
                }
                await websocket.send(json.dumps(chat_message))
                
                # Wait for response
                response_received = False
                processing_seen = False
                
                while not response_received:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        response_data = json.loads(response)
                        
                        if response_data.get('type') == 'processing':
                            processing_seen = True
                            print("⏳ Processing message...")
                        
                        elif response_data.get('type') == 'response':
                            results['tests']['chat_message_response'] = True
                            
                            response_content = response_data.get('response', {})
                            text_content = response_content.get('text_content', '')
                            citations = response_content.get('knowledge_citations', [])
                            metadata = response_data.get('metadata', {})
                            
                            print("✅ Chat response received")
                            print(f"   - Response length: {len(text_content)} characters")
                            print(f"   - Citations: {len(citations)}")
                            print(f"   - RAG enabled: {metadata.get('rag_enabled', False)}")
                            print(f"   - Processing time: {metadata.get('processing_time_ms', 'N/A')}ms")
                            
                            response_received = True
                        
                        elif response_data.get('type') == 'error':
                            results['tests']['chat_message_response'] = False
                            results['success'] = False
                            print(f"❌ Chat error: {response_data.get('message')}")
                            response_received = True
                    
                    except asyncio.TimeoutError:
                        results['tests']['chat_message_response'] = False
                        results['success'] = False
                        print("❌ Chat response timeout")
                        response_received = True
                
                results['tests']['processing_indicators'] = processing_seen
                
        except websockets.exceptions.ConnectionClosed:
            results['tests']['websocket_connection'] = False
            results['success'] = False
            print("❌ WebSocket connection closed unexpectedly")
        except Exception as e:
            results['tests']['websocket_connection'] = False
            results['success'] = False
            print(f"❌ WebSocket test error: {e}")
        
        return results
    
    async def test_rag_integration(self) -> Dict[str, Any]:
        """Test RAG integration with document knowledge."""
        
        results = {
            'success': True,
            'tests': {},
            'rag_features': {}
        }
        
        # Only test RAG if we have uploaded documents
        if not self.uploaded_documents:
            print("⚠️  Skipping RAG tests - no documents uploaded")
            results['tests']['skipped'] = True
            return results
        
        try:
            async with websockets.connect(self.websocket_url) as websocket:
                
                # Start conversation
                start_message = {"type": "start_conversation"}
                await websocket.send(json.dumps(start_message))
                await websocket.recv()  # Consume start response
                
                # Test document-specific query
                rag_query = "What information do you have about machine learning from my documents?"
                chat_message = {
                    "type": "chat_message", 
                    "message": rag_query
                }
                await websocket.send(json.dumps(chat_message))
                
                # Wait for RAG response
                response_received = False
                rag_response_data = None
                
                while not response_received:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        response_data = json.loads(response)
                        
                        if response_data.get('type') == 'response':
                            rag_response_data = response_data
                            response_received = True
                        elif response_data.get('type') == 'error':
                            results['success'] = False
                            print(f"❌ RAG query error: {response_data.get('message')}")
                            response_received = True
                    
                    except asyncio.TimeoutError:
                        results['success'] = False
                        print("❌ RAG response timeout")
                        response_received = True
                
                if rag_response_data:
                    response_content = rag_response_data.get('response', {})
                    citations = response_content.get('knowledge_citations', [])
                    metadata = rag_response_data.get('metadata', {})
                    
                    # Analyze RAG features
                    rag_features = {
                        'rag_enabled': metadata.get('rag_enabled', False),
                        'document_search_performed': metadata.get('search_results_count', 0) > 0,
                        'citations_provided': len(citations) > 0,
                        'confidence_score': metadata.get('confidence_score', 0),
                        'fallback_used': metadata.get('fallback_used', True)
                    }
                    
                    results['rag_features'] = rag_features
                    results['tests']['rag_query_response'] = True
                    
                    print("✅ RAG integration test completed")
                    print(f"   - RAG enabled: {rag_features['rag_enabled']}")
                    print(f"   - Document search performed: {rag_features['document_search_performed']}")
                    print(f"   - Citations provided: {rag_features['citations_provided']}")
                    print(f"   - Confidence score: {rag_features['confidence_score']}")
                    print(f"   - Fallback used: {rag_features['fallback_used']}")
                    
                    # Test citation quality
                    if citations:
                        print(f"   - Citation details:")
                        for i, citation in enumerate(citations[:3], 1):
                            print(f"     {i}. {citation.get('document_title', 'Unknown')} "
                                  f"(Score: {citation.get('relevance_score', 'N/A')})")
                else:
                    results['tests']['rag_query_response'] = False
                    results['success'] = False
                    print("❌ No RAG response received")
        
        except Exception as e:
            results['tests']['rag_integration'] = False
            results['success'] = False
            print(f"❌ RAG integration test error: {e}")
        
        return results
    
    async def test_cross_feature_integration(self) -> Dict[str, Any]:
        """Test cross-feature integration between chat and documents."""
        
        results = {
            'success': True,
            'tests': {},
            'integration_features': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Document upload affects chat capabilities
            if self.uploaded_documents:
                results['tests']['document_upload_integration'] = True
                print("✅ Document upload integration verified")
            else:
                results['tests']['document_upload_integration'] = False
                print("⚠️  No documents available for integration testing")
            
            # Test 2: Unified interface serves both features
            try:
                async with session.get(f"{self.base_url}/app") as response:
                    if response.status == 200:
                        html_content = await response.text()
                        
                        # Check for integration elements
                        integration_elements = {
                            'chat_document_integration': 'document-aware' in html_content.lower(),
                            'cross_navigation': 'switch-view' in html_content.lower() or 'nav' in html_content.lower(),
                            'unified_styling': 'unified' in html_content.lower(),
                            'responsive_design': 'responsive' in html_content.lower() or 'mobile' in html_content.lower()
                        }
                        
                        results['integration_features'] = integration_elements
                        results['tests']['unified_interface_integration'] = True
                        
                        print("✅ Unified interface integration features:")
                        for feature, present in integration_elements.items():
                            status = "✅" if present else "⚠️ "
                            print(f"   {status} {feature}: {present}")
                    else:
                        results['tests']['unified_interface_integration'] = False
                        results['success'] = False
                        print(f"❌ Unified interface integration test failed: {response.status}")
            except Exception as e:
                results['tests']['unified_interface_integration'] = False
                results['success'] = False
                print(f"❌ Unified interface integration error: {e}")
            
            # Test 3: API endpoints work together
            try:
                # Test that document and chat APIs are both accessible
                endpoints_to_test = [
                    ('/api/documents/', 'Document API'),
                    ('/health', 'Health API'),
                    ('/features', 'Features API')
                ]
                
                all_endpoints_working = True
                
                for endpoint, name in endpoints_to_test:
                    async with session.get(f"{self.base_url}{endpoint}") as response:
                        if response.status in [200, 422]:  # 422 acceptable for missing params
                            print(f"✅ {name} accessible")
                        else:
                            print(f"❌ {name} failed: {response.status}")
                            all_endpoints_working = False
                
                results['tests']['api_endpoints_integration'] = all_endpoints_working
                if not all_endpoints_working:
                    results['success'] = False
                    
            except Exception as e:
                results['tests']['api_endpoints_integration'] = False
                results['success'] = False
                print(f"❌ API endpoints integration error: {e}")
        
        return results
    
    async def test_error_handling(self) -> Dict[str, Any]:
        """Test error handling and fallback scenarios."""
        
        results = {
            'success': True,
            'tests': {},
            'error_scenarios': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Invalid document upload
            try:
                # Try to upload invalid file
                form_data = aiohttp.FormData()
                form_data.add_field('file', b'invalid content', 
                                  filename='test.exe',  # Invalid extension
                                  content_type='application/octet-stream')
                form_data.add_field('title', 'Invalid File Test')
                
                async with session.post(f"{self.base_url}/api/documents/upload", 
                                      data=form_data) as response:
                    if response.status == 400:  # Should reject invalid file
                        results['tests']['invalid_file_rejection'] = True
                        print("✅ Invalid file properly rejected")
                    else:
                        results['tests']['invalid_file_rejection'] = False
                        print(f"⚠️  Invalid file handling: {response.status}")
            except Exception as e:
                results['tests']['invalid_file_rejection'] = False
                print(f"❌ Invalid file test error: {e}")
            
            # Test 2: Non-existent document retrieval
            try:
                fake_doc_id = str(uuid4())
                async with session.get(f"{self.base_url}/api/documents/{fake_doc_id}") as response:
                    if response.status == 404:  # Should return not found
                        results['tests']['nonexistent_document_handling'] = True
                        print("✅ Non-existent document properly handled")
                    else:
                        results['tests']['nonexistent_document_handling'] = False
                        print(f"⚠️  Non-existent document handling: {response.status}")
            except Exception as e:
                results['tests']['nonexistent_document_handling'] = False
                print(f"❌ Non-existent document test error: {e}")
            
            # Test 3: WebSocket error handling
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    # Send malformed message
                    await websocket.send("invalid json")
                    
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        response_data = json.loads(response)
                        
                        if response_data.get('type') == 'error':
                            results['tests']['websocket_error_handling'] = True
                            print("✅ WebSocket error handling working")
                        else:
                            results['tests']['websocket_error_handling'] = False
                            print("⚠️  WebSocket error handling unclear")
                    except (asyncio.TimeoutError, json.JSONDecodeError):
                        results['tests']['websocket_error_handling'] = False
                        print("⚠️  WebSocket error handling timeout")
                        
            except Exception as e:
                results['tests']['websocket_error_handling'] = False
                print(f"❌ WebSocket error handling test error: {e}")
        
        return results
    
    async def test_performance_metrics(self) -> Dict[str, Any]:
        """Test performance metrics and response times."""
        
        results = {
            'success': True,
            'tests': {},
            'performance_metrics': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: API response times
            endpoints_to_test = [
                ('/health', 'Health endpoint'),
                ('/features', 'Features endpoint'),
                ('/api/documents/', 'Document list endpoint')
            ]
            
            for endpoint, name in endpoints_to_test:
                try:
                    start_time = time.time()
                    async with session.get(f"{self.base_url}{endpoint}") as response:
                        end_time = time.time()
                        response_time = (end_time - start_time) * 1000  # Convert to ms
                        
                        results['performance_metrics'][f'{name}_response_time_ms'] = response_time
                        
                        if response_time < 1000:  # Less than 1 second
                            print(f"✅ {name}: {response_time:.0f}ms")
                        else:
                            print(f"⚠️  {name}: {response_time:.0f}ms (slow)")
                            
                except Exception as e:
                    print(f"❌ {name} performance test error: {e}")
            
            # Test 2: WebSocket connection time
            try:
                start_time = time.time()
                async with websockets.connect(self.websocket_url) as websocket:
                    end_time = time.time()
                    connection_time = (end_time - start_time) * 1000
                    
                    results['performance_metrics']['websocket_connection_time_ms'] = connection_time
                    
                    if connection_time < 500:  # Less than 500ms
                        print(f"✅ WebSocket connection: {connection_time:.0f}ms")
                    else:
                        print(f"⚠️  WebSocket connection: {connection_time:.0f}ms (slow)")
                        
            except Exception as e:
                print(f"❌ WebSocket performance test error: {e}")
            
            # Performance thresholds check
            avg_response_time = sum([
                v for k, v in results['performance_metrics'].items() 
                if 'response_time_ms' in k
            ]) / max(1, len([k for k in results['performance_metrics'].keys() if 'response_time_ms' in k]))
            
            if avg_response_time < 1000:  # Average under 1 second
                results['tests']['performance_acceptable'] = True
                print(f"✅ Average response time acceptable: {avg_response_time:.0f}ms")
            else:
                results['tests']['performance_acceptable'] = False
                results['success'] = False
                print(f"⚠️  Average response time high: {avg_response_time:.0f}ms")
        
        return results
    
    def generate_report(self) -> str:
        """Generate a comprehensive test report."""
        
        report = []
        report.append("=" * 80)
        report.append("UNIFIED SYSTEM INTEGRATION TEST REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Overall status
        overall_success = self.test_results.get('overall_success', False)
        status_emoji = "🎉" if overall_success else "⚠️"
        report.append(f"{status_emoji} Overall Status: {'PASSED' if overall_success else 'FAILED'}")
        report.append("")
        
        # Phase results
        report.append("📋 Test Phase Results:")
        report.append("-" * 40)
        
        for phase_name, phase_result in self.test_results.items():
            if phase_name in ['overall_success', 'test_timestamp']:
                continue
                
            success = phase_result.get('success', False)
            status_emoji = "✅" if success else "❌"
            report.append(f"{status_emoji} {phase_name}: {'PASSED' if success else 'FAILED'}")
            
            # Add test details
            tests = phase_result.get('tests', {})
            for test_name, test_result in tests.items():
                test_emoji = "  ✅" if test_result else "  ❌"
                report.append(f"{test_emoji} {test_name}")
        
        report.append("")
        
        # Performance metrics
        performance_found = False
        for result in self.test_results.values():
            if isinstance(result, dict) and 'performance_metrics' in result:
                performance_found = True
                break
        
        if performance_found:
            report.append("⚡ Performance Metrics:")
            report.append("-" * 30)
            
            for phase_result in self.test_results.values():
                if isinstance(phase_result, dict) and 'performance_metrics' in phase_result:
                    for metric, value in phase_result['performance_metrics'].items():
                        if isinstance(value, (int, float)):
                            report.append(f"  {metric}: {value:.0f}")
                        else:
                            report.append(f"  {metric}: {value}")
        
        report.append("")
        
        # Integration features
        report.append("🔗 Integration Features Verified:")
        report.append("-" * 35)
        
        for phase_result in self.test_results.values():
            if isinstance(phase_result, dict) and 'integration_features' in phase_result:
                for feature, status in phase_result['integration_features'].items():
                    feature_emoji = "✅" if status else "⚠️"
                    report.append(f"{feature_emoji} {feature}: {status}")
        
        report.append("")
        
        # Recommendations
        report.append("💡 Recommendations:")
        report.append("-" * 20)
        
        if overall_success:
            report.append("✅ All integration tests passed successfully!")
            report.append("✅ The unified system is ready for production use.")
            report.append("✅ Cross-feature integration is working correctly.")
        else:
            report.append("⚠️  Some tests failed - review the details above.")
            report.append("⚠️  Address failing components before production deployment.")
            report.append("⚠️  Consider implementing additional error handling.")
        
        report.append("")
        report.append("=" * 80)
        
        return "\n".join(report)


async def main():
    """Main test execution function."""
    
    # Check if server is running
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 8000))
    sock.close()
    
    if result != 0:
        print("❌ Server is not running on localhost:8000")
        print("Please start the server with:")
        print("  python -m uvicorn src.multimodal_librarian.main:app --reload")
        return 1
    
    # Run comprehensive tests
    tester = UnifiedSystemTester()
    test_results = await tester.run_all_tests()
    
    # Generate and display report
    print("\n" + tester.generate_report())
    
    # Save results to file
    results_file = f"unified-system-integration-test-results-{int(time.time())}.json"
    with open(results_file, 'w') as f:
        json.dump(test_results, f, indent=2, default=str)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    
    # Return appropriate exit code
    return 0 if test_results.get('overall_success', False) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)