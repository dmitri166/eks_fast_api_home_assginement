# =============================================================================
# Dev Environment — Terraform Variables
# =============================================================================
# This demonstrates the multi-environment pattern.
# Each environment has its own tfvars file with appropriate values.
# =============================================================================

aws_region          = "us-east-1"
project_name        = "fastapi-app"
environment         = "dev"
vpc_cidr            = "10.0.0.0/16"
eks_cluster_version = "1.31"
node_instance_types = ["t3.medium"]
node_min_size       = 1
node_max_size       = 3
node_desired_size   = 1
