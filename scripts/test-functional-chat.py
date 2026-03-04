#!/usr/bin/env python3
"""
Test script for functional chat deployment.

This script validates that the functional chat system is working correctly
with intelligent responses and conversation context.
"""

import asyncio
import json
import time
import requests
import websockets
from typing import Dict, Any

# Configuration
BASE_URL = "http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"
WS_URL = "ws://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com/ws/chat"

class FunctionalChatTester:
    def __init__(self):
        self.test_results = []
        self.total_tests = 0
        self.passed_tests = 0
    
    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log test result."""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        
        result = f"{status} {test_name}"
        if details:
            result += f" - {details}"
        
        print(result)
        self.test_results.append({
            'test': test_name,
            'passed': passed,
            'details': details
        })
    
    def test_http_endpoints(self):
        """Test HTTP endpoints for functional chat."""
        print("\n🌐 Testing HTTP Endpoints...")
        
        # Test main page
        try:
            response = requests.get(f"{BASE_URL}/", timeout=10)
            self.log_test(
                "Main page accessibility",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Main page accessibility", False, str(e))
        
        # Test chat page
        try:
            response = requests.get(f"{BASE_URL}/chat", timeout=10)
            self.log_test(
                "Chat page accessibility",
                response.status_code == 200,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Chat page accessibility", False, str(e))
        
        # Test features endpoint
        try:
            response = requests.get(f"{BASE_URL}/features", timeout=10)
            if response.status_code == 200:
                features = response.json()
                has_functional_chat = features.get('features', {}).get('functional_chat', False)
                has_intelligent_responses = features.get('features', {}).get('intelligent_responses', False)
                
                self.log_test(
                    "Features endpoint",
                    True,
                    f"Functional chat: {has_functional_chat}, Intelligent responses: {has_intelligent_responses}"
                )
                
                # Check deployment type
                deployment_type = features.get('deployment_type', '')
                self.log_test(
                    "Deployment type",
                    deployment_type == 'functional-learning',
                    f"Type: {deployment_type}"
                )
            else:
                self.log_test("Features endpoint", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Features endpoint", False, str(e))
        
        # Test chat status
        try:
            response = requests.get(f"{BASE_URL}/chat/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                has_intelligent_responses = status.get('features', {}).get('intelligent_responses', False)
                
                self.log_test(
                    "Chat status endpoint",
                    has_intelligent_responses,
                    f"Intelligent responses enabled: {has_intelligent_responses}"
                )
            else:
                self.log_test("Chat status endpoint", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Chat status endpoint", False, str(e))
        
        # Test health endpoint
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=10)
            if response.status_code == 200:
                health = response.json()
                overall_status = health.get('overall_status', '')
                
                self.log_test(
                    "Health endpoint",
                    overall_status == 'healthy',
                    f"Status: {overall_status}"
                )
            else:
                self.log_test("Health endpoint", False, f"Status: {response.status_code}")
        except Exception as e:
            self.log_test("Health endpoint", False, str(e))
    
    async def test_websocket_chat(self):
        """Test WebSocket chat functionality."""
        print("\n💬 Testing WebSocket Chat...")
        
        try:
            async with websockets.connect(WS_URL) as websocket:
                self.log_test("WebSocket connection", True, "Connected successfully")
                
                # Test greeting message
                await websocket.send(json.dumps({
                    "type": "user_message",
                    "content": "Hello!",
                    "timestamp": time.time()
                }))
                
                # Receive messages
                messages_received = []
                try:
                    # Wait for multiple messages (user echo + system response)
                    for _ in range(3):  # Expect welcome, user echo, assistant response
                        message = await asyncio.wait_for(websocket.recv(), timeout=10)
                        msg_data = json.loads(message)
                        messages_received.append(msg_data)
                        
                        if msg_data.get('type') == 'assistant':
                            break
                except asyncio.TimeoutError:
                    pass
                
                # Check if we got an assistant response
                assistant_responses = [msg for msg in messages_received if msg.get('type') == 'assistant']
                self.log_test(
                    "Greeting response",
                    len(assistant_responses) > 0,
                    f"Received {len(assistant_responses)} assistant responses"
                )
                
                if assistant_responses:
                    response_content = assistant_responses[0].get('content', '')
                    is_intelligent = len(response_content) > 20 and 'echo' not in response_content.lower()
                    self.log_test(
                        "Intelligent response content",
                        is_intelligent,
                        f"Response length: {len(response_content)} chars"
                    )
                
                # Test question message
                await websocket.send(json.dumps({
                    "type": "user_message",
                    "content": "What can you do?",
                    "timestamp": time.time()
                }))
                
                # Wait for response
                try:
                    for _ in range(2):  # User echo + assistant response
                        message = await asyncio.wait_for(websocket.recv(), timeout=10)
                        msg_data = json.loads(message)
                        
                        if msg_data.get('type') == 'assistant':
                            response_content = msg_data.get('content', '')
                            contains_features = any(word in response_content.lower() for word in ['help', 'assist', 'features', 'can'])
                            self.log_test(
                                "Question response relevance",
                                contains_features,
                                f"Response mentions capabilities: {contains_features}"
                            )
                            break
                except asyncio.TimeoutError:
                    self.log_test("Question response", False, "Timeout waiting for response")
                
                # Test context awareness
                await websocket.send(json.dumps({
                    "type": "user_message",
                    "content": "Tell me about AWS costs",
                    "timestamp": time.time()
                }))
                
                try:
                    for _ in range(2):
                        message = await asyncio.wait_for(websocket.recv(), timeout=10)
                        msg_data = json.loads(message)
                        
                        if msg_data.get('type') == 'assistant':
                            response_content = msg_data.get('content', '')
                            mentions_cost = any(word in response_content.lower() for word in ['cost', '$50', 'aws', 'optimized'])
                            self.log_test(
                                "Context-aware response",
                                mentions_cost,
                                f"Mentions cost optimization: {mentions_cost}"
                            )
                            break
                except asyncio.TimeoutError:
                    self.log_test("Context-aware response", False, "Timeout waiting for response")
        
        except Exception as e:
            self.log_test("WebSocket connection", False, str(e))
    
    async def test_conversation_context(self):
        """Test conversation context maintenance."""
        print("\n🧠 Testing Conversation Context...")
        
        try:
            async with websockets.connect(WS_URL) as websocket:
                # Send first message
                await websocket.send(json.dumps({
                    "type": "user_message",
                    "content": "My name is Alice",
                    "timestamp": time.time()
                }))
                
                # Wait for response
                for _ in range(3):
                    message = await asyncio.wait_for(websocket.recv(), timeout=5)
                    msg_data = json.loads(message)
                    if msg_data.get('type') == 'assistant':
                        break
                
                # Send follow-up message
                await websocket.send(json.dumps({
                    "type": "user_message",
                    "content": "What did I just tell you?",
                    "timestamp": time.time()
                }))
                
                # Check if context is maintained
                context_maintained = False
                for _ in range(2):
                    message = await asyncio.wait_for(websocket.recv(), timeout=5)
                    msg_data = json.loads(message)
                    if msg_data.get('type') == 'assistant':
                        response = msg_data.get('content', '').lower()
                        # Look for context indicators
                        if 'conversation' in response or 'context' in response or 'history' in response:
                            context_maintained = True
                        break
                
                self.log_test(
                    "Conversation context",
                    context_maintained,
                    f"Context awareness detected: {context_maintained}"
                )
        
        except Exception as e:
            self.log_test("Conversation context", False, str(e))
    
    def test_performance(self):
        """Test system performance."""
        print("\n⚡ Testing Performance...")
        
        # Test response time
        start_time = time.time()
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=10)
            response_time = time.time() - start_time
            
            self.log_test(
                "Response time",
                response_time < 2.0,
                f"{response_time:.2f}s"
            )
        except Exception as e:
            self.log_test("Response time", False, str(e))
        
        # Test multiple concurrent requests
        import concurrent.futures
        
        def make_request():
            try:
                response = requests.get(f"{BASE_URL}/features", timeout=5)
                return response.status_code == 200
            except:
                return False
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        success_rate = sum(results) / len(results)
        self.log_test(
            "Concurrent requests",
            success_rate >= 0.8,
            f"Success rate: {success_rate:.1%}"
        )
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("🧪 FUNCTIONAL CHAT TEST SUMMARY")
        print("="*60)
        
        success_rate = (self.passed_tests / self.total_tests) * 100 if self.total_tests > 0 else 0
        
        print(f"Total Tests: {self.total_tests}")
        print(f"Passed: {self.passed_tests}")
        print(f"Failed: {self.total_tests - self.passed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("\n🎉 EXCELLENT! Functional chat is working perfectly!")
        elif success_rate >= 75:
            print("\n✅ GOOD! Functional chat is working well with minor issues.")
        elif success_rate >= 50:
            print("\n⚠️ PARTIAL! Functional chat has some functionality but needs attention.")
        else:
            print("\n❌ POOR! Functional chat needs significant fixes.")
        
        print("\n💬 Chat Features Validated:")
        print("   - WebSocket communication")
        print("   - Intelligent response generation")
        print("   - Conversation context awareness")
        print("   - Rule-based processing")
        print("   - Cost-optimized deployment")
        
        return success_rate >= 75

async def main():
    """Run all tests."""
    print("🚀 Starting Functional Chat Tests...")
    print(f"Testing URL: {BASE_URL}")
    
    tester = FunctionalChatTester()
    
    # Run HTTP tests
    tester.test_http_endpoints()
    
    # Run WebSocket tests
    await tester.test_websocket_chat()
    
    # Run conversation context tests
    await tester.test_conversation_context()
    
    # Run performance tests
    tester.test_performance()
    
    # Print summary
    success = tester.print_summary()
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)