# Container Failure Monitor Lambda Function
# Detects OOM kills, segfaults, and other container-level failures

# SNS Topic for alerts
resource "aws_sns_topic" "container_failure_alerts" {
  count = var.enable_container_failure_monitor ? 1 : 0
  name  = "${var.name_prefix}-container-failure-alerts"
  
  tags = {
    Name        = "${var.name_prefix}-container-failure-alerts"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# SNS Topic Subscription (email)
resource "aws_sns_topic_subscription" "container_failure_email" {
  count     = var.enable_container_failure_monitor && var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.container_failure_alerts[0].arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# IAM Role for Lambda
resource "aws_iam_role" "container_failure_monitor" {
  count = var.enable_container_failure_monitor ? 1 : 0
  name  = "${var.name_prefix}-container-failure-monitor"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.name_prefix}-container-failure-monitor"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "container_failure_monitor" {
  count = var.enable_container_failure_monitor ? 1 : 0
  name  = "${var.name_prefix}-container-failure-monitor"
  role  = aws_iam_role.container_failure_monitor[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:ListTasks",
          "ecs:DescribeTasks",
          "ecs:DescribeTaskDefinition"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.container_failure_alerts[0].arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Package Lambda function
data "archive_file" "container_failure_monitor" {
  count       = var.enable_container_failure_monitor ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/../../lambda/container_failure_monitor.py"
  output_path = "${path.module}/../../lambda/container_failure_monitor.zip"
}

# Lambda Function
resource "aws_lambda_function" "container_failure_monitor" {
  count            = var.enable_container_failure_monitor ? 1 : 0
  filename         = data.archive_file.container_failure_monitor[0].output_path
  function_name    = "${var.name_prefix}-container-failure-monitor"
  role             = aws_iam_role.container_failure_monitor[0].arn
  handler          = "container_failure_monitor.lambda_handler"
  source_code_hash = data.archive_file.container_failure_monitor[0].output_base64sha256
  runtime          = "python3.11"
  timeout          = 60
  memory_size      = 256

  environment {
    variables = {
      ECS_CLUSTER_NAME      = var.ecs_cluster_name
      ECS_SERVICE_NAME      = var.ecs_service_name
      SNS_TOPIC_ARN         = aws_sns_topic.container_failure_alerts[0].arn
      CHECK_WINDOW_MINUTES  = var.check_window_minutes
    }
  }

  tags = {
    Name        = "${var.name_prefix}-container-failure-monitor"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "container_failure_monitor" {
  count             = var.enable_container_failure_monitor ? 1 : 0
  name              = "/aws/lambda/${aws_lambda_function.container_failure_monitor[0].function_name}"
  retention_in_days = 7

  tags = {
    Name        = "${var.name_prefix}-container-failure-monitor-logs"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# EventBridge Rule to trigger Lambda every 5 minutes
resource "aws_cloudwatch_event_rule" "container_failure_monitor" {
  count               = var.enable_container_failure_monitor ? 1 : 0
  name                = "${var.name_prefix}-container-failure-monitor"
  description         = "Trigger container failure monitor every ${var.check_window_minutes} minutes"
  schedule_expression = "rate(${var.check_window_minutes} minutes)"

  tags = {
    Name        = "${var.name_prefix}-container-failure-monitor"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "container_failure_monitor" {
  count     = var.enable_container_failure_monitor ? 1 : 0
  rule      = aws_cloudwatch_event_rule.container_failure_monitor[0].name
  target_id = "ContainerFailureMonitor"
  arn       = aws_lambda_function.container_failure_monitor[0].arn
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "container_failure_monitor" {
  count         = var.enable_container_failure_monitor ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.container_failure_monitor[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.container_failure_monitor[0].arn
}

# CloudWatch Alarm for Lambda errors
resource "aws_cloudwatch_metric_alarm" "container_failure_monitor_errors" {
  count               = var.enable_container_failure_monitor ? 1 : 0
  alarm_name          = "${var.name_prefix}-container-failure-monitor-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "Alert when container failure monitor Lambda has errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.container_failure_monitor[0].function_name
  }

  alarm_actions = [aws_sns_topic.container_failure_alerts[0].arn]

  tags = {
    Name        = "${var.name_prefix}-container-failure-monitor-errors"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Outputs
output "container_failure_monitor_function_arn" {
  description = "ARN of the container failure monitor Lambda function"
  value       = var.enable_container_failure_monitor ? aws_lambda_function.container_failure_monitor[0].arn : null
}

output "container_failure_alerts_topic_arn" {
  description = "ARN of the SNS topic for container failure alerts"
  value       = var.enable_container_failure_monitor ? aws_sns_topic.container_failure_alerts[0].arn : null
}

output "container_failure_monitor_log_group" {
  description = "CloudWatch log group for container failure monitor"
  value       = var.enable_container_failure_monitor ? aws_cloudwatch_log_group.container_failure_monitor[0].name : null
}
