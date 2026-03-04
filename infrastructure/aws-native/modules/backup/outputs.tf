# Outputs for Backup Module

output "opensearch_snapshot_bucket" {
  description = "S3 bucket for OpenSearch snapshots"
  value       = aws_s3_bucket.opensearch_snapshots.bucket
}

output "opensearch_snapshot_bucket_arn" {
  description = "ARN of S3 bucket for OpenSearch snapshots"
  value       = aws_s3_bucket.opensearch_snapshots.arn
}

output "backup_lambda_function_name" {
  description = "Name of backup management Lambda function"
  value       = aws_lambda_function.backup_manager.function_name
}

output "backup_lambda_function_arn" {
  description = "ARN of backup management Lambda function"
  value       = aws_lambda_function.backup_manager.arn
}

output "backup_schedule_rule_name" {
  description = "Name of backup schedule CloudWatch Event Rule"
  value       = aws_cloudwatch_event_rule.backup_schedule.name
}

output "disaster_recovery_procedures_parameter" {
  description = "SSM parameter containing disaster recovery procedures"
  value       = aws_ssm_parameter.disaster_recovery_procedures.name
}

output "backup_monitoring_dashboard_name" {
  description = "Name of backup monitoring CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.backup_monitoring.dashboard_name
}

output "cross_region_backup_bucket" {
  description = "Cross-region backup bucket (if enabled)"
  value       = var.enable_cross_region_backup ? aws_s3_bucket.backup_replication[0].bucket : null
}

output "backup_failure_alarm_name" {
  description = "Name of backup failure CloudWatch alarm"
  value       = aws_cloudwatch_metric_alarm.backup_failures.alarm_name
}

output "backup_success_alarm_name" {
  description = "Name of backup success CloudWatch alarm"
  value       = aws_cloudwatch_metric_alarm.backup_success.alarm_name
}