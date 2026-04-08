import uuid
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import get_password_hash


@pytest.fixture
def mock_user():
    """A fully-populated fake User — no real DB needed."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.name = "Test User"
    user.email = "test@careai.com"
    user.password_hash = get_password_hash("securepassword123")
    user.created_at = datetime.utcnow()
    user.whatsapp_number = None
    user.address = None
    user.blood_type = None
    user.emergency_contact_name = None
    user.emergency_contact_phone = None
    user.notify_sms = "true"
    user.notify_email = "true"
    user.notify_report_ready = "true"
    user.notify_high_risk = "true"
    return user


def make_mock_db(first_result=None):
    """
    Build a minimal async SQLAlchemy session mock.
    first_result — the object returned by result.scalars().first()
    """
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = first_result

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.delete = AsyncMock()

    async def _refresh(obj):
        # Simulate SQLAlchemy populating server-side defaults after INSERT
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "uploaded_at", None) is None:
            obj.uploaded_at = datetime.utcnow()

    mock_db.refresh = AsyncMock(side_effect=_refresh)
    return mock_db


@pytest_asyncio.fixture
async def async_client():
    """httpx AsyncClient wired directly to the FastAPI app (no running server needed)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
