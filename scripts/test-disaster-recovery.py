#!/usr/bin/env python3
"""
Disaster Recovery Testing Script

Comprehensive testing script for disaster recovery procedures.
Tests backup and restore procedures, validates data consistency,
and checks recovery time objectives.

Usage:
    python scripts/test-disaster-recovery.py [--mode=full|backup|restore|consistency|rto]
    python scripts/test-disaster-recovery.py --help
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.integration.test_disaster_recovery import DisasterRecoveryTestFramework

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DisasterRecoveryTestRunner:
    """
    Test runner for disaster recovery testing.
    
    Provides command-line interface for running different types
    of disaster recovery tests.
    """
    
    def __init__(self):
        self.framework = DisasterRecoveryTestFramework()
        self.results_dir = project_root / "disaster_recovery_results"
        self.results_dir.mkdir(exist_ok=True)
    
    async def run_full_test(self) -> dict:
        """Run comprehensive disaster recovery test."""
        logger.info("Starting comprehensive disaster recovery test")
        return await self.framework.run_comprehensive_dr_test()
    
    async def run_backup_test(self) -> dict:
        """Run backup procedures test only."""
        logger.info("Starting backup procedures test")
        await self.framework.test_backup_procedures()
        return self.framework.test_results
    
    async def run_restore_test(self) -> dict:
        """Run restore procedures test only."""
        logger.info("Starting restore procedures test")
        await self.framework.test_restore_procedures()
        return self.framework.test_results
    
    async def run_consistency_test(self) -> dict:
        """Run data consistency test only."""
        logger.info("Starting data consistency test")
        await self.framework.test_data_consistency()
        return self.framework.test_results
    
    async def run_rto_test(self) -> dict:
        """Run recovery time objectives test only."""
        logger.info("Starting RTO/RPO test")
        await self.framework.test_recovery_time_objectives()
        return self.framework.test_results
    
    def save_results(self, results: dict, test_mode: str) -> str:
        """Save test results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dr_test_{test_mode}_{timestamp}.json"
        filepath = self.results_dir / filename
        
        # Generate comprehensive report
        report = self.framework.generate_test_report()
        report['test_mode'] = test_mode
        report['timestamp'] = timestamp
        report['raw_results'] = results
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        return str(filepath)
    
    def print_summary(self, results: dict, test_mode: str):
        """Print test summary to console."""
        report = self.framework.generate_test_report()
        
        print("\n" + "="*80)
        print(f"DISASTER RECOVERY TEST RESULTS - {test_mode.upper()} MODE")
        print("="*80)
        
        # Test summary
        summary = report['test_summary']
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed_tests']}")
        print(f"Failed: {summary['failed_tests']}")
        print(f"Success Rate: {summary['success_rate']:.1f}%")
        
        # Test duration
        if 'total_test_time' in results:
            print(f"Test Duration: {results['total_test_time']:.2f} seconds")
        
        # Overall status
        status = "✅ PASSED" if results.get('success', False) else "❌ FAILED"
        print(f"Overall Status: {status}")
        
        # Errors
        if results.get('errors'):
            print(f"\n🚨 ERRORS ({len(results['errors'])}):")
            for i, error in enumerate(results['errors'], 1):
                print(f"  {i}. {error}")
        
        # Category breakdown
        print(f"\n📊 TEST CATEGORY BREAKDOWN:")
        categories = ['backup_tests', 'restore_tests', 'consistency_tests', 'rto_tests']
        
        for category in categories:
            if category in results and isinstance(results[category], dict):
                category_tests = results[category]
                passed = sum(1 for v in category_tests.values() if v is True)
                total = len(category_tests)
                
                if total > 0:
                    success_rate = (passed / total) * 100
                    status_icon = "✅" if success_rate == 100 else "⚠️" if success_rate >= 50 else "❌"
                    print(f"  {status_icon} {category.replace('_', ' ').title()}: {passed}/{total} ({success_rate:.0f}%)")
        
        # Recommendations
        if report['recommendations']:
            print(f"\n💡 RECOMMENDATIONS:")
            for i, rec in enumerate(report['recommendations'], 1):
                print(f"  {i}. {rec}")
        
        # Next steps
        print(f"\n🎯 NEXT STEPS:")
        for i, step in enumerate(report['next_steps'], 1):
            print(f"  {i}. {step}")
        
        print("\n" + "="*80)
    
    def print_detailed_results(self, results: dict):
        """Print detailed test results."""
        print(f"\n📋 DETAILED RESULTS:")
        
        categories = ['backup_tests', 'restore_tests', 'consistency_tests', 'rto_tests']
        
        for category in categories:
            if category in results and isinstance(results[category], dict):
                print(f"\n  {category.replace('_', ' ').title()}:")
                
                for test_name, result in results[category].items():
                    if isinstance(result, bool):
                        status = "✅ PASS" if result else "❌ FAIL"
                        print(f"    {status} {test_name}")
                    elif isinstance(result, (int, float)):
                        print(f"    📊 {test_name}: {result}")
                    else:
                        print(f"    ℹ️  {test_name}: {result}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Disaster Recovery Testing Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Test Modes:
  full        - Run comprehensive disaster recovery test (default)
  backup      - Test backup procedures only
  restore     - Test restore procedures only
  consistency - Test data consistency only
  rto         - Test recovery time objectives only

Examples:
  python scripts/test-disaster-recovery.py
  python scripts/test-disaster-recovery.py --mode=backup
  python scripts/test-disaster-recovery.py --mode=rto --verbose
  python scripts/test-disaster-recovery.py --mode=full --save-results
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['full', 'backup', 'restore', 'consistency', 'rto'],
        default='full',
        help='Test mode to run (default: full)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed test results'
    )
    
    parser.add_argument(
        '--save-results',
        action='store_true',
        help='Save results to file'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        help='Directory to save results (default: ./disaster_recovery_results)'
    )
    
    args = parser.parse_args()
    
    # Set up test runner
    runner = DisasterRecoveryTestRunner()
    
    if args.output_dir:
        runner.results_dir = Path(args.output_dir)
        runner.results_dir.mkdir(exist_ok=True)
    
    # Run tests based on mode
    start_time = time.time()
    
    try:
        if args.mode == 'full':
            results = await runner.run_full_test()
        elif args.mode == 'backup':
            results = await runner.run_backup_test()
        elif args.mode == 'restore':
            results = await runner.run_restore_test()
        elif args.mode == 'consistency':
            results = await runner.run_consistency_test()
        elif args.mode == 'rto':
            results = await runner.run_rto_test()
        else:
            logger.error(f"Unknown test mode: {args.mode}")
            sys.exit(1)
        
        # Print results
        runner.print_summary(results, args.mode)
        
        if args.verbose:
            runner.print_detailed_results(results)
        
        # Save results if requested
        if args.save_results:
            filepath = runner.save_results(results, args.mode)
            print(f"\n💾 Results saved to: {filepath}")
        
        # Exit with appropriate code
        exit_code = 0 if results.get('success', False) else 1
        
        if exit_code == 0:
            print(f"\n🎉 All tests passed! Disaster recovery procedures are ready.")
        else:
            print(f"\n⚠️  Some tests failed. Please review and fix issues before production.")
        
        sys.exit(exit_code)
    
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(130)
    
    except Exception as e:
        logger.error(f"Test failed with error: {str(e)}")
        sys.exit(1)
    
    finally:
        total_time = time.time() - start_time
        logger.info(f"Test completed in {total_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())