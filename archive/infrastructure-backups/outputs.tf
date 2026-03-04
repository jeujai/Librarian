# Outputs for AWS Production Deployment Infrastructure

# VPC Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
  sensitive   = false
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.vpc.public_subnet_ids
  sensitive   = false
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnet_ids
  sensitive   = false
}

output "database_subnet_ids" {
  description = "Database subnet IDs"
  value       = module.vpc.database_subnet_ids
  sensitive   = false
}

# Application Infrastructure Outputs
output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.app.repository_url
  sensitive   = false
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
  sensitive   = false
}

output "ecs_cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
  sensitive   = false
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.app.name
  sensitive   = false
}

output "load_balancer_dns_name" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.main.dns_name
  sensitive   = false
}

output "load_balancer_zone_id" {
  description = "Application Load Balancer zone ID"
  value       = aws_lb.main.zone_id
  sensitive   = false
}

output "load_balancer_arn" {
  description = "Application Load Balancer ARN"
  value       = aws_lb.main.arn
  sensitive   = false
}

output "target_group_arn" {
  description = "Target group ARN"
  value       = aws_lb_target_group.app.arn
  sensitive   = false
}

# CloudFront Outputs
output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = var.enable_cdn ? aws_cloudfront_distribution.main[0].id : null
  sensitive   = false
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = var.enable_cdn ? aws_cloudfront_distribution.main[0].domain_name : null
  sensitive   = false
}

# ElastiCache Outputs
output "elasticache_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = var.enable_caching ? aws_elasticache_replication_group.redis[0].primary_endpoint_address : null
  sensitive   = false
}

output "elasticache_port" {
  description = "ElastiCache Redis port"
  value       = var.enable_caching ? aws_elasticache_replication_group.redis[0].port : null
  sensitive   = false
}

# Neptune Outputs
output "neptune_cluster_endpoint" {
  description = "Neptune cluster endpoint"
  value       = aws_neptune_cluster.main.endpoint
  sensitive   = false
}

output "neptune_reader_endpoint" {
  description = "Neptune cluster reader endpoint"
  value       = aws_neptune_cluster.main.reader_endpoint
  sensitive   = false
}

output "neptune_cluster_id" {
  description = "Neptune cluster identifier"
  value       = aws_neptune_cluster.main.cluster_identifier
  sensitive   = false
}

output "neptune_port" {
  description = "Neptune cluster port"
  value       = aws_neptune_cluster.main.port
  sensitive   = false
}

output "neptune_cluster_arn" {
  description = "Neptune cluster ARN"
  value       = aws_neptune_cluster.main.arn
  sensitive   = false
}

# OpenSearch Outputs
output "opensearch_domain_endpoint" {
  description = "OpenSearch domain endpoint"
  value       = aws_opensearch_domain.main.endpoint
  sensitive   = false
}

output "opensearch_domain_name" {
  description = "OpenSearch domain name"
  value       = aws_opensearch_domain.main.domain_name
  sensitive   = false
}

output "opensearch_kibana_endpoint" {
  description = "OpenSearch Kibana endpoint"
  value       = aws_opensearch_domain.main.kibana_endpoint
  sensitive   = false
}

output "opensearch_domain_arn" {
  description = "OpenSearch domain ARN"
  value       = aws_opensearch_domain.main.arn
  sensitive   = false
}

# Security Outputs
output "security_groups" {
  description = "Security group IDs"
  value = {
    alb         = module.security.alb_security_group_id
    ecs         = module.security.ecs_security_group_id
    neptune     = module.security.neptune_security_group_id
    opensearch  = module.security.opensearch_security_group_id
    elasticache = module.security.elasticache_security_group_id
  }
  sensitive = false
}

# IAM Role Outputs
output "iam_roles" {
  description = "IAM role ARNs"
  value = {
    ecs_execution = module.security.ecs_task_execution_role_arn
    ecs_task      = module.security.ecs_task_role_arn
    opensearch    = aws_iam_role.opensearch_master.arn
  }
  sensitive = false
}

# Certificate Manager outputs
output "ssl_certificate_arn" {
  description = "SSL certificate ARN"
  value       = var.domain_name != "" ? aws_acm_certificate.main[0].arn : var.ssl_certificate_arn
  sensitive   = false
}

output "ssl_certificate_domain_validation_options" {
  description = "SSL certificate domain validation options"
  value       = var.domain_name != "" ? aws_acm_certificate.main[0].domain_validation_options : null
  sensitive   = false
}

# Secrets Manager Outputs
output "secrets" {
  description = "Secrets Manager ARNs"
  value = {
    neptune_endpoint    = aws_secretsmanager_secret.neptune_endpoint.arn
    opensearch_endpoint = aws_secretsmanager_secret.opensearch_endpoint.arn
  }
  sensitive = false
}

# Application URLs
output "application_urls" {
  description = "Application access URLs"
  value = {
    load_balancer = "http://${aws_lb.main.dns_name}"
    cloudfront    = var.enable_cdn ? "https://${aws_cloudfront_distribution.main[0].domain_name}" : null
    custom_domain = var.domain_name != "" ? "https://${var.domain_name}" : null
  }
  sensitive = false
}

# Cost Estimation Outputs
output "estimated_monthly_cost_usd" {
  description = "Estimated monthly cost in USD"
  value = {
    # Database costs
    neptune_instance    = "~$150-200"
    neptune_storage     = "~$10-20"
    neptune_io         = "~$5-10"
    opensearch_instance = "~$50-70"
    opensearch_storage  = "~$2-3"
    
    # Application costs
    ecs_fargate        = "~$30-60"
    alb               = "~$20-25"
    cloudfront        = var.enable_cdn ? "~$5-15" : "$0"
    elasticache       = var.enable_caching ? "~$15-30" : "$0"
    
    # Storage and transfer
    s3_logs           = "~$5-10"
    data_transfer     = "~$10-20"
    
    total_estimated   = var.enable_cdn && var.enable_caching ? "~$302-463" : "~$282-418"
  }
  sensitive = false
}

# Environment Information
output "deployment_info" {
  description = "Deployment information"
  value = {
    region           = var.aws_region
    environment      = var.environment
    project_name     = var.project_name
    vpc_id          = module.vpc.vpc_id
    availability_zones = local.availability_zones
    features_enabled = {
      cdn             = var.enable_cdn
      caching         = var.enable_caching
      cloudtrail      = var.enable_cloudtrail
      container_insights = var.enable_container_insights
      xray           = var.enable_xray
    }
    timestamp       = timestamp()
  }
  sensitive = false
}
# =============================================================================
# MONITORING AND LOGGING OUTPUTS
# =============================================================================

output "monitoring" {
  description = "Monitoring and logging infrastructure details"
  value = {
    # SNS Topic
    alerts_topic_arn = aws_sns_topic.alerts.arn
    
    # CloudWatch Dashboard
    dashboard_url = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
    
    # CloudWatch Log Groups
    log_groups = {
      ecs_tasks           = aws_cloudwatch_log_group.ecs_tasks.name
      ecs_exec            = aws_cloudwatch_log_group.ecs_exec.name
      neptune_audit       = aws_cloudwatch_log_group.neptune_audit.name
      opensearch_slow     = aws_cloudwatch_log_group.opensearch_search_slow.name
      opensearch_index    = aws_cloudwatch_log_group.opensearch_index_slow.name
      opensearch_app      = aws_cloudwatch_log_group.opensearch_es_application.name
      elasticache_slow    = var.enable_caching ? aws_cloudwatch_log_group.elasticache_slow[0].name : null
    }
    
    # CloudWatch Alarms
    alarms = {
      alb_response_time     = aws_cloudwatch_metric_alarm.alb_high_response_time.alarm_name
      alb_4xx_errors        = aws_cloudwatch_metric_alarm.alb_high_4xx_errors.alarm_name
      alb_5xx_errors        = aws_cloudwatch_metric_alarm.alb_high_5xx_errors.alarm_name
      ecs_high_cpu          = aws_cloudwatch_metric_alarm.ecs_high_cpu.alarm_name
      ecs_high_memory       = aws_cloudwatch_metric_alarm.ecs_high_memory.alarm_name
      neptune_high_cpu      = aws_cloudwatch_metric_alarm.neptune_high_cpu.alarm_name
      neptune_connections   = aws_cloudwatch_metric_alarm.neptune_high_connections.alarm_name
      opensearch_high_cpu   = aws_cloudwatch_metric_alarm.opensearch_high_cpu.alarm_name
      opensearch_jvm_memory = aws_cloudwatch_metric_alarm.opensearch_high_jvm_memory.alarm_name
      application_errors    = aws_cloudwatch_metric_alarm.application_errors.alarm_name
      elasticache_cpu       = var.enable_caching ? aws_cloudwatch_metric_alarm.elasticache_high_cpu[0].alarm_name : null
      elasticache_memory    = var.enable_caching ? aws_cloudwatch_metric_alarm.elasticache_high_memory[0].alarm_name : null
    }
    
    # X-Ray Tracing
    xray_sampling_rule = aws_xray_sampling_rule.main.rule_name
    
    # Log Insights Queries
    log_insights_queries_parameter = aws_ssm_parameter.log_insights_queries.name
  }
}
# =============================================================================
# SECURITY CONTROLS OUTPUTS
# =============================================================================

output "security_controls" {
  description = "Security controls and compliance infrastructure details"
  value = {
    # WAF Configuration
    waf_web_acl_arn = aws_wafv2_web_acl.main.arn
    waf_web_acl_id  = aws_wafv2_web_acl.main.id
    
    # Security Services
    security_hub_enabled = var.enable_security_hub
    guardduty_enabled    = var.enable_guardduty ? aws_guardduty_detector.main[0].id : null
    inspector_enabled    = var.enable_inspector
    config_enabled       = var.enable_config
    
    # Security Monitoring
    security_alarms = {
      waf_blocked_requests = aws_cloudwatch_metric_alarm.waf_blocked_requests.alarm_name
      guardduty_findings   = var.enable_guardduty ? aws_cloudwatch_metric_alarm.guardduty_findings[0].alarm_name : null
    }
    
    # Network Security
    network_acls = {
      private_nacl  = aws_network_acl.private.id
      database_nacl = aws_network_acl.database.id
    }
    
    # VPC Flow Logs
    vpc_flow_logs = {
      log_group_name = aws_cloudwatch_log_group.vpc_flow_logs.name
      flow_log_id    = aws_flow_log.vpc.id
    }
    
    # Security Log Groups
    security_log_groups = {
      waf_logs      = aws_cloudwatch_log_group.waf_logs.name
      vpc_flow_logs = aws_cloudwatch_log_group.vpc_flow_logs.name
      config_bucket = var.enable_config ? aws_s3_bucket.config[0].bucket : null
    }
  }
}

# =============================================================================
# COST OPTIMIZATION OUTPUTS
# =============================================================================

output "cost_optimization" {
  description = "Cost optimization infrastructure and recommendations"
  value = var.enable_cost_optimization ? {
    # Budget and Cost Monitoring
    budget_name                    = aws_budgets_budget.monthly_cost[0].name
    budget_limit                   = var.monthly_budget_limit
    cost_anomaly_detector_arn     = aws_ce_anomaly_detector.main[0].arn
    cost_monitoring_dashboard_url = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.cost_monitoring[0].dashboard_name}"
    
    # Resource Cleanup
    resource_cleanup_function     = aws_lambda_function.resource_cleanup[0].function_name
    cleanup_schedule             = aws_cloudwatch_event_rule.resource_cleanup[0].schedule_expression
    
    # Scheduled Scaling
    scheduled_scaling_enabled    = var.enable_scheduled_scaling
    scale_down_schedule         = var.enable_scheduled_scaling ? aws_appautoscaling_scheduled_action.scale_down_night[0].schedule : null
    scale_up_schedule           = var.enable_scheduled_scaling ? aws_appautoscaling_scheduled_action.scale_up_morning[0].schedule : null
    
    # Cost Recommendations
    recommendations_parameter    = aws_ssm_parameter.cost_optimization_recommendations[0].name
    
    # Cost Optimization Features
    features_enabled = {
      budget_alerts         = length(var.budget_alert_emails) > 0
      cost_anomaly_detection = true
      automated_cleanup     = true
      scheduled_scaling     = var.enable_scheduled_scaling
      cost_monitoring_dashboard = true
    }
  } : null
}

output "cost_optimization_recommendations" {
  description = "Cost optimization recommendations and best practices"
  value = {
    resource_rightsizing = {
      neptune_instance = "Monitor CPU/memory utilization. Consider smaller instance types for dev/test environments."
      opensearch_instance = "Monitor search latency and CPU. Consider t3.micro.search for low-traffic workloads."
      ecs_resources = "Monitor ECS metrics. Right-size CPU/memory based on actual usage patterns."
      storage_optimization = "Use gp3 volumes instead of gp2 for better price/performance ratio."
    }
    cost_savings_opportunities = {
      reserved_instances = "Consider 1-year reserved instances for 30-40% savings on Neptune and OpenSearch"
      spot_instances = "Use Spot instances for non-production ECS tasks for up to 70% savings"
      scheduled_scaling = "Enable scheduled scaling to reduce capacity during off-hours"
      single_nat_gateway = "Use single NAT Gateway for non-production environments"
      lifecycle_policies = "Implement S3 lifecycle policies for log retention and cost reduction"
    }
    monitoring_and_alerts = {
      budgets = "Monthly budget alerts configured at 80% and 100% thresholds"
      anomaly_detection = "Cost anomaly detection enabled for unexpected spend patterns"
      cleanup_automation = "Automated resource cleanup scheduled daily at 2 AM UTC"
      cost_allocation_tags = "Ensure all resources are properly tagged for cost allocation"
    }
    estimated_savings = {
      reserved_instances = "30-40% on database costs"
      spot_instances = "Up to 70% on ECS compute costs"
      scheduled_scaling = "20-30% on compute costs during off-hours"
      automated_cleanup = "5-10% on storage and logging costs"
    }
  }
}

# =============================================================================
# BACKUP AND RECOVERY OUTPUTS
# =============================================================================

output "backup_and_recovery" {
  description = "Backup and recovery infrastructure details"
  value = {
    # Neptune Backup Configuration
    neptune_backup = {
      cluster_identifier      = aws_neptune_cluster.main.cluster_identifier
      backup_retention_period = var.neptune_backup_retention_period
      backup_window          = var.neptune_backup_window
      maintenance_window     = var.neptune_maintenance_window
      point_in_time_recovery = "Available for last ${var.neptune_backup_retention_period} days"
      automated_backups      = "Enabled"
    }
    
    # OpenSearch Backup Configuration
    opensearch_backup = {
      domain_name           = aws_opensearch_domain.main.domain_name
      snapshot_bucket       = aws_s3_bucket.opensearch_snapshots.bucket
      snapshot_bucket_arn   = aws_s3_bucket.opensearch_snapshots.arn
      automated_snapshots   = "AWS managed hourly snapshots"
      snapshot_repository   = "Configured for manual snapshots"
    }
    
    # Cross-Region Backup
    cross_region_backup = {
      enabled               = var.enable_cross_region_backup
      backup_region        = var.backup_region
      replication_bucket   = var.enable_cross_region_backup ? aws_s3_bucket.backup_replication[0].bucket : null
      replication_status   = var.enable_cross_region_backup ? "Enabled" : "Disabled"
    }
    
    # Backup Management
    backup_management = {
      lambda_function_name = aws_lambda_function.backup_manager.function_name
      lambda_function_arn  = aws_lambda_function.backup_manager.arn
      backup_schedule      = aws_cloudwatch_event_rule.backup_schedule.schedule_expression
      backup_log_group     = aws_cloudwatch_log_group.backup_manager.name
    }
    
    # Backup Monitoring
    backup_monitoring = {
      dashboard_name       = aws_cloudwatch_dashboard.backup_monitoring.dashboard_name
      dashboard_url        = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.backup_monitoring.dashboard_name}"
      backup_failure_alarm = aws_cloudwatch_metric_alarm.backup_failures.alarm_name
      backup_success_alarm = aws_cloudwatch_metric_alarm.backup_success.alarm_name
    }
    
    # Disaster Recovery
    disaster_recovery = {
      procedures_parameter = aws_ssm_parameter.disaster_recovery_procedures.name
      rto_target          = "4 hours"
      rpo_target          = "1 hour"
      recovery_regions    = var.enable_cross_region_backup ? [var.aws_region, var.backup_region] : [var.aws_region]
    }
    
    # Backup Storage
    backup_storage = {
      opensearch_snapshots = {
        bucket_name     = aws_s3_bucket.opensearch_snapshots.bucket
        bucket_arn      = aws_s3_bucket.opensearch_snapshots.arn
        encryption      = "KMS encrypted"
        lifecycle_policy = "Enabled (IA after 30 days, Glacier after 90 days, Deep Archive after 365 days)"
      }
      cross_region_replication = var.enable_cross_region_backup ? {
        bucket_name = aws_s3_bucket.backup_replication[0].bucket
        bucket_arn  = aws_s3_bucket.backup_replication[0].arn
        region      = var.backup_region
      } : null
    }
  }
}

output "disaster_recovery_procedures" {
  description = "Disaster recovery procedures and contact information"
  value = {
    neptune_recovery_steps = [
      "1. Identify the desired recovery point (timestamp)",
      "2. Create new Neptune cluster from backup using AWS CLI or Console",
      "3. Update application configuration to point to new cluster endpoint",
      "4. Verify data integrity and application functionality",
      "5. Update DNS/load balancer to redirect traffic to new cluster"
    ]
    opensearch_recovery_steps = [
      "1. Create new OpenSearch domain with same configuration",
      "2. Register snapshot repository pointing to S3 bucket: ${aws_s3_bucket.opensearch_snapshots.bucket}",
      "3. List available snapshots using OpenSearch API",
      "4. Restore from snapshot using OpenSearch API",
      "5. Verify indices and data integrity",
      "6. Update application configuration with new domain endpoint"
    ]
    application_recovery_steps = [
      "1. Identify last known good ECS task definition",
      "2. Update ECS service to use previous task definition",
      "3. Monitor service health and auto-scaling",
      "4. Verify application functionality and integrations"
    ]
    cross_region_recovery_steps = var.enable_cross_region_backup ? [
      "1. Provision infrastructure in backup region (${var.backup_region}) using Terraform",
      "2. Restore Neptune from cross-region backup",
      "3. Restore OpenSearch from replicated S3 snapshots",
      "4. Deploy application in backup region",
      "5. Update DNS to point to backup region",
      "6. Monitor and validate functionality"
    ] : ["Cross-region backup not enabled"]
    emergency_contacts = {
      primary_oncall = "Platform Team"
      backup_oncall  = "DevOps Team"
      escalation     = "Engineering Manager"
      sns_topic      = aws_sns_topic.alerts.arn
    }
    testing_schedule = {
      monthly_dr_test    = "First Saturday of each month"
      backup_validation  = "Weekly automated validation"
      recovery_testing   = "Quarterly full recovery test"
    }
  }
}