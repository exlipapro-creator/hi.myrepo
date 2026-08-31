# hi.myrepo — Architecture Overview

## The Central Principle

hi.myrepo is an event-driven control plane, not a dashboard.

- The UI does not own system state.
- The database does not receive arbitrary UI mutations as the source of truth.
- AI does not own system state.

Instead:

```
APPLICATIONS
     │
     ▼
TELEMETRY / WEBHOOKS / HEARTBEATS
     │
     ▼
EVENT INGESTION
     │
     ▼
IMMUTABLE EVENT SPINE
     │
     ├──► Correlation
     ├──► Fingerprinting
     ├──► Incident State Machine
     ├──► Historical Analysis
     ├──► Policy Engine
     ├──► AI Investigation
     ├──► Runbook Engine
     ├──► Verification
     └──► Memory
             │
             ▼
       DERIVED SYSTEM STATE
             │
             ▼
       COMMAND CENTER UI
```

The interface is a projection of reality, not the reality itself.

## Operating Philosophy

The system evolves through four controlled levels:

1. **OBSERVE** — Receive events, detect failures, record incidents
2. **UNDERSTAND** — Fingerprint errors, correlate, investigate, analyze
3. **ACT** — Recommend runbooks, get approval, execute, verify
4. **AUTONOMY** — Conditional autonomy based on evidence

## Deterministic vs Probabilistic Boundary

This is one of the most important rules in the entire architecture.

### Deterministic Systems Control:
- Authentication
- Authorization
- Event validation and persistence
- Deduplication
- Fingerprints
- Incident state machine
- Policy evaluation
- Permissions
- Runbook eligibility
- Execution and rollback
- Verification
- Audit logs

### AI Controls:
- Interpretation
- Hypothesis generation
- Debugging analysis
- Correlation suggestions
- Explanation
- Prioritization
- Remediation proposals
- Postmortem generation

**AI must never directly mutate production state.**

## The Autonomy Model

| Level | Name | Description |
|-------|------|-------------|
| 0 | Observe | Receives events, detects failures, records incidents, does nothing operationally |
| 1 | Understand | Fingerprints errors, correlates events, groups duplicates, investigates patterns |
| 2 | Recommend | Proposes runbooks, calculates confidence, estimates blast radius |
| 3 | Guarded Action | Auto-executes explicitly pre-authorized low-risk runbooks |
| 4 | Conditional Autonomy | Auto-executes when ALL policy conditions are satisfied |
| 5 | Never Unrestricted | AI proposes → Policy authorizes → Runbook executes |

## Safety Rule

No action should execute merely because AI says so.

Execution requires:
1. AI recommendation
2. Deterministic evidence
3. Policy eligibility
4. Authorized runbook
5. Required approval/autonomy level
6. Verification capability
