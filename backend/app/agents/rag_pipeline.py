import logging
import math
import os
import re
import threading
from collections import Counter

import faiss
import numpy as np

logger = logging.getLogger(__name__)

# Constants
FAISS_INDEX_PATH = "faiss_index.bin"
METADATA_PATH = "faiss_metadata.npy"  # to store mapping of index -> chunk text/report_id
CHUNK_SIZE = 500
OVERLAP = 50
EMBEDDING_DIM = 384
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# The index and its parallel metadata file must always change together;
# this lock keeps concurrent uploads/deletes from interleaving their writes.
_index_lock = threading.Lock()

# The SentenceTransformer model (and torch) is loaded on first use rather than
# at import time, so the API boots fast and tests never download the model.
_embedding_model = None
_model_lock = threading.Lock()


def get_embedding_model():
    """Return the shared embedding model, loading it on first call."""
    global _embedding_model
    if _embedding_model is None:
        with _model_lock:
            if _embedding_model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    # All-MiniLM-L6-v2 is fast and creates 384-dim embeddings (no API key needed)
                    _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
                except Exception as e:
                    logger.error(f"Failed to load sentence_transformers model: {e}")
                    raise RuntimeError("Embedding model is not loaded correctly.") from e
    return _embedding_model


def init_faiss_index():
    """Initializes or loads an existing FAISS index."""
    if os.path.exists(FAISS_INDEX_PATH):
        index = faiss.read_index(FAISS_INDEX_PATH)
    else:
        index = faiss.IndexFlatL2(EMBEDDING_DIM)
    return index


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP):
    """Splits a large text block into smaller chunks with word overlap."""
    words = text.split()
    chunks = []

    if len(words) <= chunk_size:
        return [text]

    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        chunks.append(" ".join(chunk_words))

    return chunks


def chunk_pages(pages, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP):
    """
    Chunk a page-aware extraction, keeping each chunk tied to one page.

    Chunking never crosses a page boundary, so every chunk can cite exactly one
    page. Returns dicts of {"text", "page", "index"}, where `index` counts
    chunks within that page and makes the chunk id stable.
    """
    out = []
    for page in pages:
        page_no = int(page.get("page", 1))
        for i, piece in enumerate(chunk_text(page.get("text", ""), chunk_size, overlap)):
            if piece.strip():
                out.append({"text": piece, "page": page_no, "index": i})
    return out


def make_chunk_id(report_id: str, page: int, index: int) -> str:
    """
    Stable identifier for one chunk: report, page, position within the page.

    It does not depend on the chunk's position in the FAISS index, so deleting
    another report never renames it, and re-processing the same report produces
    the same ids. Eval sets reference chunks by this id.
    """
    return f"{report_id}:{page}:{index}"


def _write_metadata(metadata_list):
    np.save(METADATA_PATH, np.array(metadata_list, dtype=object))


def save_metadata(metadata_list):
    """Appends metadata locally as a numpy object array to match the FAISS index."""
    existing = load_metadata()
    existing.extend(metadata_list)
    _write_metadata(existing)


def load_metadata():
    """Loads parallel metadata chunks."""
    if os.path.exists(METADATA_PATH):
        return np.load(METADATA_PATH, allow_pickle=True).tolist()
    return []


def embed_and_store(report_id: str, content):
    """
    Core RAG Pipeline Storage:
    1. Chunks the text, one chunk per page section
    2. Embeds the chunks locally
    3. Stores vectors in FAISS with a stable chunk id and page number

    `content` is either the page list from `extract_report_pages()` or a plain
    string, which is treated as a single page.

    Re-processing a report replaces its previous vectors instead of
    duplicating them.
    """
    pages = [{"page": 1, "text": content}] if isinstance(content, str) else list(content)

    chunks = chunk_pages(pages)
    if not chunks:
        return

    # Generate embeddings
    embeddings = get_embedding_model().encode([c["text"] for c in chunks])
    embeddings = np.array(embeddings).astype("float32")  # FAISS strictly requires float32

    # Store parallel metadata so we don't lose the context of the chunks.
    # "chunk" holds the text (the key every agent reads); chunk_id and page are
    # what citations and the eval sets are built on.
    metadata = [
        {
            "chunk_id": make_chunk_id(str(report_id), c["page"], c["index"]),
            "report_id": str(report_id),
            "page": c["page"],
            "chunk": c["text"],
        }
        for c in chunks
    ]

    with _index_lock:
        _remove_report_vectors_unlocked(str(report_id))

        index = init_faiss_index()
        index.add(embeddings)
        faiss.write_index(index, FAISS_INDEX_PATH)
        save_metadata(metadata)

    logger.info(f"Successfully embedded {len(chunks)} contextual chunks for report_id: {report_id}")


def _remove_report_vectors_unlocked(report_id: str) -> int:
    """Drop every vector + metadata row for report_id. Caller must hold _index_lock."""
    metadata = load_metadata()
    positions = [i for i, m in enumerate(metadata) if m.get("report_id") == report_id]
    if not positions:
        return 0

    index = init_faiss_index()
    # IndexFlat compacts remaining ids after removal, which keeps them aligned
    # with the metadata list once the same positions are dropped there.
    index.remove_ids(np.array(positions, dtype="int64"))
    faiss.write_index(index, FAISS_INDEX_PATH)

    drop = set(positions)
    _write_metadata([m for i, m in enumerate(metadata) if i not in drop])
    return len(positions)


def delete_report_vectors(report_id: str) -> int:
    """Remove a report's chunks from the FAISS index. Returns how many were removed."""
    with _index_lock:
        removed = _remove_report_vectors_unlocked(str(report_id))
    if removed:
        logger.info(f"Removed {removed} FAISS chunks for report_id: {report_id}")
    return removed


def _allowed_report_ids(filter_report_id, filter_report_ids):
    """Normalise the two filter arguments into a set, or None for no filter."""
    if filter_report_ids is not None:
        allowed = {str(r) for r in filter_report_ids}
        # An explicit empty list means "this user owns nothing", which must
        # return nothing rather than silently searching everyone's reports.
        return allowed
    if filter_report_id is not None:
        return {str(filter_report_id)}
    return None


def _similarity(distance) -> float:
    """L2 distance to a 0-1 score, so dense and lexical hits can be compared."""
    return 1.0 / (1.0 + float(distance))


def search_similar_chunks(query: str, top_k: int = 3, filter_report_id: str = None,
                          filter_report_ids=None):
    """
    Nearest chunks to `query`, restricted to the given reports.

    The filter is applied *before* the top_k cut. That distinction is the whole
    point: the previous version took FAISS's global top_k and then dropped
    other users' chunks, so with many patients indexed a user's own pages
    almost never survived. Recall@5 measured 1.2% against 30.0% for filtering
    first (see eval/README.md).

    FAISS cannot filter inside the search, so filtering first means fetching a
    wider candidate window and widening it until top_k of the caller's own
    chunks are found. That is a stopgap: in pgvector this is a WHERE clause on
    the same index scan, with no over-fetch at all.
    """
    allowed = _allowed_report_ids(filter_report_id, filter_report_ids)
    if allowed is not None and not allowed:
        return []

    with _index_lock:
        index = init_faiss_index()
        metadata = load_metadata()

    if index.ntotal == 0 or len(metadata) == 0:
        return []

    query_embedding = get_embedding_model().encode([query])
    query_embedding = np.array(query_embedding).astype("float32")

    # No filter: the old top_k * 3 window is already more than enough.
    # With a filter: start wide, then widen until we have top_k or run out.
    fetch = min(index.ntotal, top_k * 3 if allowed is None else max(top_k * 20, 128))

    while True:
        distances, indices = index.search(query_embedding, fetch)

        results = []
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1 or idx >= len(metadata):
                continue
            data = metadata[idx]
            if allowed is not None and str(data.get("report_id")) not in allowed:
                continue
            hit = dict(data)
            hit["score"] = _similarity(distance)
            results.append(hit)
            if len(results) >= top_k:
                break

        if len(results) >= top_k or fetch >= index.ntotal:
            return results
        fetch = min(index.ntotal, fetch * 4)


# ── Lexical search ──────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9][a-z0-9.]*")


def _tokenize(text: str):
    """Lowercase word/number tokens. Keeps decimals ('11.2') in one piece,
    because a lab value is exactly the kind of term dense search loses."""
    return _TOKEN.findall(text.lower())


def bm25_search(query: str, top_k: int = 5, filter_report_id: str = None,
                filter_report_ids=None, k1: float = 1.5, b: float = 0.75):
    """
    BM25 over the candidate chunks' text.

    Dense embeddings are weak where this corpus is hardest: a patient's twenty
    biochemistry pages differ only in numbers and dates, which is a keyword
    match rather than a semantic one. The measured by-type split showed
    exactly that, with cross-report questions at 20% Recall@5.

    Statistics are computed over the candidate set on each call rather than
    cached. The candidate set is one patient's chunks, which is small, and a
    cache keyed on a mutable index is a correctness risk for no real gain
    here. In pgvector this becomes a tsvector/GIN index doing the same job.
    """
    allowed = _allowed_report_ids(filter_report_id, filter_report_ids)
    if allowed is not None and not allowed:
        return []

    with _index_lock:
        metadata = load_metadata()

    corpus = [m for m in metadata
              if allowed is None or str(m.get("report_id")) in allowed]
    if not corpus:
        return []

    terms = _tokenize(query)
    if not terms:
        return []

    docs = [_tokenize(m.get("chunk", "")) for m in corpus]
    lengths = [len(d) for d in docs]
    avg_len = sum(lengths) / len(lengths) if lengths else 0.0
    if avg_len == 0:
        return []

    # Document frequency for the query's terms only.
    doc_freq = Counter()
    doc_counts = []
    for doc in docs:
        counts = Counter(doc)
        doc_counts.append(counts)
        for term in set(terms):
            if term in counts:
                doc_freq[term] += 1

    total = len(corpus)
    scored = []
    for i, counts in enumerate(doc_counts):
        score = 0.0
        for term in terms:
            freq = counts.get(term, 0)
            if not freq:
                continue
            n_q = doc_freq[term]
            # Lucene's BM25 idf. The +1 inside the log keeps it positive even
            # for a term in every document, so the max() never actually fires
            # here; it is kept only so a future change to this expression
            # cannot start returning negative contributions unnoticed.
            # A universal term still scores, but weakly enough that a
            # selective term in the same query decides the ranking.
            idf = max(0.0, math.log(1 + (total - n_q + 0.5) / (n_q + 0.5)))
            norm = freq * (k1 + 1) / (freq + k1 * (1 - b + b * lengths[i] / avg_len))
            score += idf * norm
        if score > 0:
            hit = dict(corpus[i])
            hit["score"] = score
            scored.append(hit)

    scored.sort(key=lambda h: h["score"], reverse=True)
    return scored[:top_k]


# ── Hybrid search ───────────────────────────────────────────────────────

def _rrf_key(hit: dict) -> str:
    """Chunk identity for fusion. chunk_id is stable; fall back to the text
    for any row written before chunk ids existed."""
    return str(hit.get("chunk_id") or hit.get("chunk", ""))


def hybrid_search(query: str, top_k: int = 5, filter_report_id: str = None,
                  filter_report_ids=None, candidates: int = 20, rrf_k: int = 60):
    """
    Dense and BM25 results fused with Reciprocal Rank Fusion.

    RRF sums 1/(rrf_k + rank) across the lists. It uses only ranks, never the
    raw scores, which is what makes it safe here: an L2 similarity and a BM25
    score are on unrelated scales and normalising them against each other
    would be arbitrary. rrf_k = 60 is the value from the original RRF paper,
    kept rather than tuned so the number in EXPERIMENTS.md is not fitted to
    this test set.
    """
    dense = search_similar_chunks(query, top_k=candidates,
                                  filter_report_id=filter_report_id,
                                  filter_report_ids=filter_report_ids)
    lexical = bm25_search(query, top_k=candidates,
                          filter_report_id=filter_report_id,
                          filter_report_ids=filter_report_ids)

    fused: dict = {}
    for ranking in (dense, lexical):
        for rank, hit in enumerate(ranking, start=1):
            key = _rrf_key(hit)
            if key not in fused:
                fused[key] = {"hit": dict(hit), "score": 0.0}
            fused[key]["score"] += 1.0 / (rrf_k + rank)

    ordered = sorted(fused.values(), key=lambda e: e["score"], reverse=True)
    out = []
    for entry in ordered[:top_k]:
        hit = entry["hit"]
        hit["score"] = entry["score"]
        out.append(hit)
    return out
