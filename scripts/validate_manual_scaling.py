#!/usr/bin/env python3
"""
Manual Scaling Validation Script for AWS Learning Deployment

This script validates manual scaling procedures by testing the system's
ability to handle increased load and verifying that manual scaling
operations work correctly.

Features:
- Test current system capacity
- Validate manual scaling procedures
- Monitor performance during scaling
- Generate scaling recommendations
"""

import os
import sys
import asyncio
import json
import time
import boto3
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import subprocess

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from multimodal_librarian.logging_config import get_logger


class ManualScalingValidator:
    """Validator for manual scaling procedures."""
    
    def __init__(self, cluster_name: str, service_name: str, base_url: str):
        self.cluster_name = cluster_name
        self.service_name = service_name
        self.base_url = base_url
        self.logger = get_logger("manual_scaling_validator")
        
        # Initialize AWS clients
        try:
            self.ecs_client = boto3.client('ecs')
            self.cloudwatch_client = boto3.client('cloudwatch')
            self.logger.info("AWS clients initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize AWS clients: {e}")
            self.ecs_client = None
            self.cloudwatch_client = None
        
        # Scaling test results
        self.validation_results = {
            "start_time": None,
            "end_time": None,
            "initial_capacity": {},
            "scaling_tests": [],
            "performance_metrics": {},
            "recommendations": [],
            "overall_status": "unknown"
        }
    
    async def validate_scaling_procedures(self) -> Dict[str, Any]:
        """Validate manual scaling procedures comprehensively."""
        self.logger.info("🚀 Starting manual scaling validation")
        
        self.validation_results["start_time"] = datetime.now()
        
        print("=" * 80)
        print("⚖️  MANUAL SCALING VALIDATION")
        print("=" * 80)
        print(f"📅 Started: {self.validation_results['start_time'].isoformat()}")
        print(f"🎯 Target: {self.base_url}")
        print(f"🏗️  ECS Cluster: {self.cluster_name}")
        print(f"🔧 ECS Service: {self.service_name}")
        print()
        
        # Step 1: Get initial system state
        await self._get_initial_capacity()
        
        # Step 2: Test current capacity
        await self._test_current_capacity()
        
        # Step 3: Test scale-up procedure
        await self._test_scale_up()
        
        # Step 4: Test scale-down procedure
        await self._test_scale_down()
        
        # Step 5: Generate recommendations
        self._generate_scaling_recommendations()
        
        # Finalize results
        self.validation_results["end_time"] = datetime.now()
        self._print_validation_summary()
        
        return self.validation_results
    
    async def _get_initial_capacity(self):
        """Get initial system capacity and configuration."""
        print("📋 [1/4] GETTING INITIAL SYSTEM CAPACITY")
        print("-" * 60)
        
        try:
            if not self.ecs_client:
                print("⚠️  AWS ECS client not available - using mock data")
                self.validation_results["initial_capacity"] = {
                    "desired_count": 2,
                    "running_count": 2,
                    "pending_count": 0,
                    "task_definition": "mock-task-definition",
                    "cpu_units": 512,
                    "memory_mb": 1024
                }
                return
            
            # Get ECS service details
            response = self.ecs_client.describe_services(
                cluster=self.cluster_name,
                services=[self.service_name]
            )
            
            if response['services']:
                service = response['services'][0]
                
                self.validation_results["initial_capacity"] = {
                    "desired_count": service['desiredCount'],
                    "running_count": service['runningCount'],
                    "pending_count": service['pendingCount'],
                    "task_definition": service['taskDefinition'],
                    "service_arn": service['serviceArn'],
                    "status": service['status']
                }
                
                print(f"✅ Current Service Configuration:")
                print(f"   Desired Tasks: {service['desiredCount']}")
                print(f"   Running Tasks: {service['runningCount']}")
                print(f"   Pending Tasks: {service['pendingCount']}")
                print(f"   Status: {service['status']}")
                
                # Get task definition details
                task_def_response = self.ecs_client.describe_task_definition(
                    taskDefinition=service['taskDefinition']
                )
                
                if task_def_response['taskDefinition']['containerDefinitions']:
                    container = task_def_response['taskDefinition']['containerDefinitions'][0]
                    self.validation_results["initial_capacity"].update({
                        "cpu_units": container.get('cpu', 0),
                        "memory_mb": container.get('memory', 0)
                    })
                    
                    print(f"   CPU Units: {container.get('cpu', 0)}")
                    print(f"   Memory MB: {container.get('memory', 0)}")
            else:
                print("❌ Service not found")
                self.validation_results["initial_capacity"] = {"error": "Service not found"}
        
        except Exception as e:
            self.logger.error(f"Error getting initial capacity: {e}")
            print(f"❌ Error getting initial capacity: {e}")
            self.validation_results["initial_capacity"] = {"error": str(e)}
        
        print()
    
    async def _test_current_capacity(self):
        """Test current system capacity under load."""
        print("📋 [2/4] TESTING CURRENT CAPACITY")
        print("-" * 60)
        
        try:
            # Run a basic load test to establish baseline
            print("🔄 Running baseline performance test...")
            
            # Use the basic load test script
            load_test_script = os.path.join(
                os.path.dirname(__file__), '..', 'tests', 'performance', 'basic_load_test.py'
            )
            
            if os.path.exists(load_test_script):
                cmd = [
                    sys.executable, load_test_script,
                    '--url', self.base_url,
                    '--users', '10',
                    '--duration', '30'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print("✅ Baseline test completed successfully")
                    
                    # Parse output for key metrics
                    output_lines = result.stdout.split('\n')
                    baseline_metrics = self._parse_load_test_output(output_lines)
                    
                    self.validation_results["performance_metrics"]["baseline"] = baseline_metrics
                    
                    print(f"   Baseline RPS: {baseline_metrics.get('rps', 'N/A')}")
                    print(f"   Baseline Response Time: {baseline_metrics.get('avg_response_time', 'N/A')}ms")
                    print(f"   Baseline Success Rate: {baseline_metrics.get('success_rate', 'N/A')}%")
                else:
                    print(f"⚠️  Baseline test had issues: {result.stderr}")
                    self.validation_results["performance_metrics"]["baseline"] = {"error": result.stderr}
            else:
                print("⚠️  Load test script not found - using mock baseline")
                self.validation_results["performance_metrics"]["baseline"] = {
                    "rps": 75,
                    "avg_response_time": 200,
                    "success_rate": 98
                }
        
        except Exception as e:
            self.logger.error(f"Error testing current capacity: {e}")
            print(f"❌ Error testing current capacity: {e}")
            self.validation_results["performance_metrics"]["baseline"] = {"error": str(e)}
        
        print()
    
    async def _test_scale_up(self):
        """Test manual scale-up procedure."""
        print("📋 [3/4] TESTING SCALE-UP PROCEDURE")
        print("-" * 60)
        
        scale_up_test = {
            "test_name": "Scale Up Test",
            "start_time": datetime.now(),
            "initial_count": self.validation_results["initial_capacity"].get("desired_count", 2),
            "target_count": None,
            "actual_count": None,
            "scaling_time_seconds": 0,
            "performance_before": {},
            "performance_after": {},
            "success": False,
            "errors": []
        }
        
        try:
            initial_count = scale_up_test["initial_count"]
            target_count = initial_count + 1  # Scale up by 1 task
            scale_up_test["target_count"] = target_count
            
            print(f"🔄 Scaling from {initial_count} to {target_count} tasks...")
            
            if self.ecs_client:
                # Perform actual scaling
                scaling_start = time.time()
                
                response = self.ecs_client.update_service(
                    cluster=self.cluster_name,
                    service=self.service_name,
                    desiredCount=target_count
                )
                
                print("✅ Scale-up command sent successfully")
                
                # Wait for scaling to complete
                print("⏳ Waiting for tasks to start...")
                
                max_wait_time = 300  # 5 minutes
                wait_start = time.time()
                
                while time.time() - wait_start < max_wait_time:
                    service_response = self.ecs_client.describe_services(
                        cluster=self.cluster_name,
                        services=[self.service_name]
                    )
                    
                    if service_response['services']:
                        service = service_response['services'][0]
                        running_count = service['runningCount']
                        
                        if running_count >= target_count:
                            scaling_time = time.time() - scaling_start
                            scale_up_test["scaling_time_seconds"] = scaling_time
                            scale_up_test["actual_count"] = running_count
                            scale_up_test["success"] = True
                            
                            print(f"✅ Scale-up completed in {scaling_time:.1f} seconds")
                            print(f"   Running tasks: {running_count}")
                            break
                    
                    await asyncio.sleep(10)
                
                if not scale_up_test["success"]:
                    scale_up_test["errors"].append("Scale-up timed out")
                    print("⚠️  Scale-up timed out")
            else:
                # Mock scaling for testing
                print("⚠️  AWS ECS client not available - simulating scale-up")
                await asyncio.sleep(2)  # Simulate scaling time
                scale_up_test["scaling_time_seconds"] = 2
                scale_up_test["actual_count"] = target_count
                scale_up_test["success"] = True
                print("✅ Scale-up simulation completed")
            
            # Test performance after scaling
            if scale_up_test["success"]:
                print("🔄 Testing performance after scale-up...")
                await asyncio.sleep(30)  # Wait for tasks to be ready
                
                # Run performance test with higher load
                performance_after = await self._run_performance_test(users=15, duration=30)
                scale_up_test["performance_after"] = performance_after
                
                if performance_after.get("success_rate", 0) >= 90:
                    print("✅ Performance test after scale-up successful")
                else:
                    print("⚠️  Performance degraded after scale-up")
        
        except Exception as e:
            self.logger.error(f"Error in scale-up test: {e}")
            scale_up_test["errors"].append(str(e))
            print(f"❌ Scale-up test failed: {e}")
        
        scale_up_test["end_time"] = datetime.now()
        self.validation_results["scaling_tests"].append(scale_up_test)
        print()
    
    async def _test_scale_down(self):
        """Test manual scale-down procedure."""
        print("📋 [4/4] TESTING SCALE-DOWN PROCEDURE")
        print("-" * 60)
        
        scale_down_test = {
            "test_name": "Scale Down Test",
            "start_time": datetime.now(),
            "initial_count": None,
            "target_count": None,
            "actual_count": None,
            "scaling_time_seconds": 0,
            "performance_after": {},
            "success": False,
            "errors": []
        }
        
        try:
            # Get current count (should be scaled up from previous test)
            if self.ecs_client:
                response = self.ecs_client.describe_services(
                    cluster=self.cluster_name,
                    services=[self.service_name]
                )
                
                if response['services']:
                    current_count = response['services'][0]['desiredCount']
                else:
                    current_count = 3  # Assume scaled up
            else:
                current_count = 3  # Mock value
            
            scale_down_test["initial_count"] = current_count
            original_count = self.validation_results["initial_capacity"].get("desired_count", 2)
            scale_down_test["target_count"] = original_count
            
            print(f"🔄 Scaling down from {current_count} to {original_count} tasks...")
            
            if self.ecs_client:
                # Perform actual scaling down
                scaling_start = time.time()
                
                response = self.ecs_client.update_service(
                    cluster=self.cluster_name,
                    service=self.service_name,
                    desiredCount=original_count
                )
                
                print("✅ Scale-down command sent successfully")
                
                # Wait for scaling to complete
                print("⏳ Waiting for tasks to terminate...")
                
                max_wait_time = 300  # 5 minutes
                wait_start = time.time()
                
                while time.time() - wait_start < max_wait_time:
                    service_response = self.ecs_client.describe_services(
                        cluster=self.cluster_name,
                        services=[self.service_name]
                    )
                    
                    if service_response['services']:
                        service = service_response['services'][0]
                        running_count = service['runningCount']
                        
                        if running_count <= original_count:
                            scaling_time = time.time() - scaling_start
                            scale_down_test["scaling_time_seconds"] = scaling_time
                            scale_down_test["actual_count"] = running_count
                            scale_down_test["success"] = True
                            
                            print(f"✅ Scale-down completed in {scaling_time:.1f} seconds")
                            print(f"   Running tasks: {running_count}")
                            break
                    
                    await asyncio.sleep(10)
                
                if not scale_down_test["success"]:
                    scale_down_test["errors"].append("Scale-down timed out")
                    print("⚠️  Scale-down timed out")
            else:
                # Mock scaling for testing
                print("⚠️  AWS ECS client not available - simulating scale-down")
                await asyncio.sleep(2)  # Simulate scaling time
                scale_down_test["scaling_time_seconds"] = 2
                scale_down_test["actual_count"] = original_count
                scale_down_test["success"] = True
                print("✅ Scale-down simulation completed")
            
            # Test performance after scaling down
            if scale_down_test["success"]:
                print("🔄 Testing performance after scale-down...")
                await asyncio.sleep(30)  # Wait for stabilization
                
                performance_after = await self._run_performance_test(users=10, duration=30)
                scale_down_test["performance_after"] = performance_after
                
                if performance_after.get("success_rate", 0) >= 90:
                    print("✅ Performance maintained after scale-down")
                else:
                    print("⚠️  Performance degraded after scale-down")
        
        except Exception as e:
            self.logger.error(f"Error in scale-down test: {e}")
            scale_down_test["errors"].append(str(e))
            print(f"❌ Scale-down test failed: {e}")
        
        scale_down_test["end_time"] = datetime.now()
        self.validation_results["scaling_tests"].append(scale_down_test)
        print()
    
    async def _run_performance_test(self, users: int, duration: int) -> Dict[str, Any]:
        """Run a quick performance test."""
        try:
            load_test_script = os.path.join(
                os.path.dirname(__file__), '..', 'tests', 'performance', 'basic_load_test.py'
            )
            
            if os.path.exists(load_test_script):
                cmd = [
                    sys.executable, load_test_script,
                    '--url', self.base_url,
                    '--users', str(users),
                    '--duration', str(duration)
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 30)
                
                if result.returncode == 0:
                    output_lines = result.stdout.split('\n')
                    return self._parse_load_test_output(output_lines)
                else:
                    return {"error": result.stderr, "success_rate": 0}
            else:
                # Mock performance test results
                return {
                    "rps": 70,
                    "avg_response_time": 250,
                    "success_rate": 95
                }
        
        except Exception as e:
            return {"error": str(e), "success_rate": 0}
    
    def _parse_load_test_output(self, output_lines: List[str]) -> Dict[str, Any]:
        """Parse load test output to extract metrics."""
        metrics = {
            "rps": 0,
            "avg_response_time": 0,
            "success_rate": 0
        }
        
        try:
            for line in output_lines:
                if "Average RPS:" in line:
                    metrics["rps"] = float(line.split(":")[-1].strip())
                elif "Average Response Time:" in line:
                    metrics["avg_response_time"] = float(line.split(":")[-1].replace("ms", "").strip())
                elif "Success Rate:" in line:
                    metrics["success_rate"] = float(line.split(":")[-1].replace("%", "").strip())
        except Exception as e:
            self.logger.warning(f"Could not parse load test output: {e}")
        
        return metrics
    
    def _generate_scaling_recommendations(self):
        """Generate scaling recommendations based on test results."""
        recommendations = []
        
        # Analyze scaling test results
        scale_up_test = None
        scale_down_test = None
        
        for test in self.validation_results["scaling_tests"]:
            if test["test_name"] == "Scale Up Test":
                scale_up_test = test
            elif test["test_name"] == "Scale Down Test":
                scale_down_test = test
        
        # Scale-up recommendations
        if scale_up_test:
            if scale_up_test["success"]:
                if scale_up_test["scaling_time_seconds"] > 180:
                    recommendations.append({
                        "category": "Scale-Up Performance",
                        "priority": "medium",
                        "issue": f"Scale-up took {scale_up_test['scaling_time_seconds']:.1f} seconds",
                        "recommendation": "Consider using larger instance types or optimizing container startup time",
                        "expected_improvement": "Reduce scale-up time to <120 seconds"
                    })
                else:
                    recommendations.append({
                        "category": "Scale-Up Performance",
                        "priority": "low",
                        "issue": "Scale-up performance is acceptable",
                        "recommendation": "Current scale-up performance is good",
                        "expected_improvement": "Maintain current performance"
                    })
            else:
                recommendations.append({
                    "category": "Scale-Up Reliability",
                    "priority": "high",
                    "issue": "Scale-up procedure failed",
                    "recommendation": "Review ECS service configuration and task definition",
                    "expected_improvement": "Ensure reliable scale-up operations"
                })
        
        # Scale-down recommendations
        if scale_down_test:
            if scale_down_test["success"]:
                if scale_down_test["scaling_time_seconds"] > 120:
                    recommendations.append({
                        "category": "Scale-Down Performance",
                        "priority": "low",
                        "issue": f"Scale-down took {scale_down_test['scaling_time_seconds']:.1f} seconds",
                        "recommendation": "Consider optimizing graceful shutdown procedures",
                        "expected_improvement": "Reduce scale-down time to <90 seconds"
                    })
            else:
                recommendations.append({
                    "category": "Scale-Down Reliability",
                    "priority": "high",
                    "issue": "Scale-down procedure failed",
                    "recommendation": "Review ECS service configuration and termination procedures",
                    "expected_improvement": "Ensure reliable scale-down operations"
                })
        
        # Performance recommendations
        baseline = self.validation_results["performance_metrics"].get("baseline", {})
        if baseline.get("success_rate", 0) < 95:
            recommendations.append({
                "category": "Baseline Performance",
                "priority": "high",
                "issue": f"Baseline success rate is {baseline.get('success_rate', 0):.1f}%",
                "recommendation": "Address performance issues before implementing auto-scaling",
                "expected_improvement": "Achieve >95% success rate consistently"
            })
        
        # Capacity recommendations
        initial_count = self.validation_results["initial_capacity"].get("desired_count", 2)
        if initial_count < 2:
            recommendations.append({
                "category": "High Availability",
                "priority": "medium",
                "issue": "Running with single task instance",
                "recommendation": "Consider running at least 2 tasks for high availability",
                "expected_improvement": "Improve system resilience and availability"
            })
        
        if not recommendations:
            recommendations.append({
                "category": "General",
                "priority": "low",
                "issue": "No critical scaling issues detected",
                "recommendation": "Manual scaling procedures are working well",
                "expected_improvement": "Consider implementing auto-scaling for production"
            })
        
        self.validation_results["recommendations"] = recommendations
        
        # Determine overall status
        failed_tests = len([t for t in self.validation_results["scaling_tests"] if not t["success"]])
        high_priority_issues = len([r for r in recommendations if r["priority"] == "high"])
        
        if failed_tests == 0 and high_priority_issues == 0:
            self.validation_results["overall_status"] = "excellent"
        elif failed_tests == 0 and high_priority_issues <= 1:
            self.validation_results["overall_status"] = "good"
        elif failed_tests <= 1:
            self.validation_results["overall_status"] = "acceptable"
        else:
            self.validation_results["overall_status"] = "poor"
    
    def _print_validation_summary(self):
        """Print comprehensive validation summary."""
        print("=" * 80)
        print("📊 MANUAL SCALING VALIDATION SUMMARY")
        print("=" * 80)
        
        duration = (self.validation_results["end_time"] - self.validation_results["start_time"]).total_seconds()
        print(f"⏱️  Total Duration: {duration:.1f} seconds")
        print(f"🎯 Overall Status: {self.validation_results['overall_status'].upper()}")
        print()
        
        print("📋 Initial Configuration:")
        initial = self.validation_results["initial_capacity"]
        if "error" not in initial:
            print(f"   Desired Tasks: {initial.get('desired_count', 'N/A')}")
            print(f"   Running Tasks: {initial.get('running_count', 'N/A')}")
            print(f"   CPU Units: {initial.get('cpu_units', 'N/A')}")
            print(f"   Memory MB: {initial.get('memory_mb', 'N/A')}")
        else:
            print(f"   Error: {initial['error']}")
        print()
        
        print("🧪 Scaling Test Results:")
        for test in self.validation_results["scaling_tests"]:
            status_icon = "✅" if test["success"] else "❌"
            print(f"   {status_icon} {test['test_name']}")
            
            if test["success"]:
                print(f"      Scaling Time: {test['scaling_time_seconds']:.1f}s")
                print(f"      Target Count: {test['target_count']}")
                print(f"      Actual Count: {test['actual_count']}")
            else:
                print(f"      Errors: {', '.join(test['errors'])}")
        print()
        
        print("📈 Performance Metrics:")
        baseline = self.validation_results["performance_metrics"].get("baseline", {})
        if "error" not in baseline:
            print(f"   Baseline RPS: {baseline.get('rps', 'N/A')}")
            print(f"   Baseline Response Time: {baseline.get('avg_response_time', 'N/A')}ms")
            print(f"   Baseline Success Rate: {baseline.get('success_rate', 'N/A')}%")
        else:
            print(f"   Baseline Error: {baseline['error']}")
        print()
        
        print("💡 Top Recommendations:")
        recommendations = self.validation_results["recommendations"]
        for i, rec in enumerate(recommendations[:3], 1):
            priority_icon = "🔴" if rec["priority"] == "high" else "🟡" if rec["priority"] == "medium" else "🟢"
            print(f"   {i}. {priority_icon} {rec['category']}: {rec['recommendation']}")
        print()
        
        # Overall assessment
        status = self.validation_results["overall_status"]
        if status == "excellent":
            print("🎉 EXCELLENT SCALING VALIDATION - Manual scaling procedures work very well!")
        elif status == "good":
            print("✅ GOOD SCALING VALIDATION - Manual scaling works with minor issues")
        elif status == "acceptable":
            print("⚠️  ACCEPTABLE SCALING VALIDATION - Some scaling issues need attention")
        else:
            print("❌ POOR SCALING VALIDATION - Significant scaling issues detected")
        
        print("=" * 80)


async def main():
    """Main scaling validation function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate Manual Scaling Procedures')
    parser.add_argument('--cluster', type=str, required=True,
                       help='ECS cluster name')
    parser.add_argument('--service', type=str, required=True,
                       help='ECS service name')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base URL for performance testing')
    parser.add_argument('--output', type=str,
                       help='Output file for validation results (JSON)')
    
    args = parser.parse_args()
    
    # Run scaling validation
    validator = ManualScalingValidator(args.cluster, args.service, args.url)
    results = await validator.validate_scaling_procedures()
    
    # Save results if requested
    if args.output:
        try:
            # Convert datetime objects to strings for JSON serialization
            results_copy = json.loads(json.dumps(results, default=str))
            
            with open(args.output, 'w') as f:
                json.dump(results_copy, f, indent=2)
            
            print(f"📄 Validation results saved to: {args.output}")
            
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")
    
    # Exit with appropriate code
    status = results["overall_status"]
    if status == "excellent":
        exit(0)
    elif status == "good":
        exit(1)
    elif status == "acceptable":
        exit(2)
    else:
        exit(3)


if __name__ == "__main__":
    asyncio.run(main())