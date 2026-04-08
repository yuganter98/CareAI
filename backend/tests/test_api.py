"""
API Tests — auth login & report upload.
No real database or filesystem required; dependencies are overridden per test.
"""
import io
import pytest
from unittest.mock import patch, AsyncMock

from app.main import app
from app.api.deps import get_current_user
from app.db.session import get_db
from tests.conftest import make_mock_db


# ─────────────────────────────────────────────
#  Test 1: POST /auth/login
# ─────────────────────────────────────────────

class TestLoginEndpoint:

    async def test_valid_credentials_set_httponly_cookie(self, async_client, mock_user):
        """
        A correct email + password should return 200, a success message,
        and an httpOnly careai_token cookie.
        """
        mock_db = make_mock_db(first_result=mock_user)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            response = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "test@careai.com", "password": "securepassword123"},
            )
            assert response.status_code == 200
            assert response.json() == {"message": "Login successful"}
            assert "careai_token" in response.cookies
        finally:
            app.dependency_overrides.clear()

    async def test_wrong_password_returns_401(self, async_client, mock_user):
        """
        A wrong password must be rejected with 401 Unauthorized —
        no cookie should be issued.
        """
        mock_db = make_mock_db(first_result=mock_user)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            response = await async_client.post(
                "/api/v1/auth/login",
                data={"username": "test@careai.com", "password": "wrongpassword"},
            )
            assert response.status_code == 401
            assert "careai_token" not in response.cookies
        finally:
            app.dependency_overrides.clear()


# ─────────────────────────────────────────────
#  Test 2: POST /reports/upload
# ─────────────────────────────────────────────

class TestReportUpload:

    async def test_authenticated_user_can_upload_pdf(self, async_client, mock_user):
        """
        An authenticated user posting a PDF file should get a 201 response
        with the correct file_type and file_url from the saved path.
        """
        mock_db = make_mock_db()

        async def override_db():
            yield mock_db

        async def override_user():
            return mock_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        try:
            with patch(
                "app.api.endpoints.reports.save_upload_file",
                new_callable=AsyncMock,
                return_value="uploads/fake_report.pdf",
            ):
                fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
                response = await async_client.post(
                    "/api/v1/reports/upload",
                    files={"file": ("report.pdf", fake_pdf, "application/pdf")},
                    data={"file_type": "pdf"},
                )

            assert response.status_code == 201
            body = response.json()
            assert body["file_type"] == "pdf"
            assert body["file_url"] == "uploads/fake_report.pdf"
        finally:
            app.dependency_overrides.clear()

    async def test_unauthenticated_upload_returns_401(self, async_client):
        """
        A request with no session cookie should be rejected before
        touching the filesystem or database.
        """
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake content")
        response = await async_client.post(
            "/api/v1/reports/upload",
            files={"file": ("report.pdf", fake_pdf, "application/pdf")},
            data={"file_type": "pdf"},
        )
        assert response.status_code == 401
