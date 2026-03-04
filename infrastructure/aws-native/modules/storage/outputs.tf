# Storage Module Outputs

output "efs_file_system_id" {
  description = "EFS file system ID"
  value       = aws_efs_file_system.model_cache.id
}

output "efs_file_system_arn" {
  description = "EFS file system ARN"
  value       = aws_efs_file_system.model_cache.arn
}

output "efs_access_point_id" {
  description = "EFS access point ID"
  value       = aws_efs_access_point.model_cache.id
}

output "efs_access_point_arn" {
  description = "EFS access point ARN"
  value       = aws_efs_access_point.model_cache.arn
}

output "efs_dns_name" {
  description = "EFS DNS name for mounting"
  value       = aws_efs_file_system.model_cache.dns_name
}
