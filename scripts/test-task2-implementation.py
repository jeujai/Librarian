#!/usr/bin/env python3
"""
Test Task 2 Implementation - Enhanced Chat Service

This script tests the enhanced chat service features implemented in Task 2:
- Enhanced WebSocket chat handler with real-time communication
- Advanced conversation memory and context management
- User session handling and authentication
- Message routing and broadcasting system
"""

import asyncio
import json
import time
import websockets
import requests
from typing import Dict, List, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Task2Tester:
    """Test enhanced chat service features."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.test_results = {}
    
    async def test_enhanced_websocket_connection(self):
        """Test enhanced WebSocket connection with session features."""
        logger.info("Testing enhanced WebSocket connection...")
        
        try:
            uri = f"{self.ws_url}/api/chat/ws"
            async with websockets.connect(uri) as websocket:
                # Wait for session_started message
                response = await websocket.recv()
                data = json.loads(response)
                
                # Verify enhanced session features
                expected_features = [
                    "typing_indicators",
                    "message_routing", 
                    "context_management",
                    "multi_session",
                    "conversation_memory"
                ]
                
                session_features = data.get("features", {})
                features_present = all(feature in session_features for feature in expected_features)
                
                self.test_results["enhanced_websocket_connection"] = {
                    "status": "passed" if features_present else "failed",
                    "session_type": data.get("type"),
                    "features_found": list(session_features.keys()),
                    "expected_features": expected_features,
                    "all_features_present": features_present
                }
                
                logger.info(f"Enhanced WebSocket connection: {'✓' if features_present else '✗'}")
                return features_present
                
        except Exception as e:
            logger.error(f"Enhanced WebSocket connection test failed: {e}")
            self.test_results["enhanced_websocket_connection"] = {
                "status": "failed",
                "error": str(e)
            }
            return False
    
    async def test_message_routing(self):
        """Test enhanced message routing system."""
        logger.info("Testing message routing system...")
        
        try:
            uri = f"{self.ws_url}/api/chat/ws"
            async with websockets.connect(uri) as websocket:
                # Wait for session start
                await websocket.recv()
                
                # Test different message types
                message_types = [
                    {"type": "user_message", "content": "Hello, this is a test message"},
                    {"type": "typing_start"},
                    {"type": "typing_stop"},
                    {"type": "session_info"},
                    {"type": "get_suggestions"},
                    {"type": "heartbeat"}
                ]
                
                responses_received = []
                
                for message in message_types:
                    await websocket.send(json.dumps(message))
                    
                    # Wait for response (with timeout)
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        response_data = json.loads(response)
                        responses_received.append({
                            "sent_type": message["type"],
                            "received_type": response_data.get("type"),
                            "success": True
                        })
                    except asyncio.TimeoutError:
                        responses_received.append({
                            "sent_type": message["type"],
                            "received_type": None,
                            "success": False,
                            "error": "timeout"
                        })
                
                success_count = sum(1 for r in responses_received if r["success"])
                routing_success = success_count >= len(message_types) * 0.7  # 70% success rate
                
                self.test_results["message_routing"] = {
                    "status": "passed" if routing_success else "failed",
                    "total_messages": len(message_types),
                    "successful_responses": success_count,
                    "success_rate": success_count / len(message_types),
                    "responses": responses_received
                }
                
                logger.info(f"Message routing: {'✓' if routing_success else '✗'} ({success_count}/{len(message_types)})")
                return routing_success
                
        except Exception as e:
            logger.error(f"Message routing test failed: {e}")
            self.test_results["message_routing"] = {
                "status": "failed",
                "error": str(e)
            }
            return False
    
    async def test_conversation_context_management(self):
        """Test enhanced conversation context management."""
        logger.info("Testing conversation context management...")
        
        try:
            uri = f"{self.ws_url}/api/chat/ws"
            async with websockets.connect(uri) as websocket:
                # Wait for session start
                await websocket.recv()
                
                # Send a series of messages to build context
                test_messages = [
                    "Hello, I'm testing the conversation system",
                    "Can you remember what I just said?",
                    "What was my first message about?",
                    "Tell me about the context management features"
                ]
                
                context_responses = []
                
                for i, message in enumerate(test_messages):
                    # Send user message
                    await websocket.send(json.dumps({
                        "type": "user_message",
                        "content": message
                    }))
                    
                    # Wait for AI response
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        response_data = json.loads(response)
                        
                        if response_data.get("type") == "assistant":
                            context_responses.append({
                                "message_number": i + 1,
                                "user_message": message,
                                "ai_response": response_data.get("content", ""),
                                "has_context": "context" in response_data.get("content", "").lower() or 
                                             "remember" in response_data.get("content", "").lower() or
                                             "said" in response_data.get("content", "").lower()
                            })
                    except asyncio.TimeoutError:
                        context_responses.append({
                            "message_number": i + 1,
                            "user_message": message,
                            "ai_response": None,
                            "has_context": False,
                            "error": "timeout"
                        })
                
                # Check if AI demonstrates context awareness
                context_aware_responses = sum(1 for r in context_responses if r.get("has_context", False))
                context_success = context_aware_responses >= 1  # At least one context-aware response
                
                self.test_results["conversation_context_management"] = {
                    "status": "passed" if context_success else "failed",
                    "total_messages": len(test_messages),
                    "context_aware_responses": context_aware_responses,
                    "responses": context_responses
                }
                
                logger.info(f"Conversation context: {'✓' if context_success else '✗'} ({context_aware_responses} context-aware)")
                return context_success
                
        except Exception as e:
            logger.error(f"Conversation context test failed: {e}")
            self.test_results["conversation_context_management"] = {
                "status": "failed",
                "error": str(e)
            }
            return False
    
    async def test_session_statistics(self):
        """Test session statistics and information."""
        logger.info("Testing session statistics...")
        
        try:
            uri = f"{self.ws_url}/api/chat/ws"
            async with websockets.connect(uri) as websocket:
                # Wait for session start
                await websocket.recv()
                
                # Send some messages to generate statistics
                for i in range(3):
                    await websocket.send(json.dumps({
                        "type": "user_message",
                        "content": f"Test message {i + 1}"
                    }))
                    await websocket.recv()  # Wait for response
                
                # Request session info
                await websocket.send(json.dumps({"type": "session_info"}))
                
                # Wait for session info response
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                
                # Verify session statistics
                has_statistics = (
                    response_data.get("type") == "session_info" and
                    "data" in response_data and
                    "statistics" in response_data["data"]
                )
                
                statistics = response_data.get("data", {}).get("statistics", {})
                
                self.test_results["session_statistics"] = {
                    "status": "passed" if has_statistics else "failed",
                    "has_session_info": "data" in response_data,
                    "has_statistics": "statistics" in response_data.get("data", {}),
                    "statistics_fields": list(statistics.keys()) if statistics else [],
                    "session_data": response_data.get("data", {})
                }
                
                logger.info(f"Session statistics: {'✓' if has_statistics else '✗'}")
                return has_statistics
                
        except Exception as e:
            logger.error(f"Session statistics test failed: {e}")
            self.test_results["session_statistics"] = {
                "status": "failed",
                "error": str(e)
            }
            return False
    
    def test_chat_status_api(self):
        """Test enhanced chat status API."""
        logger.info("Testing enhanced chat status API...")
        
        try:
            response = requests.get(f"{self.base_url}/api/chat/status", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for enhanced features
                enhanced_features = [
                    "enhanced_context_management",
                    "conversation_summarization", 
                    "intelligent_context_trimming",
                    "typing_indicators",
                    "message_routing",
                    "multi_session_support",
                    "session_statistics",
                    "conversation_suggestions"
                ]
                
                features = data.get("features", {})
                enhanced_features_present = sum(1 for f in enhanced_features if features.get(f, False))
                
                has_context_strategies = "context_strategies" in data
                has_message_types = "message_types" in data
                
                status_success = (
                    enhanced_features_present >= len(enhanced_features) * 0.8 and  # 80% of features
                    has_context_strategies and
                    has_message_types
                )
                
                self.test_results["chat_status_api"] = {
                    "status": "passed" if status_success else "failed",
                    "enhanced_features_found": enhanced_features_present,
                    "total_enhanced_features": len(enhanced_features),
                    "has_context_strategies": has_context_strategies,
                    "has_message_types": has_message_types,
                    "context_strategies": data.get("context_strategies", []),
                    "message_types": data.get("message_types", []),
                    "features": features
                }
                
                logger.info(f"Chat status API: {'✓' if status_success else '✗'} ({enhanced_features_present}/{len(enhanced_features)} features)")
                return status_success
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Chat status API test failed: {e}")
            self.test_results["chat_status_api"] = {
                "status": "failed",
                "error": str(e)
            }
            return False
    
    async def run_all_tests(self):
        """Run all Task 2 tests."""
        logger.info("🚀 Starting Task 2 Enhanced Chat Service Tests")
        logger.info("=" * 60)
        
        tests = [
            ("Enhanced WebSocket Connection", self.test_enhanced_websocket_connection()),
            ("Message Routing System", self.test_message_routing()),
            ("Conversation Context Management", self.test_conversation_context_management()),
            ("Session Statistics", self.test_session_statistics()),
            ("Chat Status API", self.test_chat_status_api())
        ]
        
        results = []
        for test_name, test_coro in tests:
            if asyncio.iscoroutine(test_coro):
                result = await test_coro
            else:
                result = test_coro
            results.append((test_name, result))
        
        # Summary
        logger.info("=" * 60)
        logger.info("📊 Task 2 Test Results Summary")
        logger.info("=" * 60)
        
        passed_tests = 0
        total_tests = len(results)
        
        for test_name, passed in results:
            status = "✅ PASSED" if passed else "❌ FAILED"
            logger.info(f"{status} - {test_name}")
            if passed:
                passed_tests += 1
        
        logger.info("=" * 60)
        logger.info(f"📈 Overall Results: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
        
        if passed_tests == total_tests:
            logger.info("🎉 All Task 2 tests passed! Enhanced chat service is working correctly.")
        elif passed_tests >= total_tests * 0.8:
            logger.info("⚠️  Most Task 2 tests passed. Minor issues may need attention.")
        else:
            logger.info("🚨 Several Task 2 tests failed. Enhanced chat service needs fixes.")
        
        return {
            "overall_status": "passed" if passed_tests == total_tests else "partial" if passed_tests >= total_tests * 0.8 else "failed",
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "success_rate": passed_tests / total_tests,
            "detailed_results": self.test_results
        }

async def main():
    """Main test execution."""
    import sys
    
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    tester = Task2Tester(base_url)
    results = await tester.run_all_tests()
    
    # Save detailed results
    with open("task2-test-results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"📄 Detailed results saved to task2-test-results.json")
    
    # Exit with appropriate code
    sys.exit(0 if results["overall_status"] == "passed" else 1)

if __name__ == "__main__":
    asyncio.run(main())