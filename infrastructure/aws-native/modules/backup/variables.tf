# Variables for Backup Module

variable "name_prefix" {
  description = "Name prefix for resources"
  type        = string
}

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN for encryption"
  type        = string
}

variable "random_suffix" {
  description = "Random suffix for unique resource names"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "backup_retention_days" {
  description = "Backup retention period in days"
  type        = number
  default     = 30

  validation {
    condition     = var.backup_retention_days >= 1 && var.backup_retention_days <= 365
    error_message = "Backup retention days must be between 1 and 365."
  }
}

variable "enable_cross_region_backup" {
  description = "Enable cross-region backup replication"
  type        = bool
  default     = false
}

variable "backup_region" {
  description = "Region for cross-region backups"
  type        = string
  default     = "us-west-2"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.backup_region))
    error_message = "Backup region must be a valid AWS region format."
  }
}

variable "opensearch_snapshot_hour" {
  description = "Hour of day (UTC) for OpenSearch automated snapshots (0-23)"
  type        = number
  default     = 3

  validation {
    condition     = var.opensearch_snapshot_hour >= 0 && var.opensearch_snapshot_hour <= 23
    error_message = "OpenSearch snapshot hour must be between 0 and 23."
  }
}

variable "backup_monitoring_enabled" {
  description = "Enable backup monitoring and alerting"
  type        = bool
  default     = true
}

variable "disaster_recovery_testing_enabled" {
  description = "Enable automated disaster recovery testing"
  type        = bool
  default     = false
}

variable "sns_topic_arn" {
  description = "SNS topic ARN for backup alerts"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}