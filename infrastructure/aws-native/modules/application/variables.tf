# Application Module Variables

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC"
  type        = string
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for ALB"
  type        = string
}

variable "ecs_security_group_id" {
  description = "Security group ID for ECS"
  type        = string
}

variable "elasticache_security_group_id" {
  description = "Security group ID for ElastiCache"
  type        = string
}

variable "ecs_task_execution_role_arn" {
  description = "ARN of ECS task execution role"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  type        = string
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption"
  type        = string
}

variable "ecr_repository_url" {
  description = "URL of existing ECR repository"
  type        = string
  default     = ""
}

variable "random_suffix" {
  description = "Random suffix for unique resource names"
  type        = string
}

# Application Configuration
variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
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

variable "ecs_cpu" {
  description = "CPU units for ECS tasks"
  type        = number
  default     = 1024
}

variable "ecs_memory" {
  description = "Memory (MB) for ECS tasks"
  type        = number
  default     = 2048
}

variable "min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 2
}

variable "max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 10
}

# Secrets
variable "neptune_secret_arn" {
  description = "ARN of Neptune secret"
  type        = string
}

variable "opensearch_secret_arn" {
  description = "ARN of OpenSearch secret"
  type        = string
}

variable "redis_auth_token" {
  description = "Auth token for Redis"
  type        = string
  sensitive   = true
}

# SSL Configuration
variable "certificate_arn" {
  description = "ARN of SSL certificate"
  type        = string
  default     = ""
}

# Logging Configuration
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# EFS Configuration
variable "efs_file_system_id" {
  description = "EFS file system ID for model cache"
  type        = string
  default     = ""
}

variable "efs_access_point_id" {
  description = "EFS access point ID for model cache"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}