# =============================================================================
# Secrets Module — AWS Secrets Manager + IRSA for ESO
# =============================================================================

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "eks_oidc_provider" {
  description = "EKS OIDC provider ARN"
  type        = string
}

variable "eks_oidc_issuer" {
  description = "EKS OIDC issuer URL (without https://)"
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace for the service"
  type        = string
}

variable "service_account" {
  description = "Kubernetes service account name"
  type        = string
}

# ---------------------------------------------------------------------------
# KMS Key for Secrets Encryption
# ---------------------------------------------------------------------------
resource "aws_kms_key" "secrets" {
  description             = "KMS key for ${var.project_name} secrets"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-${var.environment}-secrets-kms"
  }
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.project_name}-${var.environment}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# ---------------------------------------------------------------------------
# Secrets Manager Secret (placeholder — product team populates values)
# ---------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "app" {
  name        = "${var.environment}/${var.project_name}"
  description = "Application secrets for ${var.project_name}"
  kms_key_id  = aws_kms_key.secrets.key_id

  tags = {
    Name = "${var.project_name}-${var.environment}-secrets"
  }
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    database_url = "placeholder://change-me"
    api_key      = "placeholder-change-me"
  })

  lifecycle {
    ignore_changes = [secret_string] # Don't overwrite after initial creation
  }
}

# ---------------------------------------------------------------------------
# IAM Role for ESO Service Account (IRSA)
# ---------------------------------------------------------------------------
resource "aws_iam_role" "eso" {
  name = "${var.project_name}-${var.environment}-eso-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = var.eks_oidc_provider
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${var.eks_oidc_issuer}:sub" = "system:serviceaccount:${var.namespace}:${var.service_account}"
          "${var.eks_oidc_issuer}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "eso_secrets_access" {
  name = "secrets-access"
  role = aws_iam_role.eso.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = aws_secretsmanager_secret.app.arn
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = aws_kms_key.secrets.arn
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
output "secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "role_arn" {
  description = "IAM role ARN to annotate the K8s service account with"
  value       = aws_iam_role.eso.arn
}

output "kms_key_arn" {
  value = aws_kms_key.secrets.arn
}
