# Databases Module - Neptune and OpenSearch with production configuration

# Neptune Subnet Group
resource "aws_neptune_subnet_group" "main" {
  name       = "${var.name_prefix}-neptune-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-neptune-subnet-group"
  })
}

# Neptune Parameter Group
resource "aws_neptune_parameter_group" "main" {
  family = "neptune1.3"
  name   = "${var.name_prefix}-neptune-params"

  parameter {
    name  = "neptune_query_timeout"
    value = "120000"
  }

  tags = var.tags
}

# Neptune Cluster
resource "aws_neptune_cluster" "main" {
  cluster_identifier           = "${var.name_prefix}-neptune"
  engine                       = "neptune"
  engine_version               = "1.3.2.1"
  backup_retention_period      = var.backup_retention_period
  preferred_backup_window      = var.neptune_backup_window
  preferred_maintenance_window = "sun:05:00-sun:06:00"
  skip_final_snapshot          = false
  final_snapshot_identifier    = "${var.name_prefix}-neptune-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"

  vpc_security_group_ids               = var.security_group_ids
  neptune_subnet_group_name            = aws_neptune_subnet_group.main.name

  storage_encrypted = true

  enable_cloudwatch_logs_exports = ["audit"]

  apply_immediately = false

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-neptune-cluster"
  })

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}

# Neptune Cluster Instances
resource "aws_neptune_cluster_instance" "main" {
  count = var.neptune_instance_count

  cluster_identifier = aws_neptune_cluster.main.id
  engine             = "neptune"
  instance_class     = var.neptune_instance_type

  auto_minor_version_upgrade = true

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-neptune-instance-${count.index + 1}"
  })
}

# IAM Role for Neptune Enhanced Monitoring
resource "aws_iam_role" "neptune_monitoring" {
  name = "${var.name_prefix}-neptune-monitoring-role"

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

  tags = var.tags
}

# IAM Role Policy Attachment for Neptune Monitoring
resource "aws_iam_role_policy_attachment" "neptune_monitoring" {
  role       = aws_iam_role.neptune_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# CloudWatch Log Group for Neptune Audit Logs
resource "aws_cloudwatch_log_group" "neptune_audit" {
  name              = "/aws/neptune/${var.name_prefix}/audit"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# OpenSearch Domain
resource "aws_opensearch_domain" "main" {
  domain_name    = "${var.name_prefix}-search"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type            = var.opensearch_instance_type
    instance_count           = var.opensearch_instance_count
    dedicated_master_enabled = var.opensearch_instance_count >= 3
    dedicated_master_type    = var.opensearch_instance_count >= 3 ? "t3.small.search" : null
    dedicated_master_count   = var.opensearch_instance_count >= 3 ? 3 : null
    zone_awareness_enabled   = var.opensearch_instance_count > 1

    dynamic "zone_awareness_config" {
      for_each = var.opensearch_instance_count > 1 ? [1] : []
      content {
        availability_zone_count = min(var.opensearch_instance_count, length(var.availability_zones))
      }
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.opensearch_volume_size
    throughput  = 125
    iops        = 3000
  }

  vpc_options {
    security_group_ids = var.security_group_ids
    subnet_ids         = slice(var.private_subnet_ids, 0, min(var.opensearch_instance_count, length(var.private_subnet_ids)))
  }

  encrypt_at_rest {
    enabled    = true
    kms_key_id = var.kms_key_arn
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  advanced_security_options {
    enabled                        = true
    anonymous_auth_enabled         = false
    internal_user_database_enabled = true

    master_user_options {
      master_user_name     = var.opensearch_master_user
      master_user_password = var.opensearch_master_password
    }
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_search_slow.arn
    log_type                 = "SEARCH_SLOW_LOGS"
    enabled                  = true
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_index_slow.arn
    log_type                 = "INDEX_SLOW_LOGS"
    enabled                  = true
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_es_application.arn
    log_type                 = "ES_APPLICATION_LOGS"
    enabled                  = true
  }

  auto_tune_options {
    desired_state       = "DISABLED"
    rollback_on_disable = "NO_ROLLBACK"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-search"
  })

  depends_on = [
    aws_cloudwatch_log_resource_policy.opensearch_search_slow,
    aws_cloudwatch_log_resource_policy.opensearch_index_slow,
    aws_cloudwatch_log_resource_policy.opensearch_es_application
  ]
}

# CloudWatch Log Groups for OpenSearch
resource "aws_cloudwatch_log_group" "opensearch_search_slow" {
  name              = "/aws/opensearch/domains/${var.name_prefix}-search/search-slow-logs"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "opensearch_index_slow" {
  name              = "/aws/opensearch/domains/${var.name_prefix}-search/index-slow-logs"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "opensearch_es_application" {
  name              = "/aws/opensearch/domains/${var.name_prefix}-search/es-application-logs"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# CloudWatch Log Resource Policies for OpenSearch
resource "aws_cloudwatch_log_resource_policy" "opensearch_search_slow" {
  policy_name = "${var.name_prefix}-opensearch-search-slow-logs-policy"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "es.amazonaws.com"
        }
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogGroup",
          "logs:CreateLogStream"
        ]
        Resource = "${aws_cloudwatch_log_group.opensearch_search_slow.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_resource_policy" "opensearch_index_slow" {
  policy_name = "${var.name_prefix}-opensearch-index-slow-logs-policy"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "es.amazonaws.com"
        }
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogGroup",
          "logs:CreateLogStream"
        ]
        Resource = "${aws_cloudwatch_log_group.opensearch_index_slow.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_resource_policy" "opensearch_es_application" {
  policy_name = "${var.name_prefix}-opensearch-es-application-logs-policy"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "es.amazonaws.com"
        }
        Action = [
          "logs:PutLogEvents",
          "logs:CreateLogGroup",
          "logs:CreateLogStream"
        ]
        Resource = "${aws_cloudwatch_log_group.opensearch_es_application.arn}:*"
      }
    ]
  })
}

# IAM Service Linked Role for OpenSearch (conditional - may already exist)
resource "aws_iam_service_linked_role" "opensearch" {
  count = 0 # Disabled since it likely already exists

  aws_service_name = "es.amazonaws.com"
  description      = "Service linked role for OpenSearch"

  tags = var.tags
}

# S3 Bucket for OpenSearch Snapshots
resource "aws_s3_bucket" "opensearch_snapshots" {
  bucket        = "${var.name_prefix}-search-snapshots-${var.random_suffix}"
  force_destroy = false

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-search-snapshots"
  })
}

# S3 Bucket Versioning for OpenSearch Snapshots
resource "aws_s3_bucket_versioning" "opensearch_snapshots" {
  bucket = aws_s3_bucket.opensearch_snapshots.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Bucket Encryption for OpenSearch Snapshots
resource "aws_s3_bucket_server_side_encryption_configuration" "opensearch_snapshots" {
  bucket = aws_s3_bucket.opensearch_snapshots.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# S3 Bucket Public Access Block for OpenSearch Snapshots
resource "aws_s3_bucket_public_access_block" "opensearch_snapshots" {
  bucket = aws_s3_bucket.opensearch_snapshots.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# IAM Role for OpenSearch Snapshot Access
resource "aws_iam_role" "opensearch_snapshot" {
  name = "${var.name_prefix}-search-snapshot-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "opensearch.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# IAM Policy for OpenSearch Snapshot Access
resource "aws_iam_role_policy" "opensearch_snapshot" {
  name = "${var.name_prefix}-search-snapshot-policy"
  role = aws_iam_role.opensearch_snapshot.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:ListBucketMultipartUploads",
          "s3:ListBucketVersions"
        ]
        Resource = aws_s3_bucket.opensearch_snapshots.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts"
        ]
        Resource = "${aws_s3_bucket.opensearch_snapshots.arn}/*"
      }
    ]
  })
}