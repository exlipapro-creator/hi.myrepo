"""
hi.myrepo - Authentication API

User registration, login, and token management.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.connection import db_manager
from app.database.models import Organization, User
from app.security.auth import (
    TokenData,
    TokenResponse,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter()
settings = get_settings()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    organization_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    autonomy_level: int
    organization_id: str


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest):
    """Register a new user and organization."""
    async with db_manager.get_session() as session:
        # Check if user already exists
        existing = await session.execute(
            select(User).where(User.email == req.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        # Create organization
        org = Organization(
            id=uuid.uuid4(),
            name=req.organization_name,
            slug=req.organization_name.lower().replace(" ", "-"),
        )
        session.add(org)
        await session.flush()

        # Create user as admin
        user = User(
            id=uuid.uuid4(),
            email=req.email,
            hashed_password=hash_password(req.password),
            full_name=req.full_name,
            role="admin",
            organization_id=org.id,
            autonomy_level=2,  # RECOMMEND by default for admin
        )
        session.add(user)
        await session.flush()

        # Generate token
        token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            organization_id=str(org.id),
            autonomy_level=user.autonomy_level,
        )

        return TokenResponse(
            access_token=token,
            expires_in=settings.jwt_expiration_minutes * 60,
        )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Authenticate and receive a JWT token."""
    async with db_manager.get_session() as session:
        result = await session.execute(
            select(User).where(User.email == req.email)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        token = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            organization_id=str(user.organization_id),
            autonomy_level=user.autonomy_level,
        )

        return TokenResponse(
            access_token=token,
            expires_in=settings.jwt_expiration_minutes * 60,
        )


@router.get("/me", response_model=UserResponse)
async def get_me(user: TokenData = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse(
        id=user.user_id,
        email=user.email,
        role=user.role,
        autonomy_level=user.autonomy_level,
        organization_id=user.organization_id,
    )
