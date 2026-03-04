# Databases Module Outputs

# Neptune Outputs
output "neptune_cluster_id" {
  description = "ID of the Neptune cluster"
  value       = aws_neptune_cluster.main.cluster_identifier
}

output "neptune_cluster_arn" {
  description = "ARN of the Neptune cluster"
  value       = aws_neptune_cluster.main.arn
}

output "neptune_endpoint" {
  description = "Neptune cluster endpoint"
  value       = aws_neptune_cluster.main.endpoint
}

output "neptune_reader_endpoint" {
  description = "Neptune cluster reader endpoint"
  value       = aws_neptune_cluster.main.reader_endpoint
}

output "neptune_port" {
  description = "Neptune cluster port"
  value       = aws_neptune_cluster.main.port
}

output "neptune_cluster_resource_id" {
  description = "Neptune cluster resource ID"
  value       = aws_neptune_cluster.main.cluster_resource_id
}

# OpenSearch Outputs
output "opensearch_domain_id" {
  description = "ID of the OpenSearch domain"
  value       = aws_opensearch_domain.main.domain_id
}

output "opensearch_domain_name" {
  description = "Name of the OpenSearch domain"
  value       = aws_opensearch_domain.main.domain_name
}

output "opensearch_domain_arn" {
  description = "ARN of the OpenSearch domain"
  value       = aws_opensearch_domain.main.arn
}

output "opensearch_endpoint" {
  description = "OpenSearch domain endpoint"
  value       = aws_opensearch_domain.main.endpoint
}

output "opensearch_kibana_endpoint" {
  description = "OpenSearch Kibana endpoint (deprecated - use dashboard_endpoint)"
  value       = aws_opensearch_domain.main.dashboard_endpoint
}

output "opensearch_dashboard_endpoint" {
  description = "OpenSearch dashboard endpoint"
  value       = aws_opensearch_domain.main.dashboard_endpoint
}

# S3 Backup Outputs
output "opensearch_snapshots_bucket" {
  description = "S3 bucket for OpenSearch snapshots"
  value       = aws_s3_bucket.opensearch_snapshots.bucket
}

output "opensearch_snapshots_bucket_arn" {
  description = "ARN of S3 bucket for OpenSearch snapshots"
  value       = aws_s3_bucket.opensearch_snapshots.arn
}

# IAM Role Outputs
output "neptune_monitoring_role_arn" {
  description = "ARN of Neptune monitoring role"
  value       = aws_iam_role.neptune_monitoring.arn
}

output "opensearch_snapshot_role_arn" {
  description = "ARN of OpenSearch snapshot role"
  value       = aws_iam_role.opensearch_snapshot.arn
}

# CloudWatch Log Group Outputs
output "neptune_audit_log_group" {
  description = "Neptune audit log group name"
  value       = aws_cloudwatch_log_group.neptune_audit.name
}

output "opensearch_log_groups" {
  description = "OpenSearch log group names"
  value = {
    search_slow    = aws_cloudwatch_log_group.opensearch_search_slow.name
    index_slow     = aws_cloudwatch_log_group.opensearch_index_slow.name
    es_application = aws_cloudwatch_log_group.opensearch_es_application.name
  }
}