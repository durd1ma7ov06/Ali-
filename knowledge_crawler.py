"""
knowledge_crawler.py — Stage 1 of the University Knowledge RAG plan.

Crawls the official university website inside an allow-list of domains,
extracts clean visible text from HTML pages, and stores results in:

  university_knowledge/raw_pages.jsonl     (append-only JSONL, one page per line)
  university_knowledge/knowledge.sqlite    (documents + crawl_log tables)

NO chunking, NO embeddings, NO AI calls — this module only fetches and
stores raw cleaned text. Stages 2+ build on top of these files.

CLI:
  python knowledge_crawler.py --crawl              # run a crawl
  python knowledge_crawler.py --crawl --max-pages 50
  python knowledge_crawler.py --reset              # clear state
  python knowledge_crawler.py --status             # print storage summary
  python knowledge_crawler.py --reset --crawl --max-pages 20

Dependencies: requests, beautifulsoup4, PyYAML, stdlib (sqlite3, hashlib, ...)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' is required. Install with: pip install requests")
    sys.exit(2)

try:
    import yaml
except ImportError:
    print("[ERROR] 'PyYAML' is required. Install with: pip install PyYAML")
    sys.exit(2)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("[ERROR] 'beautifulsoup4' is required. "
          "Install with: pip install beautifulsoup4")
    sys.exit(2)


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.resolve()
KNOWLEDGE_DIR = PROJECT_ROOT / "amir_temur_knowledge"
SOURCES_PATH  = KNOWLEDGE_DIR / "sources.yaml"
RAW_JSONL     = KNOWLEDGE_DIR / "raw_pages.jsonl"
DB_PATH       = KNOWLEDGE_DIR / "knowledge.sqlite"


# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────

DEFAULTS: dict = {
    "start_urls":            [],
    "allowed_domains":       [],
    "exclude_patterns":      [],
    "exclude_extensions":    [],
    "max_pages":             300,
    "request_delay_seconds": 0.3,
    "timeout_seconds":       15,
    "user_agent":            "UriuKnowledgeBot/1.0 (+https://uriu.uz)",
    "min_text_chars":        80,
}


def load_config(path: Path = SOURCES_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"sources.yaml not found at {path}. "
            "Create it before running the crawler."
        )
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = {**DEFAULTS, **raw}

    # Light validation / normalisation
    if not isinstance(cfg["start_urls"], list) or not cfg["start_urls"]:
        raise ValueError("sources.yaml: 'start_urls' must be a non-empty list.")
    if not isinstance(cfg["allowed_domains"], list) or not cfg["allowed_domains"]:
        raise ValueError("sources.yaml: 'allowed_domains' must be non-empty.")
    cfg["allowed_domains"]    = [d.strip().lower() for d in cfg["allowed_domains"]]
    cfg["exclude_patterns"]   = [str(p).lower() for p in cfg["exclude_patterns"]]
    cfg["exclude_extensions"] = [str(e).lower().lstrip(".")
                                 for e in cfg["exclude_extensions"]]
    cfg["max_pages"]             = int(cfg["max_pages"])
    cfg["request_delay_seconds"] = float(cfg["request_delay_seconds"])
    cfg["timeout_seconds"]       = float(cfg["timeout_seconds"])
    cfg["min_text_chars"]        = int(cfg["min_text_chars"])
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# URL helpers
# ─────────────────────────────────────────────────────────────────────────────

# Tracking / session params we drop while normalising URLs.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS_EXACT = {
    "fbclid", "gclid", "yclid", "mc_cid", "mc_eid",
    "_ga", "_gl", "ref", "ref_src", "share",
}


def normalize_url(url: str, base: str | None = None) -> str:
    """
    Resolve relative → absolute, drop fragments, lower-case host, strip
    common tracking query params, normalise trailing slash on bare hosts.
    """
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)  # drop "#fragment"

    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return ""

    # Lower-case scheme + host. Keep path/query case-sensitive.
    scheme = p.scheme.lower()
    if scheme not in ("http", "https"):
        return ""
    netloc = p.netloc.lower()

    # Strip tracking params
    if p.query:
        kept = []
        for kv in p.query.split("&"):
            if not kv:
                continue
            key = kv.split("=", 1)[0].lower()
            if key in _TRACKING_PARAMS_EXACT:
                continue
            if any(key.startswith(pref) for pref in _TRACKING_PARAM_PREFIXES):
                continue
            kept.append(kv)
        query = "&".join(kept)
    else:
        query = ""

    path = p.path or "/"
    return urlunparse((scheme, netloc, path, p.params, query, ""))


def host_matches_allowed(url: str, allowed: list[str]) -> bool:
    host = urlparse(url).netloc.lower()
    if not host:
        return False
    for d in allowed:
        d = d.lower()
        if host == d or host.endswith("." + d):
            return True
    return False


_NON_HTTP_SCHEME = re.compile(
    r"^(mailto|tel|javascript|data|sms|whatsapp|skype|viber|geo|ftp):",
    re.IGNORECASE,
)


def url_excluded_by_pattern(url: str, patterns: list[str]) -> str | None:
    """Return the matched pattern if the URL is excluded, else None."""
    low = url.lower()
    for p in patterns:
        if p and p in low:
            return p
    return None


def url_excluded_by_extension(url: str, exts: list[str]) -> str | None:
    """Return the matched extension if the URL points to a skipped file type."""
    path = urlparse(url).path.lower()
    if "." not in path.rsplit("/", 1)[-1]:
        return None
    ext = path.rsplit(".", 1)[-1]
    if ext in exts:
        return ext
    return None


# ─────────────────────────────────────────────────────────────────────────────
# HTML cleaning / text extraction
# ─────────────────────────────────────────────────────────────────────────────

# Tags whose entire subtree is dropped before text extraction.
_STRIP_TAGS = (
    "script", "style", "noscript",
    "nav", "footer", "header", "aside",
    "form", "iframe", "svg", "canvas",
    "menu", "menuitem",
)

# Common navigation/menu CSS class/id substrings we also strip.
_MENU_CLASS_HINTS = (
    "menu", "navbar", "nav-bar", "navigation", "sidebar",
    "breadcrumb", "footer", "header", "topbar", "top-bar",
    "cookie", "popup", "modal", "social",
)

_WS_RE = re.compile(r"[ \t\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


def _strip_menu_like_blocks(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        try:
            classes = " ".join(tag.get("class") or [])
            tag_id = tag.get("id") or ""
            blob = f"{classes} {tag_id}".lower()
            if any(hint in blob for hint in _MENU_CLASS_HINTS):
                tag.decompose()
        except Exception:
            continue


def extract_clean_text(html: str) -> tuple[str, str]:
    """
    Parse HTML and return (title, cleaned_text).
    Removes script/style/nav/footer/menu, collapses whitespace.
    Multi-language text is preserved as-is (no translation).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

    # Drop noise subtrees
    for tag_name in _STRIP_TAGS:
        for t in soup.find_all(tag_name):
            t.decompose()

    # Drop blocks whose class/id smells like menu/footer/etc.
    _strip_menu_like_blocks(soup)

    # Prefer <main> / <article> if present, else fall back to <body>.
    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = root.get_text(separator="\n", strip=True)

    # Collapse whitespace
    text = _WS_RE.sub(" ", text)
    # Trim trailing spaces on each line
    text = "\n".join(line.strip() for line in text.split("\n"))
    # Drop empty lines beyond 2 in a row
    text = _NL_RE.sub("\n\n", text)
    text = text.strip()

    return title, text


def discover_links(html: str, base_url: str) -> list[str]:
    """Return all absolute URLs found in <a href> tags inside the page."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        if not raw:
            continue
        if _NON_HTTP_SCHEME.match(raw):
            continue
        norm = normalize_url(raw, base=base_url)
        if norm:
            out.append(norm)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Storage: SQLite + JSONL
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE NOT NULL,
    title        TEXT,
    text         TEXT,
    fetched_at   TEXT,
    content_hash TEXT,
    status_code  INTEGER
);

CREATE INDEX IF NOT EXISTS ix_documents_hash ON documents(content_hash);

CREATE TABLE IF NOT EXISTS crawl_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url        TEXT,
    status     TEXT,
    message    TEXT,
    created_at TEXT
);
"""


def _connect() -> sqlite3.Connection:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(_SCHEMA)
    return conn


def log_event(conn: sqlite3.Connection, url: str, status: str,
              message: str = "") -> None:
    conn.execute(
        "INSERT INTO crawl_log(url, status, message, created_at) "
        "VALUES (?, ?, ?, ?)",
        (url, status, message[:1000] if message else "",
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


def upsert_document(conn: sqlite3.Connection, doc: dict) -> bool:
    """Insert or replace a document. Returns True if a new row was created."""
    cur = conn.execute(
        "SELECT id FROM documents WHERE url=?", (doc["url"],)
    ).fetchone()
    is_new = cur is None
    conn.execute(
        "INSERT INTO documents(url, title, text, fetched_at, "
        "content_hash, status_code) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(url) DO UPDATE SET "
        "title=excluded.title, text=excluded.text, "
        "fetched_at=excluded.fetched_at, content_hash=excluded.content_hash, "
        "status_code=excluded.status_code",
        (doc["url"], doc["title"], doc["text"],
         doc["fetched_at"], doc["content_hash"], doc["status_code"]),
    )
    return is_new


def append_jsonl(doc: dict) -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    with open(RAW_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Reset / status
# ─────────────────────────────────────────────────────────────────────────────

def reset_state() -> None:
    """Clear raw_pages.jsonl, documents and crawl_log."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_JSONL.exists():
        RAW_JSONL.unlink()
        print(f"[RESET] removed {RAW_JSONL}")
    conn = _connect()
    try:
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM crawl_log")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN "
                     "('documents','crawl_log')")
        conn.commit()
        print(f"[RESET] cleared documents and crawl_log in {DB_PATH}")
    finally:
        conn.close()


def print_status() -> None:
    if not DB_PATH.exists():
        print("[STATUS] knowledge.sqlite does not exist yet. "
              "Run with --crawl to create it.")
        return

    conn = _connect()
    try:
        n_docs = conn.execute("SELECT COUNT(1) FROM documents").fetchone()[0]
        n_log  = conn.execute("SELECT COUNT(1) FROM crawl_log").fetchone()[0]
        last = conn.execute(
            "SELECT MAX(fetched_at) FROM documents"
        ).fetchone()[0]
        sample = [r[0] for r in conn.execute(
            "SELECT url FROM documents ORDER BY id DESC LIMIT 5"
        ).fetchall()]

        # Skip / error counts
        skip_rows = conn.execute(
            "SELECT status, COUNT(1) FROM crawl_log GROUP BY status"
        ).fetchall()
        skip_summary = {s: c for s, c in skip_rows}
    finally:
        conn.close()

    print("=" * 60)
    print(f"  KNOWLEDGE_DIR  : {KNOWLEDGE_DIR}")
    print(f"  raw_pages.jsonl: {'OK' if RAW_JSONL.exists() else 'missing'} "
          f"({RAW_JSONL.stat().st_size if RAW_JSONL.exists() else 0} bytes)")
    print(f"  knowledge.sqlite stored documents: {n_docs}")
    print(f"  crawl_log rows                 : {n_log}")
    print(f"  last fetched_at                : {last or '(none)'}")
    if skip_summary:
        print("  status counts:")
        for k, v in sorted(skip_summary.items(), key=lambda x: -x[1]):
            print(f"    - {k}: {v}")
    print("  sample URLs:")
    for u in sample:
        print(f"    {u}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Crawler
# ─────────────────────────────────────────────────────────────────────────────

class CrawlStats:
    def __init__(self) -> None:
        self.fetched = 0
        self.stored  = 0
        self.skipped = 0
        self.errors  = 0
        self.reasons: dict[str, int] = {}

    def bump(self, key: str) -> None:
        self.reasons[key] = self.reasons.get(key, 0) + 1

    def summary(self) -> str:
        lines = [
            f"fetched={self.fetched}",
            f"stored={self.stored}",
            f"skipped={self.skipped}",
            f"errors={self.errors}",
        ]
        if self.reasons:
            top = sorted(self.reasons.items(), key=lambda x: -x[1])[:8]
            lines.append("reasons=" + ", ".join(f"{k}:{v}" for k, v in top))
        return " | ".join(lines)


def _is_html_response(resp: requests.Response) -> bool:
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "html" in ctype:
        return True
    # Some servers omit Content-Type; sniff first bytes.
    if not ctype:
        head = resp.content[:512].lstrip().lower()
        return head.startswith(b"<!doctype") or head.startswith(b"<html")
    return False


def crawl(cfg: dict, max_pages_override: int | None = None) -> CrawlStats:
    stats = CrawlStats()
    max_pages = max_pages_override or cfg["max_pages"]
    if max_pages <= 0:
        print("[CRAWL] max_pages must be positive.")
        return stats

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = _connect()

    session = requests.Session()
    session.headers.update({
        "User-Agent":      cfg["user_agent"],
        "Accept":          "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "uz,ru;q=0.9,en;q=0.8",
    })

    seen: set[str] = set()
    queue: deque[str] = deque()

    for s in cfg["start_urls"]:
        n = normalize_url(s)
        if n and n not in seen:
            seen.add(n)
            queue.append(n)

    print(f"[CRAWL] start_urls={list(cfg['start_urls'])} "
          f"allowed={cfg['allowed_domains']} max_pages={max_pages}")
    started_at = time.monotonic()

    try:
        while queue and stats.stored < max_pages:
            url = queue.popleft()

            # 1. Domain check
            if not host_matches_allowed(url, cfg["allowed_domains"]):
                stats.skipped += 1
                stats.bump("skip_off_domain")
                log_event(conn, url, "skip_off_domain", "")
                continue

            # 2. Pattern exclusion
            patt = url_excluded_by_pattern(url, cfg["exclude_patterns"])
            if patt:
                stats.skipped += 1
                stats.bump("skip_pattern")
                log_event(conn, url, "skip_pattern", f"matched:{patt}")
                continue

            # 3. Extension exclusion
            ext = url_excluded_by_extension(url, cfg["exclude_extensions"])
            if ext:
                stats.skipped += 1
                stats.bump("skip_extension")
                log_event(conn, url, "skip_extension", f"ext:{ext}")
                continue

            # 4. Fetch
            try:
                resp = session.get(url, timeout=cfg["timeout_seconds"],
                                   allow_redirects=True)
            except requests.RequestException as exc:
                stats.errors += 1
                stats.bump("fetch_error")
                log_event(conn, url, "fetch_error", str(exc))
                continue

            stats.fetched += 1

            # 5. Status / content type
            if resp.status_code >= 400:
                stats.errors += 1
                stats.bump(f"http_{resp.status_code}")
                log_event(conn, url, "http_error",
                          f"status={resp.status_code}")
                _polite_sleep(cfg)
                continue

            # Follow redirect by storing the *final* URL
            final_url = normalize_url(resp.url) or url
            if final_url != url and final_url in seen:
                # Redirected onto a URL we already processed
                stats.skipped += 1
                stats.bump("skip_redirect_seen")
                log_event(conn, url, "skip_redirect_seen", final_url)
                _polite_sleep(cfg)
                continue
            seen.add(final_url)

            if not _is_html_response(resp):
                stats.skipped += 1
                stats.bump("skip_non_html")
                log_event(conn, final_url, "skip_non_html",
                          resp.headers.get("Content-Type", ""))
                _polite_sleep(cfg)
                continue

            # 6. Decode
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                # requests defaults to ISO-8859-1 when server doesn't say.
                resp.encoding = resp.apparent_encoding or "utf-8"
            try:
                html = resp.text
            except Exception as exc:
                stats.errors += 1
                stats.bump("decode_error")
                log_event(conn, final_url, "decode_error", str(exc))
                _polite_sleep(cfg)
                continue

            # 7. Extract
            try:
                title, text = extract_clean_text(html)
            except Exception as exc:
                stats.errors += 1
                stats.bump("parse_error")
                log_event(conn, final_url, "parse_error", str(exc))
                _polite_sleep(cfg)
                continue

            if len(text) < cfg["min_text_chars"]:
                stats.skipped += 1
                stats.bump("thin_page")
                log_event(conn, final_url, "thin_page",
                          f"len={len(text)}")
                _polite_sleep(cfg)
            else:
                # 8. Persist
                content_hash = hashlib.sha256(
                    text.encode("utf-8", errors="replace")
                ).hexdigest()
                doc = {
                    "url":          final_url,
                    "title":        title or "",
                    "text":         text,
                    "fetched_at":   datetime.now(timezone.utc)
                                            .isoformat(timespec="seconds"),
                    "content_hash": content_hash,
                    "status_code":  resp.status_code,
                }
                try:
                    is_new = upsert_document(conn, doc)
                    append_jsonl(doc)
                    log_event(conn, final_url, "stored",
                              f"len={len(text)} new={is_new}")
                    stats.stored += 1
                    stats.bump("stored")
                    if stats.stored % 10 == 0:
                        elapsed = time.monotonic() - started_at
                        print(f"[CRAWL] progress stored={stats.stored} "
                              f"queue={len(queue)} elapsed={elapsed:.1f}s")
                except Exception as exc:
                    stats.errors += 1
                    stats.bump("store_error")
                    log_event(conn, final_url, "store_error", str(exc))
                conn.commit()

            # 9. Discover new links
            try:
                links = discover_links(html, final_url)
            except Exception as exc:
                links = []
                log_event(conn, final_url, "link_extract_error", str(exc))
            for link in links:
                if not link or link in seen:
                    continue
                if not host_matches_allowed(link, cfg["allowed_domains"]):
                    continue
                # Cheap pre-filter — leave deep checks to the loop above.
                if url_excluded_by_pattern(link, cfg["exclude_patterns"]):
                    continue
                if url_excluded_by_extension(link, cfg["exclude_extensions"]):
                    continue
                seen.add(link)
                queue.append(link)

            _polite_sleep(cfg)
    finally:
        conn.commit()
        conn.close()

    elapsed = time.monotonic() - started_at
    print(f"[CRAWL] done in {elapsed:.1f}s — {stats.summary()}")
    return stats


def _polite_sleep(cfg: dict) -> None:
    delay = cfg.get("request_delay_seconds", 0.0)
    if delay > 0:
        time.sleep(delay)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Stage 1 crawler for the university knowledge base."
    )
    p.add_argument("--crawl",     action="store_true",
                   help="run a crawl using sources.yaml")
    p.add_argument("--max-pages", type=int, default=None,
                   help="override max_pages from sources.yaml")
    p.add_argument("--reset",     action="store_true",
                   help="clear raw_pages.jsonl and SQLite tables before any other action")
    p.add_argument("--status",    action="store_true",
                   help="print number of stored documents and sample URLs")
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
    if not (args.crawl or args.reset or args.status):
        _build_argparser().print_help()
        return 0

    if args.reset:
        reset_state()

    if args.crawl:
        try:
            cfg = load_config()
        except Exception as exc:
            print(f"[ERROR] failed to load sources.yaml: {exc}")
            return 2
        try:
            crawl(cfg, max_pages_override=args.max_pages)
        except KeyboardInterrupt:
            print("\n[CRAWL] interrupted by user.")

    if args.status:
        print_status()

    return 0


if __name__ == "__main__":
    sys.exit(main())
