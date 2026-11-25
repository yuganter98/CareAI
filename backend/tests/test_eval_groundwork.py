"""
Week 0 groundwork: the guarantees the eval sets are built on.

- extraction keeps page numbers
- chunks stay inside one page and carry a stable id
- stored vectors record chunk_id and page
- the eval set's reference ranges match the app's
"""
import importlib.util
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytest

from app.agents import rag_pipeline as rp
from app.agents.extractor import extract_report_pages, join_pages

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_pdf(path: Path, pages: list[str]) -> Path:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 100), text, fontsize=11)
    doc.save(str(path))
    doc.close()
    return path


class _StubEncoder:
    """Deterministic stand-in for the sentence-transformers model."""

    def encode(self, texts):
        return np.array(
            [[float(len(t) % 7) + i] + [0.0] * (rp.EMBEDDING_DIM - 1) for i, t in enumerate(texts)],
            dtype="float32",
        )


@pytest.fixture
def faiss_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "FAISS_INDEX_PATH", str(tmp_path / "index.bin"))
    monkeypatch.setattr(rp, "METADATA_PATH", str(tmp_path / "meta.npy"))
    monkeypatch.setattr(rp, "get_embedding_model", _StubEncoder)
    return tmp_path


# ── Extraction keeps pages ──────────────────────────────────────────────

class TestPageAwareExtraction:

    def test_each_page_comes_back_separately(self, tmp_path):
        pdf = _make_pdf(tmp_path / "r.pdf", ["Hemoglobin 11.2 g/dL", "Glucose 212 mg/dL"])
        pages = extract_report_pages(str(pdf), "pdf")

        assert [p["page"] for p in pages] == [1, 2]
        assert "Hemoglobin" in pages[0]["text"]
        assert "Glucose" in pages[1]["text"]
        # The value a citation would point at is only on its own page
        assert "212" not in pages[0]["text"]

    def test_blank_pages_do_not_renumber_later_pages(self, tmp_path):
        pdf = _make_pdf(tmp_path / "r.pdf", ["First page", "", "Third page"])
        pages = extract_report_pages(str(pdf), "pdf")

        assert [p["page"] for p in pages] == [1, 3]
        assert "Third" in pages[-1]["text"]

    def test_join_pages_returns_the_whole_document(self, tmp_path):
        pdf = _make_pdf(tmp_path / "r.pdf", ["Alpha", "Beta"])
        text = join_pages(extract_report_pages(str(pdf), "pdf"))

        assert "Alpha" in text and "Beta" in text

    def test_a_document_with_no_text_is_rejected(self, tmp_path):
        pdf = _make_pdf(tmp_path / "blank.pdf", ["", ""])
        with pytest.raises(ValueError):
            extract_report_pages(str(pdf), "pdf")


# ── Chunking and stable ids ─────────────────────────────────────────────

class TestChunkIdentity:

    def test_chunks_never_cross_a_page_boundary(self):
        pages = [{"page": 1, "text": "alpha " * 900}, {"page": 4, "text": "beta " * 30}]
        chunks = rp.chunk_pages(pages)

        assert len(chunks) > 2, "the long page should split"
        for chunk in chunks:
            words = set(chunk["text"].split())
            assert words <= {"alpha"} or words <= {"beta"}
        assert {c["page"] for c in chunks} == {1, 4}

    def test_index_restarts_on_each_page(self):
        chunks = rp.chunk_pages([{"page": 1, "text": "a " * 900}, {"page": 2, "text": "b"}])

        first_page = [c["index"] for c in chunks if c["page"] == 1]
        assert first_page == list(range(len(first_page)))
        assert [c["index"] for c in chunks if c["page"] == 2] == [0]

    def test_id_is_stable_and_independent_of_other_reports(self):
        assert rp.make_chunk_id("abc", 2, 1) == "abc:2:1"
        # Same inputs, same id — re-processing a report does not rename chunks
        assert rp.make_chunk_id("abc", 2, 1) == rp.make_chunk_id("abc", 2, 1)
        assert rp.make_chunk_id("abc", 2, 1) != rp.make_chunk_id("abd", 2, 1)


# ── What gets stored ────────────────────────────────────────────────────

class TestStoredMetadata:

    def test_stored_chunks_carry_id_and_page(self, faiss_tmp):
        rp.embed_and_store("rep-1", [
            {"page": 1, "text": "Hemoglobin 11.2 g/dL"},
            {"page": 2, "text": "Glucose 212 mg/dL"},
        ])

        meta = rp.load_metadata()
        assert [m["chunk_id"] for m in meta] == ["rep-1:1:0", "rep-1:2:0"]
        assert [m["page"] for m in meta] == [1, 2]
        assert all(m["report_id"] == "rep-1" for m in meta)
        # "chunk" still holds the text every agent reads
        assert "Glucose" in meta[1]["chunk"]

    def test_a_plain_string_is_stored_as_page_one(self, faiss_tmp):
        rp.embed_and_store("rep-2", "Creatinine 1.1 mg/dL")

        meta = rp.load_metadata()
        assert len(meta) == 1
        assert meta[0]["page"] == 1
        assert meta[0]["chunk_id"] == "rep-2:1:0"

    def test_reprocessing_keeps_the_same_ids_and_adds_no_duplicates(self, faiss_tmp):
        pages = [{"page": 1, "text": "Hemoglobin 11.2 g/dL"}, {"page": 2, "text": "Glucose 212 mg/dL"}]
        rp.embed_and_store("rep-3", pages)
        first = [m["chunk_id"] for m in rp.load_metadata()]

        rp.embed_and_store("rep-3", pages)
        second = [m["chunk_id"] for m in rp.load_metadata()]

        assert first == second
        assert rp.init_faiss_index().ntotal == len(second)

    def test_deleting_another_report_does_not_renumber_chunks(self, faiss_tmp):
        rp.embed_and_store("keep", [{"page": 1, "text": "Hemoglobin 11.2 g/dL"}])
        rp.embed_and_store("drop", [{"page": 1, "text": "Glucose 212 mg/dL"}])

        rp.delete_report_vectors("drop")

        meta = rp.load_metadata()
        assert [m["chunk_id"] for m in meta] == ["keep:1:0"]


# ── The eval set and the app agree on what is abnormal ──────────────────

class TestEvalRangesMatchTheApp:

    def _eval_ranges(self):
        path = REPO_ROOT / "eval" / "ranges.py"
        spec = importlib.util.spec_from_file_location("eval_ranges", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_ranges_are_identical(self):
        from app.analytics.personalized_insights import REFERENCE_RANGES as app_ranges

        assert self._eval_ranges().REFERENCE_RANGES == app_ranges, (
            "eval/ranges.py has drifted from the app's REFERENCE_RANGES; "
            "every score in the eval set is measured against these buckets."
        )

    def test_bucketing_agrees_with_the_app(self):
        from app.analytics.personalized_insights import _assess

        eval_ranges = self._eval_ranges()
        cases = [
            ("glucose", 85), ("glucose", 110), ("glucose", 150), ("glucose", 260),
            ("hemoglobin", 14.0), ("hemoglobin", 11.5), ("hemoglobin", 9.0), ("hemoglobin", 6.2),
            ("creatinine", 1.0), ("creatinine", 1.5), ("creatinine", 2.4), ("creatinine", 3.6),
            ("blood_pressure_systolic", 118), ("blood_pressure_systolic", 190),
            ("blood_pressure_diastolic", 70), ("blood_pressure_diastolic", 125),
        ]
        for metric, value in cases:
            assert eval_ranges.assess(metric, value) == _assess(metric, value), metric

    def test_risk_rule_is_driven_by_the_worst_value(self):
        risk = self._eval_ranges().expected_risk

        assert risk(["normal", "borderline"]) == "Low"
        assert risk(["normal", "elevated"]) == "Medium"
        assert risk(["normal", "elevated", "critical"]) == "High"
