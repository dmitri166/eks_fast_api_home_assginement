# =============================================================================
# Makefile — Developer Shortcuts
# =============================================================================
# Usage: make <target>
# =============================================================================

.PHONY: help test lint format build run clean helm-lint helm-template tf-validate

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
test: ## Run unit tests with coverage
	cd app && pip install -r requirements.txt pytest pytest-cov httpx -q && \
	pytest tests/ -v --cov=. --cov-report=term-missing

lint: ## Lint Python code
	cd app && pip install ruff -q && ruff check . && ruff format --check .

format: ## Format Python code
	cd app && pip install ruff -q && ruff format .

build: ## Build Docker image
	cd app && docker build -t fastapi-app:local .

run: build ## Build and run locally
	docker run --rm -p 8080:8000 --name fastapi-app fastapi-app:local

clean: ## Stop and remove running container
	docker stop fastapi-app 2>/dev/null || true

# ---------------------------------------------------------------------------
# Helm
# ---------------------------------------------------------------------------
helm-lint: ## Lint Helm chart
	helm lint helm/fastapi-app/

helm-template: ## Render Helm templates
	helm template test-release helm/fastapi-app/

# ---------------------------------------------------------------------------
# Terraform
# ---------------------------------------------------------------------------
tf-init: ## Initialize Terraform
	cd terraform && terraform init

tf-validate: tf-init ## Validate Terraform configuration
	cd terraform && terraform validate

tf-plan: tf-init ## Run Terraform plan (dry-run)
	cd terraform && terraform plan -var-file=environments/dev/dev.tfvars

# ---------------------------------------------------------------------------
# All
# ---------------------------------------------------------------------------
ci: lint test build helm-lint tf-validate ## Run full CI locally
