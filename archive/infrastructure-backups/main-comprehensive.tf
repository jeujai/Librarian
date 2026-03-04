# AWS Production Deployment Infrastructure - COMPREHENSIVE VERSION
# This is a recreation of the original comprehensive main.tf file
# Based on references found in other files and previous context

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

# Data sources
data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
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

  tags = {
    Name = "${var.neptune_cluster_identifier}-${count.index + 1}"
  }
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

  tags = merge(local.common_tags, {
    Name = "neptune-audit-logs"
    Type = "log-group"
  })
}

# OpenSearch Domain
resource "aws_opensearch_domain" "main" {
  domain_name    = var.opensearch_domain_name
  engine_version = var.opensearch_engine_version

  cluster_config {
    instance_type            = var.opensearch_instance_type
    instance_count           = var.opensearch_instance_count
    dedicated_master_enabled = var.opensearch_dedicated_master_enabled
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
    enabled = var.opensearch_encrypt_at_rest
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

# ECR Repository for application images
resource "aws_ecr_repository" "app" {
  name                 = "${local.name_prefix}-app"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = module.security.main_kms_key_arn
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-app-repository"
    Type = "ecr-repository"
  })
}

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "${local.name_prefix}-cluster"

  configuration {
    execute_command_configuration {
      kms_key_id = module.security.main_kms_key_arn
      logging    = "OVERRIDE"

      log_configuration {
        cloud_watch_encryption_enabled = true
        cloud_watch_log_group_name     = aws_cloudwatch_log_group.ecs_exec.name
      }
    }
  }

  setting {
    name  = "containerInsights"
    value = var.enable_container_insights ? "enabled" : "disabled"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-cluster"
    Type = "ecs-cluster"
  })
}

# CloudWatch Log Group for ECS Exec
resource "aws_cloudwatch_log_group" "ecs_exec" {
  name              = "/aws/ecs/${local.name_prefix}/exec"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "ecs-exec-logs"
    Type = "log-group"
  })
}

# CloudWatch Log Group for ECS Tasks
resource "aws_cloudwatch_log_group" "ecs_tasks" {
  name              = "/aws/ecs/${local.name_prefix}/tasks"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, {
    Name = "ecs-tasks-logs"
    Type = "log-group"
  })
}

# ECS Task Definition
resource "aws_ecs_task_definition" "app" {
  family                   = "${local.name_prefix}-app"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = module.security.ecs_task_execution_role_arn
  task_role_arn           = module.security.ecs_task_role_arn

  container_definitions = jsonencode([
    {
      name  = "app"
      image = "${aws_ecr_repository.app.repository_url}:latest"
      
      essential = true
      
      portMappings = [
        {
          containerPort = var.app_port
          protocol      = "tcp"
        }
      ]
      
      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "ENVIRONMENT"
          value = var.environment
        },
        {
          name  = "APP_PORT"
          value = tostring(var.app_port)
        },
        {
          name  = "NEPTUNE_ENDPOINT"
          value = aws_neptune_cluster.main.endpoint
        },
        {
          name  = "OPENSEARCH_ENDPOINT"
          value = aws_opensearch_domain.main.endpoint
        }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_tasks.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "app"
        }
      }
      
      healthCheck = {
        command = [
          "CMD-SHELL",
          "curl -f http://localhost:${var.app_port}${var.health_check_path} || exit 1"
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-app-task-definition"
    Type = "ecs-task-definition"
  })
}

# Application Load Balancer
resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [module.security.alb_security_group_id]
  subnets            = module.vpc.public_subnet_ids

  enable_deletion_protection = var.environment == "production" ? false : false  # Disabled for initial deployment
  enable_http2              = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-application-load-balancer"
    Type = "application-load-balancer"
  })
}

# ALB Target Group
resource "aws_lb_target_group" "app" {
  name        = "${local.name_prefix}-app-tg"
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    path                = var.health_check_path
    matcher             = "200"
    port                = "traffic-port"
    protocol            = "HTTP"
  }

  deregistration_delay = 30

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-app-target-group"
    Type = "alb-target-group"
  })
}

# ALB Listener (HTTP)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-http-listener"
    Type = "alb-listener"
  })
}

# ECS Service
resource "aws_ecs_service" "app" {
  name            = "${local.name_prefix}-app-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"
  
  platform_version = "LATEST"

  network_configuration {
    security_groups  = [module.security.ecs_security_group_id]
    subnets          = module.vpc.private_subnet_ids
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.app.arn
    container_name   = "app"
    container_port   = var.app_port
  }

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 50
    
    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }

  enable_execute_command = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-app-service"
    Type = "ecs-service"
  })

  depends_on = [
    aws_lb_listener.http
  ]
}

# Auto Scaling Target
resource "aws_appautoscaling_target" "ecs_target" {
  max_capacity       = var.ecs_max_capacity
  min_capacity       = var.ecs_min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.app.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-autoscaling-target"
    Type = "autoscaling-target"
  })
}

# Auto Scaling Policy - CPU
resource "aws_appautoscaling_policy" "ecs_cpu" {
  name               = "${local.name_prefix}-ecs-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = var.cpu_target_value
    scale_in_cooldown  = var.scale_down_cooldown
    scale_out_cooldown = var.scale_up_cooldown
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-ecs-cpu-scaling-policy"
    Type = "autoscaling-policy"
  })
}