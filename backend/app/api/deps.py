import uuid
from typing import Optional
from fastapi import Cookie, Depends, HTTPException, status
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.db.session import get_db
from app.db.models import User, Report
from app.schemas.user import TokenPayload


async def resolve_user_from_token(db: AsyncSession, token: Optional[str]) -> User:
    """
    Decode a careai_token JWT and load the matching user.
    Shared by the HTTP cookie dependency and the WebSocket handshake.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    if not token_data.sub:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token subject")

    try:
        user_uuid = uuid.UUID(token_data.sub)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token subject")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    careai_token: Optional[str] = Cookie(default=None),
) -> User:
    return await resolve_user_from_token(db, careai_token)


async def get_owned_report(db: AsyncSession, report_id: str, user: User) -> Report:
    """
    Load a report by id, enforcing that it belongs to `user`.
    Raises 400 for a malformed id and 404 when missing or owned by someone else.
    """
    try:
        report_uuid = uuid.UUID(str(report_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid report_id format.")

    result = await db.execute(
        select(Report).where(Report.id == report_uuid, Report.user_id == user.id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found or access denied.")
    return report
