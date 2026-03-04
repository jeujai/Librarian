#!/usr/bin/env python3
"""
Hot Reload Performance Benchmark

This script benchmarks the hot reload performance by measuring:
- File change detection time
- Server restart time
- Memory usage during reloads
- CPU usage patterns
- Overall development experience metrics
"""

import os
import sys
import time
import tempfile
import subprocess
import threading
import statistics
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
import psutil
import requests


@dataclass
class BenchmarkResult:
    """Results from a hot reload benchmark test."""
    test_name: str
    file_change_detection_time: float
    server_restart_time: float
    total_reload_time: float
    memory_usage_mb: float
    cpu_usage_percent: float
    success: bool
    error_message: str = ""


class HotReloadBenchmark:
    """Hot reload performance benchmark suite."""
    
    def __init__(self):
        self.results: List[BenchmarkResult] = []
        self.server_url = "http://localhost:8000"
        self.health_endpoint = f"{self.server_url}/health/simple"
        self.source_dir = Path("/app/src/multimodal_librarian")
        self.test_files = []
        
    def setup(self):
        """Setup benchmark environment."""
        print("🔧 Setting up hot reload benchmark...")
        
        # Check if server is running
        if not self._is_server_running():
            print("❌ Server is not running. Please start the hot reload environment first.")
            print("   Run: make dev-hot-reload")
            return False
        
        # Create test files for benchmarking
        self._create_test_files()
        
        print("✅ Benchmark setup complete")
        return True
    
    def _is_server_running(self) -> bool:
        """Check if the development server is running."""
        try:
            response = requests.get(self.health_endpoint, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def _create_test_files(self):
        """Create test files for benchmarking."""
        test_files = [
            # High priority files (should reload fast)
            self.source_dir / "test_benchmark_main.py",
            self.source_dir / "api" / "test_benchmark_router.py",
            
            # Medium priority files
            self.source_dir / "services" / "test_benchmark_service.py",
            self.source_dir / "models" / "test_benchmark_model.py",
            
            # Low priority files
            self.source_dir / "utils" / "test_benchmark_util.py",
        ]
        
        for test_file in test_files:
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(f"""# Benchmark test file
# Created: {time.time()}

def benchmark_function():
    '''Test function for hot reload benchmarking.'''
    return "benchmark_test_{time.time()}"

# Test constant
BENCHMARK_CONSTANT = {time.time()}
""")
            self.test_files.append(test_file)
    
    def _cleanup_test_files(self):
        """Clean up test files."""
        for test_file in self.test_files:
            try:
                test_file.unlink()
            except FileNotFoundError:
                pass
    
    def _wait_for_server_restart(self, timeout: float = 30.0) -> Tuple[bool, float]:
        """Wait for server to restart and measure the time."""
        start_time = time.time()
        
        # Wait for server to go down
        while self._is_server_running() and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        # Wait for server to come back up
        while not self._is_server_running() and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        restart_time = time.time() - start_time
        success = self._is_server_running()
        
        return success, restart_time
    
    def _get_system_metrics(self) -> Tuple[float, float]:
        """Get current system metrics."""
        try:
            # Get memory usage (in MB)
            memory_info = psutil.virtual_memory()
            memory_mb = (memory_info.total - memory_info.available) / 1024 / 1024
            
            # Get CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            return memory_mb, cpu_percent
        except Exception:
            return 0.0, 0.0
    
    def benchmark_file_change_detection(self, file_path: Path, priority: str) -> BenchmarkResult:
        """Benchmark file change detection time."""
        print(f"📊 Benchmarking {priority} priority file change detection...")
        
        start_time = time.time()
        memory_before, cpu_before = self._get_system_metrics()
        
        try:
            # Modify the file
            original_content = file_path.read_text()
            modified_content = original_content + f"\n# Modified at {time.time()}\n"
            
            change_start = time.time()
            file_path.write_text(modified_content)
            
            # Wait for server restart
            success, restart_time = self._wait_for_server_restart()
            
            total_time = time.time() - start_time
            detection_time = restart_time - (time.time() - change_start)
            
            memory_after, cpu_after = self._get_system_metrics()
            
            # Restore original content
            file_path.write_text(original_content)
            
            return BenchmarkResult(
                test_name=f"{priority}_priority_file_change",
                file_change_detection_time=detection_time,
                server_restart_time=restart_time,
                total_reload_time=total_time,
                memory_usage_mb=memory_after - memory_before,
                cpu_usage_percent=cpu_after - cpu_before,
                success=success
            )
            
        except Exception as e:
            return BenchmarkResult(
                test_name=f"{priority}_priority_file_change",
                file_change_detection_time=0.0,
                server_restart_time=0.0,
                total_reload_time=0.0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                success=False,
                error_message=str(e)
            )
    
    def benchmark_multiple_file_changes(self) -> BenchmarkResult:
        """Benchmark handling of multiple simultaneous file changes."""
        print("📊 Benchmarking multiple file changes (batching)...")
        
        start_time = time.time()
        memory_before, cpu_before = self._get_system_metrics()
        
        try:
            # Modify multiple files simultaneously
            original_contents = []
            for test_file in self.test_files[:3]:  # Use first 3 files
                original_contents.append(test_file.read_text())
            
            change_start = time.time()
            
            # Modify all files quickly
            for i, test_file in enumerate(self.test_files[:3]):
                modified_content = original_contents[i] + f"\n# Batch modified at {time.time()}\n"
                test_file.write_text(modified_content)
                time.sleep(0.1)  # Small delay to simulate real editing
            
            # Wait for server restart (should be batched)
            success, restart_time = self._wait_for_server_restart()
            
            total_time = time.time() - start_time
            detection_time = restart_time - (time.time() - change_start)
            
            memory_after, cpu_after = self._get_system_metrics()
            
            # Restore original contents
            for i, test_file in enumerate(self.test_files[:3]):
                test_file.write_text(original_contents[i])
            
            return BenchmarkResult(
                test_name="multiple_file_changes_batching",
                file_change_detection_time=detection_time,
                server_restart_time=restart_time,
                total_reload_time=total_time,
                memory_usage_mb=memory_after - memory_before,
                cpu_usage_percent=cpu_after - cpu_before,
                success=success
            )
            
        except Exception as e:
            return BenchmarkResult(
                test_name="multiple_file_changes_batching",
                file_change_detection_time=0.0,
                server_restart_time=0.0,
                total_reload_time=0.0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                success=False,
                error_message=str(e)
            )
    
    def benchmark_config_file_change(self) -> BenchmarkResult:
        """Benchmark config file change (should be fastest)."""
        print("📊 Benchmarking config file change...")
        
        config_file = Path("/app/.env.local")
        if not config_file.exists():
            return BenchmarkResult(
                test_name="config_file_change",
                file_change_detection_time=0.0,
                server_restart_time=0.0,
                total_reload_time=0.0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                success=False,
                error_message="Config file not found"
            )
        
        start_time = time.time()
        memory_before, cpu_before = self._get_system_metrics()
        
        try:
            # Modify config file
            original_content = config_file.read_text()
            modified_content = original_content + f"\n# Benchmark test at {time.time()}\n"
            
            change_start = time.time()
            config_file.write_text(modified_content)
            
            # Wait for server restart
            success, restart_time = self._wait_for_server_restart()
            
            total_time = time.time() - start_time
            detection_time = restart_time - (time.time() - change_start)
            
            memory_after, cpu_after = self._get_system_metrics()
            
            # Restore original content
            config_file.write_text(original_content)
            
            return BenchmarkResult(
                test_name="config_file_change",
                file_change_detection_time=detection_time,
                server_restart_time=restart_time,
                total_reload_time=total_time,
                memory_usage_mb=memory_after - memory_before,
                cpu_usage_percent=cpu_after - cpu_before,
                success=success
            )
            
        except Exception as e:
            return BenchmarkResult(
                test_name="config_file_change",
                file_change_detection_time=0.0,
                server_restart_time=0.0,
                total_reload_time=0.0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                success=False,
                error_message=str(e)
            )
    
    def run_benchmarks(self) -> List[BenchmarkResult]:
        """Run all benchmark tests."""
        print("🚀 Starting hot reload performance benchmarks...")
        print("=" * 60)
        
        if not self.setup():
            return []
        
        try:
            # Test different priority files
            test_files_with_priority = [
                (self.test_files[0], "high"),
                (self.test_files[1], "high"),
                (self.test_files[2], "medium"),
                (self.test_files[3], "medium"),
                (self.test_files[4], "low"),
            ]
            
            # Run individual file change benchmarks
            for test_file, priority in test_files_with_priority:
                result = self.benchmark_file_change_detection(test_file, priority)
                self.results.append(result)
                time.sleep(2)  # Wait between tests
            
            # Test multiple file changes
            result = self.benchmark_multiple_file_changes()
            self.results.append(result)
            time.sleep(2)
            
            # Test config file changes
            result = self.benchmark_config_file_change()
            self.results.append(result)
            
        finally:
            self._cleanup_test_files()
        
        return self.results
    
    def print_results(self):
        """Print benchmark results in a formatted table."""
        if not self.results:
            print("❌ No benchmark results to display")
            return
        
        print("\n" + "=" * 80)
        print("📊 HOT RELOAD PERFORMANCE BENCHMARK RESULTS")
        print("=" * 80)
        
        # Print individual results
        print(f"{'Test Name':<35} {'Detection':<10} {'Restart':<10} {'Total':<10} {'Memory':<10} {'Success':<8}")
        print("-" * 80)
        
        successful_results = []
        for result in self.results:
            status = "✅" if result.success else "❌"
            print(f"{result.test_name:<35} "
                  f"{result.file_change_detection_time:<10.2f} "
                  f"{result.server_restart_time:<10.2f} "
                  f"{result.total_reload_time:<10.2f} "
                  f"{result.memory_usage_mb:<10.1f} "
                  f"{status:<8}")
            
            if result.success:
                successful_results.append(result)
            elif result.error_message:
                print(f"  Error: {result.error_message}")
        
        if not successful_results:
            print("\n❌ No successful benchmark results")
            return
        
        # Print statistics
        print("\n" + "=" * 80)
        print("📈 PERFORMANCE STATISTICS")
        print("=" * 80)
        
        detection_times = [r.file_change_detection_time for r in successful_results]
        restart_times = [r.server_restart_time for r in successful_results]
        total_times = [r.total_reload_time for r in successful_results]
        
        print(f"File Change Detection Time:")
        print(f"  Average: {statistics.mean(detection_times):.2f}s")
        print(f"  Median:  {statistics.median(detection_times):.2f}s")
        print(f"  Min:     {min(detection_times):.2f}s")
        print(f"  Max:     {max(detection_times):.2f}s")
        
        print(f"\nServer Restart Time:")
        print(f"  Average: {statistics.mean(restart_times):.2f}s")
        print(f"  Median:  {statistics.median(restart_times):.2f}s")
        print(f"  Min:     {min(restart_times):.2f}s")
        print(f"  Max:     {max(restart_times):.2f}s")
        
        print(f"\nTotal Reload Time:")
        print(f"  Average: {statistics.mean(total_times):.2f}s")
        print(f"  Median:  {statistics.median(total_times):.2f}s")
        print(f"  Min:     {min(total_times):.2f}s")
        print(f"  Max:     {max(total_times):.2f}s")
        
        # Performance assessment
        print("\n" + "=" * 80)
        print("🎯 PERFORMANCE ASSESSMENT")
        print("=" * 80)
        
        avg_total_time = statistics.mean(total_times)
        
        if avg_total_time < 2.0:
            print("🚀 EXCELLENT: Hot reload performance is excellent (< 2s average)")
        elif avg_total_time < 5.0:
            print("✅ GOOD: Hot reload performance is good (< 5s average)")
        elif avg_total_time < 10.0:
            print("⚠️  FAIR: Hot reload performance is acceptable (< 10s average)")
        else:
            print("❌ POOR: Hot reload performance needs optimization (> 10s average)")
        
        # Priority-based analysis
        high_priority_results = [r for r in successful_results if "high" in r.test_name]
        medium_priority_results = [r for r in successful_results if "medium" in r.test_name]
        low_priority_results = [r for r in successful_results if "low" in r.test_name]
        
        if high_priority_results and medium_priority_results and low_priority_results:
            high_avg = statistics.mean([r.total_reload_time for r in high_priority_results])
            medium_avg = statistics.mean([r.total_reload_time for r in medium_priority_results])
            low_avg = statistics.mean([r.total_reload_time for r in low_priority_results])
            
            print(f"\nPriority-based Performance:")
            print(f"  High Priority:   {high_avg:.2f}s average")
            print(f"  Medium Priority: {medium_avg:.2f}s average")
            print(f"  Low Priority:    {low_avg:.2f}s average")
            
            if high_avg < medium_avg < low_avg:
                print("✅ Priority-based optimization is working correctly")
            else:
                print("⚠️  Priority-based optimization may need tuning")
        
        print("\n" + "=" * 80)


def main():
    """Main entry point."""
    if os.getenv("ML_ENVIRONMENT") != "local":
        print("❌ Hot reload benchmarks can only be run in local development mode")
        print("   Set ML_ENVIRONMENT=local and start the hot reload environment")
        sys.exit(1)
    
    benchmark = HotReloadBenchmark()
    results = benchmark.run_benchmarks()
    benchmark.print_results()
    
    # Return appropriate exit code
    successful_count = sum(1 for r in results if r.success)
    if successful_count == 0:
        print("\n❌ All benchmark tests failed")
        sys.exit(1)
    elif successful_count < len(results):
        print(f"\n⚠️  {len(results) - successful_count} benchmark tests failed")
        sys.exit(2)
    else:
        print(f"\n✅ All {successful_count} benchmark tests passed")
        sys.exit(0)


if __name__ == "__main__":
    main()