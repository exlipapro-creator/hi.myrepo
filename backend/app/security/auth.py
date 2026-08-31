"""
hi.myrepo - Authentication & Authorization

JWT-based authentication with role-based access control.
Secrets are NEVER hardcoded — loaded from environment.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.core.config import get_settings
from app.database.connection import db_manager
from app.database.models import User

settings = get_settings()
security_scheme = HTTPBearer()


class TokenData(BaseModel):
    user_id: str
    email: str
    role: str
    organization_id: str
    autonomy_level: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return _bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    organization_id: str,
    autonomy_level: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expiration_minutes)

    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "org_id": organization_id,
        "autonomy_level": autonomy_level,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "iss": "hi.myrepo",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="hi.myrepo",
        )
        return TokenData(
            user_id=payload["sub"],
            email=payload["email"],
            role=payload["role"],
            organization_id=payload["org_id"],
            autonomy_level=payload.get("autonomy_level", 0),
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> TokenData:
    """FastAPI dependency for extracting the authenticated user."""
    return decode_token(credentials.credentials)


def require_role(*allowed_roles: str):
    """Decorator to enforce role-based access."""

    async def role_checker(user: TokenData = Depends(get_current_user)) -> TokenData:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not in allowed roles: {allowed_roles}",
            )
        return user

    return role_checker


def require_autonomy_level(min_level: int):
    """Ensure user has sufficient autonomy level."""

    async def autonomy_checker(
        user: TokenData = Depends(get_current_user),
    ) -> TokenData:
        if user.autonomy_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Autonomy level {user.autonomy_level} insufficient. Required: {min_level}",
            )
        return user

    return autonomy_checker


async def require_project_access(
    project_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
) -> TokenData:
    """
    Verify the authenticated user's organization owns the specified project.

    This is the project-level authorization boundary.
    Every protected resource must check that the user's organization
    owns the project they are trying to access.

    Never trust project_id from the browser — always verify server-side.
    """
    import uuid as _uuid
    from sqlalchemy import select
    from app.database.connection import db_manager
    from app.database.models import Project

    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )

        if str(project.organization_id) != user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: project belongs to another organization",
            )

    return user


async def require_incident_access(
    incident_id: uuid.UUID,
    user: TokenData = Depends(get_current_user),
):
    """
    Verify the authenticated user's organization owns the incident's project.

    Returns (user, incident) tuple so callers can use the incident object.
    """
    from sqlalchemy import select
    from app.database.connection import db_manager
    from app.database.models import Incident

    async with db_manager.get_session() as session:
        result = await session.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()

        if not incident:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Incident not found",
            )

        # Check project access
        await require_project_access(incident.project_id, user)

    return user, incident
