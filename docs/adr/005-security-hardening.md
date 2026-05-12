# ADR 005: Security-First Application Hardening

## Status
Accepted

## Context
A production EKS environment is exposed to various threats. We need a "Defense in Depth" strategy that protects the application even if one layer (like the Ingress) is compromised.

## Decisions

### 1. Non-Root Containers
We use a dedicated `appuser` (UID 1000) instead of the default `root`. This prevents attackers from gaining root access to the underlying node if they escape the container.

### 2. Read-Only Root Filesystem
We set `readOnlyRootFilesystem: true` in the Kubernetes SecurityContext and the Dockerfile. We mount a dedicated `emptyDir` on `/tmp` for legitimate temporary writes. 
**Why**: This significantly reduces the attack surface by preventing malware from being downloaded or persisted on the container's disk.

### 3. Capability Dropping
We use `capabilities.drop: [ALL]`. 
**Why**: Linux capabilities provide granular root powers. Dropping all of them ensures the container cannot perform privileged operations (like changing network settings or mounting disks).

### 4. IRSA (IAM Roles for Service Accounts)
We use OIDC-based identity (IRSA) for AWS API access (e.g., getting secrets).
**Why**: This eliminates the need for static `AWS_ACCESS_KEY_ID` secrets in Git, which are a major security risk.

### 5. Network Segmentation
We use `NetworkPolicy` to restrict traffic. The app only accepts traffic from the Ingress and Monitoring namespaces.

## Consequences
- Slightly higher configuration complexity (need to handle `/tmp` and IRSA).
- Minimal performance impact.
- Significantly higher security posture that satisfies "Hardened" production requirements.
