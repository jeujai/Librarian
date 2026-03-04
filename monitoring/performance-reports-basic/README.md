# Basic Performance Reports for AWS Learning Deployment

This directory contains performance testing reports and monitoring data for the Multimodal Librarian system deployed on AWS in a learning-focused configuration.

## Overview

The performance testing framework provides comprehensive analysis of system behavior under load, focusing on:

- **Basic Load Testing**: General API endpoint performance
- **Chat Interface Testing**: WebSocket and real-time messaging performance  
- **ML Training Testing**: Machine learning and processing pipeline performance
- **System Resource Monitoring**: CPU, memory, and database performance
- **Cost Analysis**: Performance vs. cost optimization insights

## Report Types

### 1. Load Test Reports
- **File Pattern**: `load_test_report_YYYYMMDD_HHMMSS.json`
- **Content**: Basic API endpoint performance under concurrent load
- **Metrics**: Response times, throughput, error rates, success rates

### 2. Chat Performance Reports
- **File Pattern**: `chat_performance_YYYYMMDD_HHMMSS.json`
- **Content**: WebSocket connection and messaging performance
- **Metrics**: Connection success rates, message latency, delivery rates

### 3. ML Training Reports
- **File Pattern**: `ml_performance_YYYYMMDD_HHMMSS.json`
- **Content**: ML training and processing pipeline performance
- **Metrics**: Processing times, throughput, resource utilization

### 4. System Monitoring Reports
- **File Pattern**: `system_monitoring_YYYYMMDD_HHMMSS.json`
- **Content**: System resource utilization during testing
- **Metrics**: CPU usage, memory consumption, database performance

### 5. Performance Summary Reports
- **File Pattern**: `performance_summary_YYYYMMDD.json`
- **Content**: Daily aggregated performance metrics
- **Metrics**: Trends, comparisons, recommendations

## Key Performance Indicators (KPIs)

### Response Time Targets (Learning Environment)
- **Health Check**: < 100ms (95th percentile)
- **API Endpoints**: < 500ms (95th percentile)
- **Chat Messages**: < 200ms (95th percentile)
- **Document Processing**: < 5000ms (95th percentile)
- **ML Training Operations**: < 10000ms (95th percentile)

### Throughput Targets
- **Concurrent Users**: 10-20 users (learning load)
- **Requests per Second**: 50-100 RPS
- **WebSocket Connections**: 20-50 concurrent
- **Document Processing**: 5-10 documents/minute
- **ML Operations**: 2-5 operations/minute

### Success Rate Targets
- **API Endpoints**: > 95% success rate
- **WebSocket Connections**: > 90% success rate
- **Message Delivery**: > 95% delivery rate
- **Document Processing**: > 90% success rate
- **ML Training**: > 85% success rate

### Resource Utilization Targets (Cost-Optimized)
- **CPU Usage**: < 70% average, < 90% peak
- **Memory Usage**: < 80% average, < 95% peak
- **Database Connections**: < 80% of pool size
- **Storage Usage**: Monitor growth trends

## Performance Testing Scenarios

### Basic Load Testing
```bash
# Run basic load test
python tests/performance/basic_load_test.py \
  --url https://your-alb-url.amazonaws.com \
  --users 10 \
  --duration 30 \
  --output monitoring/performance-reports-basic/load_test_$(date +%Y%m%d_%H%M%S).json
```

### Chat Interface Testing
```bash
# Run chat performance test
python tests/performance/chat_basic_load_test.py \
  --url https://your-alb-url.amazonaws.com \
  --ws-url wss://your-alb-url.amazonaws.com \
  --users 10 \
  --duration 60 \
  --messages 10 \
  --output monitoring/performance-reports-basic/chat_performance_$(date +%Y%m%d_%H%M%S).json
```

### ML Training Testing
```bash
# Run ML performance test
python tests/performance/ml_training_basic_test.py \
  --url https://your-alb-url.amazonaws.com \
  --concurrent 5 \
  --operations 10 \
  --duration 120 \
  --output monitoring/performance-reports-basic/ml_performance_$(date +%Y%m%d_%H%M%S).json
```

## Performance Analysis

### Automated Analysis
The performance testing framework automatically provides:

- **Response Time Analysis**: Percentile distributions, outlier detection
- **Throughput Analysis**: Peak capacity, sustained load capabilities
- **Error Analysis**: Error patterns, failure modes, recovery times
- **Resource Correlation**: Performance vs. resource utilization
- **Cost Analysis**: Performance per dollar spent

### Manual Analysis Guidelines

1. **Trend Analysis**: Compare reports over time to identify performance trends
2. **Bottleneck Identification**: Look for consistent slow operations or high error rates
3. **Capacity Planning**: Use peak performance data to plan scaling decisions
4. **Cost Optimization**: Identify performance improvements that reduce costs

## Performance Optimization Recommendations

### Database Optimization
- Monitor slow queries and optimize indexes
- Tune connection pool settings based on load patterns
- Consider read replicas for read-heavy workloads

### Application Optimization
- Implement caching for frequently accessed data
- Optimize API response sizes and formats
- Use connection pooling for external services

### Infrastructure Optimization
- Monitor CloudWatch metrics for scaling decisions
- Optimize ECS task resource allocations
- Consider CloudFront caching for static content

### Cost Optimization
- Right-size instances based on actual usage patterns
- Use spot instances for non-critical workloads
- Implement auto-scaling based on performance metrics

## Monitoring Integration

### CloudWatch Integration
Performance test results are automatically sent to CloudWatch custom metrics:

- `PerformanceTest/ResponseTime`
- `PerformanceTest/Throughput`
- `PerformanceTest/ErrorRate`
- `PerformanceTest/SuccessRate`

### Alerting
CloudWatch alarms are configured for:

- Response time degradation (> 2x baseline)
- Error rate spikes (> 5%)
- Throughput drops (< 50% of baseline)
- Resource utilization alerts

## Report Retention

- **Daily Reports**: Kept for 30 days
- **Weekly Summaries**: Kept for 6 months
- **Monthly Summaries**: Kept for 2 years
- **Critical Incident Reports**: Kept indefinitely

## Troubleshooting Performance Issues

### High Response Times
1. Check database query performance
2. Review application logs for bottlenecks
3. Monitor resource utilization (CPU, memory)
4. Check network latency and connectivity

### High Error Rates
1. Review application error logs
2. Check database connection health
3. Verify external service availability
4. Monitor rate limiting and throttling

### Low Throughput
1. Check resource constraints (CPU, memory)
2. Review connection pool settings
3. Monitor database performance
4. Check for serialization bottlenecks

### WebSocket Issues
1. Check load balancer WebSocket configuration
2. Monitor connection timeouts and keepalives
3. Review WebSocket error logs
4. Test connection stability under load

## Learning Objectives

This performance testing framework is designed to help learn:

1. **Performance Testing Fundamentals**: Load testing concepts and methodologies
2. **AWS Performance Monitoring**: CloudWatch metrics and alerting
3. **Application Optimization**: Identifying and resolving performance bottlenecks
4. **Cost Optimization**: Balancing performance with cost considerations
5. **Capacity Planning**: Understanding system limits and scaling requirements

## Next Steps

After completing basic performance testing:

1. **Advanced Load Testing**: Implement more complex load patterns
2. **Chaos Engineering**: Test system resilience under failure conditions
3. **Performance Regression Testing**: Automate performance testing in CI/CD
4. **Real User Monitoring**: Implement RUM for production insights
5. **Advanced Optimization**: Implement advanced caching and optimization strategies

## Support

For questions about performance testing or optimization:

1. Review CloudWatch dashboards and metrics
2. Check application logs for performance insights
3. Consult AWS documentation for optimization best practices
4. Consider AWS support for complex performance issues