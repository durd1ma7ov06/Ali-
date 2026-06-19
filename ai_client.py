"""
ai_client.py — Provider-agnostic OpenAI-compatible chat client.

Goal:
  The robot must work with ANY OpenAI-compatible chat-completion API.
  The user only edits .env to switch providers — no code change.

Read order (preferred ➜ legacy fallback):
  AI_API_KEY            ← OPENROUTER_API_KEY
  AI_BASE_URL           ← (default: https://openrouter.ai/api/v1)
  AI_MODEL              ← GEMINI_TEXT_MODEL
  AI_FALLBACK_MODELS    ← GEMINI_TEXT_FALLBACK_MODELS
  AI_PROVIDER           ← (optional label, just for logs)
  AI_REQUEST_TIMEOUT    (default 8.0)

Examples
--------
OpenRouter (default):
  AI_BASE_URL=https://openrouter.ai/api/v1
  AI_API_KEY=sk-or-v1-...
  AI_MODEL=google/gemini-2.5-flash
  AI_FALLBACK_MODELS=deepseek/deepseek-chat-v3-0324:free

Google AI Studio (OpenAI-compatible endpoint):
  AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
  AI_API_KEY=AIza...
  AI_MODEL=gemini-2.0-flash
  AI_FALLBACK_MODELS=gemini-1.5-flash

OpenAI:
  AI_BASE_URL=https://api.openai.com/v1
  AI_API_KEY=sk-proj-...
  AI_MODEL=gpt-4o-mini

Local Ollama (OpenAI-compatible mode):
  AI_BASE_URL=http://localhost:11434/v1
  AI_API_KEY=ollama
  AI_MODEL=llama3.2
"""
from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# .env loader (so this module works standalone — `python ai_client.py`)
# ─────────────────────────────────────────────────────────────────────────────

def _load_env_file_once(path: Path | None = None) -> None:
    if path is None:
        path = Path(__file__).resolve().parent / ".env"
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
                # Do not overwrite values already in the real environment.
                os.environ.setdefault(key.strip(), value)
    except Exception as exc:
        print(f"[AI] .env load warning: {exc}")


_load_env_file_once()


# ─────────────────────────────────────────────────────────────────────────────
# Env helpers
# ─────────────────────────────────────────────────────────────────────────────

def _first_env(*names: str, default: str = "") -> str:
    for n in names:
        v = (os.environ.get(n) or "").strip()
        if v:
            return v
    return default


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Public configuration accessors (read at call time so .env reloads work)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def base_url() -> str:
    return _first_env("AI_BASE_URL", default=DEFAULT_BASE_URL)


def api_key() -> str:
    return _first_env("AI_API_KEY", "OPENROUTER_API_KEY")


def has_api_key() -> bool:
    return bool(api_key())


def primary_model() -> str:
    return _first_env(
        "AI_MODEL", "GEMINI_TEXT_MODEL",
        default="google/gemini-2.5-flash",
    )


def fallback_models() -> list[str]:
    """Ordered list of models to try: primary first, then user fallbacks."""
    raw = _first_env("AI_FALLBACK_MODELS", "GEMINI_TEXT_FALLBACK_MODELS")
    return _unique([primary_model()] + _split_csv(raw))


def provider_label() -> str:
    explicit = _first_env("AI_PROVIDER")
    if explicit:
        return explicit
    url = base_url().lower()
    if "openrouter.ai" in url:
        return "openrouter"
    if "googleapis.com" in url:
        return "google"
    if "api.openai.com" in url:
        return "openai"
    if "anthropic.com" in url:
        return "anthropic"
    if "localhost" in url or "127.0.0.1" in url:
        return "local"
    return "custom"


def request_timeout(default: float = 8.0) -> float:
    raw = _first_env("AI_REQUEST_TIMEOUT")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Client (lazy-built, cached)
# ─────────────────────────────────────────────────────────────────────────────

_client: Any | None = None
_client_signature: tuple[str, str] = ("", "")
_client_lock = threading.Lock()


def get_client() -> Any:
    """
    Lazy-build an openai.OpenAI client from the current env. Re-creates the
    client if base_url or api_key change between calls (lets the user edit
    .env at runtime).
    """
    global _client, _client_signature
    from openai import OpenAI  # imported lazily so this module doesn't crash if openai is missing

    sig = (base_url(), api_key())
    with _client_lock:
        if _client is not None and _client_signature == sig:
            return _client
        _client = OpenAI(
            base_url=sig[0],
            api_key=sig[1] or "missing",   # OpenAI client requires a non-empty string
            default_headers={
                "HTTP-Referer": "https://amir-temur-ai.uz",
                "X-Title":      "HumanoidRobotAI",
            },
        )
        _client_signature = sig
        return _client


def reset_client() -> None:
    global _client, _client_signature
    with _client_lock:
        _client = None
        _client_signature = ("", "")


# ─────────────────────────────────────────────────────────────────────────────
# Chat call helpers
# ─────────────────────────────────────────────────────────────────────────────

class AIError(RuntimeError):
    """Raised when every candidate model fails."""


def call_ollama_fallback(messages: list[dict], response_format: dict | None = None) -> str | None:
    """
    Attempts to call a local Ollama instance (defaulting to http://localhost:11434/v1)
    using the model specified in OLLAMA_FALLBACK_MODEL (defaulting to llama3.2).
    Returns the string text if successful, else None.
    """
    from openai import OpenAI
    ollama_url = os.environ.get("OLLAMA_FALLBACK_URL", "http://localhost:11434/v1").strip()
    ollama_model = os.environ.get("OLLAMA_FALLBACK_MODEL", "llama3.2").strip()
    try:
        print(f"[OLLAMA] Attempting local fallback on {ollama_url} with model {ollama_model}...")
        client = OpenAI(base_url=ollama_url, api_key="ollama")
        kwargs = {
            "model": ollama_model,
            "messages": messages,
            "timeout": float(os.environ.get("OLLAMA_TIMEOUT", "6.0")),
        }
        if response_format:
            kwargs["response_format"] = response_format
        
        resp = client.chat.completions.create(**kwargs)
        text = (resp.choices[0].message.content or "").strip()
        if text:
            print(f"[OLLAMA] Local fallback response successful: {text[:60]}...")
            return text
    except Exception as exc:
        print(f"[OLLAMA] Local fallback failed: {exc}")
        if response_format:
            try:
                print("[OLLAMA] Retrying local fallback without response_format...")
                client = OpenAI(base_url=ollama_url, api_key="ollama")
                kwargs = {
                    "model": ollama_model,
                    "messages": messages,
                    "timeout": float(os.environ.get("OLLAMA_TIMEOUT", "6.0")),
                }
                resp = client.chat.completions.create(**kwargs)
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    print(f"[OLLAMA] Local fallback retry response successful: {text[:60]}...")
                    return text
            except Exception as retry_exc:
                print(f"[OLLAMA] Local fallback retry failed: {retry_exc}")
    return None


def call_with_timeout(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 220,
    top_p: float = 0.9,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    timeout: float | None = None,
    response_format: dict | None = None,
):
    """
    Single-model call with a soft thread-based timeout. Returns the raw
    response object from the openai SDK. Raises on error or timeout.
    """
    if timeout is None:
        timeout = request_timeout()
    if model is None:
        model = primary_model()

    client = get_client()
    result_q: queue.Queue = queue.Queue(maxsize=1)

    kwargs: dict[str, Any] = {
        "model":       model,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
        "top_p":       top_p,
        "timeout":     timeout,
    }
    if response_format:
        kwargs["response_format"] = response_format

    # frequency_penalty / presence_penalty are OpenAI-specific.
    # Google (Gemini) and some other providers reject them entirely —
    # strip them when targeting a Google or unknown-compat endpoint.
    _gemini_provider = provider_label() in ("google",) or "gemini" in model.lower()
    if frequency_penalty and not _gemini_provider:
        kwargs["frequency_penalty"] = frequency_penalty
    if presence_penalty and not _gemini_provider:
        kwargs["presence_penalty"] = presence_penalty

    def worker():
        try:
            resp = client.chat.completions.create(**kwargs)
            result_q.put(("ok", resp))
        except Exception as exc:
            result_q.put(("err", exc))

    t = threading.Thread(
        target=worker, name=f"ai-{model}", daemon=True,
    )
    t.start()
    try:
        status, value = result_q.get(timeout=timeout + 0.5)
    except queue.Empty:
        raise TimeoutError(f"{model} timed out after {timeout:.1f}s")

    if status == "err":
        raise value
    return value


def chat_text(
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 220,
    top_p: float = 0.9,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    timeout: float | None = None,
    models: list[str] | None = None,
    max_attempts: int | None = None,
    response_format: dict | None = None,
) -> str:
    """
    Try each model in `models` (or fallback_models() by default) until one
    returns a non-empty assistant text. Returns the text or raises AIError.
    """
    last_err: Exception | None = None
    if has_api_key():
        candidates = models or fallback_models()
        if max_attempts is not None:
            candidates = candidates[: max(1, int(max_attempts))]

        for m in candidates:
            try:
                resp = call_with_timeout(
                    messages,
                    model=m,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                    timeout=timeout,
                    response_format=response_format,
                )
            except Exception as exc:
                last_err = exc
                print(f"[AI] Model {m} failed: {exc}")
                continue
            try:
                text = (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                last_err = exc
                print(f"[AI] Model {m} returned malformed response: {exc}")
                continue
            if text:
                try:
                    import dashboard_server
                    dashboard_server.update_status(online=True, provider="OpenRouter", model=m)
                except ImportError:
                    pass
                return text

    # Fall back to local Ollama if online calls failed or key is missing
    ollama_text = call_ollama_fallback(messages, response_format=response_format)
    if ollama_text:
        try:
            import dashboard_server
            dashboard_server.update_status(
                online=False,
                provider="Ollama",
                model=os.environ.get("OLLAMA_FALLBACK_MODEL", "llama3.2").strip()
            )
        except ImportError:
            pass
        return ollama_text

    raise AIError(
        f"All model(s) and local Ollama fallback failed. Last error: {last_err}"
    )


def ping() -> bool:
    """
    Quick connectivity check used at startup. Returns True if the configured
    provider answers any candidate model with a non-empty reply.
    """
    if not has_api_key():
        return False
    try:
        chat_text(
            [
                {"role": "system", "content": "Reply with exactly: ok"},
                {"role": "user",   "content": "ping"},
            ],
            temperature=0.0,
            max_tokens=4,
            timeout=request_timeout(default=8.0),
            max_attempts=len(fallback_models()),
        )
        return True
    except Exception as exc:
        print(f"[AI] Ping failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostic banner
# ─────────────────────────────────────────────────────────────────────────────

def describe() -> dict:
    """Return a small dict for status logs. Never includes the API key."""
    key = api_key()
    return {
        "provider":        provider_label(),
        "base_url":        base_url(),
        "model":           primary_model(),
        "fallback_models": fallback_models(),
        "api_key_set":     bool(key),
        "api_key_prefix":  (key[:6] + "…") if key else "",
        "request_timeout": request_timeout(),
    }


def print_banner() -> None:
    info = describe()
    print(f"[AI] provider={info['provider']} model={info['model']} "
          f"base={info['base_url']} key_set={info['api_key_set']} "
          f"timeout={info['request_timeout']}s")


if __name__ == "__main__":
    # Manual self-check:
    #   python ai_client.py
    print_banner()
    if has_api_key():
        ok = ping()
        print(f"  ping: {'OK' if ok else 'FAIL'}")
    else:
        print("  AI_API_KEY/OPENROUTER_API_KEY is empty — set it in .env")
