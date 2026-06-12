"""
pipeline_core.py — Low-latency voice pipeline shared helpers.

Round 2 additions:
  - VoiceConfig  (mic selection, VAD energy, interrupt, TTS max chars)
  - InterruptListener  (stop-word background listener during TTS)
  - stop_playback()  (immediate pygame stop)
  - truncate_for_tts()  (TTS_MAX_TEXT_CHARS enforcement)
  - configure_recognizer() now reads VAD_DYNAMIC_ENERGY_THRESHOLD / VAD_ENERGY_THRESHOLD
  - LatencyConfig unchanged (backward-compatible)
"""
from __future__ import annotations

import asyncio
import atexit
import io
import os
import queue
import re
import sys
import threading
import time as _time
from dataclasses import dataclass, field
from typing import Callable

import pygame
import speech_recognition as sr
import edge_tts

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _warn(var: str, raw, default) -> None:
    print(f"[WARN] {var}: invalid value {raw!r}, using default {default}")


def _read_float(var: str, default: float, lo: float | None, hi: float | None) -> float:
    raw = os.environ.get(var)
    if raw is None:
        return default
    try:
        val = float(raw)
    except (ValueError, TypeError):
        _warn(var, raw, default)
        return default
    if (lo is not None and val < lo) or (hi is not None and val > hi):
        _warn(var, raw, default)
        return default
    return val


def _read_int(var: str, default: int, lo: int, hi: int) -> int:
    raw = os.environ.get(var)
    if raw is None:
        return default
    try:
        val = int(float(raw))
    except (ValueError, TypeError):
        _warn(var, raw, default)
        return default
    if val < lo or val > hi:
        _warn(var, raw, default)
        return default
    return val


def _read_bool(var: str, default: bool) -> bool:
    raw = os.environ.get(var)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    _warn(var, raw, default)
    return default


def _read_choice(var: str, default: str, choices: tuple[str, ...]) -> str:
    raw = os.environ.get(var)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in choices:
        return normalized
    _warn(var, raw, default)
    return default


# ---------------------------------------------------------------------------
# LatencyConfig  (unchanged from round 1 — backward compatible)
# ---------------------------------------------------------------------------

@dataclass
class LatencyConfig:
    """All latency-related configuration for the voice pipeline."""

    vad_ambient_calibration_duration: float = 1.0
    vad_pause_threshold: float = 0.6
    vad_non_speaking_duration: float = 0.3
    vad_phrase_time_limit: int = 8
    vad_listen_timeout: int = 5
    tts_min_chunk_bytes: int = 4096
    ai_request_timeout: float = 6.0
    arm_command_timeout: float = 5.0
    turn_cooldown_seconds: float = 0.0
    latency_logging_enabled: bool = True
    latency_log_level: str = "summary"

    @classmethod
    def load(cls) -> "LatencyConfig":
        vad_ambient_calibration_duration = _read_float(
            "VAD_AMBIENT_CALIBRATION_DURATION", 1.0, 0.0, None)
        vad_pause_threshold = _read_float("VAD_PAUSE_THRESHOLD", 0.6, 0.2, 3.0)
        vad_non_speaking_duration = _read_float("VAD_NON_SPEAKING_DURATION", 0.3, 0.1, 2.0)
        if vad_non_speaking_duration > vad_pause_threshold:
            print(f"[WARN] VAD_NON_SPEAKING_DURATION: value {vad_non_speaking_duration} "
                  f"exceeds VAD_PAUSE_THRESHOLD {vad_pause_threshold}, clamping.")
            vad_non_speaking_duration = vad_pause_threshold
        vad_phrase_time_limit = _read_int("VAD_PHRASE_TIME_LIMIT", 8, 1, 60)
        vad_listen_timeout = _read_int("VAD_LISTEN_TIMEOUT", 5, 1, 60)
        tts_min_chunk_bytes = _read_int("TTS_MIN_CHUNK_BYTES", 4096, 512, 2**31 - 1)
        ai_request_timeout = _read_float("AI_REQUEST_TIMEOUT", 6.0, 0.1, 300.0)
        arm_command_timeout = _read_float("ARM_COMMAND_TIMEOUT", 5.0, 0.0, 60.0)
        turn_cooldown_seconds = _read_float("TURN_COOLDOWN_SECONDS", 0.0, 0.0, 5.0)
        latency_logging_enabled = _read_bool("LATENCY_LOGGING_ENABLED", True)
        latency_log_level = _read_choice("LATENCY_LOG_LEVEL", "summary", ("summary", "verbose"))

        cfg = cls(
            vad_ambient_calibration_duration=vad_ambient_calibration_duration,
            vad_pause_threshold=vad_pause_threshold,
            vad_non_speaking_duration=vad_non_speaking_duration,
            vad_phrase_time_limit=vad_phrase_time_limit,
            vad_listen_timeout=vad_listen_timeout,
            tts_min_chunk_bytes=tts_min_chunk_bytes,
            ai_request_timeout=ai_request_timeout,
            arm_command_timeout=arm_command_timeout,
            turn_cooldown_seconds=turn_cooldown_seconds,
            latency_logging_enabled=latency_logging_enabled,
            latency_log_level=latency_log_level,
        )
        if cfg.latency_logging_enabled:
            for k, v in [
                ("VAD_AMBIENT_CALIBRATION_DURATION", cfg.vad_ambient_calibration_duration),
                ("VAD_PAUSE_THRESHOLD", cfg.vad_pause_threshold),
                ("VAD_NON_SPEAKING_DURATION", cfg.vad_non_speaking_duration),
                ("VAD_PHRASE_TIME_LIMIT", cfg.vad_phrase_time_limit),
                ("VAD_LISTEN_TIMEOUT", cfg.vad_listen_timeout),
                ("TTS_MIN_CHUNK_BYTES", cfg.tts_min_chunk_bytes),
                ("AI_REQUEST_TIMEOUT", cfg.ai_request_timeout),
                ("ARM_COMMAND_TIMEOUT", cfg.arm_command_timeout),
                ("TURN_COOLDOWN_SECONDS", cfg.turn_cooldown_seconds),
                ("LATENCY_LOGGING_ENABLED", cfg.latency_logging_enabled),
                ("LATENCY_LOG_LEVEL", cfg.latency_log_level),
            ]:
                print(f"[LATENCY CONFIG] {k}={v}")
        return cfg


def load_latency_config() -> LatencyConfig:
    return LatencyConfig.load()


# ---------------------------------------------------------------------------
# VoiceConfig  (Round 2 — mic, VAD energy, interrupt, TTS limits)
# ---------------------------------------------------------------------------

# Default stop words (multilingual)
_DEFAULT_STOP_WORDS = (
    "stop,cancel,enough,toxtat,to'xtat,to`xtat,yetarli,bas,"
    "bekor qil,остановись,стоп,хватит"
)


@dataclass
class VoiceConfig:
    """
    Round-2 voice configuration: microphone selection, VAD energy thresholds,
    stop-word interrupt listener, and TTS text limits.
    """

    # Microphone selection
    mic_device_index: int | None = None       # MIC_DEVICE_INDEX (overrides hardware.py)
    mic_device_name: str = ""                 # MIC_DEVICE_NAME  (substring match)

    # VAD energy
    vad_dynamic_energy_threshold: bool = True  # VAD_DYNAMIC_ENERGY_THRESHOLD
    vad_energy_threshold: int = 300            # VAD_ENERGY_THRESHOLD

    # Interrupt listener
    interrupt_listener_enabled: bool = True    # INTERRUPT_LISTENER_ENABLED
    interrupt_stop_words: list[str] = field(default_factory=list)  # INTERRUPT_STOP_WORDS
    interrupt_listener_timeout: float = 0.25  # INTERRUPT_LISTENER_TIMEOUT
    interrupt_listener_phrase_limit: float = 2.0  # INTERRUPT_LISTENER_PHRASE_LIMIT

    # TTS limits
    tts_max_text_chars: int = 0               # TTS_MAX_TEXT_CHARS (0 = unlimited)

    @classmethod
    def load(cls) -> "VoiceConfig":
        # Mic index
        raw_idx = os.environ.get("MIC_DEVICE_INDEX", "").strip()
        mic_device_index: int | None = None
        if raw_idx:
            try:
                mic_device_index = int(raw_idx)
            except ValueError:
                print(f"[WARN] MIC_DEVICE_INDEX: invalid value {raw_idx!r}, ignoring.")

        mic_device_name = os.environ.get("MIC_DEVICE_NAME", "").strip()

        vad_dynamic = _read_bool("VAD_DYNAMIC_ENERGY_THRESHOLD", True)
        vad_energy = _read_int("VAD_ENERGY_THRESHOLD", 300, 0, 32767)

        interrupt_enabled = _read_bool("INTERRUPT_LISTENER_ENABLED", True)

        raw_words = os.environ.get("INTERRUPT_STOP_WORDS", _DEFAULT_STOP_WORDS)
        stop_words = [w.strip().lower() for w in raw_words.split(",") if w.strip()]

        interrupt_timeout = _read_float("INTERRUPT_LISTENER_TIMEOUT", 0.25, 0.05, 5.0)
        interrupt_phrase = _read_float("INTERRUPT_LISTENER_PHRASE_LIMIT", 2.0, 0.1, 10.0)

        tts_max = _read_int("TTS_MAX_TEXT_CHARS", 0, 0, 10000)

        cfg = cls(
            mic_device_index=mic_device_index,
            mic_device_name=mic_device_name,
            vad_dynamic_energy_threshold=vad_dynamic,
            vad_energy_threshold=vad_energy,
            interrupt_listener_enabled=interrupt_enabled,
            interrupt_stop_words=stop_words,
            interrupt_listener_timeout=interrupt_timeout,
            interrupt_listener_phrase_limit=interrupt_phrase,
            tts_max_text_chars=tts_max,
        )

        print(f"[VOICE CONFIG] MIC_DEVICE_INDEX={cfg.mic_device_index}")
        print(f"[VOICE CONFIG] MIC_DEVICE_NAME={cfg.mic_device_name!r}")
        print(f"[VOICE CONFIG] VAD_DYNAMIC_ENERGY_THRESHOLD={cfg.vad_dynamic_energy_threshold}")
        print(f"[VOICE CONFIG] VAD_ENERGY_THRESHOLD={cfg.vad_energy_threshold}")
        print(f"[VOICE CONFIG] INTERRUPT_LISTENER_ENABLED={cfg.interrupt_listener_enabled}")
        print(f"[VOICE CONFIG] INTERRUPT_STOP_WORDS={cfg.interrupt_stop_words}")
        print(f"[VOICE CONFIG] INTERRUPT_LISTENER_TIMEOUT={cfg.interrupt_listener_timeout}")
        print(f"[VOICE CONFIG] INTERRUPT_LISTENER_PHRASE_LIMIT={cfg.interrupt_listener_phrase_limit}")
        print(f"[VOICE CONFIG] TTS_MAX_TEXT_CHARS={cfg.tts_max_text_chars}")
        return cfg


# ---------------------------------------------------------------------------
# Recognizer helpers  (updated: reads VAD_ENERGY_THRESHOLD / DYNAMIC)
# ---------------------------------------------------------------------------

def configure_recognizer(
    recognizer: sr.Recognizer,
    cfg: LatencyConfig,
    vcfg: "VoiceConfig | None" = None,
) -> None:
    """Apply VAD thresholds from config to the recognizer."""
    recognizer.pause_threshold = cfg.vad_pause_threshold
    recognizer.non_speaking_duration = cfg.vad_non_speaking_duration
    if vcfg is not None:
        recognizer.dynamic_energy_threshold = vcfg.vad_dynamic_energy_threshold
        recognizer.energy_threshold = vcfg.vad_energy_threshold
        print(f"[VAD] energy_threshold={vcfg.vad_energy_threshold}, "
              f"dynamic={vcfg.vad_dynamic_energy_threshold}, "
              f"pause_threshold={cfg.vad_pause_threshold}s, "
              f"non_speaking_duration={cfg.vad_non_speaking_duration}s")
    else:
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = 300


def calibrate_once(
    recognizer: sr.Recognizer,
    mic: sr.Microphone,
    cfg: LatencyConfig,
) -> None:
    """Single startup ambient noise calibration (skipped if duration == 0)."""
    if cfg.vad_ambient_calibration_duration == 0:
        print("[VAD] Ambient calibration skipped (VAD_AMBIENT_CALIBRATION_DURATION=0).")
        return
    print(f"[VAD] Calibrating ambient noise for {cfg.vad_ambient_calibration_duration}s...")
    with mic as source:
        recognizer.adjust_for_ambient_noise(
            source,
            duration=cfg.vad_ambient_calibration_duration,
        )
    print(f"[VAD] Calibration done. energy_threshold={recognizer.energy_threshold:.0f}")


# ---------------------------------------------------------------------------
# Persistent TTS event loop — runs forever in a dedicated background thread.
# ---------------------------------------------------------------------------
# Why a dedicated thread?
#   loop.run_until_complete() cannot be called from a thread that is already
#   inside any asyncio context. Some imported libraries (edge-tts, openai,
#   pygame audio drivers on certain Windows builds) leave the main thread in
#   a state where Python thinks there is a "running loop". That makes
#   "Cannot run the event loop while another loop is running" reproducible
#   on every TTS call.
#
# Solution: own a private event loop on a dedicated daemon thread, and
# submit coroutines with run_coroutine_threadsafe(). The future's result()
# blocks the caller without touching the caller's loop state.

_tts_loop: asyncio.AbstractEventLoop | None = None
_tts_loop_thread: threading.Thread | None = None
_tts_loop_lock = threading.Lock()
# Process-wide serializer — only one TTS playback at a time across threads.
_tts_run_lock = threading.RLock()


def _tts_loop_runner(loop: asyncio.AbstractEventLoop) -> None:
    """Body of the dedicated TTS loop thread. Runs until the loop stops."""
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        try:
            # Drain any pending tasks before the thread exits.
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        try:
            loop.close()
        except Exception:
            pass


def get_tts_loop() -> asyncio.AbstractEventLoop:
    """Lazy-start the dedicated TTS loop thread and return its loop."""
    global _tts_loop, _tts_loop_thread
    with _tts_loop_lock:
        if (
            _tts_loop is not None
            and not _tts_loop.is_closed()
            and _tts_loop_thread is not None
            and _tts_loop_thread.is_alive()
        ):
            return _tts_loop
        _tts_loop = asyncio.new_event_loop()
        _tts_loop_thread = threading.Thread(
            target=_tts_loop_runner,
            args=(_tts_loop,),
            name="tts-loop",
            daemon=True,
        )
        _tts_loop_thread.start()
        return _tts_loop


def close_tts_loop() -> None:
    """Stop the dedicated TTS loop thread (called on process exit)."""
    global _tts_loop, _tts_loop_thread
    with _tts_loop_lock:
        loop = _tts_loop
        thread = _tts_loop_thread
        _tts_loop = None
        _tts_loop_thread = None
    if loop is not None and not loop.is_closed():
        try:
            loop.call_soon_threadsafe(loop.stop)
        except Exception:
            pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)


atexit.register(close_tts_loop)

# ---------------------------------------------------------------------------
# TTS interrupt flag  (set by InterruptListener, cleared by run_speak)
# ---------------------------------------------------------------------------

_tts_interrupted = threading.Event()


def is_tts_interrupted() -> bool:
    return _tts_interrupted.is_set()


def clear_tts_interrupt() -> None:
    _tts_interrupted.clear()


def signal_tts_interrupt() -> None:
    _tts_interrupted.set()


def stop_playback() -> None:
    """Immediately stop pygame audio playback."""
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# InterruptListener  (background stop-word detector during TTS)
# ---------------------------------------------------------------------------

class InterruptListener:
    """
    Lightweight background thread that listens for stop words while the robot
    is speaking.  Uses a *separate* sr.Recognizer and sr.Microphone instance
    so it never conflicts with the main conversation listener.

    Usage:
        listener = InterruptListener(vcfg, stt_language, mic_device_index)
        listener.start()          # call just before run_speak()
        run_speak(text, cfg)      # plays audio; listener watches in background
        listener.stop()           # call after run_speak() returns
        if listener.was_interrupted():
            ...
    """

    def __init__(
        self,
        vcfg: VoiceConfig,
        stt_language: str,
        mic_device_index: int | None = None,
    ) -> None:
        self._vcfg = vcfg
        self._stt_language = stt_language
        self._mic_device_index = mic_device_index
        self._stop_event = threading.Event()
        self._interrupted = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._vcfg.interrupt_listener_enabled:
            return
        if not self._vcfg.interrupt_stop_words:
            return
        clear_tts_interrupt()
        self._stop_event.clear()
        self._interrupted.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="interrupt-listener",
            daemon=True,
        )
        self._thread.start()
        print("[INTERRUPT] Listener started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        print("[INTERRUPT] Listener stopped.")

    def was_interrupted(self) -> bool:
        return self._interrupted.is_set()

    def _run(self) -> None:
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = self._vcfg.vad_energy_threshold
            recognizer.dynamic_energy_threshold = False  # keep stable during TTS
            recognizer.pause_threshold = 0.3

            mic_kwargs: dict = {}
            if self._mic_device_index is not None:
                mic_kwargs["device_index"] = self._mic_device_index

            mic = sr.Microphone(**mic_kwargs)

            while not self._stop_event.is_set():
                try:
                    with mic as source:
                        audio = recognizer.listen(
                            source,
                            timeout=self._vcfg.interrupt_listener_timeout,
                            phrase_time_limit=self._vcfg.interrupt_listener_phrase_limit,
                        )
                    try:
                        text = recognizer.recognize_google(
                            audio, language=self._stt_language
                        ).lower().strip()
                    except sr.UnknownValueError:
                        continue
                    except Exception:
                        continue

                    for word in self._vcfg.interrupt_stop_words:
                        if word in text:
                            print(f"[INTERRUPT] Stop word detected: {text!r}")
                            self._interrupted.set()
                            signal_tts_interrupt()
                            stop_playback()
                            return
                except sr.WaitTimeoutError:
                    continue
                except Exception:
                    _time.sleep(0.05)
                    continue
        except Exception as exc:
            print(f"[INTERRUPT] Listener error: {exc}")


# ---------------------------------------------------------------------------
# LatencyTimer
# ---------------------------------------------------------------------------

_listen_complete_t0: float | None = None


class LatencyTimer:
    SUMMARY_STAGES = {"listen_complete", "tts_playback_complete"}

    def __init__(self, stage_name: str, cfg: LatencyConfig) -> None:
        self.stage_name = stage_name
        self.cfg = cfg
        self._t0: float | None = None
        self._t1: float | None = None

    def start(self) -> "LatencyTimer":
        global _listen_complete_t0
        self._t0 = _time.monotonic()
        if self.stage_name == "listen_complete":
            _listen_complete_t0 = self._t0
        return self

    def stop(self) -> float:
        self._t1 = _time.monotonic()
        elapsed = self._t1 - (self._t0 if self._t0 is not None else self._t1)
        self._maybe_log(elapsed)
        return elapsed

    def elapsed_ms(self) -> int:
        if self._t0 is None or self._t1 is None:
            return 0
        return round((self._t1 - self._t0) * 1000)

    def _maybe_log(self, elapsed: float) -> None:
        if not self.cfg.latency_logging_enabled:
            return
        duration_ms = round(elapsed * 1000)
        if self.cfg.latency_log_level == "verbose":
            print(f"[TIMING] {self.stage_name}: {duration_ms}ms")
        elif self.cfg.latency_log_level == "summary":
            if self.stage_name in self.SUMMARY_STAGES:
                print(f"[TIMING] {self.stage_name}: {duration_ms}ms")
                if self.stage_name == "tts_playback_complete":
                    global _listen_complete_t0
                    if _listen_complete_t0 is not None and self._t1 is not None:
                        total = round((self._t1 - _listen_complete_t0) * 1000)
                        print(f"[TIMING] turn_total: {total}ms")

    def __enter__(self) -> "LatencyTimer":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# ArmCommandWorker
# ---------------------------------------------------------------------------

class ArmCommandWorker:
    def __init__(self, cfg: LatencyConfig) -> None:
        self.cfg = cfg
        self._queue: queue.Queue[Callable[[], None] | None] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._current_job_done = threading.Event()
        self._current_job_done.set()

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="arm-command-worker", daemon=True)
        self._thread.start()

    def dispatch(self, job: Callable[[], None]) -> None:
        finished = self._current_job_done.wait(timeout=self.cfg.arm_command_timeout)
        if not finished:
            print(f"[WARN] ArmCommandWorker: previous job still running after "
                  f"{self.cfg.arm_command_timeout}s, proceeding anyway.")
        self._current_job_done.clear()
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(job)

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                break
            try:
                job()
            except Exception as exc:
                print(f"[WARN] ArmCommandWorker: job failed: {exc}")
            finally:
                self._current_job_done.set()


# ---------------------------------------------------------------------------
# turn_cooldown
# ---------------------------------------------------------------------------

import time  # noqa: E402


def turn_cooldown(cfg: LatencyConfig) -> None:
    """Wait for playback to finish, then apply optional inter-turn cooldown."""
    try:
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(20)
    except Exception:
        pass
    if cfg.turn_cooldown_seconds > 0.0:
        time.sleep(cfg.turn_cooldown_seconds)


# ---------------------------------------------------------------------------
# Text preparation helpers
# ---------------------------------------------------------------------------

def sanitize_text_for_tts(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[*_#>\[\]\(\)]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[{}\[\]<>]", " ", text)
    text = re.sub(r"[^\w\s.,!?;:'\-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_long_speech_into_chunks(text: str, limit: int = 280) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def prepare_uzbek_spoken_text(text: str) -> str:
    # Normalize all kinds of Uzbek apostrophes / modifier letters to a standard single quote '
    # so that they are preserved by sanitization and read correctly as a single word by TTS.
    apostrophes = ["\u2018", "\u2019", "\u02bb", "\u02bc", "\u02b9", "`", "´", "ʻ", "ʼ"]
    for apo in apostrophes:
        text = text.replace(apo, "'")
        
    text = (
        text.replace("\u00e2\u20ac\u201c", "-")
        .replace("\u00e2\u20ac\u201d", "-")
        .replace("\u00c3\u00a2\u00c3\u201a\u00e2\u20ac\u201c", "-")
        .replace("\u00c3\u00a2\u00c3\u201a\u00e2\u20ac\u0153", "-")
    )
    text = sanitize_text_for_tts(text)
    text = re.sub(r"\s*-\s*", ", ", text)
    text = re.sub(r"([!?.,])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate_for_tts(text: str, max_chars: int) -> str:
    """
    Truncate text to max_chars at a sentence boundary if possible.
    max_chars == 0 means unlimited.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    # Try to cut at last sentence boundary before limit
    truncated = text[:max_chars]
    last_end = max(
        truncated.rfind("."),
        truncated.rfind("!"),
        truncated.rfind("?"),
    )
    if last_end > max_chars // 2:
        truncated = truncated[: last_end + 1]
    print(f"[TTS] Text truncated from {len(text)} to {len(truncated)} chars "
          f"(TTS_MAX_TEXT_CHARS={max_chars}).")
    return truncated.strip()


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

FALLBACK_TTS_ERROR = "Kechirasiz, ovoz chiqarishda muammo bo'ldi."
FALLBACK_TEXT_ONLY = "Mayli, hozircha javobni matn ko'rinishida ko'rsataman."


# ---------------------------------------------------------------------------
# Mixer helper
# ---------------------------------------------------------------------------

_mixer_initialized = False


def _ensure_mixer() -> None:
    global _mixer_initialized
    if not _mixer_initialized:
        buf = 4096 if sys.platform.startswith("linux") else 2048
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=buf)
        _mixer_initialized = True


# ---------------------------------------------------------------------------
# EarlyStartTTSPlayer  (interrupt-aware)
# ---------------------------------------------------------------------------

class EarlyStartTTSPlayer:
    """
    Streams edge-tts audio with early-start buffering.
    Checks _tts_interrupted flag between buffers to support stop-word cancellation.
    """

    def __init__(
        self,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        cfg: LatencyConfig,
    ) -> None:
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.cfg = cfg

    async def stream_and_play(self, text: str) -> bool:
        """
        Stream and play one text segment.
        Returns True if completed normally, False if interrupted.
        """
        if is_tts_interrupted():
            return False

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch,
            volume=self.volume,
        )

        buffer = bytearray()
        received_any = False

        try:
            async for chunk in communicate.stream():
                if is_tts_interrupted():
                    stop_playback()
                    return False
                if chunk["type"] == "audio":
                    received_any = True
                    buffer.extend(chunk["data"])
                    if len(buffer) >= self.cfg.tts_min_chunk_bytes:
                        if is_tts_interrupted():
                            stop_playback()
                            return False
                        self._play_buffer(bytes(buffer))
                        buffer = bytearray()
        except Exception as exc:
            print(f"[XATO] {FALLBACK_TTS_ERROR}: {exc}")
            print(f"[AI] {FALLBACK_TEXT_ONLY}")
            return False

        if not received_any:
            print("[WARN] TTS: no audio for segment")
            return True

        if buffer and not is_tts_interrupted():
            self._play_buffer(bytes(buffer))

        # Wait for playback, checking interrupt flag
        while pygame.mixer.music.get_busy():
            if is_tts_interrupted():
                stop_playback()
                return False
            pygame.time.Clock().tick(20)

        return True

    def _play_buffer(self, audio_bytes: bytes) -> None:
        _ensure_mixer()
        while pygame.mixer.music.get_busy():
            if is_tts_interrupted():
                stop_playback()
                return
            pygame.time.Clock().tick(20)
        stream = io.BytesIO(audio_bytes)
        pygame.mixer.music.load(stream, "mp3")
        pygame.mixer.music.play()


# ---------------------------------------------------------------------------
# _async_speak and run_speak  (interrupt-aware, TTS_MAX_TEXT_CHARS support)
# ---------------------------------------------------------------------------

async def _async_speak(
    text: str,
    cfg: LatencyConfig,
    vcfg: "VoiceConfig | None" = None,
) -> None:
    clean = prepare_uzbek_spoken_text(text)
    if not clean:
        return

    # Apply TTS_MAX_TEXT_CHARS if configured
    if vcfg is not None and vcfg.tts_max_text_chars > 0:
        clean = truncate_for_tts(clean, vcfg.tts_max_text_chars)

    segments = split_long_speech_into_chunks(clean)
    voice = os.environ.get("EDGE_TTS_VOICE", "uz-UZ-SardorNeural")
    rate = os.environ.get("EDGE_TTS_RATE", "+15%")
    pitch = os.environ.get("EDGE_TTS_PITCH", "+50Hz")
    volume = os.environ.get("EDGE_TTS_VOLUME", "+18%")
    player = EarlyStartTTSPlayer(voice, rate, pitch, volume, cfg)
    for segment in segments:
        if is_tts_interrupted():
            print("[TTS] Playback cancelled (interrupt).")
            break
        completed = await player.stream_and_play(segment)
        if not completed:
            print("[TTS] Segment interrupted.")
            break


def run_speak(
    text: str,
    cfg: LatencyConfig,
    vcfg: "VoiceConfig | None" = None,
) -> None:
    """
    Run TTS on the dedicated background loop thread.

    Uses asyncio.run_coroutine_threadsafe() so the caller never drives an
    event loop directly — that fully avoids
    "Cannot run the event loop while another loop is running".

    A process-wide RLock serialises playback so concurrent callers (main
    loop + face-greeting handler) don't overlap their audio.
    """
    if not _tts_run_lock.acquire(timeout=30.0):
        print("[WARN] TTS busy >30s — dropping this utterance.")
        return
    try:
        clear_tts_interrupt()
        loop = get_tts_loop()
        coro = _async_speak(text, cfg, vcfg)
        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as exc:
            print(f"[XATO] TTS schedule failed: {exc}")
            try:
                coro.close()
            except Exception:
                pass
            try:
                stop_playback()
            except Exception:
                pass
            return

        # Block the caller until playback finishes (or fails).
        try:
            future.result()
        except Exception as exc:
            print(f"[XATO] TTS playback failed: {exc}")
            try:
                stop_playback()
            except Exception:
                pass
    finally:
        _tts_run_lock.release()

