# Runbook: Emergency Deployment Rollback (RB-04)

## Overview

Automated deployment rollback when a regression is detected with high confidence.

## Preconditions

- Deployment regression detected
- Rollback target available (previous version)
- Confidence ≥ 85%
- Blast radius is low or medium

## Authorization Requirements

- Minimum autonomy level: 4
- Human approval required unless all conditions met:
  - Confidence ≥ 90%
  - Blast radius = low
  - All dependencies healthy
  - Verification available
  - Runbook is reversible

## Execution Steps

1. **Snapshot Current State**
   - Capture current deployment state for forensic analysis
   - Record commit SHA, environment, timestamps

2. **Execute Rollback**
   - Deploy the previous known-good version
   - Record rollback commit SHA

3. **Wait for Propagation**
   - Wait 30 seconds for rollback to propagate
   - Allow load balancers to refresh

4. **Health Check**
   - Verify service responds to health checks
   - Check 3 consecutive health checks

5. **Observe Error Rate**
   - Monitor error rate for 120 seconds
   - Compare pre/post rollback error rates

6. **Compare Metrics**
   - Verify error rate has decreased
   - Verify latency is within normal bounds

## Rollback Strategy

If the rollback itself causes issues:
- Re-deploy the rolled-back version
- Escalate to human intervention

## Verification Procedure

- Type: Health check + error rate monitoring
- Required consecutive passes: 3
- Check interval: 15 seconds
- Max verification duration: 300 seconds

## Timeout

600 seconds (10 minutes)

## Blast Radius

Medium — affects the entire service during rollback

## Audit Requirements

All actions must be recorded in the audit log with:
- WHO performed the action
- WHAT was done
- WHEN it happened
- WHY (evidence and confidence)
- Authorization chain
- Verification results
