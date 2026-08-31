"""
hi.myrepo - Database Seed Loader

Loads default runbooks, policies, and AI providers into the database
on startup if they don't already exist.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AIProvider,
    Policy,
    ProviderStatus,
    Runbook,
    RunbookStatus,
)

logger = structlog.get_logger()

# Resolve paths relative to the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS_DIR = PROJECT_ROOT / "database" / "seeds"
POLICIES_DIR = PROJECT_ROOT / "database" / "policies"


async def seed_runbooks(session: AsyncSession) -> int:
    """Load default runbooks from JSON seed file. Returns count of new runbooks."""
    seed_file = SEEDS_DIR / "default_runbooks.json"
    if not seed_file.exists():
        logger.warning("runbook_seed_file_not_found", path=str(seed_file))
        return 0

    with open(seed_file) as f:
        runbooks_data = json.load(f)

    loaded = 0
    for rb_data in runbooks_data:
        # Check if runbook already exists by code
        existing = await session.execute(
            select(Runbook).where(Runbook.code == rb_data["code"])
        )
        if existing.scalar_one_or_none():
            continue

        runbook = Runbook(
            id=uuid.uuid4(),
            code=rb_data["code"],
            name=rb_data["name"],
            description=rb_data["description"],
            status=rb_data.get("status", RunbookStatus.ACTIVE),
            preconditions=rb_data.get("preconditions", {}),
            authorization_requirements=rb_data.get("authorization_requirements", {}),
            execution_steps=rb_data.get("execution_steps", []),
            rollback_strategy=rb_data.get("rollback_strategy"),
            verification_procedure=rb_data.get("verification_procedure", {}),
            timeout_seconds=rb_data.get("timeout_seconds", 300),
            max_blast_radius=rb_data.get("max_blast_radius", "medium"),
            is_reversible=rb_data.get("is_reversible", True),
            required_autonomy_level=rb_data.get("required_autonomy_level", 2),
        )
        session.add(runbook)
        loaded += 1

    if loaded > 0:
        await session.flush()
        logger.info("runbooks_seeded", count=loaded)
    return loaded


async def seed_policies(session: AsyncSession) -> int:
    """Load default autonomy policies from JSON seed file."""
    seed_file = POLICIES_DIR / "default_autonomy.json"
    if not seed_file.exists():
        logger.warning("policy_seed_file_not_found", path=str(seed_file))
        return 0

    with open(seed_file) as f:
        policies_data = json.load(f)

    loaded = 0
    for pol_data in policies_data:
        existing = await session.execute(
            select(Policy).where(Policy.name == pol_data["name"])
        )
        if existing.scalar_one_or_none():
            continue

        policy = Policy(
            id=uuid.uuid4(),
            name=pol_data["name"],
            description=pol_data.get("description"),
            is_active=pol_data.get("is_active", True),
            priority=pol_data.get("priority", 0),
            conditions=pol_data.get("conditions", {}),
            action=pol_data["action"],
            target_resource=pol_data["target_resource"],
        )
        session.add(policy)
        loaded += 1

    if loaded > 0:
        await session.flush()
        logger.info("policies_seeded", count=loaded)
    return loaded


async def seed_ai_providers(session: AsyncSession) -> int:
    """Initialize AI provider records in the database."""
    from app.core.config import get_settings
    settings = get_settings()

    provider_configs = [
        {
            "name": "gemini",
            "api_key_env": "gemini_api_key",
            "capabilities": ["text", "vision", "reasoning", "code", "long_context"],
            "models": ["gemini-2.0-flash", "gemini-2.0-pro", "gemini-1.5-flash"],
        },
        {
            "name": "openai",
            "api_key_env": "openai_api_key",
            "capabilities": ["text", "vision", "reasoning", "code", "structured_output"],
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        },
        {
            "name": "groq",
            "api_key_env": "groq_api_key",
            "capabilities": ["text", "speed", "code"],
            "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        },
    ]

    created = 0
    for config in provider_configs:
        existing = await session.execute(
            select(AIProvider).where(AIProvider.name == config["name"])
        )
        if existing.scalar_one_or_none():
            continue

        api_key = getattr(settings, config["api_key_env"], "")
        has_key = bool(api_key)

        provider = AIProvider(
            id=uuid.uuid4(),
            name=config["name"],
            status=ProviderStatus.HEALTHY if has_key else ProviderStatus.UNKNOWN,
            capabilities=config["capabilities"],
            models_available=config["models"],
            circuit_state="closed",
        )
        session.add(provider)
        created += 1

    if created > 0:
        await session.flush()
        logger.info("ai_providers_seeded", count=created)
    return created


async def run_all_seeds(session: AsyncSession) -> None:
    """Run all seed functions during application startup."""
    try:
        rb_count = await seed_runbooks(session)
        pol_count = await seed_policies(session)
        prov_count = await seed_ai_providers(session)
        logger.info(
            "seeds_complete",
            runbooks=rb_count,
            policies=pol_count,
            providers=prov_count,
        )
    except Exception as e:
        logger.error("seed_error", error=str(e), exc_info=True)
