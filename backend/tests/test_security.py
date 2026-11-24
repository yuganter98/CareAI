"""
Security & hardening tests:
- WebSocket handshake requires a valid token and report ownership
- /ai/agent-query enforces report ownership
- Upload validation (extension, magic bytes, size)
- Report deletion cleans up the stored file and FAISS vectors
"""
import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.db.session import get_db
from tests.conftest import make_mock_db


def _mock_db_sequence(*results):
    """Mock session whose successive execute() calls return the given .first() values."""
    db = make_mock_db()
    side = []
    for r in results:
        res = MagicMock()
        res.scalars.return_value.first.return_value = r
        side.append(res)
    db.execute = AsyncMock(side_effect=side)
    db.close = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


# ── WebSocket auth ──────────────────────────────────────────────

class TestWebSocketAuth:

    def _override_db(self, db):
        async def override():
            yield db
        app.dependency_overrides[get_db] = override

    def test_rejects_handshake_without_cookie(self):
        self._override_db(_mock_db_sequence())
        client = TestClient(app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/agents/{uuid.uuid4()}"):
                pass
        assert exc.value.code == 1008

    def test_rejects_report_owned_by_someone_else(self, mock_user):
        # 1st query → user found, 2nd query → report not found for this user
        self._override_db(_mock_db_sequence(mock_user, None))
        client = TestClient(app)
        client.cookies.set("careai_token", create_access_token(str(mock_user.id)))
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws/agents/{uuid.uuid4()}"):
                pass
        assert exc.value.code == 1008

    def test_owner_can_connect_and_ping(self, mock_user):
        report = MagicMock(id=uuid.uuid4(), user_id=mock_user.id)
        self._override_db(_mock_db_sequence(mock_user, report))
        client = TestClient(app)
        client.cookies.set("careai_token", create_access_token(str(mock_user.id)))
        with client.websocket_connect(f"/ws/agents/{report.id}") as ws:
            ws.send_text("ping")
            assert ws.receive_json() == {"type": "pong"}


# ── Ownership on RAG query ──────────────────────────────────────

class TestAgentQueryOwnership:

    async def test_agent_query_rejects_foreign_report(self, async_client, mock_user):
        db = make_mock_db(first_result=None)  # report lookup finds nothing for this user

        async def override_db():
            yield db

        async def override_user():
            return mock_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user

        with patch("app.agents.orchestrator.orchestrator.process_event", new_callable=AsyncMock) as pe:
            resp = await async_client.post(
                "/api/v1/ai/agent-query",
                json={"report_id": str(uuid.uuid4()), "question": "What is my glucose?"},
            )
        assert resp.status_code == 404
        pe.assert_not_called()


# ── Upload validation ───────────────────────────────────────────

class TestUploadValidation:

    def _auth(self, mock_user):
        db = make_mock_db()

        async def override_db():
            yield db

        async def override_user():
            return mock_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        return db

    async def test_rejects_unsupported_extension(self, async_client, mock_user, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
        db = self._auth(mock_user)
        resp = await async_client.post(
            "/api/v1/reports/upload",
            files={"file": ("payload.exe", io.BytesIO(b"MZ..."), "application/octet-stream")},
        )
        assert resp.status_code == 415
        db.add.assert_not_called()

    async def test_rejects_spoofed_pdf(self, async_client, mock_user, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
        self._auth(mock_user)
        resp = await async_client.post(
            "/api/v1/reports/upload",
            files={"file": ("report.pdf", io.BytesIO(b"not really a pdf"), "application/pdf")},
        )
        assert resp.status_code == 415
        assert list(tmp_path.iterdir()) == []  # partial file cleaned up

    async def test_rejects_oversized_file(self, async_client, mock_user, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
        monkeypatch.setattr("app.core.config.settings.MAX_UPLOAD_SIZE_MB", 1)
        self._auth(mock_user)
        big = b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)
        resp = await async_client.post(
            "/api/v1/reports/upload",
            files={"file": ("report.pdf", io.BytesIO(big), "application/pdf")},
        )
        assert resp.status_code == 413
        assert list(tmp_path.iterdir()) == []

    async def test_file_type_comes_from_extension_not_client(self, async_client, mock_user, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
        self._auth(mock_user)
        resp = await async_client.post(
            "/api/v1/reports/upload",
            files={"file": ("scan.PNG", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 32), "image/png")},
            data={"file_type": "pdf"},  # lying client
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["file_type"] == "image"
        assert body["file_url"].endswith(".png")


# ── Deletion cleanup ────────────────────────────────────────────

class TestReportDeletion:

    async def test_delete_removes_file_and_vectors(self, async_client, mock_user, tmp_path, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.UPLOAD_DIR", str(tmp_path))
        stored = tmp_path / "abc.pdf"
        stored.write_bytes(b"%PDF-1.4")
        report = MagicMock(id=uuid.uuid4(), user_id=mock_user.id, file_url=str(stored))
        db = make_mock_db(first_result=report)

        async def override_db():
            yield db

        async def override_user():
            return mock_user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user

        with patch("app.agents.rag_pipeline.delete_report_vectors") as dv:
            resp = await async_client.delete(f"/api/v1/reports/{report.id}")

        assert resp.status_code == 204
        assert not stored.exists()
        dv.assert_called_once_with(str(report.id))


# ── FAISS vector removal keeps index + metadata aligned ─────────

class TestFaissVectorRemoval:

    def test_remove_keeps_remaining_vectors_aligned(self, tmp_path, monkeypatch):
        import faiss
        from app.agents import rag_pipeline as rp

        monkeypatch.setattr(rp, "FAISS_INDEX_PATH", str(tmp_path / "idx.bin"))
        monkeypatch.setattr(rp, "METADATA_PATH", str(tmp_path / "meta.npy"))

        dim = rp.EMBEDDING_DIM
        vecs = np.eye(4, dim, dtype="float32")
        index = faiss.IndexFlatL2(dim)
        index.add(vecs)
        faiss.write_index(index, rp.FAISS_INDEX_PATH)
        rp._write_metadata([
            {"report_id": "A", "chunk": "a0"},
            {"report_id": "B", "chunk": "b0"},
            {"report_id": "A", "chunk": "a1"},
            {"report_id": "C", "chunk": "c0"},
        ])

        assert rp.delete_report_vectors("A") == 2

        index = rp.init_faiss_index()
        meta = rp.load_metadata()
        assert index.ntotal == 2
        assert [m["chunk"] for m in meta] == ["b0", "c0"]
        # The vector at position 0 must now be B's original vector (row 1)
        _, ids = index.search(vecs[1:2], 1)
        assert meta[ids[0][0]]["chunk"] == "b0"
        _, ids = index.search(vecs[3:4], 1)
        assert meta[ids[0][0]]["chunk"] == "c0"
