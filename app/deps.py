from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User


async def get_optional_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    discord_id = request.session.get("discord_id")
    if not discord_id:
        return None
    try:
        did = int(discord_id)
    except (TypeError, ValueError):
        return None
    row = await db.execute(select(User).where(User.discord_id == did))
    return row.scalar_one_or_none()


async def require_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    return user


async def require_user_redirect(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not signed in",
            headers={"Location": "/auth/login"},
        )
    return user
