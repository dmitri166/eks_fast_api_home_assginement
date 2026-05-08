# ADR-003: SLO-Based Alerting Over Threshold-Based

## Status
Accepted

## Context
We need alerting for the business-critical `/process` endpoint. Two approaches:
1. **Threshold-based**: Alert when a metric crosses a static value (e.g., error count > 10)
2. **SLO-based**: Alert when service level objectives are at risk of being violated

## Decision
Use **SLO-based alerting** tied to availability and latency targets.

## Rationale
- **Actionable**: An SLO alert means "customers are impacted" — not "a number is high"
- **Reduced noise**: Threshold alerts fire on spikes that may self-resolve; SLO alerts use sustained windows (5min)
- **Business alignment**: The 1% error rate threshold directly maps to the product team's "zero tolerance" requirement
- **Error budget**: SLOs make trade-offs explicit — "we have 43.8 minutes of downtime budget this month"

## Alert Definitions

| Alert | SLO | Window | Severity |
|---|---|---|---|
| ProcessHighErrorRate | < 1% error rate | 5min | critical |
| ProcessHighLatency | p99 < 400ms | 5min | warning |
| AppDown | > 0 available replicas | 1min | critical |

## Intentional Tension
The app's inherent 5% failure rate means `ProcessHighErrorRate` will fire immediately. This is **by design** — it surfaces the reliability gap to the product team. The platform provides the observability; the product team owns the fix.

## Consequences
- Requires clear SLO definitions agreed with the product team
- Initial alert noise until the product team addresses the 5% failure rate
- Team must understand error budget concepts
