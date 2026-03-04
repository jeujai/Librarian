# Progressive Loading Memory Validation Tests

## Overview

This test suite validates memory usage during progressive model loading to ensure the application stays within memory constraints and doesn't leak memory over time.

## Test Coverage

### 1. Baseline Memory Usage
- Establishes stable baseline before any model loading
- Validates baseline stability (< 50MB drift)
- Checks for reasonable baseline memory usage

### 2. MINIMAL Phase Memory
- Validates minimal memory footprint during initial phase
- Ensures < 100MB growth during minimal operations
- No models should be loaded in this phase

### 3. ESSENTIAL Models Memory
- Monitors memory growth during essential model loading (3 models)
- Expected: ~150MB per model
- Validates memory stays within threshold
- Checks memory pressure levels

### 4. FULL Models Memory
- Validates memory usage during full model loading (4 additional models)
- Expected: ~300MB per model (larger models)
- Ensures total memory stays within limits
- Monitors memory pressure

### 5. Memory Leak Detection
- Runs for 2 minutes monitoring memory over time
- Statistical analysis to detect memory leaks
- Threshold: < 10MB/min leak rate
- Uses linear regression for trend analysis

### 6. Memory Cleanup After Unload
- Tests memory cleanup when models are unloaded
- Validates garbage collection effectiveness
- Expected: At least 100MB freed from 3 models
- Ensures no memory retention issues

### 7. Memory Pool Efficiency
- Tests memory pool utilization
- Validates pool operations don't cause memory growth
- Efficiency scoring based on memory stability

## Usage

```bash
# Run with default settings (2000MB threshold)
python tests/performance/test_progressive_loading_memory.py

# Run with custom threshold
python tests/performance/test_progressive_loading_memory.py --threshold 3000

# Specify output directory
python tests/performance/test_progressive_loading_memory.py --output-dir my_results
```

## Output

### Console Output
- Real-time test progress
- Pass/fail status for each test
- Memory growth metrics
- Efficiency scores
- Requirement validation

### JSON Output
Detailed results saved to `load_test_results/progressive_loading_memory_test_<timestamp>.json`:
- Complete memory snapshots at each phase
- Violation and warning tracking
- Efficiency scores
- Memory growth analysis
- Leak detection metrics

## Metrics Tracked

- **RSS (Resident Set Size)**: Actual physical memory used
- **VMS (Virtual Memory Size)**: Total virtual memory allocated
- **Available Memory**: System-wide available memory
- **Memory Pressure**: Low/Medium/High/Critical levels
- **Swap Usage**: Swap memory utilization
- **Models Loaded**: Number of models loaded at each snapshot

## Requirements Validated

- **REQ-2**: Application Startup Optimization
  - Memory stays within configured threshold
  - Progressive loading doesn't cause excessive memory growth
  
- **REQ-4**: Resource Initialization Optimization
  - No memory leaks detected
  - Proper memory cleanup after model unloading

## Thresholds

- **Memory Growth**: Max 150% growth from baseline
- **Memory Leak**: Max 10MB/min leak rate
- **Baseline Stability**: Max 50MB drift
- **Memory Threshold**: Configurable (default 2000MB)

## Integration

This test integrates with:
- `psutil` for system memory monitoring
- Progressive loading infrastructure
- Memory manager components
- Startup phase management

## Exit Codes

- `0`: All tests passed (100% pass rate)
- `1`: Tests passed with warnings (80-99% pass rate)
- `2`: Tests failed (< 80% pass rate)
