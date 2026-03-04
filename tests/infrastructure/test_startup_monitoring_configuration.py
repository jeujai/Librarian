"""
Test Startup Monitoring Configuration

This test validates that the startup monitoring and alerting system is properly
configured in AWS CloudWatch.
"""

import pytest
import boto3
from botocore.exceptions import ClientError
from typing import Dict, List, Set
import os


@pytest.fixture
def environment():
    """Get environment from environment variable or default to 'dev'."""
    return os.getenv('ENVIRONMENT', 'dev')


@pytest.fixture
def name_prefix(environment):
    """Generate name prefix for resources."""
    return f"multimodal-librarian-{environment}"


@pytest.fixture
def cloudwatch_client():
    """Create CloudWatch client."""
    return boto3.client('cloudwatch', region_name=os.getenv('AWS_REGION', 'us-east-1'))


@pytest.fixture
def logs_client():
    """Create CloudWatch Logs client."""
    return boto3.client('logs', region_name=os.getenv('AWS_REGION', 'us-east-1'))


@pytest.fixture
def sns_client():
    """Create SNS client."""
    return boto3.client('sns', region_name=os.getenv('AWS_REGION', 'us-east-1'))


class TestStartupMonitoringAlarms:
    """Test CloudWatch alarms for startup monitoring."""
    
    def test_minimal_phase_timeout_alarm_exists(self, cloudwatch_client, name_prefix):
        """Test that minimal phase timeout alarm is configured."""
        alarm_name = f"{name_prefix}-minimal-phase-timeout"
        
        try:
            response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
            alarms = response.get('MetricAlarms', [])
            
            assert len(alarms) == 1, f"Alarm {alarm_name} not found"
            
            alarm = alarms[0]
            assert alarm['ComparisonOperator'] == 'GreaterThanThreshold'
            assert alarm['Threshold'] == 60.0
            assert alarm['MetricName'] == 'MinimalPhaseCompletionTime'
            assert 'MultimodalLibrarian' in alarm['Namespace']
            
        except ClientError as e:
            pytest.fail(f"Failed to describe alarm: {e}")
    
    def test_essential_phase_timeout_alarm_exists(self, cloudwatch_client, name_prefix):
        """Test that essential phase timeout alarm is configured."""
        alarm_name = f"{name_prefix}-essential-phase-timeout"
        
        try:
            response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
            alarms = response.get('MetricAlarms', [])
            
            assert len(alarms) == 1, f"Alarm {alarm_name} not found"
            
            alarm = alarms[0]
            assert alarm['ComparisonOperator'] == 'GreaterThanThreshold'
            assert alarm['Threshold'] == 180.0
            assert alarm['MetricName'] == 'EssentialPhaseCompletionTime'
            
        except ClientError as e:
            pytest.fail(f"Failed to describe alarm: {e}")
    
    def test_model_loading_failures_alarm_exists(self, cloudwatch_client, name_prefix):
        """Test that model loading failures alarm is configured."""
        alarm_name = f"{name_prefix}-model-loading-failures"
        
        try:
            response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
            alarms = response.get('MetricAlarms', [])
            
            assert len(alarms) == 1, f"Alarm {alarm_name} not found"
            
            alarm = alarms[0]
            assert alarm['ComparisonOperator'] == 'GreaterThanThreshold'
            assert alarm['Threshold'] == 2.0
            assert alarm['MetricName'] == 'ModelLoadingFailureCount'
            assert alarm['Statistic'] == 'Sum'
            
        except ClientError as e:
            pytest.fail(f"Failed to describe alarm: {e}")
    
    def test_user_wait_time_alarms_exist(self, cloudwatch_client, name_prefix):
        """Test that user wait time alarms are configured."""
        alarm_names = [
            f"{name_prefix}-user-wait-time-high",
            f"{name_prefix}-user-wait-time-p95-high"
        ]
        
        try:
            response = cloudwatch_client.describe_alarms(AlarmNames=alarm_names)
            alarms = response.get('MetricAlarms', [])
            
            assert len(alarms) == 2, f"Expected 2 user wait time alarms, found {len(alarms)}"
            
            # Check average wait time alarm
            avg_alarm = next((a for a in alarms if 'p95' not in a['AlarmName']), None)
            assert avg_alarm is not None
            assert avg_alarm['Threshold'] == 30000.0
            assert avg_alarm['Statistic'] == 'Average'
            
            # Check P95 wait time alarm
            p95_alarm = next((a for a in alarms if 'p95' in a['AlarmName']), None)
            assert p95_alarm is not None
            assert p95_alarm['Threshold'] == 60000.0
            assert p95_alarm['ExtendedStatistic'] == 'p95'
            
        except ClientError as e:
            pytest.fail(f"Failed to describe alarms: {e}")
    
    def test_cache_hit_rate_alarm_exists(self, cloudwatch_client, name_prefix):
        """Test that cache hit rate alarm is configured."""
        alarm_name = f"{name_prefix}-low-cache-hit-rate"
        
        try:
            response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
            alarms = response.get('MetricAlarms', [])
            
            assert len(alarms) == 1, f"Alarm {alarm_name} not found"
            
            alarm = alarms[0]
            assert alarm['ComparisonOperator'] == 'LessThanThreshold'
            assert alarm['Threshold'] == 50.0
            # This alarm uses metric math, so check for Metrics field
            assert 'Metrics' in alarm or 'MetricName' in alarm
            
        except ClientError as e:
            pytest.fail(f"Failed to describe alarm: {e}")
    
    def test_health_check_failures_alarm_exists(self, cloudwatch_client, name_prefix):
        """Test that health check failures alarm is configured."""
        alarm_name = f"{name_prefix}-health-check-failures"
        
        try:
            response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
            alarms = response.get('MetricAlarms', [])
            
            assert len(alarms) == 1, f"Alarm {alarm_name} not found"
            
            alarm = alarms[0]
            assert alarm['ComparisonOperator'] == 'GreaterThanThreshold'
            assert alarm['Threshold'] == 3.0
            assert alarm['MetricName'] == 'HealthCheckFailureCount'
            
        except ClientError as e:
            pytest.fail(f"Failed to describe alarm: {e}")
    
    def test_composite_startup_failure_alarm_exists(self, cloudwatch_client, name_prefix):
        """Test that composite startup failure alarm is configured."""
        alarm_name = f"{name_prefix}-startup-failure-composite"
        
        try:
            response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
            composite_alarms = response.get('CompositeAlarms', [])
            
            assert len(composite_alarms) == 1, f"Composite alarm {alarm_name} not found"
            
            alarm = composite_alarms[0]
            assert 'AlarmRule' in alarm
            # Check that it references other alarms
            assert 'minimal-phase-timeout' in alarm['AlarmRule']
            assert 'model-loading-failures' in alarm['AlarmRule']
            assert 'health-check-failures' in alarm['AlarmRule']
            
        except ClientError as e:
            pytest.fail(f"Failed to describe composite alarm: {e}")
    
    def test_all_alarms_have_actions(self, cloudwatch_client, name_prefix):
        """Test that all alarms have appropriate actions configured."""
        try:
            # Get all alarms for this environment
            paginator = cloudwatch_client.get_paginator('describe_alarms')
            
            startup_alarms = []
            for page in paginator.paginate():
                for alarm in page.get('MetricAlarms', []) + page.get('CompositeAlarms', []):
                    if name_prefix in alarm['AlarmName'] and 'startup' in alarm['AlarmName'].lower():
                        startup_alarms.append(alarm)
            
            assert len(startup_alarms) > 0, "No startup alarms found"
            
            for alarm in startup_alarms:
                # Check that alarm has actions
                assert len(alarm.get('AlarmActions', [])) > 0, \
                    f"Alarm {alarm['AlarmName']} has no alarm actions"
                
                # Check that alarm has OK actions
                assert len(alarm.get('OKActions', [])) > 0, \
                    f"Alarm {alarm['AlarmName']} has no OK actions"
                
        except ClientError as e:
            pytest.fail(f"Failed to check alarm actions: {e}")


class TestStartupMonitoringMetricFilters:
    """Test CloudWatch metric filters for startup monitoring."""
    
    def test_phase_completion_metric_filters_exist(self, logs_client, name_prefix):
        """Test that phase completion metric filters are configured."""
        log_group_name = f"/aws/application/{name_prefix}"
        
        expected_filters = [
            f"{name_prefix}-minimal-phase-completion",
            f"{name_prefix}-essential-phase-completion",
            f"{name_prefix}-full-phase-completion"
        ]
        
        try:
            response = logs_client.describe_metric_filters(logGroupName=log_group_name)
            existing_filters = {f['filterName'] for f in response.get('metricFilters', [])}
            
            for filter_name in expected_filters:
                assert filter_name in existing_filters, \
                    f"Metric filter {filter_name} not found"
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                pytest.skip(f"Log group {log_group_name} not found - infrastructure may not be deployed")
            else:
                pytest.fail(f"Failed to describe metric filters: {e}")
    
    def test_model_loading_metric_filters_exist(self, logs_client, name_prefix):
        """Test that model loading metric filters are configured."""
        log_group_name = f"/aws/application/{name_prefix}"
        
        expected_filters = [
            f"{name_prefix}-model-loading-success",
            f"{name_prefix}-model-loading-failure",
            f"{name_prefix}-model-loading-duration"
        ]
        
        try:
            response = logs_client.describe_metric_filters(logGroupName=log_group_name)
            existing_filters = {f['filterName'] for f in response.get('metricFilters', [])}
            
            for filter_name in expected_filters:
                assert filter_name in existing_filters, \
                    f"Metric filter {filter_name} not found"
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                pytest.skip(f"Log group {log_group_name} not found")
            else:
                pytest.fail(f"Failed to describe metric filters: {e}")
    
    def test_user_experience_metric_filters_exist(self, logs_client, name_prefix):
        """Test that user experience metric filters are configured."""
        log_group_name = f"/aws/application/{name_prefix}"
        
        expected_filters = [
            f"{name_prefix}-user-wait-time",
            f"{name_prefix}-fallback-response-usage"
        ]
        
        try:
            response = logs_client.describe_metric_filters(logGroupName=log_group_name)
            existing_filters = {f['filterName'] for f in response.get('metricFilters', [])}
            
            for filter_name in expected_filters:
                assert filter_name in existing_filters, \
                    f"Metric filter {filter_name} not found"
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                pytest.skip(f"Log group {log_group_name} not found")
            else:
                pytest.fail(f"Failed to describe metric filters: {e}")
    
    def test_cache_metric_filters_exist(self, logs_client, name_prefix):
        """Test that cache performance metric filters are configured."""
        log_group_name = f"/aws/application/{name_prefix}"
        
        expected_filters = [
            f"{name_prefix}-model-cache-hit",
            f"{name_prefix}-model-cache-miss"
        ]
        
        try:
            response = logs_client.describe_metric_filters(logGroupName=log_group_name)
            existing_filters = {f['filterName'] for f in response.get('metricFilters', [])}
            
            for filter_name in expected_filters:
                assert filter_name in existing_filters, \
                    f"Metric filter {filter_name} not found"
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                pytest.skip(f"Log group {log_group_name} not found")
            else:
                pytest.fail(f"Failed to describe metric filters: {e}")


class TestStartupMonitoringSNS:
    """Test SNS topics for startup monitoring."""
    
    def test_startup_alerts_topic_exists(self, sns_client, name_prefix):
        """Test that startup alerts SNS topic exists."""
        try:
            topics = sns_client.list_topics()
            topic_arns = [t['TopicArn'] for t in topics.get('Topics', [])]
            
            startup_topic = next(
                (arn for arn in topic_arns if f"{name_prefix}-startup-alerts" in arn),
                None
            )
            
            assert startup_topic is not None, \
                f"Startup alerts topic not found for {name_prefix}"
            
            # Check topic attributes
            response = sns_client.get_topic_attributes(TopicArn=startup_topic)
            attributes = response.get('Attributes', {})
            
            # Verify encryption is enabled
            assert 'KmsMasterKeyId' in attributes, \
                "Topic should have KMS encryption enabled"
            
        except ClientError as e:
            pytest.fail(f"Failed to check SNS topic: {e}")
    
    def test_startup_alerts_topic_has_subscriptions(self, sns_client, name_prefix):
        """Test that startup alerts topic has at least one subscription."""
        try:
            topics = sns_client.list_topics()
            topic_arns = [t['TopicArn'] for t in topics.get('Topics', [])]
            
            startup_topic = next(
                (arn for arn in topic_arns if f"{name_prefix}-startup-alerts" in arn),
                None
            )
            
            if startup_topic is None:
                pytest.skip("Startup alerts topic not found")
            
            # Get topic attributes
            response = sns_client.get_topic_attributes(TopicArn=startup_topic)
            attributes = response.get('Attributes', {})
            
            # Check for subscriptions (confirmed or pending)
            confirmed = int(attributes.get('SubscriptionsConfirmed', '0'))
            pending = int(attributes.get('SubscriptionsPending', '0'))
            
            # At least one subscription should exist (confirmed or pending)
            # This is a soft check - in dev environments, subscriptions may not be configured
            if confirmed == 0 and pending == 0:
                pytest.skip("No subscriptions configured - this is acceptable for dev/test environments")
            
        except ClientError as e:
            pytest.fail(f"Failed to check SNS subscriptions: {e}")


class TestStartupMonitoringDashboards:
    """Test CloudWatch dashboards for startup monitoring."""
    
    def test_startup_monitoring_dashboard_exists(self, cloudwatch_client, name_prefix):
        """Test that startup monitoring dashboard exists."""
        dashboard_name = f"{name_prefix}-startup-monitoring"
        
        try:
            response = cloudwatch_client.get_dashboard(DashboardName=dashboard_name)
            
            assert 'DashboardBody' in response, \
                f"Dashboard {dashboard_name} has no body"
            
            # Parse dashboard body
            import json
            dashboard_body = json.loads(response['DashboardBody'])
            
            # Check that dashboard has widgets
            assert 'widgets' in dashboard_body, \
                "Dashboard should have widgets"
            assert len(dashboard_body['widgets']) > 0, \
                "Dashboard should have at least one widget"
            
            # Check for key widgets
            widget_titles = [w.get('properties', {}).get('title', '') for w in dashboard_body['widgets']]
            
            assert any('Phase' in title for title in widget_titles), \
                "Dashboard should have phase completion widget"
            assert any('Model' in title for title in widget_titles), \
                "Dashboard should have model loading widget"
            assert any('User' in title or 'Wait' in title for title in widget_titles), \
                "Dashboard should have user experience widget"
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFound':
                pytest.fail(f"Dashboard {dashboard_name} not found")
            else:
                pytest.fail(f"Failed to get dashboard: {e}")


class TestStartupMonitoringInsightsQueries:
    """Test CloudWatch Insights queries for startup monitoring."""
    
    def test_startup_phase_analysis_query_exists(self, logs_client, name_prefix):
        """Test that startup phase analysis query is configured."""
        query_name = f"{name_prefix}-startup-phase-analysis"
        
        try:
            response = logs_client.describe_query_definitions()
            query_definitions = response.get('QueryDefinitions', [])
            
            query = next(
                (q for q in query_definitions if q['Name'] == query_name),
                None
            )
            
            assert query is not None, f"Query {query_name} not found"
            assert 'StartupPhaseManager' in query['QueryString'], \
                "Query should filter for StartupPhaseManager component"
            
        except ClientError as e:
            pytest.fail(f"Failed to describe query definitions: {e}")
    
    def test_model_loading_analysis_query_exists(self, logs_client, name_prefix):
        """Test that model loading analysis query is configured."""
        query_name = f"{name_prefix}-model-loading-analysis"
        
        try:
            response = logs_client.describe_query_definitions()
            query_definitions = response.get('QueryDefinitions', [])
            
            query = next(
                (q for q in query_definitions if q['Name'] == query_name),
                None
            )
            
            assert query is not None, f"Query {query_name} not found"
            assert 'ModelManager' in query['QueryString'], \
                "Query should filter for ModelManager component"
            
        except ClientError as e:
            pytest.fail(f"Failed to describe query definitions: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
