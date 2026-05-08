# 🚨 Incident Runbook — FastAPI App

This runbook covers the most common operational scenarios for the FastAPI production service.

---

## Alert: ProcessHighErrorRate

**Severity:** Critical  
**Meaning:** `/process` endpoint error rate exceeds 1% over a 5-minute window.  
**Business Impact:** Business-critical endpoint failing — callers experience errors.

### Triage Steps

1. **Open Grafana dashboard** → FastAPI App — Production Dashboard
2. **Check error rate panel** — is it sustained or a spike?
3. **Check recent deployments** — was a new version deployed?
   ```bash
   kubectl -n fastapi-app rollout history deployment/fastapi-app
   ```
4. **Check pod health**:
   ```bash
   kubectl -n fastapi-app get pods
   kubectl -n fastapi-app describe pod <pod-name>
   kubectl -n fastapi-app logs <pod-name> --tail=100 | jq '.event'
   ```
5. **Check traces in Tempo** — search by error status to find specific failure patterns

### Resolution

| Cause | Action |
|---|---|
| Bad deployment | `kubectl -n fastapi-app rollout undo deployment/fastapi-app` or revert Git commit |
| Resource exhaustion | Check memory/CPU panels; increase limits in `values.yaml` |
| Inherent 5% failure rate | Expected behavior — discuss with product team about error handling improvements |
| Upstream dependency failure | Check egress NetworkPolicy and DNS resolution |

---

## Alert: ProcessHighLatency

**Severity:** Warning  
**Meaning:** `/process` p99 latency exceeds 400ms over 5 minutes.

### Triage Steps

1. **Check Grafana latency panels** — which percentiles are affected?
2. **Check HPA status** — are replicas at max?
   ```bash
   kubectl -n fastapi-app get hpa
   ```
3. **Check node resource pressure**:
   ```bash
   kubectl top nodes
   kubectl top pods -n fastapi-app
   ```
4. **Check traces in Tempo** — look for slow spans

### Resolution

| Cause | Action |
|---|---|
| Insufficient replicas | Increase `autoscaling.maxReplicas` in `values.yaml` |
| CPU throttling | Increase `resources.limits.cpu` |
| Node resource exhaustion | Scale node group or change instance type |

---

## Alert: AppDown

**Severity:** Critical  
**Meaning:** Zero available replicas — complete service outage.

### Triage Steps

1. **Immediately check pods**:
   ```bash
   kubectl -n fastapi-app get pods -o wide
   kubectl -n fastapi-app get events --sort-by='.lastTimestamp' | tail -20
   ```
2. **Check for scheduling failures**:
   ```bash
   kubectl -n fastapi-app describe pod <pending-pod>
   ```
3. **Check node availability**:
   ```bash
   kubectl get nodes
   ```

### Resolution

| Cause | Action |
|---|---|
| Image pull failure | Verify ECR image exists and tag is correct |
| Node group down | Check ASG in AWS console; verify EKS node group health |
| OOMKilled | Increase memory limits; check for memory leaks |
| CrashLoopBackOff | Check logs: `kubectl -n fastapi-app logs <pod> --previous` |
| PDB blocking rollout | Check PDB status: `kubectl -n fastapi-app get pdb` |

---

## Alert: PodRestartLoop

**Severity:** Warning  
**Meaning:** A pod has restarted more than 3 times in 15 minutes.

### Triage Steps

1. **Check restart reason**:
   ```bash
   kubectl -n fastapi-app describe pod <pod-name> | grep -A5 "Last State"
   ```
2. **Possible reasons**: OOMKilled, liveness probe failure, application crash

---

## Rollback Procedure

### Via ArgoCD (preferred)
```bash
# Revert the Git commit that caused the issue
git revert <commit-sha>
git push origin main
# ArgoCD auto-syncs the reverted state
```

### Via Helm (emergency)
```bash
helm -n fastapi-app rollback fastapi-app <revision>
```

### Via kubectl (last resort)
```bash
kubectl -n fastapi-app rollout undo deployment/fastapi-app
```

---

## Escalation Path

1. **L1 — On-call platform engineer**: Triage using this runbook (15 min)
2. **L2 — Platform team lead**: If not resolved, escalate with context
3. **L3 — Product team**: If the issue is in application logic (e.g., 5% inherent failure rate)

---

## Useful Commands Cheat Sheet

```bash
# Logs (structured JSON, pipe through jq)
kubectl -n fastapi-app logs -l app.kubernetes.io/name=fastapi-app --tail=50 | jq '.'

# Filter error logs only
kubectl -n fastapi-app logs -l app.kubernetes.io/name=fastapi-app --tail=100 | jq 'select(.level == "error")'

# Search by correlation ID
kubectl -n fastapi-app logs -l app.kubernetes.io/name=fastapi-app --tail=1000 | jq 'select(.request_id == "YOUR-ID")'

# HPA status
kubectl -n fastapi-app get hpa -w

# Resource usage
kubectl -n fastapi-app top pods

# ArgoCD app status
argocd app get fastapi-app
```
