# Monitoring Module Variables

variable "name_prefix" {
  description = "Prefix for resource names"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "kms_key_arn" {
  description = "KMS key ARN for SNS topic encryption"
  type        = string
}

variable "log_retention_days" {
  description = "Number of days to retain logs"
  type        = number
  default     = 7
}

variable "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
}

variable "ecs_service_name" {
  description = "Name of the ECS service"
  type        = string
}

variable "alb_arn_suffix" {
  description = "ARN suffix of the Application Load Balancer"
  type        = string
}

variable "neptune_cluster_id" {
  description = "Neptune cluster identifier"
  type        = string
}

variable "opensearch_domain_name" {
  description = "OpenSearch domain name"
  type        = string
}

variable "enable_waf_monitoring" {
  description = "Enable WAF monitoring alarms"
  type        = bool
  default     = false
}

variable "waf_web_acl_arn" {
  description = "WAF Web ACL ARN"
  type        = string
  default     = ""
}

variable "enable_guardduty_monitoring" {
  description = "Enable GuardDuty monitoring alarms"
  type        = bool
  default     = false
}

# Container Failure Monitor Variables
variable "alert_email" {
  description = "Email address for container failure alerts"
  type        = string
  default     = ""
}

variable "check_window_minutes" {
  description = "How many minutes back to check for container failures"
  type        = number
  default     = 5
}

variable "enable_container_failure_monitor" {
  description = "Enable container failure monitoring Lambda"
  type        = bool
  default     = true
}
