# Startup Optimization Monitoring Configuration
# This file contains CloudWatch alarms and metrics for application startup monitoring

# SNS Topic for Startup Alerts
resource "aws_sns_topic" "startup_alerts" {
  name              = "${var.name_prefix}-startup-alerts"
  kms_master_key_id = var.kms_key_arn

  tags = merge(var.tags, {
    Component = "StartupMonitoring"
    Purpose   = "StartupAlerts"
  })
}

# CloudWatch Log Metric Filters for Startup Events

# Startup Phase Completion Metrics
resource "aws_cloudwatch_log_metric_filter" "minimal_phase_completion" {
  name           = "${var.name_prefix}-minimal-phase-completion"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"StartupPhaseManager\", message=\"*Phase transition*\", phase=\"minimal\", status=\"completed\", duration]"

  metric_transformation {
    name      = "MinimalPhaseCompletionTime"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "$duration"
    unit      = "Seconds"
  }
}

resource "aws_cloudwatch_log_metric_filter" "essential_phase_completion" {
  name           = "${var.name_prefix}-essential-phase-completion"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"StartupPhaseManager\", message=\"*Phase transition*\", phase=\"essential\", status=\"completed\", duration]"

  metric_transformation {
    name      = "EssentialPhaseCompletionTime"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "$duration"
    unit      = "Seconds"
  }
}

resource "aws_cloudwatch_log_metric_filter" "full_phase_completion" {
  name           = "${var.name_prefix}-full-phase-completion"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"StartupPhaseManager\", message=\"*Phase transition*\", phase=\"full\", status=\"completed\", duration]"

  metric_transformation {
    name      = "FullPhaseCompletionTime"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "$duration"
    unit      = "Seconds"
  }
}

# Model Loading Metrics
resource "aws_cloudwatch_log_metric_filter" "model_loading_success" {
  name           = "${var.name_prefix}-model-loading-success"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"ModelManager\", message=\"*Model loaded successfully*\", model_name, duration]"

  metric_transformation {
    name      = "ModelLoadingSuccessCount"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "model_loading_failure" {
  name           = "${var.name_prefix}-model-loading-failure"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level=\"ERROR\", component=\"ModelManager\", message=\"*Model loading failed*\", model_name]"

  metric_transformation {
    name      = "ModelLoadingFailureCount"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "model_loading_duration" {
  name           = "${var.name_prefix}-model-loading-duration"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"ModelManager\", message=\"*Model loaded*\", model_name, duration_seconds]"

  metric_transformation {
    name      = "ModelLoadingDuration"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "$duration_seconds"
    unit      = "Seconds"
  }
}

# User Experience Metrics
resource "aws_cloudwatch_log_metric_filter" "user_wait_time" {
  name           = "${var.name_prefix}-user-wait-time"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"UserWaitTracking\", message=\"*User request completed*\", wait_time_ms]"

  metric_transformation {
    name      = "UserWaitTime"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "$wait_time_ms"
    unit      = "Milliseconds"
  }
}

resource "aws_cloudwatch_log_metric_filter" "fallback_response_usage" {
  name           = "${var.name_prefix}-fallback-response-usage"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"FallbackService\", message=\"*Fallback response provided*\"]"

  metric_transformation {
    name      = "FallbackResponseCount"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "cache_hit_rate" {
  name           = "${var.name_prefix}-model-cache-hit"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"ModelCache\", message=\"*Cache hit*\", model_name]"

  metric_transformation {
    name      = "ModelCacheHitCount"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "cache_miss_rate" {
  name           = "${var.name_prefix}-model-cache-miss"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level, component=\"ModelCache\", message=\"*Cache miss*\", model_name]"

  metric_transformation {
    name      = "ModelCacheMissCount"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "1"
    unit      = "Count"
  }
}

# Health Check Metrics
resource "aws_cloudwatch_log_metric_filter" "health_check_failure" {
  name           = "${var.name_prefix}-health-check-failure"
  log_group_name = aws_cloudwatch_log_group.application.name
  pattern        = "[timestamp, request_id, level=\"ERROR\", component=\"HealthCheck\", message=\"*Health check failed*\"]"

  metric_transformation {
    name      = "HealthCheckFailureCount"
    namespace = "MultimodalLibrarian/${var.environment}/Startup"
    value     = "1"
    unit      = "Count"
  }
}

# CloudWatch Alarms for Startup Phases

# Minimal Phase Timeout Alarm
resource "aws_cloudwatch_metric_alarm" "minimal_phase_timeout" {
  alarm_name          = "${var.name_prefix}-minimal-phase-timeout"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "MinimalPhaseCompletionTime"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "60"
  statistic           = "Maximum"
  threshold           = "60"
  alarm_description   = "Minimal startup phase taking longer than 60 seconds"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.critical_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "High"
    Component = "StartupPhase"
    Phase     = "Minimal"
  })
}

# Essential Phase Timeout Alarm
resource "aws_cloudwatch_metric_alarm" "essential_phase_timeout" {
  alarm_name          = "${var.name_prefix}-essential-phase-timeout"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "EssentialPhaseCompletionTime"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "120"
  statistic           = "Maximum"
  threshold           = "180"
  alarm_description   = "Essential startup phase taking longer than 3 minutes"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.warning_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "High"
    Component = "StartupPhase"
    Phase     = "Essential"
  })
}

# Full Phase Timeout Alarm
resource "aws_cloudwatch_metric_alarm" "full_phase_timeout" {
  alarm_name          = "${var.name_prefix}-full-phase-timeout"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "FullPhaseCompletionTime"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "600"
  alarm_description   = "Full startup phase taking longer than 10 minutes"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.warning_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "Medium"
    Component = "StartupPhase"
    Phase     = "Full"
  })
}

# Model Loading Failure Alarm
resource "aws_cloudwatch_metric_alarm" "model_loading_failures" {
  alarm_name          = "${var.name_prefix}-model-loading-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ModelLoadingFailureCount"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "300"
  statistic           = "Sum"
  threshold           = "2"
  alarm_description   = "Multiple model loading failures detected"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.critical_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "Critical"
    Component = "ModelLoading"
  })
}

# Model Loading Duration Alarm
resource "aws_cloudwatch_metric_alarm" "model_loading_slow" {
  alarm_name          = "${var.name_prefix}-model-loading-slow"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ModelLoadingDuration"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "300"
  statistic           = "Average"
  threshold           = "180"
  alarm_description   = "Model loading taking longer than expected (>3 minutes average)"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.warning_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "Medium"
    Component = "ModelLoading"
  })
}

# User Wait Time Alarm
resource "aws_cloudwatch_metric_alarm" "user_wait_time_high" {
  alarm_name          = "${var.name_prefix}-user-wait-time-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "UserWaitTime"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "300"
  statistic           = "Average"
  threshold           = "30000"
  alarm_description   = "User wait times exceeding 30 seconds on average"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.warning_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "Medium"
    Component = "UserExperience"
  })
}

# P95 User Wait Time Alarm
resource "aws_cloudwatch_metric_alarm" "user_wait_time_p95_high" {
  alarm_name          = "${var.name_prefix}-user-wait-time-p95-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "UserWaitTime"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "300"
  extended_statistic  = "p95"
  threshold           = "60000"
  alarm_description   = "P95 user wait times exceeding 60 seconds"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.critical_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "High"
    Component = "UserExperience"
  })
}

# High Fallback Usage Alarm
resource "aws_cloudwatch_metric_alarm" "high_fallback_usage" {
  alarm_name          = "${var.name_prefix}-high-fallback-usage"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "3"
  metric_name         = "FallbackResponseCount"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "300"
  statistic           = "Sum"
  threshold           = "50"
  alarm_description   = "High fallback response usage indicating degraded service"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.warning_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "Medium"
    Component = "UserExperience"
  })
}

# Cache Performance Alarm
resource "aws_cloudwatch_metric_alarm" "low_cache_hit_rate" {
  alarm_name          = "${var.name_prefix}-low-cache-hit-rate"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "3"
  threshold           = "50"
  alarm_description   = "Model cache hit rate below 50%"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.warning_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "cache_hit_rate"
    expression  = "(hits / (hits + misses)) * 100"
    label       = "Cache Hit Rate Percentage"
    return_data = true
  }

  metric_query {
    id = "hits"
    metric {
      metric_name = "ModelCacheHitCount"
      namespace   = "MultimodalLibrarian/${var.environment}/Startup"
      period      = "300"
      stat        = "Sum"
    }
  }

  metric_query {
    id = "misses"
    metric {
      metric_name = "ModelCacheMissCount"
      namespace   = "MultimodalLibrarian/${var.environment}/Startup"
      period      = "300"
      stat        = "Sum"
    }
  }

  tags = merge(var.tags, {
    Severity  = "Medium"
    Component = "CachePerformance"
  })
}

# Health Check Failure Alarm
resource "aws_cloudwatch_metric_alarm" "health_check_failures" {
  alarm_name          = "${var.name_prefix}-health-check-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HealthCheckFailureCount"
  namespace           = "MultimodalLibrarian/${var.environment}/Startup"
  period              = "60"
  statistic           = "Sum"
  threshold           = "3"
  alarm_description   = "Multiple consecutive health check failures"
  alarm_actions       = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.critical_alerts.arn]
  ok_actions          = [aws_sns_topic.info_alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(var.tags, {
    Severity  = "Critical"
    Component = "HealthCheck"
  })
}

# Composite Alarm for Startup Failure
resource "aws_cloudwatch_composite_alarm" "startup_failure" {
  alarm_name        = "${var.name_prefix}-startup-failure-composite"
  alarm_description = "Composite alarm for overall startup failure detection"
  actions_enabled   = true
  alarm_actions     = [aws_sns_topic.startup_alerts.arn, aws_sns_topic.critical_alerts.arn]
  ok_actions        = [aws_sns_topic.info_alerts.arn]

  alarm_rule = join(" OR ", [
    "ALARM(${aws_cloudwatch_metric_alarm.minimal_phase_timeout.alarm_name})",
    "ALARM(${aws_cloudwatch_metric_alarm.model_loading_failures.alarm_name})",
    "ALARM(${aws_cloudwatch_metric_alarm.health_check_failures.alarm_name})"
  ])

  tags = merge(var.tags, {
    Severity  = "Critical"
    Component = "StartupSystem"
    Type      = "Composite"
  })
}

# CloudWatch Insights Queries for Startup Analysis
resource "aws_cloudwatch_query_definition" "startup_phase_analysis" {
  name = "${var.name_prefix}-startup-phase-analysis"

  log_group_names = [
    aws_cloudwatch_log_group.application.name
  ]

  query_string = <<EOF
fields @timestamp, phase, duration, status
| filter component = "StartupPhaseManager"
| filter message like /Phase transition/
| stats avg(duration) as avg_duration, max(duration) as max_duration, min(duration) as min_duration by phase
| sort phase asc
EOF
}

resource "aws_cloudwatch_query_definition" "model_loading_analysis" {
  name = "${var.name_prefix}-model-loading-analysis"

  log_group_names = [
    aws_cloudwatch_log_group.application.name
  ]

  query_string = <<EOF
fields @timestamp, model_name, duration_seconds, cache_hit, memory_usage_mb
| filter component = "ModelManager"
| filter message like /Model loaded/
| stats avg(duration_seconds) as avg_load_time, count(*) as load_count, sum(cache_hit) as cache_hits by model_name
| sort avg_load_time desc
EOF
}

resource "aws_cloudwatch_query_definition" "user_experience_analysis" {
  name = "${var.name_prefix}-user-experience-analysis"

  log_group_names = [
    aws_cloudwatch_log_group.application.name
  ]

  query_string = <<EOF
fields @timestamp, wait_time_ms, fallback_used, startup_phase
| filter component = "UserWaitTracking"
| stats avg(wait_time_ms) as avg_wait, max(wait_time_ms) as max_wait, count(*) as request_count, sum(fallback_used) as fallback_count by startup_phase
| sort startup_phase asc
EOF
}

resource "aws_cloudwatch_query_definition" "startup_errors" {
  name = "${var.name_prefix}-startup-errors"

  log_group_names = [
    aws_cloudwatch_log_group.application.name
  ]

  query_string = <<EOF
fields @timestamp, component, message, error_type
| filter level = "ERROR"
| filter component in ["StartupPhaseManager", "ModelManager", "HealthCheck", "ModelCache"]
| stats count(*) as error_count by component, error_type
| sort error_count desc
EOF
}

# Enhanced Startup Dashboard
resource "aws_cloudwatch_dashboard" "startup_monitoring" {
  dashboard_name = "${var.name_prefix}-startup-monitoring"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["MultimodalLibrarian/${var.environment}/Startup", "MinimalPhaseCompletionTime", { stat = "Average", label = "Minimal Phase (avg)" }],
            ["...", { stat = "Maximum", label = "Minimal Phase (max)" }],
            [".", "EssentialPhaseCompletionTime", { stat = "Average", label = "Essential Phase (avg)" }],
            ["...", { stat = "Maximum", label = "Essential Phase (max)" }],
            [".", "FullPhaseCompletionTime", { stat = "Average", label = "Full Phase (avg)" }],
            ["...", { stat = "Maximum", label = "Full Phase (max)" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Startup Phase Completion Times"
          period  = 300
          yAxis = {
            left = {
              label = "Duration (seconds)"
            }
          }
          annotations = {
            horizontal = [
              {
                label = "Minimal Phase Target (30s)"
                value = 30
                fill  = "below"
                color = "#2ca02c"
              },
              {
                label = "Minimal Phase Threshold (60s)"
                value = 60
                fill  = "above"
                color = "#d62728"
              },
              {
                label = "Essential Phase Target (120s)"
                value = 120
              },
              {
                label = "Essential Phase Threshold (180s)"
                value = 180
              }
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["MultimodalLibrarian/${var.environment}/Startup", "ModelLoadingDuration", { stat = "Average", label = "Avg Load Time" }],
            ["...", { stat = "Maximum", label = "Max Load Time" }],
            ["...", { stat = "p95", label = "P95 Load Time" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Model Loading Performance"
          period  = 300
          yAxis = {
            left = {
              label = "Duration (seconds)"
            }
          }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 8
        height = 6

        properties = {
          metrics = [
            ["MultimodalLibrarian/${var.environment}/Startup", "ModelLoadingSuccessCount", { stat = "Sum", label = "Successful Loads" }],
            [".", "ModelLoadingFailureCount", { stat = "Sum", label = "Failed Loads" }]
          ]
          view    = "timeSeries"
          stacked = true
          region  = var.aws_region
          title   = "Model Loading Success vs Failures"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 6
        width  = 8
        height = 6

        properties = {
          metrics = [
            [{ expression = "(hits / (hits + misses)) * 100", label = "Cache Hit Rate %", id = "hit_rate" }],
            ["MultimodalLibrarian/${var.environment}/Startup", "ModelCacheHitCount", { id = "hits", visible = false }],
            [".", "ModelCacheMissCount", { id = "misses", visible = false }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Model Cache Hit Rate"
          period  = 300
          yAxis = {
            left = {
              label = "Hit Rate (%)"
              min   = 0
              max   = 100
            }
          }
          annotations = {
            horizontal = [
              {
                label = "Target (70%)"
                value = 70
                fill  = "above"
                color = "#2ca02c"
              },
              {
                label = "Threshold (50%)"
                value = 50
                fill  = "below"
                color = "#d62728"
              }
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 6
        width  = 8
        height = 6

        properties = {
          metrics = [
            ["MultimodalLibrarian/${var.environment}/Startup", "UserWaitTime", { stat = "Average", label = "Avg Wait Time" }],
            ["...", { stat = "p95", label = "P95 Wait Time" }],
            ["...", { stat = "Maximum", label = "Max Wait Time" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "User Wait Times"
          period  = 300
          yAxis = {
            left = {
              label = "Wait Time (ms)"
            }
          }
          annotations = {
            horizontal = [
              {
                label = "Target (30s)"
                value = 30000
                fill  = "below"
                color = "#2ca02c"
              },
              {
                label = "P95 Threshold (60s)"
                value = 60000
                fill  = "above"
                color = "#d62728"
              }
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["MultimodalLibrarian/${var.environment}/Startup", "FallbackResponseCount", { stat = "Sum", label = "Fallback Responses" }],
            [".", "HealthCheckFailureCount", { stat = "Sum", label = "Health Check Failures" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "User Experience & Health Indicators"
          period  = 300
        }
      },
      {
        type   = "log"
        x      = 12
        y      = 12
        width  = 12
        height = 6

        properties = {
          query  = "SOURCE '${aws_cloudwatch_log_group.application.name}' | fields @timestamp, phase, duration, status | filter component = 'StartupPhaseManager' | filter message like /Phase transition/ | sort @timestamp desc | limit 20"
          region = var.aws_region
          title  = "Recent Startup Phase Transitions"
          view   = "table"
        }
      }
    ]
  })
}

# Outputs for integration
output "startup_alerts_topic_arn" {
  description = "ARN of the startup alerts SNS topic"
  value       = aws_sns_topic.startup_alerts.arn
}

output "startup_dashboard_name" {
  description = "Name of the startup monitoring dashboard"
  value       = aws_cloudwatch_dashboard.startup_monitoring.dashboard_name
}
