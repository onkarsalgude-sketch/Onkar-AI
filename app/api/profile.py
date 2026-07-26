"""Instance Profile API router."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.profile_service import (
    ProfilePersistenceError,
    ProfileValidationError,
    get_instance_profile,
    update_instance_profile,
)

router = APIRouter(
    prefix="/profile",
    tags=["Profile"],
)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(
        default=None,
        description="User display name (1..50 characters).",
    )
    timezone: str | None = Field(
        default=None,
        description="Optional IANA timezone string or null.",
    )


@router.get("")
async def read_profile():
    try:
        profile = get_instance_profile()
        return {
            "service": "profile",
            "profile": profile,
        }
    except ProfilePersistenceError as error:
        raise HTTPException(
            status_code=503,
            detail="Profile is unavailable.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Profile is unavailable.",
        ) from error


@router.put("")
async def update_profile(payload: ProfileUpdateRequest):
    try:
        profile = update_instance_profile(
            display_name=payload.display_name,
            timezone=payload.timezone,
        )
        return {
            "service": "profile",
            "profile": profile,
        }
    except ProfileValidationError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except ProfilePersistenceError as error:
        raise HTTPException(
            status_code=503,
            detail="Profile is unavailable.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Profile is unavailable.",
        ) from error
