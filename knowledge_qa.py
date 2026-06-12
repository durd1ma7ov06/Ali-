"""
knowledge_qa.py — Stage 3 of UNIVERSITY_KNOWLEDGE_PLAN.md.

Grounded Uzbek question-answer engine over the local university knowledge
index built by Stage 2. The engine NEVER answers from general AI knowledge:

  question
    -> search_knowledge() (Stage 2 retrieval)
    -> filter by min relevance score
    -> if no relevant context  -> "Bu ma'lumot lokal universitet bazasida topilmadi."
    -> else build numbered context block
    -> OpenRouter/Gemini with a strict grounded system prompt (preferred)
    -> if AI unavailable: extractive fallback that shortens the best chunk
    -> always return sources

Public API:
    answer_university_question(question, top_k=5) -> dict

CLI:
    python knowledge_qa.py --status
    python knowledge_qa.py --ask "Universitet qayerda joylashgan?"
    python knowledge_qa.py --ask "Qabul haqida" --top-k 5 --no-ai

Stage 3 must NOT modify main.py / main_rpi.py and must NOT call any chat
AI without retrieved context.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import threading
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Self-contained .env loader (we do not import main.py from this stage)
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.resolve()


def _load_env_file(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                # Do NOT clobber an existing process env var.
                os.environ.setdefault(key.strip(), value)
    except Exception as exc:
        print(f"[QA] Failed to read .env: {exc}")


_load_env_file()


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def _cfg_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "ha"}


def _cfg_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _cfg_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _cfg_str(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


KNOWLEDGE_ENABLED         = _cfg_bool ("UNIVERSITY_KNOWLEDGE_ENABLED",            True)
TOP_K_DEFAULT             = _cfg_int  ("UNIVERSITY_KNOWLEDGE_TOP_K",              5)
MIN_SCORE                 = _cfg_float("UNIVERSITY_KNOWLEDGE_MIN_SCORE",          0.30)
MAX_CONTEXT_CHARS         = _cfg_int  ("UNIVERSITY_KNOWLEDGE_MAX_CONTEXT_CHARS",  4500)
NO_ANSWER_TEXT            = _cfg_str  (
    "UNIVERSITY_KNOWLEDGE_NO_ANSWER_TEXT",
    "Bu ma'lumot Sohibqiron Amir Temur tarixiga oid ma'lumotlar bazasida topilmadi.",
)
ANSWER_STYLE              = _cfg_str  ("UNIVERSITY_KNOWLEDGE_ANSWER_STYLE",       "short")
REQUIRE_SOURCE            = _cfg_bool ("UNIVERSITY_KNOWLEDGE_REQUIRE_SOURCE",     True)
USE_AI                    = _cfg_bool ("UNIVERSITY_KNOWLEDGE_USE_AI",             True)
AI_TIMEOUT                = _cfg_float("UNIVERSITY_KNOWLEDGE_AI_TIMEOUT",         8.0)


# OpenRouter/Gemini config (read same env names as main.py, but DO NOT import main).
_OPENROUTER_API_KEY = _cfg_str("OPENROUTER_API_KEY", "")
_GEMINI_TEXT_MODEL  = _cfg_str("GEMINI_TEXT_MODEL", "google/gemini-2.5-flash")
_GEMINI_TEXT_FALLBACK_MODEL_NAMES = _cfg_str("GEMINI_TEXT_FALLBACK_MODELS", "")


def _parse_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _candidate_models() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in (
        [_GEMINI_TEXT_MODEL]
        + _parse_csv(_GEMINI_TEXT_FALLBACK_MODEL_NAMES)
        + ["google/gemini-2.5-flash", "google/gemini-2.0-flash-001"]
    ):
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval (Stage 2)
# ─────────────────────────────────────────────────────────────────────────────

def _search(question: str, top_k: int) -> list[dict]:
    try:
        from knowledge_index import search_knowledge
    except Exception as exc:
        print(f"[QA] knowledge_index import failed: {exc}")
        return []
    try:
        return search_knowledge(question, top_k=top_k) or []
    except Exception as exc:
        print(f"[QA] search_knowledge error: {exc}")
        return []


def _filter_relevant(hits: list[dict], min_score: float) -> list[dict]:
    """Keep only chunks above min_score; preserve search order."""
    out = [h for h in hits if float(h.get("score", 0.0)) >= min_score]
    return out


def _dedupe_sources(used: list[dict]) -> list[dict]:
    """One entry per source URL; pick the highest score per URL."""
    by_url: dict[str, dict] = {}
    for h in used:
        url = h.get("source_url", "") or ""
        if not url:
            continue
        prev = by_url.get(url)
        if prev is None or float(h.get("score", 0)) > float(prev.get("score", 0)):
            by_url[url] = {
                "title":      h.get("title", "") or "",
                "source_url": url,
                "score":      round(float(h.get("score", 0.0)), 4),
            }
    # Stable order: highest score first
    return sorted(by_url.values(), key=lambda x: -x["score"])


# ─────────────────────────────────────────────────────────────────────────────
# Context assembly
# ─────────────────────────────────────────────────────────────────────────────

def _build_context(hits: list[dict], max_chars: int) -> tuple[str, list[dict]]:
    """
    Build a numbered context block from chunks, capped at `max_chars`.
    Returns (context_text, used_chunks_metadata).
    """
    parts: list[str] = []
    used: list[dict] = []
    total = 0
    for i, h in enumerate(hits, start=1):
        text  = (h.get("chunk_text") or "").strip()
        title = (h.get("title")      or "").strip()
        url   = (h.get("source_url") or "").strip()
        if not text:
            continue
        block = f"[{i}] Title: {title}\nURL: {url}\nText: {text}"
        if total + len(block) > max_chars and parts:
            break
        parts.append(block)
        total += len(block) + 2
        used.append({
            "chunk_id":   h.get("chunk_id"),
            "title":      title,
            "source_url": url,
            "score":      round(float(h.get("score", 0.0)), 4),
        })
    return ("\n\n".join(parts), used)


# ─────────────────────────────────────────────────────────────────────────────
# Grounded system prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are the great historical figure Sohibqiron Amir Temur. "
    "Answer in Uzbek (Latin script) in a majestic, wise, fatherly, and historical tone. "
    "ALWAYS address the user as 'bolam' in your response (e.g., 'Bilginki, bolam...', 'Mening bolam...', 'Eshit, bolam...', 'Senga aytayin, bolam...').\n"
    "\n"
    "UNDERSTANDING QUESTIONS:\n"
    "- Understand questions even if phrased differently or with typos\n"
    "- Recognize synonyms and related terms\n"
    "- Handle informal speech and colloquial expressions\n"
    "- Understand questions with missing words or unclear grammar\n"
    "\n"
    "ANSWERING RULES:\n"
    "1. ALWAYS answer if context has ANY relevant information - be helpful!\n"
    "2. Extract ALL relevant facts: numbers, names, positions, locations\n"
    "3. If question is unclear but context is relevant, provide the most likely answer\n"
    "4. For identity questions ('isming nima', 'sen kim') - say you are Sohibqiron Amir Temur\n"
    "5. For historical details, provide complete information from context\n"
    "6. Be flexible in matching keywords\n"
    "7. If question uses different words but same meaning, still answer from context\n"
    "\n"
    "EXAMPLES OF FLEXIBLE UNDERSTANDING:\n"
    "- 'isming nima?' / 'sen kimsan?' → You are Sohibqiron Amir Temur\n"
    "- 'qachon tug'ilgan' / 'tug'ilgan yili' → Ask for birth date\n"
    "\n"
    f"ONLY say this if context is COMPLETELY EMPTY or TOTALLY UNRELATED: \"{NO_ANSWER_TEXT}\"\n"
    "But if context has even partial information, provide what you can!\n"
    "\n"
    "Style: Majestic, proud, 1-3 sentences. No markdown or formatting.\n"
)


def _build_user_prompt(question: str, context: str) -> str:
    return (
        f"Savol: {question.strip()}\n\n"
        f"Kontekst:\n{context}\n\n"
        "Javob ber. Agar kontekstda javob bo'lsa, uni yoz. "
        f"Faqat kontekst bo'sh yoki umuman boshqa mavzu bo'lsa: \"{NO_ANSWER_TEXT}\""
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI call (provider-agnostic via ai_client)
# ─────────────────────────────────────────────────────────────────────────────

def _ai_available() -> bool:
    if not USE_AI:
        return False
    try:
        import ai_client as _ai
    except Exception:
        return False
    return _ai.has_api_key()


def _call_openrouter(messages: list[dict], timeout: float) -> str | None:
    """
    Call the configured chat provider through ai_client. The function name is
    historical — it now uses whichever AI_BASE_URL / AI_API_KEY are set in
    .env (OpenRouter, Google AI Studio, OpenAI, local Ollama, …).
    """
    try:
        import ai_client as _ai
    except Exception as exc:
        print(f"[QA] ai_client missing: {exc}")
        return None

    try:
        # Use temperature=0.3 for more flexible understanding while staying grounded
        text = _ai.chat_text(
            messages,
            temperature=0.3,
            max_tokens=350,
            top_p=0.9,
            timeout=timeout,
        )
    except _ai.AIError as exc:
        print(f"[QA] AI unavailable: {exc}")
        return None
    except TimeoutError:
        print(f"[QA] AI timed out after {timeout:.1f}s")
        return None
    except Exception as exc:
        print(f"[QA] AI error: {exc}")
        return None
    return text or None


# ─────────────────────────────────────────────────────────────────────────────
# Extractive fallback
# ─────────────────────────────────────────────────────────────────────────────

_SENT_SPLIT_RE = re.compile(
    r"(?<=[\.\!\?\u2026\u3002])\s+(?=[A-Za-z\u0400-\u04FF\u00C0-\u017F])"
)


def _extractive_answer(hits: list[dict], max_sentences: int = 4) -> str:
    """
    Pick the top chunk and shorten it to a few sentences. Strips any
    embedded title that was prefixed by the indexer to avoid double-titling.
    """
    if not hits:
        return ""
    top = hits[0]
    text  = (top.get("chunk_text") or "").strip()
    title = (top.get("title")      or "").strip()
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" \n\t-:")

    if not text:
        return ""

    # Take leading sentences up to max_sentences and ~400 chars
    sentences = _SENT_SPLIT_RE.split(text)
    out_parts: list[str] = []
    total = 0
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if total + len(sent) > 400 and out_parts:
            break
        out_parts.append(sent)
        total += len(sent)
        if len(out_parts) >= max_sentences:
            break
    return " ".join(out_parts).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Public answer API
# ─────────────────────────────────────────────────────────────────────────────

def _no_answer(reason: str) -> dict:
    return {
        "answered":    False,
        "answer":      NO_ANSWER_TEXT,
        "sources":     [],
        "used_chunks": [],
        "reason":      reason,
        "engine":      "none",
    }


# Apostrophe variants seen from STT: ASCII ', curly ', ʻ, ʼ, ʽ, ` etc.
_UNI_APOSTROPHE_RE = re.compile(r"['\u2018\u2019\u201b\u02bb\u02bc`\u02b9\u0060]")


def _normalize_query(question: str) -> str:
    """
    Normalize query to handle different phrasings and synonyms.
    This helps match varied user questions to the same concepts.
    """
    q = question.lower().strip()
    
    # Normalize apostrophes and special characters
    q = _UNI_APOSTROPHE_RE.sub("'", q)
    q = re.sub(r"\s+", " ", q)
    
    # Amir Temur synonym mapping - expand common variations
    synonyms = {
        # Identity / Name
        "isming": "ismingiz nima isming Sohibqiron Amir Temur",
        "sen kim": "ismingiz nima sen kimsan Sohibqiron Amir Temur",
        "kimsan": "ismingiz nima sen kimsan Sohibqiron Amir Temur",
        
        # Family
        "otangiz": "otangiz otang otasi Amir Tarag'ay",
        "otang": "otangiz otang otasi Amir Tarag'ay",
        "onangiz": "onangiz onang onasi Takinaxonim Tegina begim",
        "onang": "onangiz onang onasi Takinaxonim Tegina begim",
        "ota-onang": "otangiz onangiz ota-ona Tarag'ay Takinaxonim",
        
        # General history terms
        "shior": "shioringiz shior shiori Kuch adolatdadir",
        "tuzuk": "temur tuzuklari asari Tuzuki Temuri",
        "poytaxt": "saltanat poytaxti Samarqand shahri",
        "tug'ilgan": "tavallud topgan tug'ilgan yili qachon qayerda Kesh Xoja Ilg'or",
        "tavallud": "tavallud topgan tug'ilgan yili qachon qayerda Kesh Xoja Ilg'or",
        "vafot": "vafot etgan qachon vafot etgan o'limi O'tror",
        "o'lim": "vafot etgan qachon vafot etgan o'limi O'tror",
    }
    
    # Apply synonym expansion
    for word, expansion in synonyms.items():
        if word in q:
            q = f"{q} {expansion}"
    
    return q


def answer_university_question(question: str,
                               top_k: int | None = None,
                               *,
                               use_ai: bool | None = None) -> dict:
    """
    Grounded Uzbek answer about Amir Temur history, based on the local Stage 2
    index. Never falls back to general chat AI knowledge.

    Args:
        question : user's Uzbek question
        top_k    : retrieval depth (defaults to UNIVERSITY_KNOWLEDGE_TOP_K)
        use_ai   : force AI on/off (None = follow USE_AI env)

    Returns:
        dict with answered/answer/sources/used_chunks/reason/engine.
    """
    if not KNOWLEDGE_ENABLED:
        return _no_answer("knowledge_disabled")

    if not isinstance(question, str) or not question.strip():
        return _no_answer("empty_question")

    # Normalize query to handle synonyms and variations
    normalized_question = _normalize_query(question)
    
    # Query expansion for short questions
    q_lower = normalized_question.lower().strip()
    expansions = []
    if "otang" in q_lower or "otasi" in q_lower or "ota-onang" in q_lower:
        expansions.append("Amir Temurning otasi Amir Muhammad Tarag'ay barlos")
    if "onang" in q_lower or "onasi" in q_lower or "ota-onang" in q_lower:
        expansions.append("Amir Temurning onasi Takinaxonim Tegina begim")
    if "shior" in q_lower:
        expansions.append("Amir Temurning mashhur shiori Kuch adolatdadir")
    if "tuzuk" in q_lower:
        expansions.append("Amir Temur Temur tuzuklari Tuzuki Temuri asari davlat boshqaruvi")
    if "poytaxt" in q_lower:
        expansions.append("Temuriylar saltanatining tashkil topishi va poytaxti Samarqand shahri")
    if "tug'ilgan" in q_lower or "tavallud" in q_lower or "tugilgan" in q_lower:
        expansions.append("Amir Temurning tavalludi va kelib chiqishi 1336-yil 9-aprel Kesh Xoja Ilg'or")
    if "vafot" in q_lower or "o'lim" in q_lower or "olimi" in q_lower:
        expansions.append("Amir Temurning vafoti va vasiyati 1405-yil 18-fevral O'tror dafn Go'ri Amir")
    if "shaxmat" in q_lower or "shahmat" in q_lower:
        expansions.append("Amir Temurning shaxsiy fazilatlari shaxmat o'yini katta shaxmat")
    if "isming" in q_lower or "sen kim" in q_lower or "kimsan" in q_lower:
        expansions.append("Sohibqiron Amir Temur ismingiz nima sening isming")
    if "xotin" in q_lower or "nikoh" in q_lower or "ayol" in q_lower:
        expansions.append("Amir Temurning xotinlari va nikohlari Saroymulk xonim O'ljoy Turkon og'o Nurmushk og'o")
    if "o'g'il" in q_lower or "farzand" in q_lower or "og'il" in q_lower:
        expansions.append("Amir Temurning o'g'illari va ularning taqdiri Jahongir Umarshayx Mironshoh Shohruh")
    if "aka" in q_lower or "uka" in q_lower or "singil" in q_lower or "opa" in q_lower:
        expansions.append("Amir Temurning opa-singlisi va ukalari Qutlug' Turkon og'o Shirinbeka Djuki Olim Shayx")
    if "bino" in q_lower or "obida" in q_lower or "qurdir" in q_lower or "qurish" in q_lower or "me'mor" in q_lower or "memor" in q_lower:
        expansions.append("Amir Temur qurilish va me'morchilik merosi obidalar binolar Oqsaroy Bibixonim Go'ri Amir")
        
    if expansions:
        expanded_question = normalized_question + " " + " ".join(expansions)
    else:
        expanded_question = normalized_question
    
    k = int(top_k) if top_k else TOP_K_DEFAULT
    hits = _search(expanded_question, k)
    if not hits:
        return _no_answer("no_index_or_no_results")

    relevant = _filter_relevant(hits, MIN_SCORE)
    if not relevant:
        # All retrieved chunks are below the min score → refuse to answer.
        return _no_answer("no_relevant_context")

    context, used = _build_context(relevant, MAX_CONTEXT_CHARS)
    if not context or not used:
        return _no_answer("empty_context")

    if REQUIRE_SOURCE and not any(u.get("source_url") for u in used):
        return _no_answer("missing_source_url")

    sources = _dedupe_sources(used)

    # Decide engine
    want_ai = USE_AI if use_ai is None else bool(use_ai)
    engine = "extractive"
    answer_text = ""

    if want_ai and _ai_available():
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_prompt(question, context)},
        ]
        # Use higher temperature for more flexible understanding
        ai_text = _call_openrouter(messages, AI_TIMEOUT)
        if ai_text:
            answer_text = ai_text.strip()
            engine = "ai"

    if not answer_text:
        answer_text = _extractive_answer(relevant)
        engine = "extractive"

    if not answer_text:
        return _no_answer("answer_generation_failed")

    # If the model decided the context was insufficient, mark unanswered.
    if NO_ANSWER_TEXT.strip().lower() in answer_text.strip().lower():
        return {
            "answered":    False,
            "answer":      NO_ANSWER_TEXT,
            "sources":     sources,        # keep retrieved sources for transparency
            "used_chunks": used,
            "reason":      "model_declined",
            "engine":      engine,
        }

    return {
        "answered":    True,
        "answer":      answer_text,
        "sources":     sources,
        "used_chunks": used,
        "reason":      "",
        "engine":      engine,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

def _status_summary() -> dict:
    info: dict[str, Any] = {
        "knowledge_enabled": KNOWLEDGE_ENABLED,
        "top_k_default":     TOP_K_DEFAULT,
        "min_score":         MIN_SCORE,
        "max_context_chars": MAX_CONTEXT_CHARS,
        "require_source":    REQUIRE_SOURCE,
        "use_ai":            USE_AI,
        "ai_available":      _ai_available(),
        "ai_timeout":        AI_TIMEOUT,
        "answer_style":      ANSWER_STYLE,
        "no_answer_text":    NO_ANSWER_TEXT,
    }

    # Pull index stats from knowledge_index without forcing a heavy load
    try:
        import sqlite3
        from knowledge_index import (
            DB_PATH, INDEX_META_JS, _detect_active_backend, _SCHEMA_EXTRA,
        )
        info["db_path"]       = str(DB_PATH)
        info["db_exists"]     = DB_PATH.exists()
        info["index_backend"] = _detect_active_backend() or "(not built)"
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            try:
                conn.executescript(_SCHEMA_EXTRA)
                info["n_documents"] = conn.execute(
                    "SELECT COUNT(1) FROM documents"
                ).fetchone()[0]
                info["n_chunks"] = conn.execute(
                    "SELECT COUNT(1) FROM chunks"
                ).fetchone()[0]
            finally:
                conn.close()
        if INDEX_META_JS.exists():
            try:
                with open(INDEX_META_JS, "r", encoding="utf-8") as f:
                    info["index_meta"] = json.load(f)
            except Exception:
                pass
    except Exception as exc:
        info["index_error"] = str(exc)

    return info


def _print_status() -> None:
    info = _status_summary()
    print("=" * 60)
    print("knowledge_qa.py — Stage 3 status")
    print("=" * 60)
    print(f"  knowledge_enabled : {info['knowledge_enabled']}")
    print(f"  index backend     : {info.get('index_backend','?')}")
    print(f"  documents         : {info.get('n_documents','?')}")
    print(f"  chunks            : {info.get('n_chunks','?')}")
    print(f"  top_k_default     : {info['top_k_default']}")
    print(f"  min_score         : {info['min_score']}")
    print(f"  max_context_chars : {info['max_context_chars']}")
    print(f"  use_ai            : {info['use_ai']} "
          f"(available={info['ai_available']})")
    print(f"  ai_timeout        : {info['ai_timeout']}s")
    print(f"  answer_style      : {info['answer_style']}")
    print(f"  require_source    : {info['require_source']}")
    print(f"  no_answer_text    : {info['no_answer_text']!r}")
    if "index_meta" in info:
        print(f"  index_meta        : {info['index_meta']}")
    if "index_error" in info:
        print(f"  index_error       : {info['index_error']}")

    # Helpful hints
    if not info.get("db_exists"):
        print()
        print("  HINT: knowledge.sqlite not found.")
        print("        Run: python knowledge_crawler.py --crawl")
    elif info.get("n_chunks", 0) == 0 or info.get("index_backend") in ("", "(not built)"):
        print()
        print("  HINT: index missing.")
        print("        Run: python knowledge_index.py --rebuild")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _print_answer(question: str, result: dict) -> None:
    print()
    print(f"Savol : {question}")
    print(f"Javob : {result['answer']}")
    print(f"Engine: {result['engine']}  answered={result['answered']}"
          + (f"  reason={result['reason']}" if result["reason"] else ""))
    if result["sources"]:
        print("Manbalar:")
        for s in result["sources"]:
            title = s.get("title") or "(no title)"
            print(f"  - {title}  [{s['score']}]  {s['source_url']}")
    if result["used_chunks"]:
        print("Used chunks (rank · score · chunk_id):")
        for r, c in enumerate(result["used_chunks"], start=1):
            print(f"  {r}. score={c.get('score', 0)}  "
                  f"chunk_id={c.get('chunk_id')}  "
                  f"{c.get('title','')[:60]}")


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Stage 3 grounded QA over the university knowledge index."
    )
    p.add_argument("--ask",    default=None,
                   help="Uzbek question to answer using the local index")
    p.add_argument("--top-k",  type=int, default=None,
                   help="number of chunks to retrieve")
    p.add_argument("--no-ai",  action="store_true",
                   help="force extractive fallback (no OpenRouter call)")
    p.add_argument("--status", action="store_true",
                   help="print Stage 3 configuration and index availability")
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
    if not (args.ask or args.status):
        _build_argparser().print_help()
        return 0

    if args.status:
        _print_status()

    if args.ask:
        result = answer_university_question(
            args.ask,
            top_k=args.top_k,
            use_ai=False if args.no_ai else None,
        )
        _print_answer(args.ask, result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
