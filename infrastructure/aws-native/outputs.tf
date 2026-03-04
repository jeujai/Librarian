# Outputs for AWS Production Deployment Infrastructure

# VPC Outputs
output "vpc" {
  description = "VPC infrastructure details"
  value = {
    vpc_id             = module.vpc.vpc_id
    public_subnet_ids  = module.vpc.public_subnet_ids
    private_subnet_ids = module.vpc.private_subnet_ids
    availability_zones = var.availability_zones
  }
}

# Security Outputs
output "security" {
  description = "Security infrastructure details"
  value = {
    kms_key_arn = module.security.kms_key_arn
    waf_web_acl_arn = var.enable_waf ? module.security.waf_web_acl_arn : null
    guardduty_detector_id = var.enable_guardduty ? module.security.guardduty_detector_id : null
  }
}

# Database Outputs
output "databases" {
  description = "Database infrastructure details"
  value = {
    neptune_endpoint        = module.databases.neptune_endpoint
    neptune_reader_endpoint = module.databases.neptune_reader_endpoint
    neptune_port           = module.databases.neptune_port
    neptune_cluster_id     = module.databases.neptune_cluster_id
    opensearch_endpoint    = module.databases.opensearch_endpoint
    opensearch_domain_name = module.databases.opensearch_domain_name
  }
}

# Application Outputs
output "application" {
  description = "Application infrastructure details"
  value = {
    load_balancer_dns_name = module.application.load_balancer_dns_name
    load_balancer_zone_id  = module.application.load_balancer_zone_id
    ecs_cluster_name       = module.application.ecs_cluster_name
    ecs_service_name       = module.application.ecs_service_name
    cloudfront_domain_name = module.application.cloudfront_domain_name
  }
}

# Storage Outputs
output "storage" {
  description = "Storage infrastructure details"
  value = {
    efs_file_system_id   = module.storage.efs_file_system_id
    efs_access_point_id  = module.storage.efs_access_point_id
    efs_dns_name         = module.storage.efs_dns_name
    model_cache_path     = "/efs/model-cache"
  }
}

# Backup and Recovery Outputs
output "backup_and_recovery" {
  description = "Backup and recovery infrastructure details"
  value = {
    neptune_backup = {
      cluster_identifier      = module.databases.neptune_cluster_id
      backup_retention_period = var.neptune_backup_retention
      backup_window          = var.neptune_backup_window
      point_in_time_recovery = "Available for last ${var.neptune_backup_retention} days"
    }
    
    opensearch_backup = {
      domain_name           = module.databases.opensearch_domain_name
      snapshot_bucket       = module.backup.opensearch_snapshot_bucket
      automated_snapshots   = "AWS managed hourly snapshots"
    }
    
    cross_region_backup = {
      enabled               = var.enable_cross_region_backup
      backup_region        = var.backup_region
      replication_status   = var.enable_cross_region_backup ? "Enabled" : "Disabled"
      replication_bucket   = module.backup.cross_region_backup_bucket
    }
    
    backup_management = {
      lambda_function_name = module.backup.backup_lambda_function_name
      backup_schedule      = module.backup.backup_schedule_rule_name
      monitoring_dashboard = module.backup.backup_monitoring_dashboard_name
    }
    
    disaster_recovery = {
      procedures_parameter = module.backup.disaster_recovery_procedures_parameter
      rto_target          = "4 hours"
      rpo_target          = "1 hour"
    }
    
    monitoring = {
      backup_failure_alarm = module.backup.backup_failure_alarm_name
      backup_success_alarm = module.backup.backup_success_alarm_name
    }
  }
}

# Monitoring Outputs
output "monitoring" {
  description = "Monitoring infrastructure details"
  value = {
    log_groups = "CloudWatch log groups configured for all services"
    dashboards = "CloudWatch dashboards available for monitoring"
    alarms     = "CloudWatch alarms configured for critical metrics"
  }
}

# Connection Information
output "connection_secrets" {
  description = "AWS Secrets Manager secret ARNs for database connections"
  value = {
    neptune_secret_arn    = aws_secretsmanager_secret.neptune.arn
    opensearch_secret_arn = aws_secretsmanager_secret.opensearch.arn
  }
  sensitive = true
}

# Cost Optimization Outputs
output "cost_optimization" {
  description = "Cost optimization infrastructure details"
  value = {
    budgets = {
      monthly_budget_name  = module.cost_optimization.monthly_budget_name
      ecs_budget_name     = module.cost_optimization.ecs_budget_name
      database_budget_name = module.cost_optimization.database_budget_name
    }
    
    monitoring = {
      dashboard_name = module.cost_optimization.cost_monitoring_dashboard_name
      dashboard_url  = module.cost_optimization.cost_monitoring_dashboard_url
      high_cost_alarm = module.cost_optimization.high_cost_alarm_name
      underutilized_cpu_alarm = module.cost_optimization.underutilized_cpu_alarm_name
      underutilized_memory_alarm = module.cost_optimization.underutilized_memory_alarm_name
    }
    
    anomaly_detection = {
      detector_arn = module.cost_optimization.cost_anomaly_detector_arn
    }
    
    recommendations = {
      parameter_name = module.cost_optimization.cost_optimization_recommendations_parameter
    }
    
    summary = module.cost_optimization.cost_optimization_summary
  }
}

# Deployment Information
output "deployment_info" {
  description = "Deployment information and next steps"
  value = {
    environment    = var.environment
    aws_region     = var.aws_region
    project_name   = var.project_name
    deployment_url = module.application.load_balancer_dns_name
    
    next_steps = [
      "1. Configure DNS records to point to the load balancer",
      "2. Deploy application container to ECS service",
      "3. Configure monitoring alerts and notifications",
      "4. Review cost optimization recommendations and budgets",
      "5. Test backup and recovery procedures",
      "6. Conduct security assessment and penetration testing"
    ]
  }
}