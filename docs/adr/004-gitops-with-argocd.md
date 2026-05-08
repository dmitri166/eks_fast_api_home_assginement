# ADR-004: GitOps with ArgoCD

## Status
Accepted

## Context
We need a deployment strategy for the FastAPI service. Options:
1. **CI-driven deploy**: GitHub Actions directly applies Helm charts via `helm upgrade`
2. **GitOps**: A controller (ArgoCD/Flux) watches Git and reconciles cluster state

## Decision
Use **ArgoCD** for GitOps-based deployments.

## Rationale
- **Git as source of truth**: The desired cluster state is always in Git — auditable, reviewable, and recoverable
- **Self-healing**: If someone manually modifies a resource, ArgoCD reverts it to match Git state
- **Drift detection**: ArgoCD UI shows real-time diff between desired and actual state
- **Separation of concerns**: CI builds and tests; CD (ArgoCD) deploys. No kubectl/helm credentials in CI
- **Rollback**: Revert a deployment by reverting a Git commit — no cluster access needed
- **3-person team fit**: ArgoCD's UI provides visibility without requiring deep kubectl expertise from everyone

## Implementation
- `gitops/argocd/application.yaml` — ArgoCD Application with auto-sync + self-heal
- `gitops/argocd/project.yaml` — AppProject with least-privilege (restricted namespaces and resource types)
- CI pipeline updates the image tag → ArgoCD detects the change → auto-deploys

## HPA Compatibility
The Application spec includes `ignoreDifferences` for `/spec/replicas` on Deployments, preventing ArgoCD from fighting with the HPA over replica count.

## Consequences
- ArgoCD is an additional component to install and maintain
- Team must understand the GitOps workflow (no more `kubectl apply` in prod)
- Image updates require either ArgoCD Image Updater or tag updates in Git

## Alternatives Considered
- **Flux**: Excellent choice, slightly less UI-focused. ArgoCD chosen for its visual diff and team familiarity
- **Direct Helm deploy from CI**: Simpler but loses self-heal, drift detection, and audit trail
