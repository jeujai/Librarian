# Production Terraform Variables for Multimodal Librarian
# Production deployment configuration

# Core Configuration
aws_region   = "us-east-1"
environment  = "prod"
project_name = "ml-librarian"
cost_center  = "engineering"
owner        = "platform-team"

# Network Configuration
vpc_cidr           = "10.0.0.0/16"
az_count           = 3
enable_nat_gateway = true
single_nat_gateway = false # Use multiple NAT gateways for HA in production

# Application Configuration
app_name          = "ml-librarian"
app_port          = 8000
health_check_path = "/api/health/minimal"

# ECS Configuration - Production sizing
ecs_cpu           = 2048 # 2 vCPU for production ML workloads
ecs_memory        = 4096 # 4 GB RAM for production ML workloads
ecs_desired_count = 2    # 2 instances for HA
ecs_min_capacity  = 1    # Minimum 1 instance
ecs_max_capacity  = 10   # Scale up to 10 instances

# Auto Scaling Configuration
cpu_target_value    = 70.0
memory_target_value = 80.0
scale_up_cooldown   = 300
scale_down_cooldown = 300

# Security Configuration
enable_waf        = true
enable_cloudtrail = true
enable_config     = true
enable_guardduty  = true
enable_security_hub = true
enable_inspector  = true
enable_vpc_flow_logs = true
waf_rate_limit    = 2000

# Monitoring Configuration
enable_container_insights = true
log_retention_days        = 30 # 30 days for production
enable_xray               = true

# Backup Configuration
backup_retention_days      = 30
enable_cross_region_backup = false # Disable for initial deployment
backup_region              = "us-west-2"

# Cost Optimization Configuration
enable_cost_optimization = true
enable_spot_instances    = false # Don't use spot instances in production
enable_scheduled_scaling = false # Disable for initial deployment

# Performance Configuration
enable_caching  = true
cache_node_type = "cache.t3.micro" # Start small for initial deployment
cache_num_nodes = 1                # Single node for initial deployment

# Feature Flags
enable_cdn               = false # Disable CDN for initial deployment
enable_s3_static_hosting = true
enable_secrets_rotation  = true

# Neptune Configuration - Production ready but cost-optimized
neptune_cluster_identifier      = "ml-librarian-neptune"
neptune_engine_version          = "1.2.1.0"
neptune_instance_class          = "db.t3.medium"        # Cost-optimized for initial deployment
neptune_instance_count          = 1                     # Single instance for initial deployment
neptune_backup_retention_period = 7                     # 7 days backup retention
neptune_backup_window           = "07:00-09:00"         # UTC backup window
neptune_maintenance_window      = "sun:09:00-sun:10:00" # UTC maintenance window

# Neptune Monitoring (disabled for cost optimization)
neptune_performance_insights_enabled = false
neptune_monitoring_interval          = 0 # Enhanced monitoring disabled

# OpenSearch Configuration - Production ready but cost-optimized
opensearch_domain_name    = "ml-librarian-search"
opensearch_engine_version = "OpenSearch_2.3"
opensearch_instance_type  = "t3.small.search" # Cost-optimized for initial deployment
opensearch_instance_count = 1                 # Single instance for initial deployment

# OpenSearch Master Nodes (disabled for cost optimization)
opensearch_dedicated_master_enabled = false
opensearch_master_instance_type     = "t3.small.search"
opensearch_master_instance_count    = 0

# OpenSearch Availability (single-AZ for cost optimization)
opensearch_zone_awareness_enabled  = false
opensearch_availability_zone_count = 1

# OpenSearch Storage
opensearch_ebs_enabled = true
opensearch_volume_type = "gp3"
opensearch_volume_size = 20   # 20GB for initial deployment
opensearch_iops        = 3000 # Default for gp3
opensearch_throughput  = 125  # Default for gp3

# Security Configuration
opensearch_encrypt_at_rest           = true
opensearch_node_to_node_encryption   = true
opensearch_enforce_https             = true
opensearch_tls_security_policy       = "Policy-Min-TLS-1-2-2019-07"
opensearch_advanced_security_enabled = true

# Snapshot Configuration
skip_final_snapshot = true # Skip final snapshots for initial deployment

# Alert Configuration
alert_email = "" # Add email for alerts if needed

# Cost Monitoring
monthly_budget_limit   = 200
ecs_budget_limit      = 100
database_budget_limit = 80
budget_alert_emails    = []
cost_anomaly_threshold = 50