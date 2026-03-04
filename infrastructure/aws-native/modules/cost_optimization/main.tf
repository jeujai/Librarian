# Cost Optimization Module
# Implements cost optimization features including budgets, right-sizing, and resource cleanup

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Cost Budget for overall AWS spending
resource "aws_budgets_budget" "monthly_cost_budget" {
  name         = "${var.name_prefix}-monthly-budget"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_limit
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  time_period_start = "2024-01-01_00:00"

  cost_filter {
    name   = "Service"
    values = ["Amazon Elastic Compute Cloud - Compute", "Amazon Relational Database Service", "Amazon OpenSearch Service", "Amazon Elastic Container Service"]
  }

  dynamic "notification" {
    for_each = length(var.budget_notification_emails) > 0 ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                 = 80
      threshold_type           = "PERCENTAGE"
      notification_type        = "ACTUAL"
      subscriber_email_addresses = var.budget_notification_emails
    }
  }

  dynamic "notification" {
    for_each = length(var.budget_notification_emails) > 0 ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                 = 100
      threshold_type           = "PERCENTAGE"
      notification_type          = "FORECASTED"
      subscriber_email_addresses = var.budget_notification_emails
    }
  }

  tags = var.tags
}

# Cost Budget for ECS services
resource "aws_budgets_budget" "ecs_cost_budget" {
  count = var.enable_detailed_budgets ? 1 : 0

  name         = "${var.name_prefix}-ecs-budget"
  budget_type  = "COST"
  limit_amount = var.ecs_budget_limit
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  time_period_start = "2024-01-01_00:00"

  cost_filter {
    name   = "Service"
    values = ["Amazon Elastic Container Service"]
  }

  dynamic "notification" {
    for_each = length(var.budget_notification_emails) > 0 ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                 = 80
      threshold_type           = "PERCENTAGE"
      notification_type        = "ACTUAL"
      subscriber_email_addresses = var.budget_notification_emails
    }
  }

  tags = var.tags
}

# Cost Budget for database services
resource "aws_budgets_budget" "database_cost_budget" {
  count = var.enable_detailed_budgets ? 1 : 0

  name         = "${var.name_prefix}-database-budget"
  budget_type  = "COST"
  limit_amount = var.database_budget_limit
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  time_period_start = "2024-01-01_00:00"

  cost_filter {
    name   = "Service"
    values = ["Amazon Neptune", "Amazon OpenSearch Service"]
  }

  dynamic "notification" {
    for_each = length(var.budget_notification_emails) > 0 ? [1] : []
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                 = 80
      threshold_type           = "PERCENTAGE"
      notification_type        = "ACTUAL"
      subscriber_email_addresses = var.budget_notification_emails
    }
  }

  tags = var.tags
}

# Cost Anomaly Detection - Using CloudWatch instead of Cost Explorer
resource "aws_cloudwatch_metric_alarm" "cost_anomaly_alarm" {
  count = var.enable_cost_anomaly_detection && var.sns_topic_arn != "" ? 1 : 0

  alarm_name          = "${var.name_prefix}-cost-anomaly-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = "86400" # 24 hours
  statistic           = "Maximum"
  threshold           = var.cost_anomaly_threshold
  alarm_description   = "This metric monitors for cost anomalies"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    Currency = "USD"
  }

  tags = var.tags
}

# CloudWatch Dashboard for cost monitoring
resource "aws_cloudwatch_dashboard" "cost_monitoring" {
  dashboard_name = "${var.name_prefix}-cost-monitoring"

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
            ["AWS/Billing", "EstimatedCharges", "Currency", "USD"],
          ]
          view    = "timeSeries"
          stacked = false
          region  = data.aws_region.current.name
          title   = "Estimated Monthly Charges"
          period  = 86400
          stat    = "Maximum"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ServiceName", var.ecs_service_name, "ClusterName", var.ecs_cluster_name],
            [".", "MemoryUtilization", ".", ".", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = data.aws_region.current.name
          title   = "ECS Resource Utilization"
          period  = 300
        }
      }
    ]
  })
}

# CloudWatch Alarm for high cost utilization
resource "aws_cloudwatch_metric_alarm" "high_cost_utilization" {
  count = var.enable_cost_alerts ? 1 : 0

  alarm_name          = "${var.name_prefix}-high-cost-utilization"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = "86400" # 24 hours
  statistic           = "Maximum"
  threshold           = var.cost_alert_threshold
  alarm_description   = "This metric monitors estimated charges"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  dimensions = {
    Currency = "USD"
  }

  tags = var.tags
}

# CloudWatch Alarm for underutilized ECS resources
resource "aws_cloudwatch_metric_alarm" "underutilized_ecs_cpu" {
  count = var.enable_right_sizing_alerts ? 1 : 0

  alarm_name          = "${var.name_prefix}-underutilized-ecs-cpu"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "6" # 30 minutes of 5-minute periods
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = "300" # 5 minutes
  statistic           = "Average"
  threshold           = var.cpu_underutilization_threshold
  alarm_description   = "This metric monitors underutilized ECS CPU resources"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  dimensions = {
    ServiceName = var.ecs_service_name
    ClusterName = var.ecs_cluster_name
  }

  tags = var.tags
}

# CloudWatch Alarm for underutilized ECS memory
resource "aws_cloudwatch_metric_alarm" "underutilized_ecs_memory" {
  count = var.enable_right_sizing_alerts ? 1 : 0

  alarm_name          = "${var.name_prefix}-underutilized-ecs-memory"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "6" # 30 minutes of 5-minute periods
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = "300" # 5 minutes
  statistic           = "Average"
  threshold           = var.memory_underutilization_threshold
  alarm_description   = "This metric monitors underutilized ECS memory resources"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  dimensions = {
    ServiceName = var.ecs_service_name
    ClusterName = var.ecs_cluster_name
  }

  tags = var.tags
}

# SSM Parameter for cost optimization recommendations
resource "aws_ssm_parameter" "cost_optimization_recommendations" {
  name  = "/${var.project_name}/${var.environment}/cost-optimization/recommendations"
  type  = "String"
  value = jsonencode({
    right_sizing = {
      description = "Resource right-sizing recommendations"
      strategies = [
        "Monitor CPU and memory utilization patterns over 2-4 weeks",
        "Analyze workload requirements and peak usage patterns",
        "Consider using AWS Compute Optimizer for detailed recommendations",
        "Implement auto-scaling based on actual demand patterns",
        "Use appropriate instance types for workload characteristics",
        "Consider Fargate Spot for non-critical workloads"
      ]
      thresholds = {
        cpu_underutilization = var.cpu_underutilization_threshold
        memory_underutilization = var.memory_underutilization_threshold
        evaluation_period = "30 minutes"
      }
    }
    
    auto_scaling = {
      description = "Auto-scaling policies for cost optimization"
      policies = [
        "Scale down during low-traffic periods (nights/weekends)",
        "Scale up gradually to avoid over-provisioning",
        "Use predictive scaling for known traffic patterns",
        "Implement step scaling for cost-effective resource allocation",
        "Set appropriate cooldown periods to prevent thrashing"
      ]
      configuration = {
        target_cpu_utilization = var.target_cpu_utilization
        target_memory_utilization = var.target_memory_utilization
        scale_down_cooldown = "300s"
        scale_up_cooldown = "60s"
      }
    }
    
    cost_monitoring = {
      description = "Cost monitoring and alerting configuration"
      budgets = {
        monthly_limit = var.monthly_budget_limit
        ecs_limit = var.ecs_budget_limit
        database_limit = var.database_budget_limit
      }
      alerts = {
        cost_threshold = var.cost_alert_threshold
        anomaly_threshold = var.cost_anomaly_threshold
        notification_emails = var.budget_notification_emails
      }
    }
    
    reserved_instances = {
      description = "Reserved instances and savings plans recommendations"
      enabled = var.enable_reserved_instances
      recommendations = [
        "Analyze usage patterns for RI recommendations using AWS Cost Explorer",
        "Consider Compute Savings Plans for flexible workloads",
        "Monitor RI utilization and coverage monthly",
        "Evaluate EC2 Instance Savings Plans for predictable workloads",
        "Use Reserved Instance recommendations from AWS Trusted Advisor"
      ]
      analysis_frequency = "monthly"
    }
    
    resource_cleanup = {
      description = "Automated resource cleanup policies"
      enabled = var.enable_resource_cleanup
      policies = [
        "Clean up unused EBS volumes older than 7 days",
        "Remove old CloudWatch logs beyond retention period",
        "Clean up unused S3 objects based on lifecycle policies",
        "Remove unused security groups and network interfaces",
        "Clean up old ECS task definitions and container images"
      ]
      schedule = var.resource_cleanup_schedule
    }
  })

  description = "Cost optimization recommendations and configuration"
  tags        = var.tags
}

# S3 Lifecycle Configuration for cost optimization
resource "aws_s3_bucket_lifecycle_configuration" "cost_optimization" {
  count = var.enable_s3_lifecycle_optimization && var.s3_bucket_name != "" ? 1 : 0

  bucket = var.s3_bucket_name

  rule {
    id     = "cost_optimization"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = var.s3_object_expiration_days
    }

    noncurrent_version_expiration {
      noncurrent_days = var.s3_noncurrent_version_expiration_days
    }

    transition {
      days          = var.s3_transition_to_ia_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.s3_transition_to_glacier_days
      storage_class = "GLACIER"
    }

    transition {
      days          = var.s3_transition_to_deep_archive_days
      storage_class = "DEEP_ARCHIVE"
    }
  }
}