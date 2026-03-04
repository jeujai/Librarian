# Startup Phase Load Testing

This directory contains load testing specifically designed for validating the application's behavior during different startup phases.

## Overview

The startup phase load testing framework validates that the application performs correctly under load during:
- **MINIMAL Phase** (0-30s): Basic health checks and API availability
- **ESSENTIAL Phase** (30s-2min): Core models loading, basic functionality available
- **FULL Phase** (2-5min): All models loaded, full functionality available

## Requirements Validated

- **REQ-1**: Health Check Optimization - Health checks pass consistently during startup
- **REQ-2**: Application Startup Optimization - Progressive model loading works under load
- **REQ-3**: Startup Logging Enhancement - System remains responsive during startup

## Test Files

### `test_startup_load.py`
Main load testing framework for startup phases.

**Key Features:**
- Tests load during each startup phase independently
- Progressive load testing across all phases
- Tracks health check success rates
- Measures fallback response rates
- Validates capability availability

**Usage:**
```bash
# Run against local development server
python tests/performance/test_startup_load.py --url http://localhost:8000

# Run against staging
python tests/performance/test_startup_load.py --url https://staging.example.com

# Specify output directory
python tests/performance/test_startup_load.py --url http://localhost:8000 --output-dir ./results
```

### Quick Validation Test
```bash
# Quick validation that framework works
python test_startup_load_quick.py
```

## Test Scenarios

### 1. MINIMAL Phase Load Test
**Duration:** 30 seconds  
**Concurrent Users:** 5  
**Focus:** Health checks and basic API availability

**Expected Behavior:**
- Health endpoints respond quickly (<100ms)
- Basic API endpoints are available
- Most features return fallback responses
- No model loading blocks requests

**Success Criteria:**
- Health check success rate > 95%
- Response time < 500ms
- Error rate < 5%

### 2. ESSENTIAL Phase Load Test
**Duration:** 90 seconds  
**Concurrent Users:** 10  
**Focus:** Core functionality with essential models

**Expected Behavior:**
- Essential models are loading or loaded
- Basic chat functionality works
- Simple search operations succeed
- Some features still use fallbacks

**Success Criteria:**
- Health check success rate > 95%
- Fallback response rate < 50%
- Response time < 1000ms
- Error rate < 5%

### 3. FULL Phase Load Test
**Duration:** 120 seconds  
**Concurrent Users:** 15  
**Focus:** Full functionality with all models

**Expected Behavior:**
- All models loaded or loading
- Full functionality available
- Advanced features work
- Minimal fallback responses

**Success Criteria:**
- Health check success rate > 99%
- Fallback response rate < 10%
- Response time < 500ms
- Error rate < 1%

### 4. Progressive Load During Startup
**Duration:** 240 seconds (4 minutes)  
**Users:** 5 → 20 (progressive increase)  
**Focus:** Realistic user arrival pattern

**Expected Behavior:**
- System handles increasing load during startup
- Performance improves as models load
- No catastrophic failures
- Graceful degradation when needed

## Metrics Tracked

### Response Metrics
- Total requests
- Successful requests
- Failed requests
- Average response time
- P95 response time
- P99 response time
- Maximum response time

### Startup-Specific Metrics
- Health check success rate
- Fallback response rate
- Capability availability by phase
- Phase duration
- Error patterns

## Output Format

Results are saved as JSON files with the following structure:

```json
{
  "start_time": "2026-01-13T16:00:00",
  "base_url": "http://localhost:8000",
  "test_type": "startup_phase_load",
  "phases": {
    "minimal": {
      "phase_name": "MINIMAL",
      "phase_duration_seconds": 30.5,
      "total_requests": 150,
      "successful_requests": 145,
      "avg_response_time_ms": 85.3,
      "health_check_success_rate": 98.5,
      "fallback_response_rate": 75.0,
      "capability_availability": {
        "health_check": true,
        "basic_api": true,
        "chat": false
      }
    },
    "essential": { ... },
    "full": { ... }
  },
  "summary": {
    "total_requests": 450,
    "overall_success_rate": 96.5,
    "average_response_time_ms": 250.0
  }
}
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Run Startup Phase Load Tests
  run: |
    python tests/performance/test_startup_load.py \
      --url ${{ env.STAGING_URL }} \
      --output-dir ./test-results
  
- name: Upload Test Results
  uses: actions/upload-artifact@v2
  with:
    name: startup-load-test-results
    path: ./test-results
```

### Performance Thresholds
Configure alerts for:
- Health check success rate < 95%
- Average response time > 1000ms
- Error rate > 5%
- Fallback response rate > 80% in ESSENTIAL phase

## Troubleshooting

### High Error Rates
**Symptom:** Error rate > 10%  
**Possible Causes:**
- Application not fully started
- Health check endpoints not responding
- Network connectivity issues

**Solutions:**
- Increase startup wait time
- Check application logs
- Verify health check configuration

### High Fallback Response Rates
**Symptom:** Fallback rate > 80% in ESSENTIAL phase  
**Possible Causes:**
- Models not loading fast enough
- Model loading failures
- Incorrect phase detection

**Solutions:**
- Check model loading logs
- Verify model cache is working
- Review progressive loader configuration

### Slow Response Times
**Symptom:** Average response time > 2000ms  
**Possible Causes:**
- Resource contention during model loading
- Insufficient memory
- Network latency

**Solutions:**
- Review memory usage during startup
- Check CPU utilization
- Optimize model loading strategy

## Best Practices

1. **Run tests against staging first** - Don't run load tests against production during startup
2. **Monitor system resources** - Watch CPU, memory, and disk I/O during tests
3. **Test with realistic data** - Use production-like data volumes
4. **Vary user patterns** - Test different arrival patterns and behaviors
5. **Automate in CI/CD** - Run tests on every deployment
6. **Set appropriate thresholds** - Define clear success criteria
7. **Review results regularly** - Track trends over time

## Related Documentation

- [Startup Phase Manager](../../src/multimodal_librarian/startup/phase_manager.py)
- [Progressive Loader](../../src/multimodal_librarian/startup/progressive_loader.py)
- [Health Check Configuration](../../docs/startup/health-check-parameter-adjustments.md)
- [Comprehensive Load Testing](./comprehensive_load_test.py)

## Support

For issues or questions:
1. Check application logs during test execution
2. Review health check endpoint responses
3. Verify startup phase transitions are working
4. Consult the troubleshooting guide above
