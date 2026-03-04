# Chaos Engineering Guide

## Overview

This guide describes the chaos engineering implementation for the multimodal librarian system. Chaos engineering is a discipline of experimenting on a system to build confidence in the system's capability to withstand turbulent conditions in production.

## What is Chaos Engineering?

Chaos engineering involves intentionally injecting failures into a system to test its resilience and recovery capabilities. The goal is to identify weaknesses before they manifest in production and cause outages.

## Our Chaos Engineering Framework

### Core Components

1. **ChaosEngineeringFramework**: Main framework for running chaos experiments
2. **ChaosExperiment**: Definition of individual chaos experiments
3. **ChaosTestRunner**: Script runner for different test scenarios
4. **Integration Tests**: Pytest-compatible chaos engineering tests

### Experiment Types

Our framework supports the following types of chaos experiments:

#### 1. Random Component Failure
- **Purpose**: Test system resilience against random component failures
- **Target Components**: Database, Vector Store, AI Service, Search Service, Cache
- **Failure Types**: Connection errors, timeouts, service unavailable, authentication errors

#### 2. Cascading Failure Injection
- **Purpose**: Test the system's ability to prevent cascading failures
- **Scenario**: Primary failure in one component triggers secondary failures
- **Validation**: Ensures failure isolation and circuit breaker effectiveness

#### 3. Resource Exhaustion
- **Purpose**: Test system behavior under resource constraints
- **Resources**: Memory, CPU, Disk
- **Scenarios**: Memory pressure, CPU spikes, disk full conditions

#### 4. Network Partition
- **Purpose**: Test network failure handling
- **Scenarios**: Network timeouts, DNS failures, connection drops
- **Validation**: Retry mechanisms, timeout handling, graceful degradation

#### 5. Latency Injection
- **Purpose**: Test system tolerance to high latency
- **Target**: Database operations, AI service calls, external APIs
- **Validation**: Timeout handling, user experience degradation

#### 6. Memory Pressure
- **Purpose**: Test memory management under pressure
- **Scenario**: Gradual memory allocation to simulate memory leaks
- **Validation**: Garbage collection, memory cleanup, OOM handling

#### 7. CPU Spike
- **Purpose**: Test CPU resource management
- **Scenario**: CPU-intensive tasks consuming system resources
- **Validation**: Task scheduling, resource prioritization

#### 8. Random Restart
- **Purpose**: Test service restart handling
- **Scenario**: Random service restarts during operation
- **Validation**: Service recovery, state persistence, graceful restart

#### 9. Configuration Corruption
- **Purpose**: Test configuration error handling
- **Scenario**: Corrupted configuration files or settings
- **Validation**: Configuration validation, fallback configurations

## Test Scenarios

### Light Chaos Tests
- **Purpose**: Development environment testing
- **Impact**: Low
- **Duration**: 10-15 seconds
- **Components**: Cache, Search Service
- **Use Case**: Daily development testing, CI/CD pipelines

### Medium Chaos Tests
- **Purpose**: Staging environment validation
- **Impact**: Medium
- **Duration**: 15-25 seconds
- **Components**: Multiple components, network, memory
- **Use Case**: Pre-production validation, integration testing

### Heavy Chaos Tests
- **Purpose**: Production readiness validation
- **Impact**: High to Critical
- **Duration**: 20-35 seconds
- **Components**: Full system, all resources
- **Use Case**: Production readiness assessment, disaster recovery testing

## Running Chaos Tests

### Using the Test Runner Script

```bash
# Light chaos tests (development)
python scripts/run-chaos-engineering-tests.py --mode light

# Medium chaos tests (staging)
python scripts/run-chaos-engineering-tests.py --mode medium

# Heavy chaos tests (production readiness)
python scripts/run-chaos-engineering-tests.py --mode heavy

# Pytest integration
python scripts/run-chaos-engineering-tests.py --mode pytest

# Custom configuration
python scripts/run-chaos-engineering-tests.py --mode custom --config tests/integration/chaos_test_configs/example_custom_chaos.json
```

### Using Pytest Directly

```bash
# Run all chaos engineering tests
pytest tests/integration/test_chaos_engineering.py -v

# Run specific test
pytest tests/integration/test_chaos_engineering.py::TestChaosEngineering::test_random_component_failures -v

# Run with detailed output
pytest tests/integration/test_chaos_engineering.py -v -s
```

### Custom Configuration

Create a JSON configuration file for custom chaos tests:

```json
{
  "experiment_id": "custom_001",
  "name": "Custom Test",
  "description": "Custom chaos engineering test",
  "experiment_type": "random_component_failure",
  "target_components": ["database", "cache"],
  "impact_level": "medium",
  "duration_seconds": 20,
  "failure_probability": 0.7,
  "recovery_time_seconds": 10
}
```

## Validation Criteria

### System Resilience
A system is considered resilient if it maintains at least 30% of its functionality during chaos injection.

### Recovery Success
Recovery is successful if the system returns to normal operation within the specified recovery time.

### Cascading Failure Prevention
Cascading failures are prevented if more than 50% of services remain available during primary failures.

## Metrics and Reporting

### Experiment Metrics
- **Response Times**: System response times during chaos
- **Error Counts**: Number of errors encountered
- **Successful Operations**: Operations that completed successfully
- **Service Availability**: Availability of individual services
- **Resource Usage**: Memory, CPU, and other resource metrics

### Success Criteria
- **Success Rate**: ≥ 70% of experiments should pass
- **Resilience Rate**: ≥ 50% of experiments should show system resilience
- **Recovery Rate**: ≥ 60% of experiments should demonstrate successful recovery

### Reporting
Results are saved in JSON format with detailed metrics:

```json
{
  "suite_name": "medium",
  "start_time": "2024-01-10T10:00:00",
  "experiments": [...],
  "summary": {
    "total_experiments": 4,
    "successful_experiments": 3,
    "success_rate": 75.0,
    "resilience_rate": 50.0,
    "recovery_rate": 75.0
  }
}
```

## Best Practices

### 1. Start Small
- Begin with light chaos tests in development
- Gradually increase intensity as confidence grows
- Use staging environments for medium tests

### 2. Monitor Everything
- Monitor system metrics during experiments
- Track error rates, response times, and resource usage
- Set up alerting for critical failures

### 3. Have Rollback Plans
- Always have rollback procedures ready
- Implement circuit breakers and fallback mechanisms
- Test recovery procedures regularly

### 4. Document Findings
- Document all experiment results
- Track improvements over time
- Share learnings with the team

### 5. Automate Testing
- Integrate chaos tests into CI/CD pipelines
- Run regular chaos experiments
- Automate result analysis and reporting

## Integration with Monitoring

### Circuit Breakers
The chaos engineering framework integrates with our circuit breaker implementation to test:
- Failure threshold detection
- Automatic service isolation
- Recovery testing and validation

### Recovery Workflows
Chaos tests validate our recovery workflow manager:
- Automatic service restoration
- Recovery validation
- Recovery notifications

### Error Logging
All chaos experiments are logged through our error logging service:
- Error categorization and tracking
- Recovery attempt logging
- Pattern detection and analysis

## Troubleshooting

### Common Issues

#### 1. Tests Failing Due to Missing Dependencies
```bash
# Ensure all dependencies are installed
pip install -r requirements.txt

# Check Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

#### 2. Memory Pressure Tests Causing System Issues
- Reduce memory allocation in tests
- Run on systems with adequate memory
- Monitor system resources during tests

#### 3. Network Tests Affecting Other Services
- Use isolated test environments
- Mock external dependencies
- Implement proper cleanup procedures

### Debugging

Enable verbose logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Use the `--verbose` flag with the test runner:
```bash
python scripts/run-chaos-engineering-tests.py --mode light --verbose
```

## Future Enhancements

### Planned Features
1. **Real-time Monitoring Dashboard**: Visual monitoring during chaos experiments
2. **Advanced Failure Patterns**: More sophisticated failure injection patterns
3. **Production-safe Testing**: Safe chaos testing in production environments
4. **Machine Learning Integration**: ML-based failure prediction and testing
5. **Distributed System Testing**: Multi-node chaos engineering

### Contributing
To add new chaos experiments:
1. Define new experiment types in `ChaosExperimentType`
2. Implement injection logic in `ChaosEngineeringFramework`
3. Add validation and cleanup procedures
4. Create test cases and documentation
5. Update this guide with new experiment details

## Conclusion

Chaos engineering is essential for building resilient systems. Our framework provides comprehensive testing capabilities to validate system behavior under various failure conditions. Regular chaos testing helps identify weaknesses, improve system resilience, and build confidence in production deployments.

For questions or contributions, please refer to the project documentation or contact the development team.