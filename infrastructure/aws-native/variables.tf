# Variables for AWS Production Deployment Infrastructure

# Core Configuration
variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod, production)"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod", "production"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod, production."
  }
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "ml-librarian"
}

variable "cost_center" {
  description = "Cost center for resource tagging"
  type        = string
  default     = "engineering"
}

variable "owner" {
  description = "Owner of the resources"
  type        = string
  default     = "platform-team"
}

# Network Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "VPC CIDR must be a valid IPv4 CIDR block."
  }
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24", "10.0.13.0/24"]
}

variable "single_nat_gateway" {
  description = "Use single NAT gateway for cost optimization instead of one per AZ"
  type        = bool
  default     = false
}

variable "shared_nat_gateway_id" {
  description = "ID of existing NAT Gateway to share (for maximum cost optimization)"
  type        = string
  default     = ""
}

# Database Configuration
variable "neptune_instance_type" {
  description = "Instance type for Neptune cluster"
  type        = string
  default     = "db.r5.large"
}

variable "neptune_instance_count" {
  description = "Number of Neptune instances"
  type        = number
  default     = 2

  validation {
    condition     = var.neptune_instance_count >= 1 && var.neptune_instance_count <= 15
    error_message = "Neptune instance count must be between 1 and 15."
  }
}

variable "opensearch_instance_type" {
  description = "Instance type for OpenSearch domain"
  type        = string
  default     = "t3.medium.search"
}

variable "opensearch_instance_count" {
  description = "Number of OpenSearch instances"
  type        = number
  default     = 3

  validation {
    condition     = var.opensearch_instance_count >= 1 && var.opensearch_instance_count <= 80
    error_message = "OpenSearch instance count must be between 1 and 80."
  }
}

# Application Configuration
variable "ecs_cpu" {
  description = "CPU units for ECS tasks"
  type        = number
  default     = 1024

  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.ecs_cpu)
    error_message = "ECS CPU must be one of: 256, 512, 1024, 2048, 4096."
  }
}

variable "ecs_memory" {
  description = "Memory (MB) for ECS tasks"
  type        = number
  default     = 2048

  validation {
    condition     = var.ecs_memory >= 512 && var.ecs_memory <= 30720
    error_message = "ECS memory must be between 512 and 30720 MB."
  }
}

variable "min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 2

  validation {
    condition     = var.min_capacity >= 1 && var.min_capacity <= 100
    error_message = "Minimum capacity must be between 1 and 100."
  }
}

variable "max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 10

  validation {
    condition     = var.max_capacity >= 1 && var.max_capacity <= 100
    error_message = "Maximum capacity must be between 1 and 100."
  }
}

variable "container_port" {
  description = "Port exposed by the container"
  type        = number
  default     = 8000
}

variable "health_check_path" {
  description = "Health check path for ALB target group and ECS task definition"
  type        = string
  default     = "/api/health/minimal"
}

variable "ecr_repository_url" {
  description = "URL of existing ECR repository (optional)"
  type        = string
  default     = ""
}

# Security Configuration
variable "enable_waf" {
  description = "Enable Web Application Firewall"
  type        = bool
  default     = true
}

variable "enable_cloudtrail" {
  description = "Enable CloudTrail logging"
  type        = bool
  default     = true
}

variable "enable_guardduty" {
  description = "Enable GuardDuty threat detection"
  type        = bool
  default     = true
}

variable "enable_security_hub" {
  description = "Enable Security Hub for centralized security findings"
  type        = bool
  default     = true
}

variable "enable_inspector" {
  description = "Enable Inspector for vulnerability assessment"
  type        = bool
  default     = true
}

variable "enable_config" {
  description = "Enable AWS Config for compliance monitoring"
  type        = bool
  default     = true
}

variable "enable_vpc_flow_logs" {
  description = "Enable VPC Flow Logs for network monitoring"
  type        = bool
  default     = true
}

variable "waf_rate_limit" {
  description = "WAF rate limit per 5-minute period"
  type        = number
  default     = 2000

  validation {
    condition     = var.waf_rate_limit >= 100 && var.waf_rate_limit <= 20000000
    error_message = "WAF rate limit must be between 100 and 20,000,000."
  }
}

variable "kms_key_rotation" {
  description = "Enable automatic KMS key rotation"
  type        = bool
  default     = true
}

# Monitoring Configuration
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653], var.log_retention_days)
    error_message = "Log retention days must be a valid CloudWatch retention period."
  }
}

variable "metric_retention_days" {
  description = "CloudWatch metric retention in days"
  type        = number
  default     = 90
}

# Backup Configuration
variable "backup_region" {
  description = "AWS region for cross-region backups"
  type        = string
  default     = "us-west-2"
}

variable "neptune_backup_retention" {
  description = "Neptune backup retention period in days"
  type        = number
  default     = 7

  validation {
    condition     = var.neptune_backup_retention >= 1 && var.neptune_backup_retention <= 35
    error_message = "Neptune backup retention must be between 1 and 35 days."
  }
}

variable "opensearch_snapshot_retention" {
  description = "OpenSearch snapshot retention in days"
  type        = number
  default     = 30
}

# Cost Optimization
variable "enable_cost_optimization" {
  description = "Enable cost optimization features"
  type        = bool
  default     = true
}

variable "enable_reserved_instances" {
  description = "Enable reserved instance recommendations"
  type        = bool
  default     = false
}

# SSL Certificate Configuration
variable "domain_name" {
  description = "Domain name for SSL certificate"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ARN of existing SSL certificate"
  type        = string
  default     = ""
}

# Notification Configuration
variable "notification_email" {
  description = "Email address for notifications"
  type        = string
  default     = ""
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  default     = ""
  sensitive   = true
}
variable "opensearch_volume_size" {
  description = "EBS volume size for OpenSearch instances (GB)"
  type        = number
  default     = 20

  validation {
    condition     = var.opensearch_volume_size >= 10 && var.opensearch_volume_size <= 3584
    error_message = "OpenSearch volume size must be between 10 and 3584 GB."
  }
}

# Backup and Recovery Configuration
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

variable "neptune_backup_window" {
  description = "Neptune preferred backup window"
  type        = string
  default     = "07:00-09:00"
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

# Additional Cost Optimization Variables
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

variable "budget_alert_emails" {
  description = "List of email addresses for budget alerts"
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for email in var.budget_alert_emails : can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email))
    ])
    error_message = "All budget alert emails must be valid email addresses."
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

variable "monthly_budget_limit" {
  description = "Monthly budget limit in USD"
  type        = number
  default     = 200

  validation {
    condition     = var.monthly_budget_limit > 0
    error_message = "Monthly budget limit must be greater than 0."
  }
}

# Container Failure Monitor Configuration
variable "enable_container_failure_monitor" {
  description = "Enable automated container failure monitoring Lambda function"
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Email address for container failure alerts"
  type        = string
  default     = ""

  validation {
    condition     = var.alert_email == "" || can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.alert_email))
    error_message = "Alert email must be a valid email address or empty string."
  }
}