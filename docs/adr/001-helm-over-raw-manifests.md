# ADR-001: Helm Over Raw Kubernetes Manifests

## Status
Accepted

## Context
We need to package the FastAPI service for Kubernetes deployment. The two main options are:
1. **Raw YAML manifests** — simple, no tooling required
2. **Helm charts** — templated, parameterized, versioned

## Decision
Use **Helm charts** as the primary deployment mechanism.

## Rationale
- **Template reuse**: Common labels, selectors, and naming conventions defined once in `_helpers.tpl`
- **Values overrides**: Different environments (dev/staging/prod) use the same chart with different `values.yaml`
- **Ecosystem**: ServiceMonitor, PrometheusRule, ExternalSecret CRDs all have established Helm patterns
- **Versioning**: Chart versions enable rollback via `helm rollback`
- **ArgoCD integration**: Native Helm support in ArgoCD with parameter overrides

## Consequences
- Team must understand Helm templating syntax (Go templates)
- Debugging requires `helm template` to inspect rendered output
- Chart testing adds a CI stage (`helm lint`, `helm template`)

## Alternatives Considered
- **Kustomize**: Excellent for overlays but less flexible for complex templating (e.g., conditional resources like ExternalSecret)
- **Raw YAML + envsubst**: Simple but error-prone and doesn't scale
