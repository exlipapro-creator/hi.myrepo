"""
hi.myrepo - Policy Engine

The actual authority layer. AI proposes. Policy authorizes. Runbook executes.
No action should execute merely because AI says so.
"""

import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Incident, Policy, Runbook


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicyContext(BaseModel):
    """Context for evaluating a policy decision."""
    incident_id: Optional[uuid.UUID] = None
    incident: Optional[dict] = None  # Serialized incident data
    runbook: Optional[dict] = None  # Serialized runbook data
    deployment: Optional[dict] = None  # Recent deployment data
    dependencies: Optional[list[dict]] = None  # Dependency health data
    verification_available: bool = False
    autonomy_level: int = 0
    user_role: str = "viewer"
    is_autonomous: bool = False


class PolicyEvaluation(BaseModel):
    """Result of a policy evaluation."""
    decision: PolicyDecision
    policy_id: Optional[uuid.UUID] = None
    policy_name: Optional[str] = None
    reason: str = ""
    conditions_met: dict = Field(default_factory=dict)
    conditions_failed: dict = Field(default_factory=dict)


class PolicyEngine:
    """
    Deterministic policy evaluation.
    No randomness, no AI — pure rule evaluation.

    Example:
        IF incident.confidence >= 0.90
        AND blast_radius == LOW
        AND runbook.reversible == TRUE
        AND deployment.regression == TRUE
        AND dependencies.healthy == TRUE
        AND verification.available == TRUE
        AND autonomy_level >= required_level
        THEN eligible_for_execution
        Otherwise: human approval required
    """

    async def evaluate(
        self,
        context: PolicyContext,
        resource_type: str,  # "runbook", "incident", "autonomy"
        session: AsyncSession,
    ) -> PolicyEvaluation:
        """
        Evaluate all active policies against the context.
        Returns the most restrictive decision.
        """
        # Fetch active policies for this resource type, ordered by priority (descending)
        result = await session.execute(
            select(Policy)
            .where(Policy.is_active == True)
            .where(Policy.target_resource == resource_type)
            .order_by(Policy.priority.desc())
        )
        policies = list(result.scalars().all())

        if not policies:
            # No policies configured — default to requiring approval
            return PolicyEvaluation(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                reason="No policies configured for this resource type",
            )

        # Evaluate each policy — first match wins
        for policy in policies:
            evaluation = self._evaluate_single(policy, context)
            if evaluation.decision != PolicyDecision.REQUIRE_APPROVAL:
                evaluation.policy_id = policy.id
                evaluation.policy_name = policy.name
                return evaluation

        # Default: require approval
        return PolicyEvaluation(
            decision=PolicyDecision.REQUIRE_APPROVAL,
            reason="No policy explicitly authorized this action",
        )

    def _evaluate_single(
        self, policy: Policy, context: PolicyContext
    ) -> PolicyEvaluation:
        """Evaluate a single policy against the context."""
        conditions = policy.conditions or {}
        met = {}
        failed = {}

        for condition_key, condition_value in conditions.items():
            actual = self._get_condition_value(condition_key, context)
            if self._check_condition(actual, condition_key, condition_value):
                met[condition_key] = True
            else:
                failed[condition_key] = {
                    "expected": condition_value,
                    "actual": actual,
                }

        # All conditions met → policy action
        if not failed:
            decision = PolicyDecision(policy.action)
            return PolicyEvaluation(
                decision=decision,
                reason=f"Policy '{policy.name}' conditions all met",
                conditions_met=met,
            )

        # Some conditions failed → deny or require approval
        return PolicyEvaluation(
            decision=PolicyDecision.DENY if policy.action == "allow" else PolicyDecision.REQUIRE_APPROVAL,
            reason=f"Policy '{policy.name}' conditions not fully met",
            conditions_met=met,
            conditions_failed=failed,
        )

    def _get_condition_value(self, key: str, context: PolicyContext) -> Any:
        """Extract a value from the context by condition key."""
        if context.incident:
            if key in context.incident:
                return context.incident[key]
        if context.runbook:
            if key in context.runbook:
                return context.runbook[key]
        if context.deployment:
            if key in context.deployment:
                return context.deployment[key]

        # Direct context fields
        mapping = {
            "autonomy_level": context.autonomy_level,
            "verification_available": context.verification_available,
            "is_autonomous": context.is_autonomous,
            "user_role": context.user_role,
        }
        return mapping.get(key)

    def _check_condition(self, actual: Any, key: str, expected: Any) -> bool:
        """Check if an actual value satisfies an expected condition."""
        if actual is None:
            return False

        if isinstance(expected, dict):
            op = expected.get("op", "eq")
            value = expected.get("value")
            return self._compare(actual, op, value)
        elif isinstance(expected, bool):
            return bool(actual) == expected
        else:
            return actual == expected

    def _compare(self, actual: Any, op: str, expected: Any) -> bool:
        """Compare values using an operator."""
        try:
            if op == "eq":
                return actual == expected
            elif op == "neq":
                return actual != expected
            elif op == "gte":
                return float(actual) >= float(expected)
            elif op == "lte":
                return float(actual) <= float(expected)
            elif op == "gt":
                return float(actual) > float(expected)
            elif op == "lt":
                return float(actual) < float(expected)
            elif op == "in":
                return actual in expected
            elif op == "not_in":
                return actual not in expected
            elif op == "contains":
                return expected in str(actual)
        except (ValueError, TypeError):
            return False
        return False


# Global policy engine singleton
policy_engine = PolicyEngine()
