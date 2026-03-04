#!/usr/bin/env python3
"""
Chat Interface Load Testing for AWS Learning Deployment

This module provides specialized load testing for the chat interface,
including WebSocket connections, message sending, and conversation management.
Designed for learning-oriented testing with cost-optimized scenarios.

Test Scenarios:
- WebSocket connection load testing
- Chat message sending performance
- Conversation creation and management
- File upload through chat interface
- Real-time message delivery testing
"""

import os
import sys
import asyncio
import websockets
import aiohttp
import json
import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import threading

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger


@dataclass
class ChatLoadTestResult:
    """Chat-specific load test result."""
    test_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    concurrent_connections: int
    total_messages_sent: int
    total_messages_received: int
    successful_connections: int
    failed_connections: int
    avg_message_latency_ms: float
    max_message_latency_ms: float
    connection_success_rate: float
    message_delivery_rate: float
    websocket_errors: List[str]
    http_errors: List[str]


class ChatLoadTester:
    """Specialized load tester for chat interface."""
    
    def __init__(self, base_url: str, websocket_url: str):
        self.base_url = base_url.rstrip('/')
        self.websocket_url = websocket_url.rstrip('/')
        self.logger = get_logger("chat_load_tester")
        
        # Test tracking
        self.active_connections = 0
        self.connection_lock = threading.Lock()
        
        # Metrics
        self.message_latencies = []
        self.connection_times = []
        self.websocket_errors = []
        self.http_errors = []
        
        self.logger.info(f"Initialized chat load tester")
        self.logger.info(f"HTTP URL: {self.base_url}")
        self.logger.info(f"WebSocket URL: {self.websocket_url}")
    
    async def run_chat_load_tests(
        self, 
        concurrent_users: int = 10, 
        test_duration: int = 60,
        messages_per_user: int = 10
    ) -> Dict[str, Any]:
        """Run comprehensive chat load testing."""
        
        self.logger.info("🚀 Starting chat interface load tests")
        
        test_results = {
            "start_time": datetime.now(),
            "config": {
                "concurrent_users": concurrent_users,
                "test_duration_seconds": test_duration,
                "messages_per_user": messages_per_user,
                "base_url": self.base_url,
                "websocket_url": self.websocket_url
            },
            "test_results": [],
            "summary": {}
        }
        
        print("=" * 80)
        print("💬 CHAT INTERFACE LOAD TEST SUITE")
        print("=" * 80)
        print(f"📅 Started: {test_results['start_time'].isoformat()}")
        print(f"🎯 Target: {self.base_url}")
        print(f"🔌 WebSocket: {self.websocket_url}")
        print(f"👥 Concurrent Users: {concurrent_users}")
        print(f"⏱️  Duration: {test_duration}s")
        print()
        
        # Test scenarios
        test_scenarios = [
            {
                "name": "WebSocket Connection Load Test",
                "description": "Test WebSocket connection establishment under load",
                "test_func": self._test_websocket_connections,
                "params": {"concurrent_users": concurrent_users, "duration": 30}
            },
            {
                "name": "Chat Message Load Test",
                "description": "Test chat message sending and receiving",
                "test_func": self._test_chat_messaging,
                "params": {"concurrent_users": concurrent_users, "messages_per_user": messages_per_user}
            },
            {
                "name": "Conversation Management Load Test",
                "description": "Test conversation creation and management",
                "test_func": self._test_conversation_management,
                "params": {"concurrent_users": concurrent_users, "operations_per_user": 5}
            },
            {
                "name": "Mixed Chat Operations Load Test",
                "description": "Test mixed chat operations under load",
                "test_func": self._test_mixed_chat_operations,
                "params": {"concurrent_users": min(concurrent_users, 15), "duration": test_duration}
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
                self._print_chat_test_summary(result)
                
            except Exception as e:
                self.logger.error(f"Error in scenario {scenario['name']}: {e}")
                error_result = ChatLoadTestResult(
                    test_name=scenario['name'],
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    duration_seconds=0,
                    concurrent_connections=0,
                    total_messages_sent=0,
                    total_messages_received=0,
                    successful_connections=0,
                    failed_connections=concurrent_users,
                    avg_message_latency_ms=0,
                    max_message_latency_ms=0,
                    connection_success_rate=0,
                    message_delivery_rate=0,
                    websocket_errors=[str(e)],
                    http_errors=[]
                )
                test_results["test_results"].append(error_result)
            
            print()
        
        # Calculate final summary
        test_results["end_time"] = datetime.now()
        test_results["total_duration"] = (
            test_results["end_time"] - test_results["start_time"]
        ).total_seconds()
        test_results["summary"] = self._calculate_chat_suite_summary(test_results["test_results"])
        
        # Print final summary
        self._print_chat_suite_summary(test_results)
        
        return test_results
    
    def _reset_metrics(self):
        """Reset metrics for a new test."""
        self.message_latencies = []
        self.connection_times = []
        self.websocket_errors = []
        self.http_errors = []
        self.active_connections = 0
    
    async def _test_websocket_connections(self, concurrent_users: int, duration: int) -> ChatLoadTestResult:
        """Test WebSocket connection establishment and maintenance."""
        self.logger.info(f"Testing WebSocket connections: {concurrent_users} users for {duration}s")
        
        start_time = datetime.now()
        successful_connections = 0
        failed_connections = 0
        
        # Create connection tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._maintain_websocket_connection(user_id, duration)
            )
            tasks.append(task)
        
        # Wait for all connections to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful vs failed connections
        for result in results:
            if isinstance(result, Exception):
                failed_connections += 1
                self.websocket_errors.append(str(result))
            else:
                successful_connections += 1
        
        end_time = datetime.now()
        duration_actual = (end_time - start_time).total_seconds()
        
        return ChatLoadTestResult(
            test_name="WebSocket Connection Load Test",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_actual,
            concurrent_connections=concurrent_users,
            total_messages_sent=0,
            total_messages_received=0,
            successful_connections=successful_connections,
            failed_connections=failed_connections,
            avg_message_latency_ms=0,
            max_message_latency_ms=0,
            connection_success_rate=(successful_connections / concurrent_users) * 100,
            message_delivery_rate=0,
            websocket_errors=list(set(self.websocket_errors[:10])),
            http_errors=[]
        )
    
    async def _maintain_websocket_connection(self, user_id: int, duration: int) -> bool:
        """Maintain a WebSocket connection for the specified duration."""
        ws_url = f"{self.websocket_url}/ws"
        
        try:
            connection_start = time.time()
            
            async with websockets.connect(
                ws_url,
                timeout=10,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                connection_time = (time.time() - connection_start) * 1000
                self.connection_times.append(connection_time)
                
                with self.connection_lock:
                    self.active_connections += 1
                
                # Maintain connection for duration
                end_time = time.time() + duration
                
                while time.time() < end_time:
                    # Send periodic ping to keep connection alive
                    await websocket.ping()
                    await asyncio.sleep(5)
                
                return True
                
        except Exception as e:
            self.websocket_errors.append(f"User {user_id}: {str(e)}")
            return False
        finally:
            with self.connection_lock:
                if self.active_connections > 0:
                    self.active_connections -= 1
    
    async def _test_chat_messaging(self, concurrent_users: int, messages_per_user: int) -> ChatLoadTestResult:
        """Test chat message sending and receiving."""
        self.logger.info(f"Testing chat messaging: {concurrent_users} users, {messages_per_user} messages each")
        
        start_time = datetime.now()
        total_messages_sent = 0
        total_messages_received = 0
        successful_connections = 0
        failed_connections = 0
        
        # Create messaging tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._send_chat_messages(user_id, messages_per_user)
            )
            tasks.append(task)
        
        # Wait for all messaging to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        for result in results:
            if isinstance(result, Exception):
                failed_connections += 1
                self.websocket_errors.append(str(result))
            else:
                successful_connections += 1
                sent, received = result
                total_messages_sent += sent
                total_messages_received += received
        
        end_time = datetime.now()
        duration_actual = (end_time - start_time).total_seconds()
        
        # Calculate latency statistics
        avg_latency = sum(self.message_latencies) / max(len(self.message_latencies), 1)
        max_latency = max(self.message_latencies) if self.message_latencies else 0
        
        return ChatLoadTestResult(
            test_name="Chat Message Load Test",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_actual,
            concurrent_connections=concurrent_users,
            total_messages_sent=total_messages_sent,
            total_messages_received=total_messages_received,
            successful_connections=successful_connections,
            failed_connections=failed_connections,
            avg_message_latency_ms=avg_latency,
            max_message_latency_ms=max_latency,
            connection_success_rate=(successful_connections / concurrent_users) * 100,
            message_delivery_rate=(total_messages_received / max(total_messages_sent, 1)) * 100,
            websocket_errors=list(set(self.websocket_errors[:10])),
            http_errors=[]
        )
    
    async def _send_chat_messages(self, user_id: int, message_count: int) -> tuple:
        """Send chat messages for a single user."""
        ws_url = f"{self.websocket_url}/ws"
        messages_sent = 0
        messages_received = 0
        
        try:
            async with websockets.connect(ws_url, timeout=10) as websocket:
                for i in range(message_count):
                    message = {
                        "type": "chat_message",
                        "content": f"Load test message {i+1} from user {user_id}",
                        "timestamp": datetime.now().isoformat(),
                        "user_id": f"test_user_{user_id}"
                    }
                    
                    # Send message and measure latency
                    send_time = time.time()
                    await websocket.send(json.dumps(message))
                    messages_sent += 1
                    
                    # Wait for response (with timeout)
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        receive_time = time.time()
                        latency = (receive_time - send_time) * 1000
                        self.message_latencies.append(latency)
                        messages_received += 1
                    except asyncio.TimeoutError:
                        self.websocket_errors.append(f"Message timeout for user {user_id}")
                    
                    # Small delay between messages
                    await asyncio.sleep(0.1)
                
                return messages_sent, messages_received
                
        except Exception as e:
            self.websocket_errors.append(f"User {user_id} messaging error: {str(e)}")
            return messages_sent, messages_received
    
    async def _test_conversation_management(self, concurrent_users: int, operations_per_user: int) -> ChatLoadTestResult:
        """Test conversation creation and management via HTTP API."""
        self.logger.info(f"Testing conversation management: {concurrent_users} users, {operations_per_user} ops each")
        
        start_time = datetime.now()
        successful_connections = 0
        failed_connections = 0
        
        # Create conversation management tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._manage_conversations(user_id, operations_per_user)
            )
            tasks.append(task)
        
        # Wait for all operations to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful vs failed operations
        for result in results:
            if isinstance(result, Exception):
                failed_connections += 1
                self.http_errors.append(str(result))
            else:
                successful_connections += 1
        
        end_time = datetime.now()
        duration_actual = (end_time - start_time).total_seconds()
        
        return ChatLoadTestResult(
            test_name="Conversation Management Load Test",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_actual,
            concurrent_connections=concurrent_users,
            total_messages_sent=0,
            total_messages_received=0,
            successful_connections=successful_connections,
            failed_connections=failed_connections,
            avg_message_latency_ms=0,
            max_message_latency_ms=0,
            connection_success_rate=(successful_connections / concurrent_users) * 100,
            message_delivery_rate=0,
            websocket_errors=[],
            http_errors=list(set(self.http_errors[:10]))
        )
    
    async def _manage_conversations(self, user_id: int, operation_count: int) -> bool:
        """Perform conversation management operations for a single user."""
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                for i in range(operation_count):
                    # Create conversation
                    create_payload = {
                        "title": f"Load Test Conversation {i+1} - User {user_id}",
                        "user_id": f"test_user_{user_id}"
                    }
                    
                    async with session.post(
                        f"{self.base_url}/api/conversations",
                        json=create_payload,
                        headers={"Content-Type": "application/json"}
                    ) as response:
                        if response.status >= 400:
                            self.http_errors.append(f"Create conversation failed: {response.status}")
                            continue
                        
                        conversation_data = await response.json()
                        conversation_id = conversation_data.get("id")
                    
                    # List conversations
                    async with session.get(f"{self.base_url}/api/conversations") as response:
                        if response.status >= 400:
                            self.http_errors.append(f"List conversations failed: {response.status}")
                    
                    # Get specific conversation (if created successfully)
                    if conversation_id:
                        async with session.get(f"{self.base_url}/api/conversations/{conversation_id}") as response:
                            if response.status >= 400:
                                self.http_errors.append(f"Get conversation failed: {response.status}")
                    
                    # Small delay between operations
                    await asyncio.sleep(0.2)
                
                return True
                
        except Exception as e:
            self.http_errors.append(f"User {user_id} conversation management error: {str(e)}")
            return False
    
    async def _test_mixed_chat_operations(self, concurrent_users: int, duration: int) -> ChatLoadTestResult:
        """Test mixed chat operations (WebSocket + HTTP) under load."""
        self.logger.info(f"Testing mixed chat operations: {concurrent_users} users for {duration}s")
        
        start_time = datetime.now()
        successful_connections = 0
        failed_connections = 0
        total_messages_sent = 0
        total_messages_received = 0
        
        # Create mixed operation tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._perform_mixed_operations(user_id, duration)
            )
            tasks.append(task)
        
        # Wait for all operations to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results
        for result in results:
            if isinstance(result, Exception):
                failed_connections += 1
                self.websocket_errors.append(str(result))
            else:
                successful_connections += 1
                sent, received = result
                total_messages_sent += sent
                total_messages_received += received
        
        end_time = datetime.now()
        duration_actual = (end_time - start_time).total_seconds()
        
        # Calculate latency statistics
        avg_latency = sum(self.message_latencies) / max(len(self.message_latencies), 1)
        max_latency = max(self.message_latencies) if self.message_latencies else 0
        
        return ChatLoadTestResult(
            test_name="Mixed Chat Operations Load Test",
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration_actual,
            concurrent_connections=concurrent_users,
            total_messages_sent=total_messages_sent,
            total_messages_received=total_messages_received,
            successful_connections=successful_connections,
            failed_connections=failed_connections,
            avg_message_latency_ms=avg_latency,
            max_message_latency_ms=max_latency,
            connection_success_rate=(successful_connections / concurrent_users) * 100,
            message_delivery_rate=(total_messages_received / max(total_messages_sent, 1)) * 100,
            websocket_errors=list(set(self.websocket_errors[:10])),
            http_errors=list(set(self.http_errors[:10]))
        )
    
    async def _perform_mixed_operations(self, user_id: int, duration: int) -> tuple:
        """Perform mixed WebSocket and HTTP operations for a single user."""
        messages_sent = 0
        messages_received = 0
        end_time = time.time() + duration
        
        try:
            # Start with HTTP operations (create conversation)
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as http_session:
                # Create a conversation
                create_payload = {
                    "title": f"Mixed Test Conversation - User {user_id}",
                    "user_id": f"test_user_{user_id}"
                }
                
                async with http_session.post(
                    f"{self.base_url}/api/conversations",
                    json=create_payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status >= 400:
                        self.http_errors.append(f"Create conversation failed: {response.status}")
                
                # Now establish WebSocket connection and send messages
                ws_url = f"{self.websocket_url}/ws"
                
                async with websockets.connect(ws_url, timeout=10) as websocket:
                    message_count = 0
                    
                    while time.time() < end_time:
                        # Send WebSocket message
                        message = {
                            "type": "chat_message",
                            "content": f"Mixed test message {message_count+1} from user {user_id}",
                            "timestamp": datetime.now().isoformat(),
                            "user_id": f"test_user_{user_id}"
                        }
                        
                        send_time = time.time()
                        await websocket.send(json.dumps(message))
                        messages_sent += 1
                        message_count += 1
                        
                        # Try to receive response
                        try:
                            response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                            receive_time = time.time()
                            latency = (receive_time - send_time) * 1000
                            self.message_latencies.append(latency)
                            messages_received += 1
                        except asyncio.TimeoutError:
                            pass
                        
                        # Occasionally make HTTP requests
                        if message_count % 5 == 0:
                            async with http_session.get(f"{self.base_url}/api/conversations") as response:
                                if response.status >= 400:
                                    self.http_errors.append(f"List conversations failed: {response.status}")
                        
                        # Delay between operations
                        await asyncio.sleep(1.0)
                
                return messages_sent, messages_received
                
        except Exception as e:
            self.websocket_errors.append(f"User {user_id} mixed operations error: {str(e)}")
            return messages_sent, messages_received
    
    def _calculate_chat_suite_summary(self, test_results: List[ChatLoadTestResult]) -> Dict[str, Any]:
        """Calculate summary statistics for chat test suite."""
        if not test_results:
            return {}
        
        total_connections = sum(r.concurrent_connections for r in test_results)
        total_successful = sum(r.successful_connections for r in test_results)
        total_failed = sum(r.failed_connections for r in test_results)
        total_messages_sent = sum(r.total_messages_sent for r in test_results)
        total_messages_received = sum(r.total_messages_received for r in test_results)
        
        avg_connection_success = sum(r.connection_success_rate for r in test_results) / len(test_results)
        avg_message_delivery = sum(r.message_delivery_rate for r in test_results if r.message_delivery_rate > 0) / max(1, len([r for r in test_results if r.message_delivery_rate > 0]))
        avg_latency = sum(r.avg_message_latency_ms for r in test_results if r.avg_message_latency_ms > 0) / max(1, len([r for r in test_results if r.avg_message_latency_ms > 0]))
        
        return {
            "total_test_scenarios": len(test_results),
            "successful_scenarios": len([r for r in test_results if r.connection_success_rate > 80]),
            "total_connection_attempts": total_connections,
            "successful_connections": total_successful,
            "failed_connections": total_failed,
            "total_messages_sent": total_messages_sent,
            "total_messages_received": total_messages_received,
            "overall_connection_success_rate": avg_connection_success,
            "overall_message_delivery_rate": avg_message_delivery,
            "average_message_latency_ms": avg_latency,
            "max_message_latency_ms": max([r.max_message_latency_ms for r in test_results], default=0)
        }
    
    def _print_chat_test_summary(self, result: ChatLoadTestResult):
        """Print summary for a single chat test."""
        status_icon = "✅" if result.connection_success_rate > 90 else "⚠️" if result.connection_success_rate > 70 else "❌"
        
        print(f"{status_icon} {result.test_name}")
        print(f"   Duration: {result.duration_seconds:.1f}s")
        print(f"   Connections: {result.successful_connections}/{result.concurrent_connections} ({result.connection_success_rate:.1f}%)")
        
        if result.total_messages_sent > 0:
            print(f"   Messages: {result.total_messages_sent} sent, {result.total_messages_received} received ({result.message_delivery_rate:.1f}%)")
            print(f"   Avg Latency: {result.avg_message_latency_ms:.1f}ms")
            print(f"   Max Latency: {result.max_message_latency_ms:.1f}ms")
        
        if result.websocket_errors:
            print(f"   WebSocket Errors: {', '.join(result.websocket_errors[:3])}")
        
        if result.http_errors:
            print(f"   HTTP Errors: {', '.join(result.http_errors[:3])}")
    
    def _print_chat_suite_summary(self, test_results: Dict[str, Any]):
        """Print final chat test suite summary."""
        summary = test_results["summary"]
        
        print("=" * 80)
        print("💬 CHAT LOAD TEST SUITE SUMMARY")
        print("=" * 80)
        print(f"⏱️  Total Duration: {test_results['total_duration']:.1f} seconds")
        print()
        
        print("📋 Test Scenarios:")
        print(f"   Total: {summary.get('total_test_scenarios', 0)}")
        print(f"   ✅ Successful: {summary.get('successful_scenarios', 0)}")
        print(f"   ❌ Failed: {summary.get('total_test_scenarios', 0) - summary.get('successful_scenarios', 0)}")
        print()
        
        print("🔌 Connections:")
        print(f"   Total Attempts: {summary.get('total_connection_attempts', 0)}")
        print(f"   ✅ Successful: {summary.get('successful_connections', 0)}")
        print(f"   ❌ Failed: {summary.get('failed_connections', 0)}")
        print(f"   📈 Success Rate: {summary.get('overall_connection_success_rate', 0):.1f}%")
        print()
        
        if summary.get('total_messages_sent', 0) > 0:
            print("💬 Messages:")
            print(f"   Total Sent: {summary.get('total_messages_sent', 0)}")
            print(f"   Total Received: {summary.get('total_messages_received', 0)}")
            print(f"   📈 Delivery Rate: {summary.get('overall_message_delivery_rate', 0):.1f}%")
            print(f"   ⚡ Avg Latency: {summary.get('average_message_latency_ms', 0):.1f}ms")
            print(f"   🔥 Max Latency: {summary.get('max_message_latency_ms', 0):.1f}ms")
            print()
        
        # Overall result
        connection_success = summary.get('overall_connection_success_rate', 0)
        message_delivery = summary.get('overall_message_delivery_rate', 0)
        
        if connection_success >= 95 and message_delivery >= 95:
            print("🎉 EXCELLENT CHAT PERFORMANCE - System handled chat load very well!")
        elif connection_success >= 90 and message_delivery >= 90:
            print("✅ GOOD CHAT PERFORMANCE - Chat system performed well under load")
        elif connection_success >= 80 and message_delivery >= 80:
            print("⚠️  ACCEPTABLE CHAT PERFORMANCE - Some chat issues detected")
        else:
            print("❌ POOR CHAT PERFORMANCE - Chat system struggled under load")
        
        print("=" * 80)


async def run_chat_load_test(
    base_url: str = "http://localhost:8000",
    websocket_url: str = "ws://localhost:8000",
    concurrent_users: int = 10,
    test_duration: int = 60,
    messages_per_user: int = 10,
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """Run chat interface load test."""
    
    # Create chat load tester
    tester = ChatLoadTester(base_url, websocket_url)
    
    # Run tests
    results = await tester.run_chat_load_tests(
        concurrent_users=concurrent_users,
        test_duration=test_duration,
        messages_per_user=messages_per_user
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
    """Main chat load test runner function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Chat Interface Load Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base HTTP URL for testing')
    parser.add_argument('--ws-url', type=str, default='ws://localhost:8000',
                       help='WebSocket URL for testing')
    parser.add_argument('--users', type=int, default=10,
                       help='Number of concurrent users')
    parser.add_argument('--duration', type=int, default=60,
                       help='Test duration in seconds')
    parser.add_argument('--messages', type=int, default=10,
                       help='Messages per user for messaging tests')
    parser.add_argument('--output', type=str,
                       help='Output file for results (JSON)')
    
    args = parser.parse_args()
    
    # Run chat load test
    results = asyncio.run(run_chat_load_test(
        base_url=args.url,
        websocket_url=args.ws_url,
        concurrent_users=args.users,
        test_duration=args.duration,
        messages_per_user=args.messages,
        output_file=args.output
    ))
    
    # Exit with appropriate code
    summary = results.get("summary", {})
    connection_success = summary.get("overall_connection_success_rate", 0)
    message_delivery = summary.get("overall_message_delivery_rate", 0)
    
    if connection_success >= 90 and message_delivery >= 90:
        exit(0)  # Success
    elif connection_success >= 80 and message_delivery >= 80:
        exit(1)  # Warning
    else:
        exit(2)  # Failure


if __name__ == "__main__":
    main()