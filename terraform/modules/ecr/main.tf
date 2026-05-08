# =============================================================================
# ECR Module — Container Registry
# =============================================================================

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

# ---------------------------------------------------------------------------
# ECR Repository
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "main" {
  name                 = "${var.project_name}"
  image_tag_mutability = "IMMUTABLE"  # Enforce immutable tags for reproducibility

  image_scanning_configuration {
    scan_on_push = true  # Scan images for vulnerabilities on every push
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-ecr"
  }
}

# ---------------------------------------------------------------------------
# Lifecycle Policy — Keep last 10 tagged images, expire untagged after 1 day
# ---------------------------------------------------------------------------
resource "aws_ecr_lifecycle_policy" "main" {
  repository = aws_ecr_repository.main.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only last 10 tagged images"
        selection = {
          tagStatus   = "tagged"
          tagPrefixList = ["v"]
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
output "repository_url" {
  value = aws_ecr_repository.main.repository_url
}

output "repository_arn" {
  value = aws_ecr_repository.main.arn
}
