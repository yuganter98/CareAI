import os
import logging
import threading

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


def search_similar_chunks(query: str, top_k: int = 3, filter_report_id: str = None):
    """
    Queries the persistent FAISS index for the most relevant context chunks.
    """
    with _index_lock:
        index = init_faiss_index()
        metadata = load_metadata()

    if index.ntotal == 0 or len(metadata) == 0:
        return []

    # Embed user question
    query_embedding = get_embedding_model().encode([query])
    query_embedding = np.array(query_embedding).astype("float32")

    distances, indices = index.search(query_embedding, top_k * 3)  # Search deeper if we need to filter

    results = []
    for idx in indices[0]:
        if idx != -1 and idx < len(metadata):
            data = metadata[idx]
            # If we want to strictly filter RAG context to ONLY the patient's specific report
            if filter_report_id and data.get("report_id") != filter_report_id:
                continue

            results.append(data)
            if len(results) >= top_k:
                break

    return results
