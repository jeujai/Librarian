# Backup and Recovery Module
# Implements comprehensive backup and recovery infrastructure

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.0"
      configuration_aliases = [aws.backup_region]
    }
  }
}

# S3 Bucket for OpenSearch snapshots
resource "aws_s3_bucket" "opensearch_snapshots" {
  bucket        = "${var.name_prefix}-opensearch-snapshots-${var.random_suffix}"
  force_destroy = false # Protect backup data

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-opensearch-snapshots"
    Type = "backup-storage"
  })
}

# S3 Bucket versioning for OpenSearch snapshots
resource "aws_s3_bucket_versioning" "opensearch_snapshots" {
  bucket = aws_s3_bucket.opensearch_snapshots.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket encryption for OpenSearch snapshots
resource "aws_s3_bucket_server_side_encryption_configuration" "opensearch_snapshots" {
  bucket = aws_s3_bucket.opensearch_snapshots.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = "aws:kms"
    }
  }
}

# S3 Bucket public access block for OpenSearch snapshots
resource "aws_s3_bucket_public_access_block" "opensearch_snapshots" {
  bucket = aws_s3_bucket.opensearch_snapshots.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 Bucket lifecycle configuration for OpenSearch snapshots
resource "aws_s3_bucket_lifecycle_configuration" "opensearch_snapshots" {
  bucket = aws_s3_bucket.opensearch_snapshots.id

  rule {
    id     = "backup_lifecycle"
    status = "Enabled"

    filter {
      prefix = ""
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    expiration {
      days = 90
    }
  }
}

# Cross-region backup bucket (conditional)
resource "aws_s3_bucket" "backup_replication" {
  count = var.enable_cross_region_backup ? 1 : 0

  provider      = aws.backup_region
  bucket        = "${var.name_prefix}-backup-replication-${var.random_suffix}"
  force_destroy = false

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-backup-replication"
    Type = "cross-region-backup"
  })
}

# Cross-region backup bucket encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "backup_replication" {
  count = var.enable_cross_region_backup ? 1 : 0

  provider = aws.backup_region
  bucket   = aws_s3_bucket.backup_replication[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Cross-region backup bucket versioning
resource "aws_s3_bucket_versioning" "backup_replication" {
  count = var.enable_cross_region_backup ? 1 : 0

  provider = aws.backup_region
  bucket   = aws_s3_bucket.backup_replication[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket replication configuration
resource "aws_s3_bucket_replication_configuration" "backup_replication" {
  count = var.enable_cross_region_backup ? 1 : 0

  role   = aws_iam_role.replication[0].arn
  bucket = aws_s3_bucket.opensearch_snapshots.id

  rule {
    id     = "backup_replication"
    status = "Enabled"

    destination {
      bucket        = aws_s3_bucket.backup_replication[0].arn
      storage_class = "STANDARD_IA"
    }
  }

  depends_on = [aws_s3_bucket_versioning.opensearch_snapshots]
}

# IAM role for S3 replication
resource "aws_iam_role" "replication" {
  count = var.enable_cross_region_backup ? 1 : 0

  name = "${var.name_prefix}-s3-replication-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM policy for S3 replication
resource "aws_iam_role_policy" "replication" {
  count = var.enable_cross_region_backup ? 1 : 0

  name = "${var.name_prefix}-s3-replication-policy"
  role = aws_iam_role.replication[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObjectVersionForReplication",
          "s3:GetObjectVersionAcl"
        ]
        Resource = "${aws_s3_bucket.opensearch_snapshots.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = aws_s3_bucket.opensearch_snapshots.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ReplicateObject",
          "s3:ReplicateDelete"
        ]
        Resource = "${aws_s3_bucket.backup_replication[0].arn}/*"
      }
    ]
  })
}

# IAM role for backup Lambda function
resource "aws_iam_role" "backup_lambda" {
  name = "${var.name_prefix}-backup-lambda-role"

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

  tags = var.tags
}

# IAM policy for backup Lambda function
resource "aws_iam_role_policy" "backup_lambda" {
  name = "${var.name_prefix}-backup-lambda-policy"
  role = aws_iam_role.backup_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "neptune:DescribeDBClusters",
          "neptune:DescribeDBInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "es:ESHttpGet",
          "es:ESHttpPost",
          "es:ESHttpPut",
          "es:ESHttpDelete"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.opensearch_snapshots.arn,
          "${aws_s3_bucket.opensearch_snapshots.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

# CloudWatch log group for backup Lambda
resource "aws_cloudwatch_log_group" "backup_lambda" {
  name              = "/aws/lambda/${var.name_prefix}-backup-manager"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# Lambda function for backup management
resource "aws_lambda_function" "backup_manager" {
  filename         = data.archive_file.backup_lambda.output_path
  function_name    = "${var.name_prefix}-backup-manager"
  role            = aws_iam_role.backup_lambda.arn
  handler         = "backup_manager.lambda_handler"
  source_code_hash = data.archive_file.backup_lambda.output_base64sha256
  runtime         = "python3.9"
  timeout         = 900 # 15 minutes

  environment {
    variables = {
      PROJECT_NAME           = var.project_name
      ENVIRONMENT           = var.environment
      REGION                = var.aws_region
      SNAPSHOT_BUCKET       = aws_s3_bucket.opensearch_snapshots.bucket
      BACKUP_RETENTION_DAYS = var.backup_retention_days
    }
  }

  depends_on = [
    aws_iam_role_policy.backup_lambda,
    aws_cloudwatch_log_group.backup_lambda
  ]

  tags = var.tags
}

# Archive file for backup Lambda function
data "archive_file" "backup_lambda" {
  type        = "zip"
  output_path = "/tmp/backup_manager.zip"
  source {
    content = templatefile("${path.module}/backup_manager.py", {
      project_name           = var.project_name
      environment           = var.environment
      aws_region            = var.aws_region
      snapshot_bucket       = aws_s3_bucket.opensearch_snapshots.bucket
      backup_retention_days = var.backup_retention_days
    })
    filename = "backup_manager.py"
  }
}

# CloudWatch Event Rule for backup schedule
resource "aws_cloudwatch_event_rule" "backup_schedule" {
  name                = "${var.name_prefix}-backup-schedule"
  description         = "Trigger backup management function daily"
  schedule_expression = "cron(0 3 * * ? *)" # Daily at 3 AM UTC

  tags = var.tags
}

# CloudWatch Event Target for backup Lambda
resource "aws_cloudwatch_event_target" "backup_lambda" {
  rule      = aws_cloudwatch_event_rule.backup_schedule.name
  target_id = "BackupLambdaTarget"
  arn       = aws_lambda_function.backup_manager.arn
}

# Lambda permission for CloudWatch Events
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backup_manager.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.backup_schedule.arn
}

# CloudWatch Alarm for backup failures
resource "aws_cloudwatch_metric_alarm" "backup_failures" {
  alarm_name          = "${var.name_prefix}-backup-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "BackupErrors"
  namespace           = "Custom/Backup"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors backup job failures"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  dimensions = {
    Project     = var.project_name
    Environment = var.environment
  }

  tags = var.tags
}

# CloudWatch Alarm for backup success
resource "aws_cloudwatch_metric_alarm" "backup_success" {
  alarm_name          = "${var.name_prefix}-backup-success"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "BackupSuccess"
  namespace           = "Custom/Backup"
  period              = "86400" # 24 hours
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "This metric monitors backup job success"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  dimensions = {
    Project     = var.project_name
    Environment = var.environment
  }

  tags = var.tags
}

# CloudWatch Dashboard for backup monitoring
resource "aws_cloudwatch_dashboard" "backup_monitoring" {
  dashboard_name = "${var.name_prefix}-backup-monitoring"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["Custom/Backup", "BackupSuccess", "Project", var.project_name, "Environment", var.environment],
            [".", "BackupErrors", ".", ".", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Backup Job Status"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/S3", "BucketSizeBytes", "BucketName", aws_s3_bucket.opensearch_snapshots.bucket, "StorageType", "StandardStorage"]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Backup Storage Utilization"
          period  = 86400
        }
      }
    ]
  })
}

# SSM Parameter for disaster recovery procedures
resource "aws_ssm_parameter" "disaster_recovery_procedures" {
  name  = "/${var.project_name}-${var.environment}/disaster-recovery/procedures"
  type  = "String"
  value = jsonencode({
    rto_target = "4 hours"
    rpo_target = "1 hour"
    
    neptune_recovery = {
      description = "Neptune point-in-time recovery procedures"
      steps = [
        "1. Identify the target recovery time within the backup retention period",
        "2. Create a new Neptune cluster from point-in-time recovery",
        "3. Update application configuration to use new cluster endpoint",
        "4. Verify data integrity and application functionality",
        "5. Update DNS records if using custom domain"
      ]
      cli_example = "aws neptune restore-db-cluster-to-point-in-time --db-cluster-identifier recovery-cluster --source-db-cluster-identifier original-cluster --restore-to-time 2024-01-01T12:00:00Z"
    }
    
    opensearch_recovery = {
      description = "OpenSearch snapshot restoration procedures"
      steps = [
        "1. List available snapshots in the snapshot repository",
        "2. Create a new OpenSearch domain or use existing domain",
        "3. Register the snapshot repository with the domain",
        "4. Restore indices from the selected snapshot",
        "5. Verify index integrity and search functionality",
        "6. Update application configuration with new domain endpoint"
      ]
      cli_examples = [
        "aws es list-domain-names",
        "aws es describe-elasticsearch-domain --domain-name recovery-domain"
      ]
    }
    
    application_recovery = {
      description = "Application recovery procedures"
      steps = [
        "1. Deploy ECS service with previous task definition",
        "2. Restore configuration from AWS Secrets Manager",
        "3. Update database connection strings",
        "4. Verify application health checks",
        "5. Update load balancer target groups",
        "6. Test end-to-end functionality"
      ]
    }
    
    cross_region_recovery = {
      description = "Cross-region disaster recovery procedures"
      steps = [
        "1. Provision infrastructure in backup region using Terraform",
        "2. Restore databases from replicated backups",
        "3. Deploy application in backup region",
        "4. Update DNS records for failover",
        "5. Verify functionality in backup region",
        "6. Communicate status to stakeholders"
      ]
    }
    
    testing_procedures = {
      monthly_dr_tests = "Conduct monthly disaster recovery tests in non-production environment"
      backup_validation = "Weekly backup integrity checks and restoration tests"
      recovery_testing = "Quarterly full recovery process testing"
      documentation_updates = "Continuous improvement of recovery procedures based on test results"
    }
  })

  description = "Comprehensive disaster recovery procedures and documentation"
  tags        = var.tags
}