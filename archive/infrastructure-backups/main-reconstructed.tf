# AWS Production Deployment Infrastructure - FULLY RECONSTRUCTED VERSION
# This Terraform configuration recreates the complete comprehensive infrastructure
# for the Multimodal Librarian system using AWS-Native services
# Reconstructed from spec requirements, completion summaries, and module analysis

# Provider configuration
terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.2"
    }
  }
  
  backend "s3" {
    # Backend configuration will be provided via backend config file
    # terraform init -backend-config=backend.conf
  }
}

# Primary AWS Provider
provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Secondary AWS Provider for cross-region backup
provider "aws" {
  alias  = "backup_region"
  region = var.backup_region
  
  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
      Purpose     = "backup"
    }
  }
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

# Random password for secrets
resource "random_password" "master_password" {
  length  = 32
  special = true
}
# Local values
locals {
  name_prefix = "${var.project_name}-${var.environment}"
  
  # Network configuration
  vpc_cidr = var.vpc_cidr
  availability_zones = slice(data.aws_availability_zones.available.names, 0, var.az_count)
  
  # Calculate subnet CIDRs dynamically
  public_subnet_cidrs = [
    for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i)
  ]
  
  private_subnet_cidrs = [
    for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 10)
  ]
  
  database_subnet_cidrs = [
    for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, i + 20)
  ]
  
  # Common tags
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    CostCenter  = var.cost_center
    Owner       = var.owner
    CreatedAt   = timestamp()
  }
}

# =============================================================================
# NETWORKING INFRASTRUCTURE
# =============================================================================

# VPC Module - Creates networking infrastructure
module "vpc" {
  source = "./modules/vpc"

  name_prefix               = local.name_prefix
  vpc_cidr                 = local.vpc_cidr
  availability_zones       = local.availability_zones
  public_subnet_cidrs      = local.public_subnet_cidrs
  private_subnet_cidrs     = local.private_subnet_cidrs
  database_subnet_cidrs    = local.database_subnet_cidrs
  enable_nat_gateway       = var.enable_nat_gateway
  single_nat_gateway       = var.single_nat_gateway
  enable_flow_logs         = true
  flow_log_retention_days  = var.log_retention_days

  tags = local.common_tags
}

# =============================================================================
# SECURITY INFRASTRUCTURE
# =============================================================================

# Security Module - Creates IAM roles, KMS keys, and security groups
module "security" {
  source = "./modules/security"

  name_prefix        = local.name_prefix
  vpc_id            = module.vpc.vpc_id
  aws_region        = var.aws_region
  account_id        = data.aws_caller_identity.current.account_id
  app_port          = var.app_port
  enable_key_rotation = true
  kms_deletion_window = 7
  enable_caching     = var.enable_caching

  tags = local.common_tags
}
# =============================================================================
# CERTIFICATE MANAGER
# =============================================================================

# SSL Certificate for HTTPS
resource "aws_acm_certificate" "main" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  subject_alternative_names = [
    "*.${var.domain_name}"
  ]

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ssl-certificate"
    Type = "ssl-certificate"
  })
}

# =============================================================================
# WEB APPLICATION FIREWALL (WAF)
# =============================================================================

# WAF Web ACL
resource "aws_wafv2_web_acl" "main" {
  count = var.enable_waf ? 1 : 0
  
  name  = "${local.name_prefix}-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS Managed Rules - Core Rule Set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules - Known Bad Inputs
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "KnownBadInputsRuleSetMetric"
      sampled_requests_enabled   = true
    }
  }

  # Rate limiting rule
  rule {
    name     = "RateLimitRule"
    priority = 3

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitRuleMetric"
      sampled_requests_enabled   = true
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-waf"
    Type = "waf"
  })

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.name_prefix}WAF"
    sampled_requests_enabled   = true
  }
}
# =============================================================================
# DATABASE INFRASTRUCTURE - NEPTUNE
# =============================================================================

# Neptune Subnet Group
resource "aws_neptune_subnet_group" "main" {
  name       = "${local.name_prefix}-neptune-subnet-group"
  subnet_ids = module.vpc.database_subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-neptune-subnet-group"
    Type = "neptune-subnet-group"
  })
}

# Neptune Parameter Group
resource "aws_neptune_parameter_group" "main" {
  family = "neptune1.2"
  name   = "${local.name_prefix}-neptune-params"

  parameter {
    name  = "neptune_enable_audit_log"
    value = "1"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-neptune-params"
    Type = "neptune-parameter-group"
  })
}

# Neptune Cluster
resource "aws_neptune_cluster" "main" {
  cluster_identifier                   = var.neptune_cluster_identifier
  engine                              = "neptune"
  engine_version                      = var.neptune_engine_version
  backup_retention_period             = var.neptune_backup_retention_period
  preferred_backup_window             = var.neptune_backup_window
  preferred_maintenance_window        = var.neptune_maintenance_window
  skip_final_snapshot                 = var.skip_final_snapshot
  iam_database_authentication_enabled = true
  storage_encrypted                   = true
  kms_key_id                          = module.security.neptune_kms_key_arn
  
  vpc_security_group_ids = [module.security.neptune_security_group_id]
  neptune_subnet_group_name   = aws_neptune_subnet_group.main.name
  neptune_parameter_group_name = aws_neptune_parameter_group.main.name
  
  enable_cloudwatch_logs_exports = ["audit"]
  
  tags = merge(local.common_tags, {
    Name = var.neptune_cluster_identifier
    Type = "neptune-cluster"
  })

  depends_on = [
    aws_cloudwatch_log_group.neptune_audit
  ]
}

# Neptune Cluster Instance
resource "aws_neptune_cluster_instance" "main" {
  count              = var.neptune_instance_count
  identifier         = "${var.neptune_cluster_identifier}-${count.index + 1}"
  cluster_identifier = aws_neptune_cluster.main.id
  instance_class     = var.neptune_instance_class
  engine             = "neptune"

  performance_insights_enabled = var.neptune_performance_insights_enabled
  monitoring_interval         = var.neptune_monitoring_interval
  monitoring_role_arn        = var.neptune_monitoring_interval > 0 ? aws_iam_role.neptune_monitoring[0].arn : null

  tags = merge(local.common_tags, {
    Name = "${var.neptune_cluster_identifier}-${count.index + 1}"
    Type = "neptune-instance"
  })
}

# IAM Role for Neptune Enhanced Monitoring
resource "aws_iam_role" "neptune_monitoring" {
  count = var.neptune_monitoring_interval > 0 ? 1 : 0
  
  name = "${local.name_prefix}-neptune-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-neptune-monitoring-role"
    Type = "iam-role"
  })
}

resource "aws_iam_role_policy_attachment" "neptune_monitoring" {
  count = var.neptune_monitoring_interval > 0 ? 1 : 0
  
  role       = aws_iam_role.neptune_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# CloudWatch Log Group for Neptune
resource "aws_cloudwatch_log_group" "neptune_audit" {
  name              = "/aws/neptune/${var.neptune_cluster_identifier}/audit"
  retention_in_days = var.log_retention_days
  kms_key_id        = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "neptune-audit-logs"
    Type = "log-group"
  })
}
# =============================================================================
# DATABASE INFRASTRUCTURE - OPENSEARCH
# =============================================================================

# OpenSearch Domain
resource "aws_opensearch_domain" "main" {
  domain_name    = var.opensearch_domain_name
  engine_version = var.opensearch_engine_version

  cluster_config {
    instance_type            = var.opensearch_instance_type
    instance_count           = var.opensearch_instance_count
    dedicated_master_enabled = var.opensearch_dedicated_master_enabled
    master_instance_type     = var.opensearch_master_instance_type
    master_instance_count    = var.opensearch_master_instance_count
    zone_awareness_enabled   = var.opensearch_zone_awareness_enabled
    
    dynamic "zone_awareness_config" {
      for_each = var.opensearch_zone_awareness_enabled ? [1] : []
      content {
        availability_zone_count = var.opensearch_availability_zone_count
      }
    }
  }

  ebs_options {
    ebs_enabled = var.opensearch_ebs_enabled
    volume_type = var.opensearch_volume_type
    volume_size = var.opensearch_volume_size
    iops        = var.opensearch_volume_type == "gp3" ? var.opensearch_iops : null
    throughput  = var.opensearch_volume_type == "gp3" ? var.opensearch_throughput : null
  }

  vpc_options {
    security_group_ids = [module.security.opensearch_security_group_id]
    subnet_ids         = slice(module.vpc.database_subnet_ids, 0, min(length(module.vpc.database_subnet_ids), var.opensearch_zone_awareness_enabled ? var.opensearch_availability_zone_count : 1))
  }

  encrypt_at_rest {
    enabled    = var.opensearch_encrypt_at_rest
    kms_key_id = module.security.opensearch_kms_key_arn
  }

  node_to_node_encryption {
    enabled = var.opensearch_node_to_node_encryption
  }

  domain_endpoint_options {
    enforce_https       = var.opensearch_enforce_https
    tls_security_policy = var.opensearch_tls_security_policy
  }

  advanced_security_options {
    enabled                        = var.opensearch_advanced_security_enabled
    anonymous_auth_enabled         = false
    internal_user_database_enabled = false
    master_user_options {
      master_user_arn = aws_iam_role.opensearch_master.arn
    }
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_index_slow.arn
    log_type                 = "INDEX_SLOW_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_search_slow.arn
    log_type                 = "SEARCH_SLOW_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_application.arn
    log_type                 = "ES_APPLICATION_LOGS"
  }

  tags = merge(local.common_tags, {
    Name = var.opensearch_domain_name
    Type = "opensearch-domain"
  })

  depends_on = [
    aws_iam_service_linked_role.opensearch
  ]
}

# IAM Role for OpenSearch Master User
resource "aws_iam_role" "opensearch_master" {
  name = "${local.name_prefix}-opensearch-master"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name = "opensearch-master-role"
    Type = "iam-role"
  })
}

# IAM Service Linked Role for OpenSearch
resource "aws_iam_service_linked_role" "opensearch" {
  aws_service_name = "opensearch.amazonaws.com"
  description      = "Service linked role for OpenSearch"
}

# CloudWatch Log Groups for OpenSearch
resource "aws_cloudwatch_log_group" "opensearch_index_slow" {
  name              = "/aws/opensearch/domains/${var.opensearch_domain_name}/index-slow"
  retention_in_days = var.log_retention_days
  kms_key_id        = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "opensearch-index-slow-logs"
    Type = "log-group"
  })
}

resource "aws_cloudwatch_log_group" "opensearch_search_slow" {
  name              = "/aws/opensearch/domains/${var.opensearch_domain_name}/search-slow"
  retention_in_days = var.log_retention_days
  kms_key_id        = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "opensearch-search-slow-logs"
    Type = "log-group"
  })
}

resource "aws_cloudwatch_log_group" "opensearch_application" {
  name              = "/aws/opensearch/domains/${var.opensearch_domain_name}/application"
  retention_in_days = var.log_retention_days
  kms_key_id        = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "opensearch-application-logs"
    Type = "log-group"
  })
}
# =============================================================================
# CACHING INFRASTRUCTURE - ELASTICACHE REDIS
# =============================================================================

# ElastiCache Subnet Group
resource "aws_elasticache_subnet_group" "main" {
  count = var.enable_caching ? 1 : 0
  
  name       = "${local.name_prefix}-cache-subnet-group"
  subnet_ids = module.vpc.private_subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cache-subnet-group"
    Type = "elasticache-subnet-group"
  })
}

# ElastiCache Parameter Group
resource "aws_elasticache_parameter_group" "main" {
  count = var.enable_caching ? 1 : 0
  
  family = "redis7"
  name   = "${local.name_prefix}-cache-params"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cache-params"
    Type = "elasticache-parameter-group"
  })
}

# ElastiCache Redis Cluster
resource "aws_elasticache_replication_group" "main" {
  count = var.enable_caching ? 1 : 0
  
  replication_group_id         = "${local.name_prefix}-redis"
  description                  = "Redis cluster for ${local.name_prefix}"
  
  node_type                    = var.cache_node_type
  port                         = 6379
  parameter_group_name         = aws_elasticache_parameter_group.main[0].name
  
  num_cache_clusters           = var.cache_num_nodes
  
  engine_version               = "7.0"
  
  subnet_group_name            = aws_elasticache_subnet_group.main[0].name
  security_group_ids           = [module.security.cache_security_group_id]
  
  at_rest_encryption_enabled   = true
  transit_encryption_enabled   = true
  auth_token                   = random_password.redis_auth_token[0].result
  
  automatic_failover_enabled   = var.cache_num_nodes > 1
  multi_az_enabled            = var.cache_num_nodes > 1
  
  maintenance_window          = "sun:05:00-sun:09:00"
  snapshot_window             = "03:00-05:00"
  snapshot_retention_limit    = 5
  
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis_slow[0].name
    destination_type = "cloudwatch-logs"
    log_format       = "text"
    log_type         = "slow-log"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis"
    Type = "elasticache-redis"
  })
}

# Redis Auth Token
resource "random_password" "redis_auth_token" {
  count = var.enable_caching ? 1 : 0
  
  length  = 32
  special = false
}

# CloudWatch Log Group for Redis
resource "aws_cloudwatch_log_group" "redis_slow" {
  count = var.enable_caching ? 1 : 0
  
  name              = "/aws/elasticache/redis/${local.name_prefix}/slow-log"
  retention_in_days = var.log_retention_days
  kms_key_id        = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "redis-slow-logs"
    Type = "log-group"
  })
}
# =============================================================================
# SECRETS MANAGER
# =============================================================================

# Neptune Connection Secret
resource "aws_secretsmanager_secret" "neptune" {
  name                    = "${local.name_prefix}/neptune"
  description             = "Neptune connection details for ${local.name_prefix}"
  recovery_window_in_days = 7
  kms_key_id             = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-neptune-secret"
    Type = "secret"
  })
}

resource "aws_secretsmanager_secret_version" "neptune" {
  secret_id = aws_secretsmanager_secret.neptune.id
  secret_string = jsonencode({
    endpoint = aws_neptune_cluster.main.endpoint
    port     = aws_neptune_cluster.main.port
    engine   = "neptune"
  })
}

# OpenSearch Connection Secret
resource "aws_secretsmanager_secret" "opensearch" {
  name                    = "${local.name_prefix}/opensearch"
  description             = "OpenSearch connection details for ${local.name_prefix}"
  recovery_window_in_days = 7
  kms_key_id             = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-opensearch-secret"
    Type = "secret"
  })
}

resource "aws_secretsmanager_secret_version" "opensearch" {
  secret_id = aws_secretsmanager_secret.opensearch.id
  secret_string = jsonencode({
    endpoint = aws_opensearch_domain.main.endpoint
    port     = 443
    engine   = "opensearch"
  })
}

# Redis Connection Secret (if caching enabled)
resource "aws_secretsmanager_secret" "redis" {
  count = var.enable_caching ? 1 : 0
  
  name                    = "${local.name_prefix}/redis"
  description             = "Redis connection details for ${local.name_prefix}"
  recovery_window_in_days = 7
  kms_key_id             = module.security.main_kms_key_arn

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-redis-secret"
    Type = "secret"
  })
}

resource "aws_secretsmanager_secret_version" "redis" {
  count = var.enable_caching ? 1 : 0
  
  secret_id = aws_secretsmanager_secret.redis[0].id
  secret_string = jsonencode({
    endpoint   = aws_elasticache_replication_group.main[0].primary_endpoint_address
    port       = aws_elasticache_replication_group.main[0].port
    auth_token = random_password.redis_auth_token[0].result
    engine     = "redis"
  })
}