"""
build_index.py — One-time builder for the RAG FAISS index.

Run this ONCE on a node where the PDFs and the embedding model are available
(a GPU node is fastest but CPU works). It parses every PDF in RAG_PDF_DIR,
chunks the text, embeds with all-MiniLM-L6-v2, builds a FAISS IndexFlatL2, and
writes the index + chunk store + metadata into RAG_CACHE_DIR. Experiments then
just LOAD this cache via retrieval.py.

Usage:
    python build_index.py                # build from PDFs in RAG_PDF_DIR
    RAG_INCLUDE_URLS=1 python build_index.py   # also ingest RAG_SAMPLE_URLS

Dependencies (install in the env first):
    pip install langchain-docling langchain sentence-transformers faiss-cpu
"""

import glob
import json
import os
import sys

import rag_config as C


def _load_pdf_docs(pdf_dir: str):
    """Parse every PDF in pdf_dir with DoclingLoader -> list of (text, source)."""
    from langchain_docling import DoclingLoader

    pdfs = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))
    if not pdfs:
        print(f"[build] WARNING: no PDFs found in {pdf_dir}")
    docs = []
    for path in pdfs:
        try:
            print(f"[build] parsing {os.path.basename(path)} ...", flush=True)
            loader = DoclingLoader(file_path=path)
            for d in loader.load():
                text = (d.page_content or "").strip()
                if text:
                    docs.append((text, path))
        except Exception as e:
            print(f"[build]   skipped {os.path.basename(path)}: {e}")
    return docs


def _load_url_docs(urls):
    """Parse webpages with DoclingLoader -> list of (text, source)."""
    from langchain_docling import DoclingLoader
    docs = []
    for url in urls:
        try:
            print(f"[build] parsing URL {url} ...", flush=True)
            loader = DoclingLoader(file_path=url)
            for d in loader.load():
                text = (d.page_content or "").strip()
                if text:
                    docs.append((text, url))
        except Exception as e:
            print(f"[build]   skipped {url}: {e}")
    return docs


def main():
    # Import heavy deps here so a missing dep gives a clear message.
    # RecursiveCharacterTextSplitter moved across LangChain versions:
    #   new:  langchain_text_splitters
    #   old:  langchain.text_splitter
    # Try the new location first, then fall back.
    try:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except Exception:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
        from sentence_transformers import SentenceTransformer
        import faiss
        import numpy as np
    except Exception as e:
        print(f"[build] ERROR: missing dependency: {e}")
        print("[build] Install: pip install langchain-docling langchain-text-splitters "
              "sentence-transformers faiss-cpu")
        sys.exit(1)

    os.makedirs(C.RAG_CACHE_DIR, exist_ok=True)

    # 1. Load source documents.
    docs = _load_pdf_docs(C.RAG_PDF_DIR)
    if C.RAG_INCLUDE_URLS and C.RAG_SAMPLE_URLS:
        docs += _load_url_docs(C.RAG_SAMPLE_URLS)
    if not docs:
        print("[build] ERROR: no documents loaded; nothing to index.")
        sys.exit(1)
    print(f"[build] loaded {len(docs)} document sections")

    # 2. Chunk, keeping each chunk's source document.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=C.RAG_CHUNK_SIZE, chunk_overlap=C.RAG_CHUNK_OVERLAP)
    chunk_texts, chunk_sources = [], []
    for text, source in docs:
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if piece:
                chunk_texts.append(piece)
                chunk_sources.append(source)
    print(f"[build] produced {len(chunk_texts)} chunks")

    # 3. Embed.
    print(f"[build] embedding with {C.RAG_EMBED_MODEL} ...", flush=True)
    model = SentenceTransformer(C.RAG_EMBED_MODEL)
    embeddings = model.encode(chunk_texts, convert_to_numpy=True,
                              show_progress_bar=True, batch_size=64)
    embeddings = embeddings.astype("float32")

    # 4. Build FAISS index (L2, matching the notebook's IndexFlatL2).
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    print(f"[build] FAISS index built: {index.ntotal} vectors, dim {dim}")

    # 5. Persist index + chunk store + metadata.
    faiss.write_index(index, C.RAG_INDEX_FILE)
    with open(C.RAG_CHUNKS_FILE, "w", encoding="utf-8") as f:
        for t, s in zip(chunk_texts, chunk_sources):
            f.write(json.dumps({"text": t, "source": s}, ensure_ascii=False) + "\n")
    with open(C.RAG_META_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "embed_model": C.RAG_EMBED_MODEL,
            "chunk_size": C.RAG_CHUNK_SIZE,
            "chunk_overlap": C.RAG_CHUNK_OVERLAP,
            "n_chunks": len(chunk_texts),
            "dim": dim,
            "pdf_dir": C.RAG_PDF_DIR,
            "included_urls": bool(C.RAG_INCLUDE_URLS),
        }, f, indent=2)

    print(f"[build] DONE. Cache written to {C.RAG_CACHE_DIR}")
    print(f"[build]   index : {C.RAG_INDEX_FILE}")
    print(f"[build]   chunks: {C.RAG_CHUNKS_FILE}")


if __name__ == "__main__":
    main()
