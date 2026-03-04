# Storage Module - EFS for Model Cache

# EFS File System for Model Cache
resource "aws_efs_file_system" "model_cache" {
  creation_token = "${var.name_prefix}-model-cache"
  encrypted      = true
  kms_key_id     = var.kms_key_arn

  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  lifecycle_policy {
    transition_to_primary_storage_class = "AFTER_1_ACCESS"
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-model-cache"
    Purpose = "ML Model Cache Storage"
  })
}

# EFS Mount Targets (one per AZ)
resource "aws_efs_mount_target" "model_cache" {
  count = length(var.private_subnet_ids)

  file_system_id  = aws_efs_file_system.model_cache.id
  subnet_id       = var.private_subnet_ids[count.index]
  security_groups = [var.efs_security_group_id]
}

# EFS Access Point for Model Cache
resource "aws_efs_access_point" "model_cache" {
  file_system_id = aws_efs_file_system.model_cache.id

  root_directory {
    path = "/model-cache"
    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "755"
    }
  }

  posix_user {
    gid = 1000
    uid = 1000
  }

  tags = merge(var.tags, {
    Name = "${var.name_prefix}-model-cache-access-point"
  })
}

# CloudWatch Log Group for EFS
resource "aws_cloudwatch_log_group" "efs" {
  name              = "/aws/efs/${var.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}
