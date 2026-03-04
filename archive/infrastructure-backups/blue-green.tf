# Blue-Green Deployment Configuration
# This file defines resources for blue-green deployment strategy

# Variables for blue-green deployment
variable "blue_green_deployment" {
  description = "Enable blue-green deployment"
  type        = bool
  default     = false
}

variable "active_environment" {
  description = "Currently active environment (blue or green)"
  type        = string
  default     = "blue"
  validation {
    condition     = contains(["blue", "green"], var.active_environment)
    error_message = "Active environment must be either 'blue' or 'green'."
  }
}

# Blue Environment Target Group
resource "aws_lb_target_group" "blue" {
  name     = "${var.project_name}-blue-tg"
  port     = var.container_port
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/health/simple"
    matcher             = "200"
    port                = "traffic-port"
    protocol            = "HTTP"
  }

  target_type = "ip"

  tags = merge(var.tags, {
    Name           = "${var.project_name}-blue-target-group"
    DeploymentType = "blue"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Green Environment Target Group
resource "aws_lb_target_group" "green" {
  count = var.blue_green_deployment ? 1 : 0

  name     = "${var.project_name}-green-tg"
  port     = var.container_port
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/health/simple"
    matcher             = "200"
    port                = "traffic-port"
    protocol            = "HTTP"
  }

  target_type = "ip"

  tags = merge(var.tags, {
    Name           = "${var.project_name}-green-target-group"
    DeploymentType = "green"
  })

  lifecycle {
    create_before_destroy = true
  }
}

# Blue ECS Service
resource "aws_ecs_service" "blue" {
  name            = "${var.project_name}-blue"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = var.active_environment == "blue" ? var.desired_count : 0

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight           = 100
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.blue.arn
    container_name   = var.container_name
    container_port   = var.container_port
  }

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
    
    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }

  service_registries {
    registry_arn = aws_service_discovery_service.main.arn
  }

  depends_on = [
    aws_lb_listener.https,
    aws_iam_role_policy_attachment.ecs_task_execution_role
  ]

  tags = merge(var.tags, {
    Name           = "${var.project_name}-blue-service"
    DeploymentType = "blue"
  })

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# Green ECS Service (only created during blue-green deployment)
resource "aws_ecs_service" "green" {
  count = var.blue_green_deployment ? 1 : 0

  name            = "${var.project_name}-green"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.main.arn
  desired_count   = var.active_environment == "green" ? var.desired_count : 0

  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight           = 100
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.green[0].arn
    container_name   = var.container_name
    container_port   = var.container_port
  }

  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
    
    deployment_circuit_breaker {
      enable   = true
      rollback = true
    }
  }

  service_registries {
    registry_arn = aws_service_discovery_service.main.arn
  }

  depends_on = [
    aws_lb_listener.https,
    aws_iam_role_policy_attachment.ecs_task_execution_role
  ]

  tags = merge(var.tags, {
    Name           = "${var.project_name}-green-service"
    DeploymentType = "green"
  })

  lifecycle {
    ignore_changes = [desired_count]
  }
}

# Listener Rule for Blue Environment (default)
resource "aws_lb_listener_rule" "blue" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.blue.arn
  }

  condition {
    path_pattern {
      values = ["*"]
    }
  }

  tags = merge(var.tags, {
    Name           = "${var.project_name}-blue-listener-rule"
    DeploymentType = "blue"
  })
}

# Listener Rule for Green Environment (weighted routing during deployment)
resource "aws_lb_listener_rule" "green" {
  count = var.blue_green_deployment && var.active_environment == "green" ? 1 : 0

  listener_arn = aws_lb_listener.https.arn
  priority     = 50  # Higher priority than blue

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.green[0].arn
  }

  condition {
    path_pattern {
      values = ["*"]
    }
  }

  tags = merge(var.tags, {
    Name           = "${var.project_name}-green-listener-rule"
    DeploymentType = "green"
  })
}

# Auto Scaling for Blue Environment
resource "aws_appautoscaling_target" "blue" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.blue.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  tags = merge(var.tags, {
    Name           = "${var.project_name}-blue-autoscaling-target"
    DeploymentType = "blue"
  })
}

# Auto Scaling for Green Environment
resource "aws_appautoscaling_target" "green" {
  count = var.blue_green_deployment ? 1 : 0

  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.green[0].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  tags = merge(var.tags, {
    Name           = "${var.project_name}-green-autoscaling-target"
    DeploymentType = "green"
  })
}

# CPU Scaling Policy for Blue
resource "aws_appautoscaling_policy" "blue_cpu" {
  name               = "${var.project_name}-blue-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.blue.resource_id
  scalable_dimension = aws_appautoscaling_target.blue.scalable_dimension
  service_namespace  = aws_appautoscaling_target.blue.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}

# CPU Scaling Policy for Green
resource "aws_appautoscaling_policy" "green_cpu" {
  count = var.blue_green_deployment ? 1 : 0

  name               = "${var.project_name}-green-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.green[0].resource_id
  scalable_dimension = aws_appautoscaling_target.green[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.green[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = 70.0
  }
}

# Memory Scaling Policy for Blue
resource "aws_appautoscaling_policy" "blue_memory" {
  name               = "${var.project_name}-blue-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.blue.resource_id
  scalable_dimension = aws_appautoscaling_target.blue.scalable_dimension
  service_namespace  = aws_appautoscaling_target.blue.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value = 80.0
  }
}

# Memory Scaling Policy for Green
resource "aws_appautoscaling_policy" "green_memory" {
  count = var.blue_green_deployment ? 1 : 0

  name               = "${var.project_name}-green-memory-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.green[0].resource_id
  scalable_dimension = aws_appautoscaling_target.green[0].scalable_dimension
  service_namespace  = aws_appautoscaling_target.green[0].service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageMemoryUtilization"
    }
    target_value = 80.0
  }
}

# Parameter Store for deployment state
resource "aws_ssm_parameter" "active_deployment" {
  name  = "/${var.project_name}/${var.environment}/active-deployment"
  type  = "String"
  value = var.active_environment

  tags = merge(var.tags, {
    Name = "${var.project_name}-active-deployment-parameter"
  })
}

# Parameter Store for last stable tag
resource "aws_ssm_parameter" "last_stable_tag" {
  name  = "/${var.project_name}/${var.environment}/last-stable-tag"
  type  = "String"
  value = var.image_tag

  tags = merge(var.tags, {
    Name = "${var.project_name}-last-stable-tag-parameter"
  })

  lifecycle {
    ignore_changes = [value]
  }
}

# CloudWatch Alarms for Blue-Green Deployment Monitoring
resource "aws_cloudwatch_metric_alarm" "blue_target_health" {
  alarm_name          = "${var.project_name}-blue-target-health"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "This metric monitors blue environment target health"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    TargetGroup  = aws_lb_target_group.blue.arn_suffix
    LoadBalancer = aws_lb.main.arn_suffix
  }

  tags = merge(var.tags, {
    Name           = "${var.project_name}-blue-target-health-alarm"
    DeploymentType = "blue"
  })
}

resource "aws_cloudwatch_metric_alarm" "green_target_health" {
  count = var.blue_green_deployment ? 1 : 0

  alarm_name          = "${var.project_name}-green-target-health"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "HealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Average"
  threshold           = "1"
  alarm_description   = "This metric monitors green environment target health"
  alarm_actions       = [var.sns_topic_arn]

  dimensions = {
    TargetGroup  = aws_lb_target_group.green[0].arn_suffix
    LoadBalancer = aws_lb.main.arn_suffix
  }

  tags = merge(var.tags, {
    Name           = "${var.project_name}-green-target-health-alarm"
    DeploymentType = "green"
  })
}