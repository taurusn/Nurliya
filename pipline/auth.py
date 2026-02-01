"""
JWT Authentication module for Nurliya API.
"""

from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

from database import User, get_session
from config import get_secret
from logging_config import get_logger

logger = get_logger(__name__, service="auth")

# Configuration
JWT_SECRET = get_secret("JWT_SECRET", "nurliya-jwt-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  # 7 days

security = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    user_id: str
    email: str
    exp: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def create_access_token(user: User) -> str:
    """Create JWT token for user."""
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": str(user.id),
        "email": user.email,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """Dependency to get current authenticated user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(credentials.credentials)

    session = get_session()
    try:
        user = session.query(User).filter_by(id=token_data.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User is inactive",
            )
        return user
    finally:
        session.close()


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """Dependency to get current user if authenticated, None otherwise."""
    if not credentials:
        return None

    try:
        token_data = decode_token(credentials.credentials)
    except HTTPException:
        return None

    session = get_session()
    try:
        user = session.query(User).filter_by(id=token_data.user_id).first()
        if user and user.is_active:
            return user
        return None
    finally:
        session.close()


def register_user(data: UserCreate) -> User:
    """Register a new user."""
    session = get_session()
    try:
        # Check if email exists
        existing = session.query(User).filter_by(email=data.email.lower()).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Create user
        user = User(
            email=data.email.lower(),
            password_hash=User.hash_password(data.password),
            name=data.name,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("User registered", extra={"extra_data": {"email": user.email}})
        return user
    finally:
        session.close()


def authenticate_user(email: str, password: str) -> Optional[User]:
    """Authenticate user by email and password."""
    session = get_session()
    try:
        user = session.query(User).filter_by(email=email.lower()).first()
        if not user or not user.verify_password(password):
            return None
        logger.info("User authenticated", extra={"extra_data": {"email": user.email}})
        return user
    finally:
        session.close()
