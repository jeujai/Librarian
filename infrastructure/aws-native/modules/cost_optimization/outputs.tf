# Outputs for Cost Optimization Module

output "monthly_budget_name" {
  description = "Name of the monthly cost budget"
  value       = aws_budgets_budget.monthly_cost_budget.name
}

output "monthly_budget_arn" {
  description = "ARN of the monthly cost budget"
  value       = aws_budgets_budget.monthly_cost_budget.arn
}

output "ecs_budget_name" {
  description = "Name of the ECS cost budget"
  value       = var.enable_detailed_budgets ? aws_budgets_budget.ecs_cost_budget[0].name : null
}

output "ecs_budget_arn" {
  description = "ARN of the ECS cost budget"
  value       = var.enable_detailed_budgets ? aws_budgets_budget.ecs_cost_budget[0].arn : null
}

output "database_budget_name" {
  description = "Name of the database cost budget"
  value       = var.enable_detailed_budgets ? aws_budgets_budget.database_cost_budget[0].name : null
}

output "database_budget_arn" {
  description = "ARN of the database cost budget"
  value       = var.enable_detailed_budgets ? aws_budgets_budget.database_cost_budget[0].arn : null
}

output "cost_anomaly_detector_arn" {
  description = "ARN of the cost anomaly alarm"
  value       = var.enable_cost_anomaly_detection && var.sns_topic_arn != "" ? aws_cloudwatch_metric_alarm.cost_anomaly_alarm[0].arn : null
}

output "cost_monitoring_dashboard_name" {
  description = "Name of cost monitoring CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.cost_monitoring.dashboard_name
}

output "cost_monitoring_dashboard_url" {
  description = "URL of cost monitoring CloudWatch dashboard"
  value       = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.cost_monitoring.dashboard_name}"
}

output "high_cost_alarm_name" {
  description = "Name of high cost utilization CloudWatch alarm"
  value       = var.enable_cost_alerts ? aws_cloudwatch_metric_alarm.high_cost_utilization[0].alarm_name : null
}

output "high_cost_alarm_arn" {
  description = "ARN of high cost utilization CloudWatch alarm"
  value       = var.enable_cost_alerts ? aws_cloudwatch_metric_alarm.high_cost_utilization[0].arn : null
}

output "underutilized_cpu_alarm_name" {
  description = "Name of underutilized CPU CloudWatch alarm"
  value       = var.enable_right_sizing_alerts ? aws_cloudwatch_metric_alarm.underutilized_ecs_cpu[0].alarm_name : null
}

output "underutilized_cpu_alarm_arn" {
  description = "ARN of underutilized CPU CloudWatch alarm"
  value       = var.enable_right_sizing_alerts ? aws_cloudwatch_metric_alarm.underutilized_ecs_cpu[0].arn : null
}

output "underutilized_memory_alarm_name" {
  description = "Name of underutilized memory CloudWatch alarm"
  value       = var.enable_right_sizing_alerts ? aws_cloudwatch_metric_alarm.underutilized_ecs_memory[0].alarm_name : null
}

output "underutilized_memory_alarm_arn" {
  description = "ARN of underutilized memory CloudWatch alarm"
  value       = var.enable_right_sizing_alerts ? aws_cloudwatch_metric_alarm.underutilized_ecs_memory[0].arn : null
}

output "cost_optimization_recommendations_parameter" {
  description = "SSM parameter containing cost optimization recommendations"
  value       = aws_ssm_parameter.cost_optimization_recommendations.name
}

output "cost_optimization_recommendations_arn" {
  description = "ARN of SSM parameter containing cost optimization recommendations"
  value       = aws_ssm_parameter.cost_optimization_recommendations.arn
}

output "cost_optimization_summary" {
  description = "Summary of cost optimization configuration"
  value = {
    budgets = {
      monthly_budget_limit = var.monthly_budget_limit
      ecs_budget_limit     = var.ecs_budget_limit
      database_budget_limit = var.database_budget_limit
      detailed_budgets_enabled = var.enable_detailed_budgets
    }
    
    monitoring = {
      cost_alerts_enabled = var.enable_cost_alerts
      anomaly_detection_enabled = var.enable_cost_anomaly_detection
      right_sizing_alerts_enabled = var.enable_right_sizing_alerts
      cost_alert_threshold = var.cost_alert_threshold
      anomaly_threshold = var.cost_anomaly_threshold
    }
    
    thresholds = {
      cpu_underutilization = var.cpu_underutilization_threshold
      memory_underutilization = var.memory_underutilization_threshold
      target_cpu_utilization = var.target_cpu_utilization
      target_memory_utilization = var.target_memory_utilization
    }
    
    features = {
      reserved_instances_enabled = var.enable_reserved_instances
      resource_cleanup_enabled = var.enable_resource_cleanup
      s3_lifecycle_optimization_enabled = var.enable_s3_lifecycle_optimization
    }
    
    notifications = {
      email_count = length(var.budget_notification_emails)
      sns_topic_configured = var.sns_topic_arn != ""
    }
  }
}