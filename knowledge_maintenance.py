"""
knowledge_maintenance.py — Stage 5 of UNIVERSITY_KNOWLEDGE_PLAN.md.

A senior-friendly maintenance CLI for the university knowledge base. It
*reuses* (does not duplicate) the existing modules:

  knowledge_crawler.py   crawl(), reset_state(), load_config()
  knowledge_index.py     rebuild_all(), search_knowledge(), _load_indexing_cfg()
  knowledge_qa.py        answer_university_question()

Usage:
  python knowledge_maintenance.py --status
  python knowledge_maintenance.py --update                 # crawl → index → smoke
  python knowledge_maintenance.py --update --max-pages 50
  python knowledge_maintenance.py --crawl-only --max-pages 30
  python knowledge_maintenance.py --index-only
  python knowledge_maintenance.py --test-only
  python knowledge_maintenance.py --update --reset         # full clean rebuild

Idempotency rules:
  * --update and --crawl-only NEVER drop existing data unless you also pass
    --reset (which is forwarded to the crawler).
  * --index-only always rebuilds the chunks + vector index from the current
    documents (this is safe; rebuild_all is idempotent by design).
  * sources.yaml is never written by this script. .env is never written.
  * Robot runtime, ESP32 protocol, movement and face recognition code are
    not touched.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.resolve()
KNOWLEDGE_DIR = PROJECT_ROOT / "amir_temur_knowledge"
SOURCES_YAML  = KNOWLEDGE_DIR / "sources.yaml"
RAW_JSONL     = KNOWLEDGE_DIR / "raw_pages.jsonl"
CHUNKS_JSONL  = KNOWLEDGE_DIR / "chunks.jsonl"
DB_PATH       = KNOWLEDGE_DIR / "knowledge.sqlite"
VECTOR_DIR    = KNOWLEDGE_DIR / "vector_index"


# Smoke-test questions used by --test-only and the tail of --update.
SMOKE_QUESTIONS: list[str] = [
    "Universitet qayerda joylashgan?",
    "Innovatsion universiteti haqida nima bilasan?",
    "Qabul haqida ma'lumot bering",
]


# ─────────────────────────────────────────────────────────────────────────────
# Small UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hr(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERR]  {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

def _file_state(p: Path) -> str:
    if not p.exists():
        return "missing"
    try:
        size = p.stat().st_size
    except Exception:
        size = -1
    return f"OK ({size} bytes)"


def status() -> dict:
    """Return a dict describing the current knowledge base state."""
    info: dict[str, Any] = {
        "knowledge_dir":      str(KNOWLEDGE_DIR),
        "sources_yaml":       _file_state(SOURCES_YAML),
        "raw_pages_jsonl":    _file_state(RAW_JSONL),
        "chunks_jsonl":       _file_state(CHUNKS_JSONL),
        "knowledge_sqlite":   _file_state(DB_PATH),
        "vector_index_dir":   "missing",
    }
    if VECTOR_DIR.exists():
        files = sorted(p.name for p in VECTOR_DIR.iterdir())
        info["vector_index_dir"] = f"OK ({len(files)} files)"
        info["vector_index_files"] = files

    # Domain / source-config summary (read-only)
    try:
        from knowledge_crawler import load_config  # type: ignore
        cfg = load_config()
        info["start_urls"]       = cfg.get("start_urls", [])
        info["allowed_domains"]  = cfg.get("allowed_domains", [])
        info["max_pages_config"] = cfg.get("max_pages", "?")
    except FileNotFoundError as exc:
        info["sources_error"] = str(exc)
    except Exception as exc:
        info["sources_error"] = f"failed to read sources.yaml: {exc}"

    # Document / chunk counts via SQLite
    if DB_PATH.exists():
        import sqlite3
        try:
            from knowledge_index import _SCHEMA_EXTRA  # type: ignore
        except Exception:
            _SCHEMA_EXTRA = ""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            try:
                if _SCHEMA_EXTRA:
                    conn.executescript(_SCHEMA_EXTRA)
                info["documents"] = conn.execute(
                    "SELECT COUNT(1) FROM documents"
                ).fetchone()[0]
                info["chunks"] = conn.execute(
                    "SELECT COUNT(1) FROM chunks"
                ).fetchone()[0]
                last_doc = conn.execute(
                    "SELECT MAX(fetched_at) FROM documents"
                ).fetchone()[0]
                info["last_crawl_at"] = last_doc or "(never)"
                row = conn.execute(
                    "SELECT value FROM index_meta WHERE key='last_rebuild_at'"
                ).fetchone()
                info["last_index_rebuild_at"] = row[0] if row else "(never)"
                row = conn.execute(
                    "SELECT value FROM index_meta WHERE key='backend'"
                ).fetchone()
                info["index_backend"] = row[0] if row else "(none)"
            finally:
                conn.close()
        except Exception as exc:
            info["sqlite_error"] = str(exc)

    return info


def print_status_report() -> None:
    info = status()
    _hr("UNIVERSITY KNOWLEDGE BASE — STATUS")
    print(f"  knowledge_dir         : {info['knowledge_dir']}")
    print(f"  sources.yaml          : {info['sources_yaml']}")
    print(f"  raw_pages.jsonl       : {info['raw_pages_jsonl']}")
    print(f"  chunks.jsonl          : {info['chunks_jsonl']}")
    print(f"  knowledge.sqlite      : {info['knowledge_sqlite']}")
    print(f"  vector_index/         : {info['vector_index_dir']}")
    if "vector_index_files" in info:
        for f in info["vector_index_files"]:
            print(f"      - {f}")
    if "sources_error" in info:
        print(f"  sources error         : {info['sources_error']}")
    else:
        print(f"  start_urls            : {info.get('start_urls')}")
        print(f"  allowed_domains       : {info.get('allowed_domains')}")
        print(f"  max_pages (config)    : {info.get('max_pages_config')}")
    if "documents" in info:
        print(f"  documents in SQLite   : {info['documents']}")
        print(f"  chunks in SQLite      : {info['chunks']}")
        print(f"  index backend         : {info.get('index_backend','?')}")
        print(f"  last crawl at         : {info.get('last_crawl_at','?')}")
        print(f"  last index rebuild    : {info.get('last_index_rebuild_at','?')}")
    if "sqlite_error" in info:
        print(f"  sqlite_error          : {info['sqlite_error']}")
    print("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# Step: crawl
# ─────────────────────────────────────────────────────────────────────────────

def step_crawl(*, max_pages: int | None, do_reset: bool) -> dict:
    """Run the existing crawler. Returns a stats dict (or {'skipped': True})."""
    _hr("STEP 1 — CRAWL")
    try:
        from knowledge_crawler import crawl, load_config, reset_state
    except Exception as exc:
        _err(f"cannot import knowledge_crawler: {exc}")
        return {"error": str(exc)}

    if do_reset:
        _warn("--reset given: clearing previous documents and crawl_log "
              "before crawl.")
        try:
            reset_state()
            _ok("crawler state reset.")
        except Exception as exc:
            _err(f"reset_state failed: {exc}")
            return {"error": str(exc)}

    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        _err(str(exc))
        return {"error": str(exc)}
    except Exception as exc:
        _err(f"cannot load sources.yaml: {exc}")
        return {"error": str(exc)}

    t0 = time.monotonic()
    try:
        stats = crawl(cfg, max_pages_override=max_pages)
    except KeyboardInterrupt:
        _warn("crawl interrupted by user.")
        return {"interrupted": True}
    except Exception as exc:
        _err(f"crawl crashed: {exc}")
        return {"error": str(exc)}
    elapsed = time.monotonic() - t0

    fetched = getattr(stats, "fetched", "?")
    stored  = getattr(stats, "stored", "?")
    skipped = getattr(stats, "skipped", "?")
    errors  = getattr(stats, "errors", "?")
    _ok(f"crawl done in {elapsed:.1f}s — fetched={fetched} "
        f"stored={stored} skipped={skipped} errors={errors}")
    return {
        "fetched": fetched, "stored": stored,
        "skipped": skipped, "errors": errors,
        "elapsed_s": round(elapsed, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step: index
# ─────────────────────────────────────────────────────────────────────────────

def step_index() -> dict:
    """Rebuild chunks + vector index using the existing indexer module."""
    _hr("STEP 2 — INDEX")
    try:
        from knowledge_index import rebuild_all, _load_indexing_cfg  # type: ignore
    except Exception as exc:
        _err(f"cannot import knowledge_index: {exc}")
        return {"error": str(exc)}

    cfg = _load_indexing_cfg()
    t0 = time.monotonic()
    try:
        report = rebuild_all(cfg)
    except FileNotFoundError as exc:
        _err(str(exc))
        return {"error": str(exc)}
    except Exception as exc:
        _err(f"index rebuild crashed: {exc}")
        return {"error": str(exc)}
    elapsed = time.monotonic() - t0

    backend = report.get("backend", "?")
    n_chunks = report.get("chunks", "?")
    duplicates = report.get("duplicates", "?")
    _ok(f"index built in {elapsed:.1f}s — backend={backend} "
        f"chunks={n_chunks} duplicates_skipped={duplicates}")
    return {
        "backend": backend,
        "chunks": n_chunks,
        "duplicates": duplicates,
        "elapsed_s": round(elapsed, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step: smoke tests
# ─────────────────────────────────────────────────────────────────────────────

def step_smoke_tests(questions: list[str] | None = None) -> dict:
    """Ask a small set of grounded questions and report what came back.

    Never raises — failures are reported as warnings.
    """
    _hr("STEP 3 — QA SMOKE TESTS")
    qs = list(questions or SMOKE_QUESTIONS)

    try:
        from knowledge_qa import answer_university_question
    except Exception as exc:
        _err(f"cannot import knowledge_qa: {exc}")
        return {"error": str(exc)}

    results: list[dict] = []
    answered_count = 0
    for q in qs:
        print(f"\n  Q: {q}")
        try:
            r = answer_university_question(q)
        except Exception as exc:
            _warn(f"     QA crashed for {q!r}: {exc}")
            results.append({"q": q, "answered": False,
                            "answer": "", "engine": "error",
                            "reason": f"exception:{exc}"})
            continue
        ans      = (r.get("answer") or "").strip()
        engine   = r.get("engine", "?")
        reason   = r.get("reason", "") or ""
        answered = bool(r.get("answered"))
        if answered:
            answered_count += 1
        snippet = ans if len(ans) <= 160 else ans[:157] + "..."
        marker = "[OK]" if answered else "[WARN]"
        print(f"  {marker} answered={answered} engine={engine} "
              f"reason={reason!r}")
        print(f"        A: {snippet}")
        sources = r.get("sources") or []
        for s in sources[:2]:
            print(f"        - {s.get('score','?')}  "
                  f"{s.get('title','')[:50]}  {s.get('source_url','')}")
        results.append({
            "q": q,
            "answered": answered,
            "answer": ans,
            "engine": engine,
            "reason": reason,
            "sources_count": len(sources),
        })

    summary = f"{answered_count}/{len(qs)} questions answered."
    if answered_count == len(qs):
        _ok(summary)
    elif answered_count == 0:
        _warn(summary + " The knowledge base may be empty or out of date.")
    else:
        _warn(summary)
    return {"results": results, "answered": answered_count, "total": len(qs)}


# ─────────────────────────────────────────────────────────────────────────────
# Update workflow
# ─────────────────────────────────────────────────────────────────────────────

def workflow_update(*, max_pages: int | None, do_reset: bool) -> int:
    """Full update: crawl → index → smoke tests. Returns process exit code."""
    _hr("UNIVERSITY KNOWLEDGE — UPDATE WORKFLOW")
    print(f"  max_pages override : {max_pages}")
    print(f"  --reset            : {do_reset}")

    crawl_report = step_crawl(max_pages=max_pages, do_reset=do_reset)
    if "error" in crawl_report:
        return 2

    index_report = step_index()
    if "error" in index_report:
        return 3

    smoke = step_smoke_tests()

    _hr("FINAL REPORT")
    print(f"  crawl   : {crawl_report}")
    print(f"  index   : {index_report}")
    print(f"  smoke   : {smoke.get('answered','?')}/{smoke.get('total','?')} "
          f"questions answered")
    print("=" * 70)

    # Workflow is "successful" as soon as crawl + index finished. If smoke
    # says 0/N answered, surface it as a warning but not an error — the
    # robot will simply return the configured no-answer text at runtime.
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Maintenance CLI for the university knowledge base.",
    )
    p.add_argument("--status",     action="store_true",
                   help="show knowledge base status and exit")
    p.add_argument("--update",     action="store_true",
                   help="run the full update: crawl → index → smoke tests")
    p.add_argument("--crawl-only", action="store_true",
                   help="run only the crawler")
    p.add_argument("--index-only", action="store_true",
                   help="run only the index rebuild")
    p.add_argument("--test-only",  action="store_true",
                   help="run only the QA smoke tests")
    p.add_argument("--max-pages",  type=int, default=None,
                   help="optional max_pages override for the crawler")
    p.add_argument("--reset",      action="store_true",
                   help="reset crawler state before crawling "
                        "(only with --update or --crawl-only)")
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
    actions = (args.status, args.update, args.crawl_only,
               args.index_only, args.test_only)
    if not any(actions):
        _build_argparser().print_help()
        return 0

    # Status is a read-only inspector; safe to combine.
    if args.status:
        print_status_report()

    if args.update:
        rc = workflow_update(max_pages=args.max_pages, do_reset=args.reset)
        if rc != 0:
            return rc

    if args.crawl_only and not args.update:
        report = step_crawl(max_pages=args.max_pages, do_reset=args.reset)
        if "error" in report:
            return 2

    if args.index_only and not args.update:
        if args.reset:
            _warn("--reset is ignored for --index-only "
                  "(rebuild_all is already a clean rebuild).")
        report = step_index()
        if "error" in report:
            return 3

    if args.test_only and not args.update:
        step_smoke_tests()

    return 0


if __name__ == "__main__":
    sys.exit(main())
