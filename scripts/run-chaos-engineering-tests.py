#!/usr/bin/env python3
"""
Chaos Engineering Test Runner

This script runs comprehensive chaos engineering tests to validate system resilience.
It provides different test scenarios and detailed reporting.
"""

import asyncio
import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add the src directory and project root to the Python path
project_root = os.path.dirname(__file__) + '/..'
sys.path.insert(0, os.path.join(project_root, 'src'))
sys.path.insert(0, project_root)

# Import the chaos engineering framework
from tests.integration.test_chaos_engineering import (
    ChaosEngineeringFramework,
    ChaosExperiment,
    ChaosExperimentType,
    ChaosImpact,
    TestChaosEngineering
)


class ChaosTestRunner:
    """Runner for chaos engineering tests with different scenarios."""
    
    def __init__(self):
        self.framework = ChaosEngineeringFramework()
        self.test_results = {}
        self.start_time = None
        self.end_time = None
    
    async def run_light_chaos_tests(self) -> Dict[str, Any]:
        """Run light chaos tests suitable for development environments."""
        print("🧪 Running Light Chaos Engineering Tests")
        print("=" * 50)
        
        experiments = [
            ChaosExperiment(
                experiment_id="light_001",
                name="Light Cache Failure",
                description="Test cache service failure handling",
                experiment_type=ChaosExperimentType.RANDOM_COMPONENT_FAILURE,
                target_components=['cache'],
                impact_level=ChaosImpact.LOW,
                duration_seconds=5,  # Reduced from 10
                failure_probability=0.5,
                recovery_time_seconds=2  # Reduced from 5
            ),
            ChaosExperiment(
                experiment_id="light_002",
                name="Light Search Service Restart",
                description="Test search service restart handling",
                experiment_type=ChaosExperimentType.RANDOM_RESTART,
                target_components=['search_service'],
                impact_level=ChaosImpact.LOW,
                duration_seconds=6,  # Reduced from 15
                failure_probability=0.6,
                recovery_time_seconds=2  # Reduced from 5
            )
            # Removed third experiment for faster execution
        ]
        
        return await self._run_experiment_suite("light", experiments)
    
    async def run_medium_chaos_tests(self) -> Dict[str, Any]:
        """Run medium intensity chaos tests."""
        print("🔥 Running Medium Chaos Engineering Tests")
        print("=" * 50)
        
        experiments = [
            ChaosExperiment(
                experiment_id="medium_001",
                name="Multi-Component Failure",
                description="Test multiple component failures",
                experiment_type=ChaosExperimentType.RANDOM_COMPONENT_FAILURE,
                target_components=['database', 'vector_store', 'cache'],
                impact_level=ChaosImpact.MEDIUM,
                duration_seconds=20,
                failure_probability=0.7,
                recovery_time_seconds=10
            ),
            ChaosExperiment(
                experiment_id="medium_002",
                name="Cascading Failure Test",
                description="Test cascading failure prevention",
                experiment_type=ChaosExperimentType.CASCADING_FAILURE_INJECTION,
                target_components=['database', 'vector_store', 'ai_service'],
                impact_level=ChaosImpact.MEDIUM,
                duration_seconds=25,
                failure_probability=0.8,
                recovery_time_seconds=15
            ),
            ChaosExperiment(
                experiment_id="medium_003",
                name="Network Partition",
                description="Test network partition handling",
                experiment_type=ChaosExperimentType.NETWORK_PARTITION,
                target_components=['network'],
                impact_level=ChaosImpact.MEDIUM,
                duration_seconds=18,
                failure_probability=1.0,
                recovery_time_seconds=8
            ),
            ChaosExperiment(
                experiment_id="medium_004",
                name="Memory Pressure",
                description="Test memory pressure handling",
                experiment_type=ChaosExperimentType.MEMORY_PRESSURE,
                target_components=['memory'],
                impact_level=ChaosImpact.MEDIUM,
                duration_seconds=15,
                failure_probability=1.0,
                recovery_time_seconds=10
            )
        ]
        
        return await self._run_experiment_suite("medium", experiments)
    
    async def run_heavy_chaos_tests(self) -> Dict[str, Any]:
        """Run heavy chaos tests for production readiness validation."""
        print("💥 Running Heavy Chaos Engineering Tests")
        print("=" * 50)
        
        experiments = [
            ChaosExperiment(
                experiment_id="heavy_001",
                name="Full System Chaos",
                description="Test system-wide random failures",
                experiment_type=ChaosExperimentType.RANDOM_COMPONENT_FAILURE,
                target_components=['database', 'vector_store', 'ai_service', 'search_service', 'cache'],
                impact_level=ChaosImpact.HIGH,
                duration_seconds=30,
                failure_probability=0.8,
                recovery_time_seconds=20
            ),
            ChaosExperiment(
                experiment_id="heavy_002",
                name="Resource Exhaustion",
                description="Test resource exhaustion scenarios",
                experiment_type=ChaosExperimentType.RESOURCE_EXHAUSTION,
                target_components=['memory', 'cpu'],
                impact_level=ChaosImpact.HIGH,
                duration_seconds=25,
                failure_probability=1.0,
                recovery_time_seconds=15
            ),
            ChaosExperiment(
                experiment_id="heavy_003",
                name="Configuration Corruption",
                description="Test configuration corruption handling",
                experiment_type=ChaosExperimentType.CONFIGURATION_CORRUPTION,
                target_components=['configuration'],
                impact_level=ChaosImpact.HIGH,
                duration_seconds=20,
                failure_probability=1.0,
                recovery_time_seconds=10
            ),
            ChaosExperiment(
                experiment_id="heavy_004",
                name="CPU Spike",
                description="Test CPU spike handling",
                experiment_type=ChaosExperimentType.CPU_SPIKE,
                target_components=['cpu'],
                impact_level=ChaosImpact.HIGH,
                duration_seconds=20,
                failure_probability=1.0,
                recovery_time_seconds=10
            ),
            ChaosExperiment(
                experiment_id="heavy_005",
                name="Complex Cascading Failures",
                description="Test complex cascading failure scenarios",
                experiment_type=ChaosExperimentType.CASCADING_FAILURE_INJECTION,
                target_components=['database', 'vector_store', 'ai_service', 'chat_service'],
                impact_level=ChaosImpact.CRITICAL,
                duration_seconds=35,
                failure_probability=0.9,
                recovery_time_seconds=25
            )
        ]
        
        return await self._run_experiment_suite("heavy", experiments)
    
    async def run_custom_chaos_test(self, experiment_config: Dict[str, Any]) -> Dict[str, Any]:
        """Run a custom chaos test based on configuration."""
        print(f"⚙️ Running Custom Chaos Test: {experiment_config.get('name', 'Unknown')}")
        print("=" * 50)
        
        experiment = ChaosExperiment(
            experiment_id=experiment_config.get('experiment_id', f"custom_{int(datetime.now().timestamp())}"),
            name=experiment_config.get('name', 'Custom Chaos Test'),
            description=experiment_config.get('description', 'Custom chaos engineering test'),
            experiment_type=ChaosExperimentType(experiment_config.get('experiment_type', 'random_component_failure')),
            target_components=experiment_config.get('target_components', ['cache']),
            impact_level=ChaosImpact(experiment_config.get('impact_level', 'low')),
            duration_seconds=experiment_config.get('duration_seconds', 15),
            failure_probability=experiment_config.get('failure_probability', 0.5),
            recovery_time_seconds=experiment_config.get('recovery_time_seconds', 10)
        )
        
        return await self._run_experiment_suite("custom", [experiment])
    
    async def _run_experiment_suite(self, suite_name: str, experiments: List[ChaosExperiment]) -> Dict[str, Any]:
        """Run a suite of chaos experiments."""
        suite_results = {
            'suite_name': suite_name,
            'start_time': datetime.now().isoformat(),
            'experiments': [],
            'summary': {}
        }
        
        successful_experiments = 0
        resilient_experiments = 0
        recovered_experiments = 0
        
        for i, experiment in enumerate(experiments, 1):
            print(f"\n🧪 Experiment {i}/{len(experiments)}: {experiment.name}")
            print(f"   Type: {experiment.experiment_type.value}")
            print(f"   Impact: {experiment.impact_level.value}")
            print(f"   Duration: {experiment.duration_seconds}s")
            print(f"   Components: {', '.join(experiment.target_components)}")
            
            try:
                result = await self.framework.run_chaos_experiment(experiment)
                
                # Record results
                experiment_summary = {
                    'experiment_id': experiment.experiment_id,
                    'name': experiment.name,
                    'type': experiment.experiment_type.value,
                    'success': result.success,
                    'system_resilient': result.system_resilient,
                    'recovery_successful': result.recovery_successful,
                    'cascading_failures_prevented': result.cascading_failures_prevented,
                    'duration_seconds': (result.end_time - result.start_time).total_seconds() if result.end_time else 0,
                    'error_count': len(result.error_messages),
                    'metrics': result.metrics
                }
                
                suite_results['experiments'].append(experiment_summary)
                
                # Update counters
                if result.success:
                    successful_experiments += 1
                if result.system_resilient:
                    resilient_experiments += 1
                if result.recovery_successful:
                    recovered_experiments += 1
                
                # Print results
                print(f"   Result: {'✅ PASSED' if result.success else '❌ FAILED'}")
                print(f"   Resilient: {'✅' if result.system_resilient else '❌'}")
                print(f"   Recovered: {'✅' if result.recovery_successful else '❌'}")
                
                if result.metrics:
                    successful_ops = result.metrics.get('successful_operations', 0)
                    error_count = result.metrics.get('error_counts', 0)
                    total_ops = successful_ops + error_count
                    
                    if total_ops > 0:
                        success_rate = (successful_ops / total_ops) * 100
                        print(f"   Success rate during chaos: {success_rate:.1f}%")
                
                if result.error_messages:
                    print(f"   Errors: {len(result.error_messages)}")
                    for error in result.error_messages[:2]:  # Show first 2 errors
                        print(f"     - {error}")
                
            except Exception as e:
                print(f"   ❌ EXPERIMENT FAILED: {e}")
                suite_results['experiments'].append({
                    'experiment_id': experiment.experiment_id,
                    'name': experiment.name,
                    'type': experiment.experiment_type.value,
                    'success': False,
                    'error': str(e)
                })
        
        # Calculate suite summary
        total_experiments = len(experiments)
        suite_results['summary'] = {
            'total_experiments': total_experiments,
            'successful_experiments': successful_experiments,
            'resilient_experiments': resilient_experiments,
            'recovered_experiments': recovered_experiments,
            'success_rate': (successful_experiments / max(1, total_experiments)) * 100,
            'resilience_rate': (resilient_experiments / max(1, total_experiments)) * 100,
            'recovery_rate': (recovered_experiments / max(1, total_experiments)) * 100
        }
        
        suite_results['end_time'] = datetime.now().isoformat()
        
        # Print suite summary
        print(f"\n📊 {suite_name.title()} Chaos Test Suite Summary:")
        print(f"   Total experiments: {total_experiments}")
        print(f"   Successful: {successful_experiments} ({suite_results['summary']['success_rate']:.1f}%)")
        print(f"   Resilient: {resilient_experiments} ({suite_results['summary']['resilience_rate']:.1f}%)")
        print(f"   Recovered: {recovered_experiments} ({suite_results['summary']['recovery_rate']:.1f}%)")
        
        return suite_results
    
    def save_results(self, results: Dict[str, Any], filename: Optional[str] = None) -> str:
        """Save test results to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chaos_engineering_results_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: {filename}")
        return filename
    
    async def run_pytest_integration(self) -> Dict[str, Any]:
        """Run chaos engineering tests through pytest integration."""
        print("🧪 Running Chaos Engineering Tests via Pytest Integration")
        print("=" * 60)
        
        test_instance = TestChaosEngineering()
        
        results = {
            'test_suite': 'pytest_integration',
            'start_time': datetime.now().isoformat(),
            'tests': []
        }
        
        # Define test methods to run
        test_methods = [
            ('Random Component Failures', test_instance.test_random_component_failures),
            ('Cascading Failure Prevention', test_instance.test_cascading_failure_prevention),
            ('Resource Exhaustion Resilience', test_instance.test_resource_exhaustion_resilience),
            ('Network Partition Handling', test_instance.test_network_partition_handling),
            ('Latency Injection Tolerance', test_instance.test_latency_injection_tolerance),
            ('Comprehensive Chaos Engineering', test_instance.test_comprehensive_chaos_engineering)
        ]
        
        passed_tests = 0
        
        for test_name, test_method in test_methods:
            print(f"\n🧪 Running: {test_name}")
            
            try:
                await test_method()
                print(f"   ✅ PASSED: {test_name}")
                results['tests'].append({
                    'name': test_name,
                    'status': 'passed',
                    'timestamp': datetime.now().isoformat()
                })
                passed_tests += 1
                
            except Exception as e:
                print(f"   ❌ FAILED: {test_name}: {e}")
                results['tests'].append({
                    'name': test_name,
                    'status': 'failed',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
        
        results['end_time'] = datetime.now().isoformat()
        results['summary'] = {
            'total_tests': len(test_methods),
            'passed_tests': passed_tests,
            'failed_tests': len(test_methods) - passed_tests,
            'success_rate': (passed_tests / len(test_methods)) * 100
        }
        
        print(f"\n📊 Pytest Integration Summary:")
        print(f"   Total tests: {results['summary']['total_tests']}")
        print(f"   Passed: {results['summary']['passed_tests']}")
        print(f"   Failed: {results['summary']['failed_tests']}")
        print(f"   Success rate: {results['summary']['success_rate']:.1f}%")
        
        return results


async def main():
    """Main function to run chaos engineering tests."""
    parser = argparse.ArgumentParser(description='Run chaos engineering tests')
    parser.add_argument('--mode', choices=['light', 'medium', 'heavy', 'pytest', 'custom'], 
                       default='medium', help='Test mode to run')
    parser.add_argument('--config', help='Path to custom test configuration JSON file')
    parser.add_argument('--output', help='Output file for results')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    runner = ChaosTestRunner()
    
    print("🔥 Chaos Engineering Test Runner")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        if args.mode == 'light':
            results = await runner.run_light_chaos_tests()
        elif args.mode == 'medium':
            results = await runner.run_medium_chaos_tests()
        elif args.mode == 'heavy':
            results = await runner.run_heavy_chaos_tests()
        elif args.mode == 'pytest':
            results = await runner.run_pytest_integration()
        elif args.mode == 'custom':
            if not args.config:
                print("❌ Custom mode requires --config parameter")
                sys.exit(1)
            
            with open(args.config, 'r') as f:
                config = json.load(f)
            
            results = await runner.run_custom_chaos_test(config)
        
        # Save results
        output_file = runner.save_results(results, args.output)
        
        # Overall assessment
        if 'summary' in results:
            summary = results['summary']
            overall_success = (
                summary.get('success_rate', 0) >= 70 and
                summary.get('resilience_rate', 0) >= 50 and
                summary.get('recovery_rate', 0) >= 60
            )
        else:
            overall_success = results.get('summary', {}).get('success_rate', 0) >= 70
        
        print(f"\n🎯 Overall Chaos Engineering Assessment: {'✅ PASSED' if overall_success else '❌ FAILED'}")
        
        if not overall_success:
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n⚠️ Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())