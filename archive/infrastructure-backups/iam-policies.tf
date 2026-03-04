# IAM Policies for ECS Task Access to AWS-Native Services

# Data source for existing ECS task role
data "aws_iam_role" "ecs_task_role" {
  name = "multimodal-librarian-task-role"
}

# IAM Policy for Neptune Access
resource "aws_iam_policy" "neptune_access" {
  name        = "multimodal-librarian-neptune-access"
  description = "Policy for ECS tasks to access Neptune cluster"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "neptune-db:connect",
          "neptune-db:ReadDataViaQuery",
          "neptune-db:WriteDataViaQuery",
          "neptune-db:DeleteDataViaQuery"
        ]
        Resource = [
          aws_neptune_cluster.main.cluster_resource_id,
          "${aws_neptune_cluster.main.cluster_resource_id}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "neptune-db:GetEngineStatus",
          "neptune-db:GetQueryStatus",
          "neptune-db:ListQueries",
          "neptune-db:CancelQuery"
        ]
        Resource = aws_neptune_cluster.main.cluster_resource_id
      }
    ]
  })

  tags = {
    Name = "neptune-access-policy"
  }
}

# IAM Policy for OpenSearch Access
resource "aws_iam_policy" "opensearch_access" {
  name        = "multimodal-librarian-opensearch-access"
  description = "Policy for ECS tasks to access OpenSearch domain"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "es:ESHttpGet",
          "es:ESHttpPost",
          "es:ESHttpPut",
          "es:ESHttpDelete",
          "es:ESHttpHead"
        ]
        Resource = [
          aws_opensearch_domain.main.arn,
          "${aws_opensearch_domain.main.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "es:DescribeDomain",
          "es:DescribeDomains",
          "es:DescribeDomainConfig",
          "es:ListDomainNames",
          "es:ListTags"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name = "opensearch-access-policy"
  }
}

# IAM Policy for Secrets Manager Access
resource "aws_iam_policy" "secrets_access" {
  name        = "multimodal-librarian-aws-native-secrets-access"
  description = "Policy for ECS tasks to access AWS-Native service secrets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.neptune_endpoint.arn,
          aws_secretsmanager_secret.opensearch_endpoint.arn
        ]
      }
    ]
  })

  tags = {
    Name = "aws-native-secrets-access-policy"
  }
}

# Attach policies to existing ECS task role
resource "aws_iam_role_policy_attachment" "ecs_neptune_access" {
  role       = data.aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.neptune_access.arn
}

resource "aws_iam_role_policy_attachment" "ecs_opensearch_access" {
  role       = data.aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.opensearch_access.arn
}

resource "aws_iam_role_policy_attachment" "ecs_secrets_access" {
  role       = data.aws_iam_role.ecs_task_role.name
  policy_arn = aws_iam_policy.secrets_access.arn
}

# Output the policy ARNs for reference
output "iam_policy_arns" {
  description = "ARNs of IAM policies created for AWS-Native access"
  value = {
    neptune_access   = aws_iam_policy.neptune_access.arn
    opensearch_access = aws_iam_policy.opensearch_access.arn
    secrets_access   = aws_iam_policy.secrets_access.arn
  }
  sensitive = false
}