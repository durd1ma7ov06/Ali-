"""
knowledge_index.py — Stage 2 of UNIVERSITY_KNOWLEDGE_PLAN.md.

Reads crawled documents from `university_knowledge/knowledge.sqlite`, splits
them into search-friendly chunks, and builds a local search index. No AI
generation, summarisation, or translation here — only chunking + indexing +
retrieval.

Two backends are supported and selected automatically:

  1. embedding (preferred) — sentence-transformers multilingual encoder.
                              Stored as float32 numpy matrix.
  2. tfidf (fallback)      — scikit-learn TfidfVectorizer.

The active backend is recorded in the SQLite `index_meta` table and in
`vector_index/meta.json`. The `search_knowledge(query, top_k)` function is
backend-agnostic and is the entry point Stage 3 will call.

CLI:
  python knowledge_index.py --rebuild
  python knowledge_index.py --status
  python knowledge_index.py --search "Universitet qayerda joylashgan?"
  python knowledge_index.py --top-k 5 --search "Qabul haqida"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# ─────────────────────────────────────────────────────────────────────────────
# Paths / config
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT  = Path(__file__).parent.resolve()
KNOWLEDGE_DIR = PROJECT_ROOT / "amir_temur_knowledge"
SOURCES_PATH  = KNOWLEDGE_DIR / "sources.yaml"
DB_PATH       = KNOWLEDGE_DIR / "knowledge.sqlite"
CHUNKS_JSONL  = KNOWLEDGE_DIR / "chunks.jsonl"
INDEX_DIR     = KNOWLEDGE_DIR / "vector_index"

EMB_PATH       = INDEX_DIR / "embeddings.npy"
TFIDF_VEC_PATH = INDEX_DIR / "tfidf_vectorizer.pkl"
TFIDF_MAT_PATH = INDEX_DIR / "tfidf_matrix.pkl"
CHUNK_IDS_PATH = INDEX_DIR / "chunk_ids.json"
INDEX_META_JS  = INDEX_DIR / "meta.json"


_INDEX_DEFAULTS = {
    "chunk_size_chars":     900,
    "chunk_overlap_chars":  150,
    "min_chunk_chars":      120,
    "top_k_default":        5,
    "backend_preference":   "embedding",
    "embedding_model":      "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "embedding_batch_size": 32,
}


def _load_indexing_cfg() -> dict:
    cfg = dict(_INDEX_DEFAULTS)
    if not SOURCES_PATH.exists():
        return cfg
    try:
        import yaml  # type: ignore
    except ImportError:
        print("[INDEX] PyYAML not available; using built-in indexing defaults.")
        return cfg
    try:
        with open(SOURCES_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        section = raw.get("indexing") or {}
        for k, v in section.items():
            if k in cfg:
                cfg[k] = v
    except Exception as exc:
        print(f"[INDEX] Failed to load indexing config: {exc} — using defaults.")
    cfg["chunk_size_chars"]     = int(cfg["chunk_size_chars"])
    cfg["chunk_overlap_chars"]  = int(cfg["chunk_overlap_chars"])
    cfg["min_chunk_chars"]      = int(cfg["min_chunk_chars"])
    cfg["top_k_default"]        = int(cfg["top_k_default"])
    cfg["embedding_batch_size"] = int(cfg["embedding_batch_size"])
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# SQLite helpers
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA_EXTRA = """
CREATE TABLE IF NOT EXISTS chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER,
    source_url      TEXT,
    title           TEXT,
    chunk_index     INTEGER,
    chunk_text      TEXT,
    token_estimate  INTEGER,
    content_hash    TEXT,
    created_at      TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS ix_chunks_hash     ON chunks(content_hash);

CREATE TABLE IF NOT EXISTS index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} not found. Run knowledge_crawler.py --crawl first."
        )
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA_EXTRA)
    return conn


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO index_meta(key, value) VALUES (?, ?)",
        (key, value),
    )


def _get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM index_meta WHERE key=?", (key,)
    ).fetchone()
    return row[0] if row else default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────────────────────
# Text cleaning + chunking
# ─────────────────────────────────────────────────────────────────────────────

_WS_RE       = re.compile(r"[ \t\f\v]+")
_BLANK_RE    = re.compile(r"\n{3,}")
# Sentence terminator detector (handles ! ? . and Cyrillic period equivalents).
_SENT_END_RE = re.compile(r"(?<=[\.\!\?\u2026\u3002])\s+(?=[A-Za-z\u0400-\u04FF\u00C0-\u017F])")
# Recurring nav-like phrases observed during the dry-run; these tend to repeat
# across many crawled pages and add no value.
_BOILERPLATE_PATTERNS = (
    re.compile(r"©\s*Urganch\s+innovatsion[^\n]*", re.IGNORECASE),
    re.compile(r"All\s+Rights?\s+Reserved", re.IGNORECASE),
    re.compile(r"^\s*(Ko[‘'`]proq[^\n]*)$", re.MULTILINE),
)


def _normalise_whitespace(text: str) -> str:
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()


def _strip_boilerplate(text: str) -> str:
    for pat in _BOILERPLATE_PATTERNS:
        text = pat.sub(" ", text)
    return text


def _is_navlike_chunk(text: str) -> bool:
    """
    Heuristic: chunks dominated by short, comma/pipe-separated tokens with
    almost no full sentences look like leftover menu/navigation text.
    """
    stripped = text.strip()
    if not stripped:
        return True
    # Dense bullet/menu pattern: many short lines, very few sentence ends.
    lines = [ln.strip() for ln in stripped.split("\n") if ln.strip()]
    if len(lines) >= 6:
        short_lines = sum(1 for ln in lines if len(ln) < 30)
        if short_lines / len(lines) >= 0.85:
            sentence_terminators = sum(stripped.count(c) for c in ".!?")
            if sentence_terminators < 2:
                return True
    return False


def _split_into_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts


def _split_into_sentences(text: str) -> list[str]:
    parts = _SENT_END_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _chunkify(text: str, *, size: int, overlap: int,
              min_chunk: int) -> list[str]:
    """
    Split `text` into chunks <= `size` characters with `overlap` characters
    of context between consecutive chunks. Tries paragraph then sentence
    boundaries first; falls back to hard slicing only when a single
    paragraph/sentence is itself larger than `size`.
    """
    if not text:
        return []

    paragraphs = _split_into_paragraphs(text) or [text]
    chunks: list[str] = []
    current = ""

    def _flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for para in paragraphs:
        # Paragraph itself larger than chunk size → split into sentences first.
        if len(para) > size:
            sentences = _split_into_sentences(para)
            for sent in sentences:
                if len(sent) > size:
                    # Hard split a runaway sentence into size-sized windows.
                    for i in range(0, len(sent), max(1, size - overlap)):
                        piece = sent[i:i + size]
                        if not piece:
                            continue
                        if current and len(current) + 1 + len(piece) > size:
                            _flush()
                            if overlap and chunks:
                                tail = chunks[-1][-overlap:]
                                current = tail + " " + piece
                            else:
                                current = piece
                        else:
                            current = (current + " " + piece).strip() if current else piece
                else:
                    if current and len(current) + 1 + len(sent) > size:
                        _flush()
                        if overlap and chunks:
                            tail = chunks[-1][-overlap:]
                            current = tail + " " + sent
                        else:
                            current = sent
                    else:
                        current = (current + " " + sent).strip() if current else sent
            continue

        # Normal paragraph — try to keep it whole.
        if current and len(current) + 2 + len(para) > size:
            _flush()
            if overlap and chunks:
                tail = chunks[-1][-overlap:]
                current = tail + "\n\n" + para
            else:
                current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para

    _flush()

    # Drop micro-chunks unless the whole document is itself short.
    if len(text) <= min_chunk:
        return [text.strip()] if text.strip() else []
    return [c for c in chunks if len(c) >= min_chunk]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token works for mixed-script content)."""
    return max(1, len(text) // 4)


# ─────────────────────────────────────────────────────────────────────────────
# Build chunks from documents
# ─────────────────────────────────────────────────────────────────────────────

def build_chunks(conn: sqlite3.Connection, cfg: dict) -> dict:
    """
    Re-create the `chunks` table from the current `documents` table.
    Returns a stats dict.
    """
    docs = conn.execute(
        "SELECT id, url, title, text FROM documents ORDER BY id"
    ).fetchall()
    if not docs:
        print("[INDEX] No documents found. Run knowledge_crawler.py --crawl first.")
        return {"documents": 0, "chunks": 0, "duplicates": 0, "navlike_skipped": 0}

    conn.execute("DELETE FROM chunks")
    conn.commit()

    if CHUNKS_JSONL.exists():
        CHUNKS_JSONL.unlink()
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_fp = open(CHUNKS_JSONL, "w", encoding="utf-8")

    seen_hashes: set[str] = set()
    n_docs = 0
    n_chunks = 0
    n_dupes  = 0
    n_navlike = 0

    try:
        for doc_id, url, title, text in docs:
            n_docs += 1
            cleaned = _strip_boilerplate(text or "")
            cleaned = _normalise_whitespace(cleaned)
            if not cleaned:
                continue

            # Prepend the title to the first chunk so it's discoverable.
            pieces = _chunkify(
                cleaned,
                size=cfg["chunk_size_chars"],
                overlap=cfg["chunk_overlap_chars"],
                min_chunk=cfg["min_chunk_chars"],
            )

            chunk_idx = 0
            for piece in pieces:
                piece = _normalise_whitespace(piece)
                if not piece:
                    continue
                if _is_navlike_chunk(piece):
                    n_navlike += 1
                    continue

                # Augment the first chunk with the title for retrieval recall.
                indexed_text = (
                    f"{title}\n\n{piece}" if (chunk_idx == 0 and title)
                    else piece
                )

                h = _content_hash(indexed_text)
                if h in seen_hashes:
                    n_dupes += 1
                    continue
                seen_hashes.add(h)

                row = (
                    int(doc_id), url, title or "", chunk_idx, indexed_text,
                    _estimate_tokens(indexed_text), h, _now_iso(),
                )
                conn.execute(
                    "INSERT INTO chunks(document_id, source_url, title, "
                    "chunk_index, chunk_text, token_estimate, content_hash, "
                    "created_at) VALUES (?,?,?,?,?,?,?,?)",
                    row,
                )
                jsonl_fp.write(json.dumps({
                    "document_id":    int(doc_id),
                    "source_url":     url,
                    "title":          title or "",
                    "chunk_index":    chunk_idx,
                    "chunk_text":     indexed_text,
                    "token_estimate": _estimate_tokens(indexed_text),
                    "content_hash":   h,
                }, ensure_ascii=False) + "\n")
                chunk_idx += 1
                n_chunks += 1

        conn.commit()
    finally:
        jsonl_fp.close()

    print(
        f"[INDEX] Chunked: documents={n_docs} chunks={n_chunks} "
        f"duplicates_skipped={n_dupes} navlike_skipped={n_navlike}"
    )
    return {
        "documents":       n_docs,
        "chunks":          n_chunks,
        "duplicates":      n_dupes,
        "navlike_skipped": n_navlike,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backend probes
# ─────────────────────────────────────────────────────────────────────────────

def _probe_embedding_backend() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def _probe_tfidf_backend() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Embedding backend
# ─────────────────────────────────────────────────────────────────────────────

def _build_embedding_index(conn: sqlite3.Connection, cfg: dict) -> dict:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    rows = conn.execute(
        "SELECT id, chunk_text FROM chunks ORDER BY id"
    ).fetchall()
    if not rows:
        return {"backend": "embedding", "n_vectors": 0}

    chunk_ids = [int(r[0]) for r in rows]
    texts     = [r[1] for r in rows]

    model_name = cfg["embedding_model"]
    print(f"[INDEX] Loading embedding model: {model_name}")
    t0 = time.monotonic()
    model = SentenceTransformer(model_name)
    print(f"[INDEX] Model loaded in {time.monotonic() - t0:.1f}s — encoding "
          f"{len(texts)} chunk(s)...")

    vectors = model.encode(
        texts,
        batch_size=cfg["embedding_batch_size"],
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype(np.float32)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMB_PATH, vectors)
    with open(CHUNK_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f)
    meta = {
        "backend":     "embedding",
        "model":       model_name,
        "n_vectors":   int(vectors.shape[0]),
        "dim":         int(vectors.shape[1]),
        "built_at":    _now_iso(),
    }
    with open(INDEX_META_JS, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # Remove any stale tfidf artefacts from a previous build.
    for p in (TFIDF_VEC_PATH, TFIDF_MAT_PATH):
        if p.exists():
            p.unlink()

    print(f"[INDEX] Saved embeddings shape={vectors.shape} → {EMB_PATH.name}")
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# Search-time cache (model + vectors loaded once, reused for every query)
# ─────────────────────────────────────────────────────────────────────────────
# Without this cache the embedding model was reloaded for every question
# (~3–5 seconds extra per question on Windows CPU). With it, the second
# question and beyond complete in ≈100 ms of search work.

_emb_cache: dict = {}      # {"vectors": np.ndarray, "ids": list[int], "model": SentenceTransformer, "meta": dict}
_tfidf_cache: dict = {}    # {"vectorizer": ..., "matrix": ..., "ids": list[int]}


def warmup() -> str:
    """
    Pre-load the active backend artefacts so the first user question is fast.
    Safe to call from a background thread at startup. Returns the active
    backend name ("embedding", "tfidf", or "" if no index).
    """
    backend = _detect_active_backend()
    try:
        if backend == "embedding":
            _ensure_embedding_loaded()
        elif backend == "tfidf":
            _ensure_tfidf_loaded()
    except Exception as exc:
        print(f"[INDEX] warmup failed: {exc}")
    return backend


def _ensure_embedding_loaded() -> bool:
    """Load embeddings + model into _emb_cache once. Idempotent."""
    if _emb_cache:
        return True
    if not (EMB_PATH.exists() and CHUNK_IDS_PATH.exists()
            and INDEX_META_JS.exists()):
        return False
    import numpy as np
    from sentence_transformers import SentenceTransformer

    vectors = np.load(EMB_PATH)
    with open(CHUNK_IDS_PATH, "r", encoding="utf-8") as f:
        chunk_ids = json.load(f)
    with open(INDEX_META_JS, "r", encoding="utf-8") as f:
        meta = json.load(f)
    model_name = meta.get("model", _INDEX_DEFAULTS["embedding_model"])
    print(f"[INDEX] warming embedding cache ({len(chunk_ids)} vectors, "
          f"model={model_name})...")
    t0 = time.monotonic()
    model = SentenceTransformer(model_name)
    print(f"[INDEX] embedding cache ready in {time.monotonic() - t0:.1f}s")
    _emb_cache["vectors"] = vectors
    _emb_cache["ids"]     = chunk_ids
    _emb_cache["meta"]    = meta
    _emb_cache["model"]   = model
    return True


def _ensure_tfidf_loaded() -> bool:
    if _tfidf_cache:
        return True
    if not (TFIDF_VEC_PATH.exists() and TFIDF_MAT_PATH.exists()
            and CHUNK_IDS_PATH.exists()):
        return False
    with open(TFIDF_VEC_PATH, "rb") as f:
        vectorizer = pickle.load(f)
    with open(TFIDF_MAT_PATH, "rb") as f:
        matrix = pickle.load(f)
    with open(CHUNK_IDS_PATH, "r", encoding="utf-8") as f:
        chunk_ids = json.load(f)
    _tfidf_cache["vectorizer"] = vectorizer
    _tfidf_cache["matrix"]     = matrix
    _tfidf_cache["ids"]        = chunk_ids
    print(f"[INDEX] tfidf cache ready ({len(chunk_ids)} vectors)")
    return True


def reset_caches() -> None:
    _emb_cache.clear()
    _tfidf_cache.clear()


def _search_embedding(query: str, top_k: int) -> list[dict]:
    import numpy as np

    if not _ensure_embedding_loaded():
        return []
    vectors  : Any = _emb_cache["vectors"]
    chunk_ids: list = _emb_cache["ids"]
    model         = _emb_cache["model"]

    q = model.encode(
        [query],
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)[0]
    sims = vectors @ q  # cosine because both are L2-normed
    if top_k <= 0:
        top_k = 1
    top_idx = np.argsort(-sims)[:top_k]

    return [
        {"chunk_id": int(chunk_ids[i]), "score": float(sims[i])}
        for i in top_idx
    ]


# ─────────────────────────────────────────────────────────────────────────────
# TF-IDF backend
# ─────────────────────────────────────────────────────────────────────────────

def _build_tfidf_index(conn: sqlite3.Connection, cfg: dict) -> dict:
    from sklearn.feature_extraction.text import TfidfVectorizer

    rows = conn.execute(
        "SELECT id, chunk_text FROM chunks ORDER BY id"
    ).fetchall()
    if not rows:
        return {"backend": "tfidf", "n_vectors": 0}

    chunk_ids = [int(r[0]) for r in rows]
    texts     = [r[1] for r in rows]

    vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.95,
        lowercase=True,
        strip_accents="unicode",
    )
    matrix = vectorizer.fit_transform(texts)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(TFIDF_VEC_PATH, "wb") as f:
        pickle.dump(vectorizer, f)
    with open(TFIDF_MAT_PATH, "wb") as f:
        pickle.dump(matrix, f)
    with open(CHUNK_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f)
    meta = {
        "backend":   "tfidf",
        "n_vectors": int(matrix.shape[0]),
        "vocab":     int(matrix.shape[1]),
        "built_at":  _now_iso(),
    }
    with open(INDEX_META_JS, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    if EMB_PATH.exists():
        EMB_PATH.unlink()

    print(f"[INDEX] TF-IDF matrix shape={matrix.shape} → {TFIDF_MAT_PATH.name}")
    return meta


def _search_tfidf(query: str, top_k: int) -> list[dict]:
    if not _ensure_tfidf_loaded():
        return []
    vectorizer = _tfidf_cache["vectorizer"]
    matrix     = _tfidf_cache["matrix"]
    chunk_ids  = _tfidf_cache["ids"]

    from sklearn.metrics.pairwise import linear_kernel
    import numpy as np

    q = vectorizer.transform([query])
    sims = linear_kernel(q, matrix).ravel()
    if top_k <= 0:
        top_k = 1
    top_idx = np.argsort(-sims)[:top_k]
    return [
        {"chunk_id": int(chunk_ids[i]), "score": float(sims[i])}
        for i in top_idx
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def _detect_active_backend() -> str:
    """Inspect existing index files to know which backend was last built."""
    if INDEX_META_JS.exists():
        try:
            with open(INDEX_META_JS, "r", encoding="utf-8") as f:
                m = json.load(f)
            return m.get("backend", "")
        except Exception:
            pass
    if EMB_PATH.exists():
        return "embedding"
    if TFIDF_MAT_PATH.exists():
        return "tfidf"
    return ""


def _hydrate_results(hits: list[dict]) -> list[dict]:
    """Look up chunk metadata from SQLite for each hit."""
    if not hits:
        return []
    if not DB_PATH.exists():
        return []
    ids = [h["chunk_id"] for h in hits]
    placeholders = ",".join("?" for _ in ids)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            f"SELECT id, source_url, title, chunk_text FROM chunks "
            f"WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    finally:
        conn.close()
    by_id = {int(r[0]): r for r in rows}
    out: list[dict] = []
    for h in hits:
        r = by_id.get(int(h["chunk_id"]))
        if r is None:
            continue
        out.append({
            "chunk_id":   int(r[0]),
            "score":      round(float(h["score"]), 4),
            "title":      r[2] or "",
            "source_url": r[1] or "",
            "chunk_text": r[3] or "",
        })
    return out


def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    """
    Search the local knowledge index. Stage 3 will call this.

    Returns up to `top_k` dicts with: chunk_id, score, title, source_url,
    chunk_text. Empty list if no index is available — does not raise.
    """
    if not query or not isinstance(query, str):
        return []
    backend = _detect_active_backend()
    if not backend:
        print("[INDEX] No index found. Run: python knowledge_index.py --rebuild")
        return []

    if backend == "embedding":
        try:
            hits = _search_embedding(query, top_k)
        except Exception as exc:
            print(f"[INDEX] embedding search failed: {exc} — trying tfidf.")
            hits = _search_tfidf(query, top_k)
    else:
        hits = _search_tfidf(query, top_k)

    return _hydrate_results(hits)


# ─────────────────────────────────────────────────────────────────────────────
# Build / rebuild orchestration
# ─────────────────────────────────────────────────────────────────────────────

def _clear_index_files() -> None:
    if INDEX_DIR.exists():
        for p in INDEX_DIR.iterdir():
            try:
                p.unlink()
            except Exception:
                pass


def rebuild_all(cfg: dict) -> dict:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    conn = _connect()
    report: dict = {}
    try:
        report.update(build_chunks(conn, cfg))
        if report["chunks"] == 0:
            print("[INDEX] No chunks produced — skipping vector index.")
            _set_meta(conn, "last_rebuild_at", _now_iso())
            _set_meta(conn, "backend", "none")
            conn.commit()
            return {**report, "backend": "none"}

        # Clear stale index artefacts before writing the new one.
        _clear_index_files()

        preference = (cfg.get("backend_preference") or "embedding").lower()
        backend_used = "tfidf"
        meta: dict = {}

        if preference == "embedding" and _probe_embedding_backend():
            try:
                meta = _build_embedding_index(conn, cfg)
                backend_used = "embedding"
            except Exception as exc:
                print(f"[INDEX] embedding backend failed: {exc} — "
                      "falling back to TF-IDF.")
                _clear_index_files()
                meta = {}

        if not meta:
            if not _probe_tfidf_backend():
                raise RuntimeError(
                    "Neither sentence-transformers nor scikit-learn is "
                    "available. Install one: pip install scikit-learn"
                )
            meta = _build_tfidf_index(conn, cfg)
            backend_used = "tfidf"

        _set_meta(conn, "last_rebuild_at", meta.get("built_at", _now_iso()))
        _set_meta(conn, "backend", backend_used)
        _set_meta(conn, "n_vectors", str(meta.get("n_vectors", 0)))
        if "model" in meta:
            _set_meta(conn, "embedding_model", meta["model"])
        conn.commit()
        report["backend"] = backend_used
        report["meta"] = meta
        print(f"[INDEX] Rebuild complete — backend={backend_used} "
              f"vectors={meta.get('n_vectors', 0)}")
        return report
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

def print_status() -> None:
    print("=" * 60)
    print(f"  KNOWLEDGE_DIR : {KNOWLEDGE_DIR}")
    print(f"  index dir     : {INDEX_DIR} "
          f"({'exists' if INDEX_DIR.exists() else 'missing'})")
    if not DB_PATH.exists():
        print("  knowledge.sqlite missing — run knowledge_crawler.py --crawl")
        print("=" * 60)
        return

    conn = sqlite3.connect(str(DB_PATH))
    try:
        # Make sure auxiliary tables exist before querying
        conn.executescript(_SCHEMA_EXTRA)
        n_docs   = conn.execute("SELECT COUNT(1) FROM documents").fetchone()[0]
        n_chunks = conn.execute("SELECT COUNT(1) FROM chunks").fetchone()[0]
        backend  = _get_meta(conn, "backend", "(not built)")
        last_at  = _get_meta(conn, "last_rebuild_at", "(never)")
        nvec     = _get_meta(conn, "n_vectors", "0")
        model    = _get_meta(conn, "embedding_model", "")
    finally:
        conn.close()

    print(f"  documents in SQLite : {n_docs}")
    print(f"  chunks in SQLite    : {n_chunks}")
    print(f"  index backend       : {backend}")
    if model:
        print(f"  embedding model     : {model}")
    print(f"  vectors stored      : {nvec}")
    print(f"  last rebuild        : {last_at}")
    print(f"  chunks.jsonl        : "
          f"{'OK' if CHUNKS_JSONL.exists() else 'missing'} "
          f"({CHUNKS_JSONL.stat().st_size if CHUNKS_JSONL.exists() else 0} bytes)")
    if INDEX_META_JS.exists():
        try:
            with open(INDEX_META_JS, "r", encoding="utf-8") as f:
                meta = json.load(f)
            print(f"  vector_index/meta   : {meta}")
        except Exception:
            pass
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _print_search_results(query: str, results: list[dict]) -> None:
    print(f'\nQuery: {query!r}')
    if not results:
        print("  (no results)")
        return
    for rank, r in enumerate(results, start=1):
        snippet = (r["chunk_text"] or "").replace("\n", " ").strip()
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        print(f"  {rank}. score={r['score']:.4f} chunk_id={r['chunk_id']}")
        print(f"      title : {r['title']}")
        print(f"      url   : {r['source_url']}")
        print(f"      text  : {snippet}")


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Stage 2 indexer for the university knowledge base."
    )
    p.add_argument("--rebuild", action="store_true",
                   help="rebuild chunks and the search index from documents")
    p.add_argument("--status",  action="store_true",
                   help="print status of chunks and index")
    p.add_argument("--search",  default=None,
                   help="search the index with the given query string")
    p.add_argument("--top-k",   type=int, default=None,
                   help="number of search results to return")
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = _build_argparser().parse_args(argv)
    if not (args.rebuild or args.status or args.search):
        _build_argparser().print_help()
        return 0

    cfg = _load_indexing_cfg()

    if args.rebuild:
        try:
            rebuild_all(cfg)
        except FileNotFoundError as exc:
            print(f"[ERROR] {exc}")
            return 2

    if args.search:
        if not DB_PATH.exists():
            print("[ERROR] knowledge.sqlite missing — run "
                  "knowledge_crawler.py --crawl first.")
            return 2
        if not _detect_active_backend():
            print("[ERROR] No index found. Run: "
                  "python knowledge_index.py --rebuild")
            return 2
        top_k = args.top_k or cfg["top_k_default"]
        results = search_knowledge(args.search, top_k=top_k)
        _print_search_results(args.search, results)

    if args.status:
        print_status()

    return 0


if __name__ == "__main__":
    sys.exit(main())
