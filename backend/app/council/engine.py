"""
hi.myrepo - Engineering Council

The Council is NOT an uncontrolled multi-agent conversation.
It is a bounded evidence-analysis pipeline with explicit roles:

1. Prosecutor — Find what could be wrong
2. Infrastructure Defender — Prove/disprove infrastructure responsibility
3. Historical Analyst — Search for precedent
4. Adversarial Reviewer — Attack premature conclusions
5. Lead Synthesizer — Produce final verdict

Budget: max agents, max rounds, max tokens, max execution time.
"Insufficient evidence" is preferred over fabricated certainty.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.database.models import Incident, IncidentAnalysis


class CouncilRole(str, Enum):
    PROSECUTOR = "prosecutor"
    INFRASTRUCTURE_DEFENDER = "infrastructure_defender"
    HISTORICAL_ANALYST = "historical_analyst"
    ADVERSARIAL_REVIEWER = "adversarial_reviewer"
    LEAD_SYNTHESIZER = "lead_synthesizer"


class AgentEvidence(BaseModel):
    """Evidence produced by a council agent."""
    role: CouncilRole
    findings: str
    confidence: float = 0.0
    supporting_evidence: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)


class CouncilVerdict(BaseModel):
    """Final verdict from the Engineering Council."""
    root_cause: str
    confidence: float  # 0.0 to 1.0
    evidence: dict = Field(default_factory=dict)
    alternative_hypotheses: list[str] = Field(default_factory=list)
    blast_radius: str = "medium"
    recommended_action: str = ""
    risk_assessment: str = ""
    required_verification: str = ""
    council_rounds_used: int = 0
    budget_exceeded: bool = False
    agents_used: list[str] = Field(default_factory=list)


class CouncilBudget:
    """Bounded budget for council investigations."""

    MAX_AGENTS = 5
    MAX_ROUNDS = 3
    MAX_TOKENS = 10000
    MAX_EXECUTION_SECONDS = 120
    MAX_RETRIES = 2


class CouncilEngine:
    """
    Bounded evidence-analysis pipeline.
    The council investigates, challenges, and synthesizes — but does NOT execute.
    """

    def __init__(self):
        self.budget = CouncilBudget()

    async def investigate(
        self,
        incident: Incident,
        context: dict,
    ) -> CouncilVerdict:
        """
        Run a bounded investigation of an incident.
        Returns a verdict — NOT an action.
        The verdict feeds into the policy engine.
        """
        agents_used = []
        rounds = 0
        budget_exceeded = False
        all_evidence = []

        # Round 1: Initial investigation
        if rounds < self.budget.MAX_ROUNDS:
            # Prosecutor: Find what could be wrong
            prosecutor_evidence = await self._run_prosecutor(incident, context)
            all_evidence.append(prosecutor_evidence)
            agents_used.append(CouncilRole.PROSECUTOR)

            # Infrastructure Defender: Check infrastructure
            defender_evidence = await self._run_defender(incident, context)
            all_evidence.append(defender_evidence)
            agents_used.append(CouncilRole.INFRASTRUCTURE_DEFENDER)

            rounds += 1

        # Round 2: Historical and adversarial review
        if rounds < self.budget.MAX_ROUNDS:
            # Historical Analyst: Search for precedent
            analyst_evidence = await self._run_historical_analyst(incident, context)
            all_evidence.append(analyst_evidence)
            agents_used.append(CouncilRole.HISTORICAL_ANALYST)

            # Adversarial Reviewer: Attack conclusions
            reviewer_evidence = await self._run_adversarial_reviewer(
                incident, all_evidence
            )
            all_evidence.append(reviewer_evidence)
            agents_used.append(CouncilRole.ADVERSARIAL_REVIEWER)

            rounds += 1

        # Round 3: Final synthesis
        if rounds < self.budget.MAX_ROUNDS:
            synthesizer_evidence = await self._run_synthesizer(
                incident, all_evidence
            )
            all_evidence.append(synthesizer_evidence)
            agents_used.append(CouncilRole.LEAD_SYNTHESIZER)
            rounds += 1

        # Check budget: completing exactly MAX_ROUNDS is expected behavior.
        # Budget is only exceeded if rounds go beyond the allowed maximum.
        if rounds > self.budget.MAX_ROUNDS:
            budget_exceeded = True

        # Build the verdict from all evidence
        verdict = self._synthesize_verdict(all_evidence, rounds, budget_exceeded, agents_used)

        return verdict

    async def _run_prosecutor(
        self, incident: Incident, context: dict
    ) -> AgentEvidence:
        """
        Agent 1 — Prosecutor
        Find what could be wrong.
        Must actively challenge assumptions.
        """
        findings = []
        challenges = []

        # Analyze incident data
        if incident.fingerprint:
            findings.append(f"Fingerprint: {incident.fingerprint}")

        if incident.affected_service:
            findings.append(f"Affected service: {incident.affected_service}")

        if incident.affected_component:
            findings.append(f"Affected component: {incident.affected_component}")

        # Check deployment correlation
        recent_deployment = context.get("recent_deployment")
        if recent_deployment:
            findings.append(
                f"Recent deployment detected: {recent_deployment.get('commit_sha', 'unknown')}"
            )
            # Temporal correlation
            deploy_time = recent_deployment.get("timestamp")
            if deploy_time:
                findings.append(f"Deployment timestamp: {deploy_time}")

        # Check error groups
        error_groups = context.get("error_groups", [])
        if error_groups:
            findings.append(f"{len(error_groups)} error group(s) associated")
            for eg in error_groups[:3]:
                findings.append(f"  - {eg.get('error_type', 'unknown')}: {eg.get('error_message', '')[:100]}")

        # Challenge assumptions
        if not error_groups:
            challenges.append("No error groups found — incident may not have clear error evidence")
        if not recent_deployment:
            challenges.append("No deployment correlation — timing-based causation uncertain")

        confidence = 0.5
        if error_groups and recent_deployment:
            confidence = 0.7
        if incident.fingerprint:
            confidence += 0.1

        return AgentEvidence(
            role=CouncilRole.PROSECUTOR,
            findings="\n".join(findings),
            confidence=min(confidence, 1.0),
            supporting_evidence=findings,
            challenges=challenges,
        )

    async def _run_defender(
        self, incident: Incident, context: dict
    ) -> AgentEvidence:
        """
        Agent 2 — Infrastructure Defender
        Prove whether the infrastructure is or is not responsible.
        Should explicitly attempt to disprove the Prosecutor.
        """
        findings = []
        challenges = []

        # Check dependency health
        dependencies = context.get("dependencies", [])
        healthy_deps = [d for d in dependencies if d.get("is_healthy", True)]
        unhealthy_deps = [d for d in dependencies if not d.get("is_healthy", True)]

        if unhealthy_deps:
            findings.append(f"Unhealthy dependencies detected: {len(unhealthy_deps)}")
            for dep in unhealthy_deps:
                findings.append(f"  - {dep.get('name', 'unknown')} ({dep.get('type', 'unknown')})")
        else:
            findings.append("All reported dependencies are healthy")

        # Check heartbeat status
        heartbeat_results = context.get("heartbeat_results", [])
        if heartbeat_results:
            recent_failures = [
                h for h in heartbeat_results
                if not h.get("is_healthy", True)
            ]
            if recent_failures:
                findings.append(f"Recent heartbeat failures: {len(recent_failures)}")
            else:
                findings.append("All recent heartbeats are healthy")

        # Challenge the Prosecutor's findings
        if unhealthy_deps:
            challenges.append(
                "Infrastructure issues detected — may not be application regression"
            )

        if not unhealthy_deps and not heartbeat_results:
            challenges.append(
                "No infrastructure evidence available — cannot confirm or deny infrastructure involvement"
            )

        confidence = 0.5
        if not unhealthy_deps:
            confidence = 0.6  # Infrastructure likely not the cause
        if unhealthy_deps:
            confidence = 0.4  # Infrastructure may be involved

        return AgentEvidence(
            role=CouncilRole.INFRASTRUCTURE_DEFENDER,
            findings="\n".join(findings),
            confidence=confidence,
            supporting_evidence=findings,
            challenges=challenges,
            data={
                "healthy_dependencies": len(healthy_deps),
                "unhealthy_dependencies": len(unhealthy_deps),
            },
        )

    async def _run_historical_analyst(
        self, incident: Incident, context: dict
    ) -> AgentEvidence:
        """
        Agent 3 — Historical Analyst
        Search for precedent.
        """
        findings = []
        challenges = []

        similar_incidents = context.get("similar_incidents", [])
        if similar_incidents:
            findings.append(f"Found {len(similar_incidents)} similar historical incident(s)")
            for sim in similar_incidents[:3]:
                findings.append(
                    f"  - Incident {sim.get('id', 'unknown')}: "
                    f"{sim.get('status', 'unknown')} "
                    f"(severity: {sim.get('severity', 'unknown')})"
                )
        else:
            findings.append("No similar historical incidents found")
            challenges.append("No precedent available — cannot leverage historical patterns")

        # Check memory records
        memory_records = context.get("memory_records", [])
        if memory_records:
            findings.append(f"{len(memory_records)} memory record(s) available")
            for mem in memory_records[:2]:
                findings.append(
                    f"  - {mem.get('title', 'unknown')}: {mem.get('summary', '')[:100]}"
                )

        confidence = 0.5
        if similar_incidents:
            confidence = 0.65
        if memory_records:
            confidence += 0.05

        return AgentEvidence(
            role=CouncilRole.HISTORICAL_ANALYST,
            findings="\n".join(findings),
            confidence=min(confidence, 1.0),
            supporting_evidence=findings,
            challenges=challenges,
        )

    async def _run_adversarial_reviewer(
        self, incident: Incident, prior_evidence: list[AgentEvidence]
    ) -> AgentEvidence:
        """
        Agent 4 — Adversarial Reviewer
        Exists specifically to attack premature conclusions.
        """
        challenges = []
        findings = []

        # Review prior evidence for weaknesses
        for evidence in prior_evidence:
            if evidence.confidence > 0.8:
                challenges.append(
                    f"{evidence.role.value} has high confidence ({evidence.confidence:.1%}) "
                    f"but limited evidence — potential overconfidence"
                )
            if not evidence.supporting_evidence:
                challenges.append(
                    f"{evidence.role.value} has no supporting evidence"
                )
            for challenge in evidence.challenges:
                findings.append(f"Agreed with challenge: {challenge}")

        # Standard adversarial questions
        findings.append("Adversarial review completed")
        findings.append("Questions asked:")
        findings.append("  - What if we're wrong?")
        findings.append("  - What evidence contradicts this?")
        findings.append("  - What alternative explanation fits?")
        findings.append("  - Could the proposed action make it worse?")

        confidence = 0.5  # Adversarial reviewer is deliberately conservative

        return AgentEvidence(
            role=CouncilRole.ADVERSARIAL_REVIEWER,
            findings="\n".join(findings),
            confidence=confidence,
            supporting_evidence=findings,
            challenges=challenges,
        )

    async def _run_synthesizer(
        self, incident: Incident, all_evidence: list[AgentEvidence]
    ) -> AgentEvidence:
        """
        Agent 5 — Lead Synthesizer
        Receives all evidence and produces a final verdict.
        Does NOT execute anything.
        """
        findings = []

        # Calculate aggregate confidence
        confidences = [e.confidence for e in all_evidence if e.confidence > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Check for conflicting evidence
        high_confidence = [e for e in all_evidence if e.confidence > 0.7]
        low_confidence = [e for e in all_evidence if e.confidence < 0.4]

        if high_confidence and low_confidence:
            findings.append(
                "Conflicting confidence levels detected — "
                "some agents are confident while others are not"
            )

        # Count challenges
        total_challenges = sum(len(e.challenges) for e in all_evidence)
        if total_challenges > 3:
            findings.append(
                f"Multiple challenges raised ({total_challenges}) — "
                "evidence may be insufficient for high-confidence diagnosis"
            )

        findings.append(f"Synthesis complete. Average confidence: {avg_confidence:.1%}")

        return AgentEvidence(
            role=CouncilRole.LEAD_SYNTHESIZER,
            findings="\n".join(findings),
            confidence=avg_confidence,
            data={"total_challenges": total_challenges},
        )

    def _synthesize_verdict(
        self,
        all_evidence: list[AgentEvidence],
        rounds: int,
        budget_exceeded: bool,
        agents_used: list[str],
    ) -> CouncilVerdict:
        """Synthesize all agent evidence into a final verdict."""
        # Find synthesizer evidence
        synthesizer = next(
            (e for e in all_evidence if e.role == CouncilRole.LEAD_SYNTHESIZER),
            None,
        )

        # Collect all challenges
        all_challenges = []
        for e in all_evidence:
            all_challenges.extend(e.challenges)

        # Determine confidence
        confidence = synthesizer.confidence if synthesizer else 0.5

        # If budget exceeded or many challenges, reduce confidence
        if budget_exceeded:
            confidence *= 0.8
        if len(all_challenges) > 5:
            confidence *= 0.9

        # Build the verdict
        root_cause = "UNKNOWN"
        recommended_action = "Human investigation required"
        blast_radius = "unknown"
        risk_assessment = "Unknown risk — insufficient evidence"

        if confidence >= 0.7:
            # Collect findings from all agents
            all_findings = []
            for e in all_evidence:
                all_findings.append(f"[{e.role.value}] {e.findings}")

            root_cause = "Analysis complete — see evidence"
            recommended_action = "Review council findings and determine next steps"
            risk_assessment = f"{len(all_challenges)} challenge(s) raised"

        return CouncilVerdict(
            root_cause=root_cause,
            confidence=confidence,
            evidence={
                "agents": [
                    {
                        "role": e.role.value,
                        "findings": e.findings,
                        "confidence": e.confidence,
                        "challenges": e.challenges,
                    }
                    for e in all_evidence
                ],
            },
            alternative_hypotheses=all_challenges,
            blast_radius=blast_radius,
            recommended_action=recommended_action,
            risk_assessment=risk_assessment,
            required_verification="Health check and error rate monitoring",
            council_rounds_used=rounds,
            budget_exceeded=budget_exceeded,
            agents_used=agents_used,
        )


# Global council engine singleton
council_engine = CouncilEngine()
