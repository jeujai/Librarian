# Concurrent Startup Testing

## Overview

This test suite validates that the application handles concurrent user requests gracefully during model loading, ensuring no "model not loaded" errors occur and that users receive immediate feedback through fallback responses.

## Purpose

During application startup, models take time to load. This test suite ensures that:

1. **No Blocking**: Concurrent requests don't block each other
2. **No Errors**: No "model not loaded" errors are returned to users
3. **Immediate Feedback**: Fallback responses are provided immediately
4. **System Stability**: No race conditions or deadlocks occur
5. **Graceful Degradation**: System degrades gracefully under load

## Test Scenarios

### 1. Concurrent Requests During MINIMAL Phase
Tests behavior when models are not yet loaded.

**Configuration:**
- Concurrent Users: 10
- Requests per User: 5
- Total Requests: 50

**Expected Results:**
- All requests receive responses (no failures)
- Fallback responses provided
- Fast response times (<500ms)
- No "model not loaded" errors

### 2. Concurrent Requests During Model Loading
Tests behavior while models are actively loading.

**Configuration:**
- Concurrent Users: 15
- Requests per User: 10
- Total Requests: 150
- Request Types: Mixed (chat, search, documents, status)

**Expected Results:**
- Graceful degradation
- Fallback responses for unavailable features
- No blocking or deadlocks
- Progressive improvement as models load

### 3. High Concurrency Stress Test
Validates system stability under heavy load.

**Configuration:**
- Concurrent Users: 50
- Requests per User: 20
- Total Requests: 1000

**Expected Results:**
- System remains responsive
- Success rate >95%
- No race conditions
- No cascading failures

### 4. Mixed Request Patterns
Simulates realistic user behavior with different patterns.

**Configuration:**
- Concurrent Users: 20
- Duration: 30 seconds
- User Types: Status checkers, chat users, search users, mixed users

**Expected Results:**
- All user types handled correctly
- Appropriate responses for each request type
- No user experiences errors

## Running Tests

### Quick Validation
```bash
# Run quick validation test (recommended first)
python test_concurrent_startup_quick.py
```

### Full Test Suite
```bash
# Run against local development server
python tests/performance/test_concurrent_startup.py --url http://localhost:8000

# Run against staging environment
python tests/performance/test_concurrent_startup.py --url https://staging.example.com

# Specify output directory
python tests/performance/test_concurrent_startup.py \
  --url http://localhost:8000 \
  --output-dir my_test_results
```

### Integration with CI/CD
```yaml
# GitHub Actions example
- name: Run Concurrent Startup Tests
  run: |
    python tests/performance/test_concurrent_startup.py \
      --url http://localhost:8000 \
      --output-dir test-results
  
- name: Upload Test Results
  uses: actions/upload-artifact@v2
  with:
    name: concurrent-startup-test-results
    path: test-results/
```

## Interpreting Results

### Success Criteria

✅ **PASS**: All of the following are true:
- Model not loaded errors = 0
- Success rate ≥ 95%
- Average response time < 1000ms
- No deadlocks or race conditions

⚠️ **WARNING**: Any of the following:
- Success rate between 90-95%
- Average response time 1000-2000ms
- Some errors but no model errors

❌ **FAIL**: Any of the following:
- Model not loaded errors > 0
- Success rate < 90%
- Average response time > 2000ms
- System crashes or hangs

### Key Metrics

#### Performance Metrics
- **Average Response Time**: Should be <1000ms
- **P95 Response Time**: Should be <2000ms
- **P99 Response Time**: Should be <3000ms
- **Requests/Second**: Higher is better

#### Startup Metrics
- **Model Not Loaded Errors**: Should be 0
- **Fallback Response Rate**: Expected to be high during startup
- **Success Rate**: Should be >95%

#### Response Quality Distribution
- **Basic**: Simple responses, models not loaded
- **Enhanced**: Some models loaded
- **Full**: All models loaded
- **Error**: Failed requests

### Sample Output

```
================================================================================
🔄 CONCURRENT REQUESTS DURING MODEL LOADING TESTS
================================================================================
Target: http://localhost:8000

📊 Test 1: Concurrent Requests During MINIMAL Phase
--------------------------------------------------------------------------------
✅ Completed: 50 requests from 10 users
   Success Rate: 100.0%
   Model Not Loaded Errors: 0
   Fallback Responses: 45 (90.0%)
   Avg Response Time: 227.2ms
   Requests/sec: 6.1

📊 Test 2: Concurrent Requests During Model Loading
--------------------------------------------------------------------------------
✅ Completed: 150 requests from 15 users
   Success Rate: 98.7%
   Model Not Loaded Errors: 0
   Fallback Responses: 75 (50.0%)
   Avg Response Time: 162.4ms
   Requests/sec: 19.6

📊 Test 3: High Concurrency Stress Test
--------------------------------------------------------------------------------
✅ Completed: 1000 requests from 50 users
   Success Rate: 96.2%
   Model Not Loaded Errors: 0
   Fallback Responses: 200 (20.0%)
   Avg Response Time: 164.9ms
   P95 Response Time: 576.0ms
   Requests/sec: 127.0

📊 Test 4: Mixed Request Patterns
--------------------------------------------------------------------------------
✅ Completed: 320 requests from 20 users
   Success Rate: 97.5%
   Model Not Loaded Errors: 0
   Fallback Responses: 160 (50.0%)
   Response Quality Distribution:
     basic: 160
     enhanced: 80
     full: 72
     error: 8

================================================================================
📊 SUMMARY
================================================================================
Total Requests: 1520
Model Not Loaded Errors: 0
Average Success Rate: 98.1%

✅ REQUIREMENT VALIDATION
--------------------------------------------------------------------------------
✅ REQ-2: No requests failed due to 'model not loaded' errors
✅ REQ-3: System remains responsive under concurrent load (>95% success)
✅ REQ-3: Fallback responses provided (480 total)
```

## Troubleshooting

### High Error Rates

**Symptom**: Success rate <90%

**Possible Causes:**
1. Server not running or not accessible
2. Server overloaded
3. Network issues
4. Configuration problems

**Solutions:**
1. Verify server is running: `curl http://localhost:8000/health`
2. Check server logs for errors
3. Reduce concurrent users or requests per user
4. Increase server resources

### Model Not Loaded Errors

**Symptom**: Model not loaded errors > 0

**Possible Causes:**
1. Fallback system not working
2. Graceful degradation not implemented
3. Error handling missing

**Solutions:**
1. Check fallback service implementation
2. Verify graceful degradation logic
3. Review error handling in endpoints
4. Check design document for expected behavior

### Timeout Errors

**Symptom**: Many timeout errors in results

**Possible Causes:**
1. Server too slow
2. Timeout values too low
3. Network latency

**Solutions:**
1. Increase timeout values in test configuration
2. Optimize server performance
3. Reduce concurrent load
4. Check network connectivity

### Slow Response Times

**Symptom**: Average response time >1000ms

**Possible Causes:**
1. Server overloaded
2. Inefficient code
3. Database bottlenecks
4. Model loading blocking requests

**Solutions:**
1. Profile server performance
2. Optimize slow endpoints
3. Implement caching
4. Ensure model loading is non-blocking

## Best Practices

### 1. Test Regularly
- Run tests after every significant change
- Include in CI/CD pipeline
- Establish performance baselines

### 2. Test Different Scenarios
- Test during different startup phases
- Test with different user counts
- Test with different request patterns

### 3. Monitor Trends
- Track metrics over time
- Set up alerting for regressions
- Compare results across versions

### 4. Test Realistic Scenarios
- Use realistic user behaviors
- Test with realistic data
- Simulate production load patterns

### 5. Analyze Failures
- Review error logs
- Check server logs
- Profile performance bottlenecks
- Fix root causes, not symptoms

## Configuration

### Test Parameters

You can customize test parameters by modifying the test calls:

```python
# Customize concurrent users
result = await tester.test_concurrent_requests_minimal_phase(
    concurrent_users=20,  # Increase from default 10
    requests_per_user=10  # Increase from default 5
)

# Customize stress test
result = await tester.test_high_concurrency_stress(
    concurrent_users=100,  # Increase from default 50
    requests_per_user=50   # Increase from default 20
)

# Customize mixed patterns test
result = await tester.test_mixed_request_patterns(
    concurrent_users=30,   # Increase from default 20
    duration_seconds=60    # Increase from default 30
)
```

### Timeout Configuration

Adjust timeouts in the test code:

```python
# In test_concurrent_startup.py
timeout = aiohttp.ClientTimeout(total=60)  # Increase from 30
```

## Requirements Validated

### REQ-2: Application Startup Optimization
- ✅ No requests fail due to "model not loaded" errors
- ✅ Graceful degradation during startup
- ✅ Fallback responses provided

### REQ-3: Smart User Experience
- ✅ System remains responsive under concurrent load
- ✅ Immediate feedback to users
- ✅ No blocking or deadlocks

## Related Documentation

- `CONCURRENT_STARTUP_TESTING_IMPLEMENTATION.md` - Implementation details
- `README_STARTUP_LOAD_TESTING.md` - Startup phase load testing
- `../../.kiro/specs/application-health-startup-optimization/design.md` - Design document
- `../../.kiro/specs/application-health-startup-optimization/requirements.md` - Requirements

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review test output and error messages
3. Check server logs
4. Review design and requirements documents
5. Contact development team

## Version History

- **v1.0** (2026-01-13): Initial implementation
  - 4 test scenarios
  - Comprehensive metrics tracking
  - Requirement validation
  - Quick validation test
