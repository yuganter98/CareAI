import os
import faiss
import numpy as np
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Constants
FAISS_INDEX_PATH = "faiss_index.bin"
METADATA_PATH = "faiss_metadata.npy"  # to store mapping of index -> chunk text/report_id
CHUNK_SIZE = 500
OVERLAP = 50
EMBEDDING_DIM = 384

# Load SentenceTransformer Model globally
try:
    # All-MiniLM-L6-v2 is extremely fast and creates 384-dimensional embeddings (No API Key needed)
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2') 
except Exception as e:
    logger.error(f"Failed to load sentence_transformers model: {e}")
    embedding_model = None

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

def save_metadata(metadata_list):
    """Saves metadata locally as a numpy object array to match the FAISS index."""
    if os.path.exists(METADATA_PATH):
        existing = np.load(METADATA_PATH, allow_pickle=True).tolist()
        existing.extend(metadata_list)
        np.save(METADATA_PATH, np.array(existing, dtype=object))
    else:
        np.save(METADATA_PATH, np.array(metadata_list, dtype=object))

def load_metadata():
    """Loads parallel metadata chunks."""
    if os.path.exists(METADATA_PATH):
        return np.load(METADATA_PATH, allow_pickle=True).tolist()
    return []

def embed_and_store(report_id: str, text: str):
    """
    Core RAG Pipeline Storage:
    1. Chunks the text
    2. Embeds the chunks locally
    3. Stores vectors in FAISS
    """
    if not embedding_model:
        raise RuntimeError("Embedding model is not loaded correctly.")
        
    chunks = chunk_text(text)
    if not chunks:
        return
        
    # Generate embeddings
    embeddings = embedding_model.encode(chunks)
    embeddings = np.array(embeddings).astype("float32")  # FAISS strictly requires float32
    
    # Store parallel metadata so we don't lose the context of the chunks
    metadata = [{"report_id": str(report_id), "chunk": chunk} for chunk in chunks]
    
    # Add to FAISS and write to disk
    index = init_faiss_index()
    index.add(embeddings)
    faiss.write_index(index, FAISS_INDEX_PATH)
    
    # Append Metadata mapping to disk
    save_metadata(metadata)
    
    logger.info(f"Successfully embedded {len(chunks)} contextual chunks for report_id: {report_id}")

def search_similar_chunks(query: str, top_k: int = 3, filter_report_id: str = None):
    """
    Queries the persistent FAISS index for the most relevant context chunks.
    """
    index = init_faiss_index()
    metadata = load_metadata()
    
    if index.ntotal == 0 or len(metadata) == 0:
        return []
        
    # Embed user question
    query_embedding = embedding_model.encode([query])
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
