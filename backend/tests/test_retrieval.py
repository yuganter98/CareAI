"""
Retrieval: the ownership filter, BM25, and the RRF fusion.

The filter test is the one that matters. The shipped Copilot took FAISS's
global top_k and then dropped other users' chunks, which scored Recall@5 of
1.2% once 40 patients were indexed. A unit test cannot measure that, but it
can pin the behaviour that caused it: the filter must be applied before the
top_k cut, so a caller's own chunks are returned even when every nearest
neighbour in the index belongs to somebody else.

A fake embedding model keeps these offline and fast; no model is downloaded.
"""
import numpy as np
import pytest

from app.agents import rag_pipeline as rag

DIM = rag.EMBEDDING_DIM


def vec(*values) -> np.ndarray:
    """A DIM-length vector whose first entries are `values`."""
    out = np.zeros(DIM, dtype="float32")
    out[:len(values)] = values
    return out


class FakeModel:
    """Maps known text to fixed vectors, so distances are exactly known."""

    def __init__(self, table):
        self.table = table

    def encode(self, texts):
        return np.array([self.table[t] for t in texts], dtype="float32")


@pytest.fixture
def index_dir(tmp_path, monkeypatch):
    """Point the module's index and metadata at a temp directory."""
    monkeypatch.setattr(rag, "FAISS_INDEX_PATH", str(tmp_path / "index.bin"))
    monkeypatch.setattr(rag, "METADATA_PATH", str(tmp_path / "meta.npy"))
    return tmp_path


class TestOwnershipFilter:

    def _build(self, monkeypatch, mine_distance: float):
        """One chunk for 'mine', ten nearer chunks for other patients."""
        question = "what is my glucose"
        table = {
            question: vec(0.0),
            "mine": vec(mine_distance),
        }
        for i in range(10):
            table[f"theirs-{i}"] = vec(0.1 * (i + 1))

        monkeypatch.setattr(rag, "get_embedding_model", lambda: FakeModel(table))
        for i in range(10):
            rag.embed_and_store(f"OTHER-R{i:02d}", [{"page": 1, "text": f"theirs-{i}"}])
        rag.embed_and_store("MINE-R01", [{"page": 1, "text": "mine"}])
        return question

    def test_returns_my_chunk_though_every_neighbour_is_someone_elses(
            self, index_dir, monkeypatch):
        # 'mine' is the furthest vector in the index: a global top_k of 3
        # followed by a filter would return nothing at all.
        question = self._build(monkeypatch, mine_distance=99.0)

        unfiltered = rag.search_similar_chunks(question, top_k=3)
        assert "MINE-R01" not in {h["report_id"] for h in unfiltered}

        mine = rag.search_similar_chunks(question, top_k=3,
                                         filter_report_ids=["MINE-R01"])
        assert [h["report_id"] for h in mine] == ["MINE-R01"]

    def test_no_owned_reports_returns_nothing_not_everything(
            self, index_dir, monkeypatch):
        # An empty ownership list means the user owns no reports. Treating it
        # as "no filter" would serve them another patient's pages.
        question = self._build(monkeypatch, mine_distance=1.0)
        assert rag.search_similar_chunks(question, top_k=3, filter_report_ids=[]) == []

    def test_single_report_filter_still_works(self, index_dir, monkeypatch):
        question = self._build(monkeypatch, mine_distance=99.0)
        hits = rag.search_similar_chunks(question, top_k=3, filter_report_id="MINE-R01")
        assert [h["report_id"] for h in hits] == ["MINE-R01"]

    def test_hits_carry_page_and_score_for_citations(self, index_dir, monkeypatch):
        question = self._build(monkeypatch, mine_distance=1.0)
        hit = rag.search_similar_chunks(question, top_k=1,
                                        filter_report_ids=["MINE-R01"])[0]
        assert hit["page"] == 1
        assert hit["chunk_id"] == "MINE-R01:1:0"
        assert 0.0 < hit["score"] <= 1.0

    def test_empty_index_is_not_an_error(self, index_dir, monkeypatch):
        monkeypatch.setattr(rag, "get_embedding_model",
                            lambda: FakeModel({"q": vec(0.0)}))
        assert rag.search_similar_chunks("q", top_k=3) == []


class TestBm25:
    """BM25 reads the stored chunk text, so these need no embedding model."""

    @pytest.fixture
    def corpus(self, index_dir, monkeypatch):
        rows = [
            {"chunk_id": "R1:1:0", "report_id": "R1", "page": 1,
             "chunk": "Hemoglobin 11.2 g/dL low haematology panel"},
            {"chunk_id": "R2:2:0", "report_id": "R2", "page": 2,
             "chunk": "Glucose 212 mg/dL critical biochemistry panel"},
            {"chunk_id": "R3:1:0", "report_id": "R3", "page": 1,
             "chunk": "Creatinine 1.1 mg/dL within range biochemistry panel"},
        ]
        monkeypatch.setattr(rag, "load_metadata", lambda: rows)
        return rows

    def test_exact_term_wins(self, corpus):
        hits = rag.bm25_search("glucose", top_k=3)
        assert hits[0]["report_id"] == "R2"

    def test_a_decimal_value_is_one_token(self, corpus):
        # "11.2" must not be split into "11" and "2"; a lab value is exactly
        # the term dense search loses and lexical search should catch.
        assert rag._tokenize("Hemoglobin 11.2 g/dL") == ["hemoglobin", "11.2", "g", "dl"]
        hits = rag.bm25_search("11.2", top_k=3)
        assert [h["report_id"] for h in hits] == ["R1"]

    def test_a_term_in_every_document_does_not_decide_the_ranking(self, corpus):
        # "panel" is in all three documents. Lucene's idf keeps it positive,
        # so it still scores, but it carries almost no information: the three
        # scores come out within a few percent of each other.
        flat = rag.bm25_search("panel", top_k=3)
        assert len(flat) == 3
        assert max(h["score"] for h in flat) / min(h["score"] for h in flat) < 1.2

        # Added to a selective term, it is the selective term that ranks.
        hits = rag.bm25_search("panel creatinine", top_k=3)
        assert hits[0]["report_id"] == "R3"

    def test_respects_the_ownership_filter(self, corpus):
        hits = rag.bm25_search("biochemistry", top_k=3, filter_report_ids=["R3"])
        assert [h["report_id"] for h in hits] == ["R3"]
        assert rag.bm25_search("biochemistry", top_k=3, filter_report_ids=[]) == []

    def test_no_match_is_empty(self, corpus):
        assert rag.bm25_search("ferritin", top_k=3) == []


class TestRrfFusion:

    def test_a_chunk_both_rankings_like_beats_either_firsts(self, monkeypatch):
        # dense ranks A first, lexical ranks B first, and both place C second.
        # With rrf_k = 60 a single first place (1/61) loses to two seconds
        # (2/62), which is the behaviour that makes fusion worth anything.
        def hit(name):
            return {"chunk_id": name, "report_id": name, "page": 1, "chunk": name}

        monkeypatch.setattr(rag, "search_similar_chunks",
                            lambda *a, **kw: [hit("A"), hit("C")])
        monkeypatch.setattr(rag, "bm25_search",
                            lambda *a, **kw: [hit("B"), hit("C")])

        fused = rag.hybrid_search("q", top_k=3)
        assert [h["chunk_id"] for h in fused][0] == "C"

    def test_uses_ranks_not_raw_scores(self, monkeypatch):
        # An absurd BM25 score must not outweigh rank order, because an L2
        # similarity and a BM25 score are on unrelated scales.
        def hit(name, score):
            return {"chunk_id": name, "report_id": name, "page": 1,
                    "chunk": name, "score": score}

        monkeypatch.setattr(rag, "search_similar_chunks",
                            lambda *a, **kw: [hit("A", 0.001)])
        monkeypatch.setattr(rag, "bm25_search",
                            lambda *a, **kw: [hit("B", 9999.0)])

        fused = rag.hybrid_search("q", top_k=2)
        # Both are rank 1 in their own list, so they tie and both survive.
        assert {h["chunk_id"] for h in fused} == {"A", "B"}
        assert fused[0]["score"] == pytest.approx(fused[1]["score"])
