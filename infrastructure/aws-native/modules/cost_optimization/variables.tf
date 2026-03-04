# Variables for Cost Optimization Module

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

# Budget Configuration
variable "monthly_budget_limit" {
  description = "Monthly budget limit in USD"
  type        = number
  default     = 200

  validation {
    condition     = var.monthly_budget_limit > 0
    error_message = "Monthly budget limit must be greater than 0."
  }
}

variable "ecs_budget_limit" {
  description = "ECS service budget limit in USD"
  type        = number
  default     = 100

  validation {
    condition     = var.ecs_budget_limit > 0
    error_message = "ECS budget limit must be greater than 0."
  }
}

variable "database_budget_limit" {
  description = "Database services budget limit in USD"
  type        = number
  default     = 80

  validation {
    condition     = var.database_budget_limit > 0
    error_message = "Database budget limit must be greater than 0."
  }
}

variable "budget_notification_emails" {
  description = "List of email addresses for budget notifications"
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for email in var.budget_notification_emails : can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email))
    ])
    error_message = "All budget notification emails must be valid email addresses."
  }
}

# Cost Optimization Features
variable "enable_detailed_budgets" {
  description = "Enable detailed budgets for ECS and database services"
  type        = bool
  default     = true
}

variable "enable_cost_anomaly_detection" {
  description = "Enable cost anomaly detection"
  type        = bool
  default     = true
}

variable "enable_cost_alerts" {
  description = "Enable cost threshold alerts"
  type        = bool
  default     = true
}

variable "enable_right_sizing_alerts" {
  description = "Enable right-sizing alerts for underutilized resources"
  type        = bool
  default     = true
}

variable "enable_reserved_instances" {
  description = "Enable reserved instance recommendations"
  type        = bool
  default     = false
}

variable "enable_resource_cleanup" {
  description = "Enable automated resource cleanup"
  type        = bool
  default     = false
}

variable "enable_s3_lifecycle_optimization" {
  description = "Enable S3 lifecycle optimization"
  type        = bool
  default     = false
}

# Thresholds and Targets
variable "cost_alert_threshold" {
  description = "Cost alert threshold in USD"
  type        = number
  default     = 150

  validation {
    condition     = var.cost_alert_threshold > 0
    error_message = "Cost alert threshold must be greater than 0."
  }
}

variable "cost_anomaly_threshold" {
  description = "Cost anomaly detection threshold in USD"
  type        = number
  default     = 50

  validation {
    condition     = var.cost_anomaly_threshold > 0
    error_message = "Cost anomaly threshold must be greater than 0."
  }
}

variable "cpu_underutilization_threshold" {
  description = "CPU underutilization threshold percentage"
  type        = number
  default     = 20

  validation {
    condition     = var.cpu_underutilization_threshold >= 0 && var.cpu_underutilization_threshold <= 100
    error_message = "CPU underutilization threshold must be between 0 and 100."
  }
}

variable "memory_underutilization_threshold" {
  description = "Memory underutilization threshold percentage"
  type        = number
  default     = 30

  validation {
    condition     = var.memory_underutilization_threshold >= 0 && var.memory_underutilization_threshold <= 100
    error_message = "Memory underutilization threshold must be between 0 and 100."
  }
}

variable "target_cpu_utilization" {
  description = "Target CPU utilization percentage for auto-scaling"
  type        = number
  default     = 70

  validation {
    condition     = var.target_cpu_utilization >= 10 && var.target_cpu_utilization <= 90
    error_message = "Target CPU utilization must be between 10 and 90."
  }
}

variable "target_memory_utilization" {
  description = "Target memory utilization percentage for auto-scaling"
  type        = number
  default     = 80

  validation {
    condition     = var.target_memory_utilization >= 10 && var.target_memory_utilization <= 90
    error_message = "Target memory utilization must be between 10 and 90."
  }
}

# ECS Configuration for monitoring
variable "ecs_cluster_name" {
  description = "ECS cluster name for cost optimization monitoring"
  type        = string
}

variable "ecs_service_name" {
  description = "ECS service name for cost optimization monitoring"
  type        = string
}

# S3 Lifecycle Configuration
variable "s3_bucket_name" {
  description = "S3 bucket name for lifecycle optimization"
  type        = string
  default     = ""
}

variable "s3_object_expiration_days" {
  description = "Number of days after which S3 objects expire"
  type        = number
  default     = 365
}

variable "s3_noncurrent_version_expiration_days" {
  description = "Number of days after which noncurrent S3 object versions expire"
  type        = number
  default     = 30
}

variable "s3_transition_to_ia_days" {
  description = "Number of days after which S3 objects transition to IA"
  type        = number
  default     = 30
}

variable "s3_transition_to_glacier_days" {
  description = "Number of days after which S3 objects transition to Glacier"
  type        = number
  default     = 90
}

variable "s3_transition_to_deep_archive_days" {
  description = "Number of days after which S3 objects transition to Deep Archive"
  type        = number
  default     = 180
}

# Scheduling
variable "resource_cleanup_schedule" {
  description = "Schedule for resource cleanup (cron expression)"
  type        = string
  default     = "cron(0 2 * * ? *)" # Daily at 2 AM UTC

  validation {
    condition     = can(regex("^cron\\(.+\\)$", var.resource_cleanup_schedule))
    error_message = "Resource cleanup schedule must be a valid cron expression."
  }
}

# SNS Configuration
variable "sns_topic_arn" {
  description = "SNS topic ARN for cost alerts"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}