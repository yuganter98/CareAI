"""
Duplicate uploads.

Re-uploading the same file used to create a second report and pay for
extraction, metric extraction and analysis again. The upload now carries a
SHA-256 of its bytes, taken during the pass that writes the file, and a
matching hash for the same user returns the report they already have.

Two decisions worth stating, because neither is obvious from the code:

- The hash is scoped **per user**, not globally. Two people may legitimately
  upload the same file - a public health leaflet, a shared family report - and
  matching across accounts would merge their records and let one user learn
  that another holds a given file.
- The unique constraint, not the SELECT, is the real guard. Two uploads of
  one file can race: both SELECTs can miss before either commits.
"""
import hashlib
import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import Report
from app.main import app
from app.api.deps import get_current_user
from app.db.session import get_db
from tests.conftest import make_mock_db

pytestmark = pytest.mark.asyncio


def _existing_report(user_id, digest):
    report = Report(
        user_id=user_id,
        file_url="uploads/already_here.pdf",
        file_type="pdf",
        content_sha256=digest,
    )
    report.id = uuid.uuid4()
    from datetime import datetime
    report.uploaded_at = datetime.utcnow()
    return report


class _Overrides:
    """Install the db/user dependency overrides and take them down again."""

    def __init__(self, db, user):
        self.db, self.user = db, user

    def __enter__(self):
        async def override_db():
            yield self.db

        async def override_user():
            return self.user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        return self

    def __exit__(self, *exc):
        app.dependency_overrides.clear()


async def _upload(client):
    return await client.post(
        "/api/v1/reports/upload",
        files={"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
    )


class TestDuplicateDetection:

    async def test_a_second_upload_returns_the_first_report(
            self, async_client, mock_user):
        digest = "b" * 64
        already = _existing_report(mock_user.id, digest)
        db = make_mock_db(first_result=already)

        with _Overrides(db, mock_user):
            with patch("app.api.endpoints.reports.save_upload_file",
                       new_callable=AsyncMock,
                       return_value=("uploads/second_copy.pdf", digest)), \
                 patch("app.api.endpoints.reports.remove_stored_file") as rm:
                response = await _upload(async_client)

        assert response.status_code == 201
        assert response.json()["file_url"] == "uploads/already_here.pdf"
        # No second row, and the bytes just written are not left orphaned.
        db.add.assert_not_called()
        rm.assert_called_once_with("uploads/second_copy.pdf")

    async def test_a_new_file_is_stored_with_its_hash(
            self, async_client, mock_user):
        db = make_mock_db(first_result=None)      # nothing matches
        digest = "c" * 64

        with _Overrides(db, mock_user):
            with patch("app.api.endpoints.reports.save_upload_file",
                       new_callable=AsyncMock,
                       return_value=("uploads/new.pdf", digest)):
                response = await _upload(async_client)

        assert response.status_code == 201
        db.add.assert_called_once()
        stored = db.add.call_args[0][0]
        assert stored.content_sha256 == digest

    async def test_a_racing_duplicate_falls_back_to_the_winner(
            self, async_client, mock_user):
        # Both requests' SELECTs miss, then one INSERT loses to the unique
        # constraint. The loser must return the winner's row, not a 500.
        digest = "d" * 64
        winner = _existing_report(mock_user.id, digest)

        misses = MagicMock()
        misses.scalars.return_value.first.return_value = None
        finds = MagicMock()
        finds.scalars.return_value.first.return_value = winner

        db = make_mock_db()
        db.execute = AsyncMock(side_effect=[misses, finds])
        db.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
        db.rollback = AsyncMock()

        with _Overrides(db, mock_user):
            with patch("app.api.endpoints.reports.save_upload_file",
                       new_callable=AsyncMock,
                       return_value=("uploads/loser.pdf", digest)), \
                 patch("app.api.endpoints.reports.remove_stored_file") as rm:
                response = await _upload(async_client)

        assert response.status_code == 201
        assert response.json()["file_url"] == "uploads/already_here.pdf"
        db.rollback.assert_awaited_once()
        rm.assert_called_once_with("uploads/loser.pdf")

    async def test_an_integrity_error_with_no_winner_is_not_swallowed(
            self, async_client, mock_user):
        # A constraint violation that is *not* the duplicate one must surface.
        # Returning 201 here would hide a real database problem.
        misses = MagicMock()
        misses.scalars.return_value.first.return_value = None

        db = make_mock_db()
        db.execute = AsyncMock(return_value=misses)
        db.commit = AsyncMock(side_effect=IntegrityError("insert", {}, Exception()))
        db.rollback = AsyncMock()

        with _Overrides(db, mock_user):
            with patch("app.api.endpoints.reports.save_upload_file",
                       new_callable=AsyncMock,
                       return_value=("uploads/x.pdf", "e" * 64)), \
                 patch("app.api.endpoints.reports.remove_stored_file"):
                # ASGITransport re-raises app exceptions rather than turning
                # them into a 500, so the error arriving here *is* the
                # assertion: the endpoint re-raised instead of reporting a
                # successful upload it did not make.
                with pytest.raises(IntegrityError):
                    await _upload(async_client)


class TestTheHash:

    async def test_it_is_the_sha256_of_the_bytes_written(self, tmp_path):
        # The digest has to be over the file's real content, or two different
        # reports could collide and one would be silently discarded.
        from app.services import upload as upload_service

        content = b"%PDF-1.4 " + b"lab values here " * 50
        expected = hashlib.sha256(content).hexdigest()

        class FakeUpload:
            filename = "report.pdf"

            def __init__(self, data):
                self._stream = io.BytesIO(data)

            async def read(self, size):
                return self._stream.read(size)

        with patch.object(upload_service.settings, "UPLOAD_DIR", str(tmp_path)):
            path, digest = await upload_service.save_upload_file(FakeUpload(content))

        assert digest == expected
        assert open(path, "rb").read() == content

    async def test_two_different_files_hash_differently(self, tmp_path):
        from app.services import upload as upload_service

        class FakeUpload:
            filename = "report.pdf"

            def __init__(self, data):
                self._stream = io.BytesIO(data)

            async def read(self, size):
                return self._stream.read(size)

        with patch.object(upload_service.settings, "UPLOAD_DIR", str(tmp_path)):
            _, first = await upload_service.save_upload_file(
                FakeUpload(b"%PDF-1.4 glucose 88"))
            _, second = await upload_service.save_upload_file(
                FakeUpload(b"%PDF-1.4 glucose 450"))

        assert first != second
