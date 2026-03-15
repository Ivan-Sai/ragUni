"""FastAPI dependencies for auth and RBAC."""

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.core.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Valid roles for validation
VALID_ROLES = {"student", "teacher", "admin"}


async def get_user_by_email(email: str) -> dict | None:
    """Fetch user from MongoDB by email. Overridden in tests."""
    from app.services.database import get_database

    db = get_database()
    return await db.users.find_one({"email": email})


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    """Extract and validate current user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await get_user_by_email(email)
    if user is None:
        raise credentials_exception

    # Require is_active and is_approved fields to exist — don't default to True
    if "is_active" not in user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )

    if "is_approved" not in user or not user["is_approved"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending administrator approval",
        )

    return user


def require_role(*allowed_roles: str):
    """Factory that returns a dependency checking user role."""

    def role_checker(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in allowed_roles or user_role not in VALID_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_checker
