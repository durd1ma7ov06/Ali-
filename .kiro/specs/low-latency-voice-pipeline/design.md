# Design Document: Low-Latency Voice Pipeline

## Overview

This document describes the technical design for refactoring the humanoid robot voice pipeline
to minimize end-to-end latency. The refactor targets six concrete bottlenecks in the current
sequential, fully-blocking pipeline:

1. Per-turn ambient noise calibration (500–800 ms wasted every turn)
2. Hard-coded `pause_threshold=1.0` (robot waits too long after user stops speaking)
3. `asyncio.run()` per TTS call (new event loop overhead each utterance)
4. Full TTS buffer before playback starts (waits for entire audio before first sound)
5. Blocking arm command execution (arm movement delays TTS start)
6. Unconditional `time.sleep(0.3)` between turns

The design introduces five new helper abstractions — `LatencyConfig`, `LatencyTimer`,
`_tts_loop` (persistent event loop), `EarlyStartTTSPlayer`, and `ArmCommandWorker` — all
implemented using Python stdlib only (`threading`, `asyncio`, `queue`). Both `main.py`
(Windows) and `main_rpi.py` (Raspberry Pi) share these helpers via a new `pipeline_core.py`
module, eliminating duplication while preserving each entry point's platform-specific setup.

---

## Architecture

### Before (current — fully sequential, blocking)

```
main loop
  │
  ├─ listen()
  │    └─ adjust_for_ambient_noise()  ← 500–800 ms EVERY turn
  │    └─ recognizer.listen()
  │    └─ recognize_google()          ← network, blocking
  │
  ├─ think()                          ← OpenRouter API, no timeout, blocking
  │
  ├─ speak()
  │    └─ asyncio.run(...)            ← new event loop each call
  │         └─ _generate_edge_audio_bytes()  ← full buffer before playback
  │         └─ pygame.mixer.music.play()
  │
  ├─ execute_arm_voice_command()      ← blocks main thread
  │    └─ move_arms_to_offsets()
  │
  └─ time.sleep(0.3)                  ← unconditional delay
```

### After (refactored — overlapping stages, configurable)

```
startup
  ├─ LatencyConfig.load()             ← reads all new env vars once
  ├─ _tts_loop = new asyncio loop     ← persistent, reused every turn
  ├─ ArmCommandWorker.start()         ← background arm thread, idle
  └─ adjust_for_ambient_noise()       ← ONE TIME only

main loop
  │
  ├─ listen()                         ← no calibration; VAD thresholds from config
  │    └─ recognizer.listen(timeout=VAD_LISTEN_TIMEOUT,
  │                          phrase_time_limit=VAD_PHRASE_TIME_LIMIT)
  │    └─ recognize_google()
  │
  ├─ think()                          ← per-model AI_REQUEST_TIMEOUT; fast-path unchanged
  │
  ├─ speak_pipeline()
  │    ├─ ArmCommandWorker.dispatch() ← non-blocking, arm moves in background
  │    └─ EarlyStartTTSPlayer.play()  ← streams chunks; playback starts at TTS_MIN_CHUNK_BYTES
  │         ├─ edge-tts.communicate.stream()
  │         └─ pygame playback starts before stream ends
  │
  └─ cooldown(TURN_COOLDOWN_SECONDS)  ← default 0.0; waits for mixer.get_busy()==False
```

### Data Flow Diagram

```
User speaks
    │
    ▼
[listen()]  ──────────────────────────────────────────────────────────────────────
    │  VAD_PAUSE_THRESHOLD, VAD_NON_SPEAKING_DURATION, VAD_LISTEN_TIMEOUT         │
    │  VAD_PHRASE_TIME_LIMIT                                                       │
    ▼                                                                              │
[think()]  ←── fast-path (greeting/time/date) ──► return immediately              │
    │  AI_REQUEST_TIMEOUT per model attempt                                        │
    ▼                                                                              │
[speak_pipeline()]                                                                 │
    ├──► ArmCommandWorker.dispatch(arm_offsets)  ──► Arm_Thread (background)       │
    │                                                  move_arms_to_offsets()      │
    │                                                  ESP32 serial (Lock)         │
    └──► EarlyStartTTSPlayer.play(text)                                            │
              │                                                                    │
              ├─ split_long_speech_into_chunks()                                   │
              └─ for each chunk:                                                   │
                    _tts_loop.run_until_complete(                                  │
                        _stream_and_play_chunk(chunk)                              │
                    )                                                              │
                    │                                                              │
                    ├─ edge_tts.Communicate.stream()  ← async generator            │
                    ├─ buffer until TTS_MIN_CHUNK_BYTES                            │
                    ├─ pygame.mixer.music.load() + play()  ← EARLY START           │
                    └─ continue buffering remaining bytes                          │
    │                                                                              │
    ▼                                                                              │
[cooldown()]                                                                       │
    wait for mixer.get_busy()==False                                               │
    sleep(TURN_COOLDOWN_SECONDS)  ← default 0.0                                   │
    │                                                                              │
    └──────────────────────────────────────────────────────────────────────────────
```

---

## Components and Interfaces

### New module: `pipeline_core.py`

All new shared logic lives in a single new file `pipeline_core.py` in the project root.
Both `main.py` and `main_rpi.py` import from it. This avoids duplicating the five new
abstractions across both entry points.

```
pipeline_core.py
  ├── LatencyConfig          (dataclass + class method load())
  ├── LatencyTimer           (context manager / helper for [TIMING] logging)
  ├── _tts_loop management   (module-level loop + get/close functions)
  ├── EarlyStartTTSPlayer    (async streaming + early playback)
  └── ArmCommandWorker       (background arm thread dispatcher)
```

`main.py` and `main_rpi.py` keep all existing code unchanged except:
- Import the five abstractions from `pipeline_core`
- Replace `asyncio.run(speak(...))` with `run_speak(text, cfg)`
- Replace `time.sleep(0.3)` with `turn_cooldown(cfg)`
- Move `adjust_for_ambient_noise()` out of `listen()` into `main()` startup
- Pass `cfg` (LatencyConfig) into `listen()`, `think()`, and `speak_pipeline()`
- Call `ArmCommandWorker.dispatch()` instead of direct `execute_arm_voice_command()`

### Shared helper functions (in `pipeline_core.py`)

```python
def run_speak(text: str, cfg: LatencyConfig) -> None:
    """Entry point called from main loop. Runs EarlyStartTTSPlayer on _tts_loop."""

def turn_cooldown(cfg: LatencyConfig) -> None:
    """Wait for mixer silence, then sleep TURN_COOLDOWN_SECONDS."""

def calibrate_once(recognizer: sr.Recognizer, mic: sr.Microphone,
                   cfg: LatencyConfig) -> None:
    """Single startup ambient noise calibration."""

def configure_recognizer(recognizer: sr.Recognizer, cfg: LatencyConfig) -> None:
    """Apply VAD thresholds from config to recognizer."""
```

---

## Data Models

### `LatencyConfig` dataclass

```python
from dataclasses import dataclass, field

@dataclass
class LatencyConfig:
    # VAD
    vad_ambient_calibration_duration: float = 1.0   # VAD_AMBIENT_CALIBRATION_DURATION
    vad_pause_threshold: float = 0.6                # VAD_PAUSE_THRESHOLD
    vad_non_speaking_duration: float = 0.3          # VAD_NON_SPEAKING_DURATION
    vad_phrase_time_limit: int = 8                  # VAD_PHRASE_TIME_LIMIT
    vad_listen_timeout: int = 5                     # VAD_LISTEN_TIMEOUT

    # TTS
    tts_min_chunk_bytes: int = 4096                 # TTS_MIN_CHUNK_BYTES

    # AI
    ai_request_timeout: float = 15.0               # AI_REQUEST_TIMEOUT

    # Arm
    arm_command_timeout: float = 5.0               # ARM_COMMAND_TIMEOUT

    # Turn
    turn_cooldown_seconds: float = 0.0             # TURN_COOLDOWN_SECONDS

    # Logging
    latency_logging_enabled: bool = True           # LATENCY_LOGGING_ENABLED
    latency_log_level: str = "summary"             # LATENCY_LOG_LEVEL ("summary"|"verbose")

    @classmethod
    def load(cls) -> "LatencyConfig":
        """
        Read all latency env vars, validate ranges, log warnings for invalid values,
        apply clamping rules (e.g. non_speaking <= pause_threshold), and return
        a fully resolved LatencyConfig instance.

        Prints [LATENCY CONFIG] lines if latency_logging_enabled is True.
        """
        ...
```

#### Validation rules applied in `LatencyConfig.load()`

| Variable | Valid range | Default | Clamp rule |
|---|---|---|---|
| `VAD_AMBIENT_CALIBRATION_DURATION` | `>= 0` (float) | `1.0` | — |
| `VAD_PAUSE_THRESHOLD` | `0.2 – 3.0` | `0.6` | — |
| `VAD_NON_SPEAKING_DURATION` | `0.1 – 2.0` | `0.3` | clamp to `pause_threshold` if greater |
| `VAD_PHRASE_TIME_LIMIT` | `1 – 60` (int) | `8` | — |
| `VAD_LISTEN_TIMEOUT` | `1 – 60` (int) | `5` | — |
| `TTS_MIN_CHUNK_BYTES` | `>= 512` (int) | `4096` | — |
| `AI_REQUEST_TIMEOUT` | `0.1 – 300.0` | `15.0` | — |
| `ARM_COMMAND_TIMEOUT` | `0.0 – 60.0` | `5.0` | — |
| `TURN_COOLDOWN_SECONDS` | `0.0 – 5.0` | `0.0` | — |
| `LATENCY_LOGGING_ENABLED` | `true` / `false` | `true` | — |
| `LATENCY_LOG_LEVEL` | `summary` / `verbose` | `summary` | — |

All validation warnings use the format:
`[WARN] <VAR_NAME>: invalid value <value!r>, using default <default>`

### `LatencyTimer`

```python
import time

class LatencyTimer:
    """
    Lightweight wall-clock stage timer.

    Usage (context manager):
        with LatencyTimer("stt", cfg) as t:
            text = recognizer.recognize_google(audio)
        # logs: [TIMING] stt: 312ms  (if verbose or if stage is in summary set)

    Usage (manual):
        t = LatencyTimer("ai", cfg)
        t.start()
        response = think(text)
        t.stop()   # logs immediately
    """

    # Stages included in summary mode output
    SUMMARY_STAGES = {"listen_complete", "tts_playback_complete"}

    def __init__(self, stage_name: str, cfg: LatencyConfig) -> None:
        self.stage_name = stage_name
        self.cfg = cfg
        self._t0: float | None = None
        self._t1: float | None = None

    def start(self) -> "LatencyTimer":
        self._t0 = time.monotonic()
        return self

    def stop(self) -> float:
        """Stop timer, log if enabled, return elapsed seconds."""
        self._t1 = time.monotonic()
        elapsed = self._t1 - (self._t0 or self._t1)
        self._maybe_log(elapsed)
        return elapsed

    def elapsed_ms(self) -> int:
        if self._t0 is None or self._t1 is None:
            return 0
        return round((self._t1 - self._t0) * 1000)

    def _maybe_log(self, elapsed: float) -> None:
        if not self.cfg.latency_logging_enabled:
            return
        if self.cfg.latency_log_level == "verbose":
            print(f"[TIMING] {self.stage_name}: {round(elapsed * 1000)}ms")
        elif self.cfg.latency_log_level == "summary":
            if self.stage_name in self.SUMMARY_STAGES:
                print(f"[TIMING] {self.stage_name}: {round(elapsed * 1000)}ms")

    def __enter__(self) -> "LatencyTimer":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()
```

#### Stage names and their log keys

| Stage | `stage_name` string | In summary? |
|---|---|---|
| Mic capture start | `mic_capture_start` | no |
| VAD/listen complete | `listen_complete` | yes |
| STT complete | `stt_complete` | no |
| AI response complete | `ai_complete` | no |
| TTS first-chunk ready | `tts_first_chunk` | no |
| TTS playback complete | `tts_playback_complete` | yes |
| Hardware command dispatch | `arm_dispatch` | no |

Summary mode logs a single derived line:
`[TIMING] turn_total: <ms>ms`
where `turn_total = tts_playback_complete.t1 - listen_complete.t0`.

---

## Persistent Event Loop Pattern

### Design

A single `asyncio` event loop is created once at module import time in `pipeline_core.py`
and stored in a module-level variable `_tts_loop`. All `speak()` calls use
`_tts_loop.run_until_complete(...)` instead of `asyncio.run(...)`.

```python
# pipeline_core.py  — module level
import asyncio
import threading

_tts_loop: asyncio.AbstractEventLoop | None = None
_tts_loop_lock = threading.Lock()


def get_tts_loop() -> asyncio.AbstractEventLoop:
    """
    Return the persistent TTS event loop, creating it if necessary.
    Thread-safe. Called once during startup and on recovery after loop failure.
    """
    global _tts_loop
    with _tts_loop_lock:
        if _tts_loop is None or _tts_loop.is_closed():
            _tts_loop = asyncio.new_event_loop()
        return _tts_loop


def close_tts_loop() -> None:
    """
    Close the persistent TTS event loop. Called at program exit.
    Registered with atexit and called explicitly in KeyboardInterrupt handler.
    """
    global _tts_loop
    with _tts_loop_lock:
        if _tts_loop is not None and not _tts_loop.is_closed():
            try:
                _tts_loop.close()
            except Exception:
                pass
        _tts_loop = None
```

### How `run_speak()` uses the loop

```python
def run_speak(text: str, cfg: LatencyConfig) -> None:
    """
    Run the async speak coroutine on the persistent TTS loop.
    Retries once if the loop is closed or raises RuntimeError.
    """
    loop = get_tts_loop()
    try:
        loop.run_until_complete(_async_speak(text, cfg))
    except RuntimeError as exc:
        print(f"[WARN] TTS loop error: {exc}. Retrying with new loop.")
        close_tts_loop()
        loop = get_tts_loop()
        try:
            loop.run_until_complete(_async_speak(text, cfg))
        except Exception as retry_exc:
            print(f"[XATO] TTS retry failed: {retry_exc}")
```

### Shutdown sequence

```python
import atexit
atexit.register(close_tts_loop)
```

Both `main.py` and `main_rpi.py` also call `close_tts_loop()` explicitly in their
`KeyboardInterrupt` handler before printing the farewell message.

---

## Early-Start TTS Streaming Pattern

### Problem

The current `_generate_edge_audio_bytes()` collects the entire MP3 stream into a
`bytearray` before returning. For a 3-second utterance this means ~1–2 seconds of
network latency before the first sound plays.

### Solution: `EarlyStartTTSPlayer`

Stream chunks from `edge_tts.Communicate.stream()` into a buffer. Once the buffer
reaches `TTS_MIN_CHUNK_BYTES`, hand it off to `pygame.mixer.music` immediately and
continue accumulating the remainder. When the stream ends, play any leftover bytes.

```python
class EarlyStartTTSPlayer:
    """
    Streams edge-tts audio and starts pygame playback as soon as
    TTS_MIN_CHUNK_BYTES have been buffered, without waiting for the full stream.
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

    async def stream_and_play(self, text: str, timer: LatencyTimer | None = None) -> None:
        """
        Async coroutine. Streams one text segment from edge-tts and plays it
        with early-start buffering. Called via _tts_loop.run_until_complete().

        Steps:
          1. Create edge_tts.Communicate instance.
          2. Iterate communicate.stream() collecting audio chunks.
          3. When buffer >= TTS_MIN_CHUNK_BYTES: call _play_buffer(buffer), reset buffer.
             Record tts_first_chunk timer on first play call.
          4. After stream ends: if buffer non-empty, call _play_buffer(buffer).
          5. Wait for pygame.mixer.music.get_busy() == False.
        """
        ...

    def _play_buffer(self, audio_bytes: bytes) -> None:
        """
        Load bytes into pygame.mixer.music and start playback.
        Waits for any currently-playing audio to finish before loading new bytes,
        so consecutive buffers play sequentially without overlap.
        """
        _ensure_mixer()
        # Wait for previous buffer to finish
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(20)
        stream = io.BytesIO(audio_bytes)
        pygame.mixer.music.load(stream, "mp3")
        pygame.mixer.music.play()
```

### Sequence diagram for a single text chunk

```
edge-tts server
    │  chunk1 (1 KB)  ──►  buffer=[1KB]   < TTS_MIN_CHUNK_BYTES(4KB), keep buffering
    │  chunk2 (1 KB)  ──►  buffer=[2KB]   < threshold
    │  chunk3 (1 KB)  ──►  buffer=[3KB]   < threshold
    │  chunk4 (1 KB)  ──►  buffer=[4KB]   >= threshold → _play_buffer([4KB])
    │                                        pygame starts playing ← EARLY START
    │  chunk5 (1 KB)  ──►  buffer=[1KB]   (new buffer, stream continues)
    │  chunk6 (0.5KB) ──►  buffer=[1.5KB]
    │  [stream ends]  ──►  buffer=[1.5KB] non-empty → _play_buffer([1.5KB])
    │                                        wait for get_busy()==False
    ▼
  done
```

### Integration with `speak_pipeline()`

```python
async def _async_speak(text: str, cfg: LatencyConfig) -> None:
    """
    Top-level async speak function. Splits text, plays each chunk via
    EarlyStartTTSPlayer. Called from run_speak() via _tts_loop.run_until_complete().
    """
    clean = prepare_uzbek_spoken_text(text)
    if not clean:
        return
    segments = split_long_speech_into_chunks(clean)  # unchanged, 280-char limit
    player = EarlyStartTTSPlayer(
        EDGE_TTS_VOICE, EDGE_TTS_RATE, EDGE_TTS_PITCH, EDGE_TTS_VOLUME, cfg
    )
    for segment in segments:
        await player.stream_and_play(segment)
```

---

## ArmCommandWorker / Background Arm Thread Pattern

### Problem

`execute_arm_voice_command()` calls `move_arms_to_offsets()` which loops over
`ARM_COMMAND_STEPS` steps with `time.sleep(ARM_COMMAND_STEP_DELAY)` between each —
typically 10 steps × 45 ms = ~450 ms of blocking on the main thread before TTS starts.

### Solution: `ArmCommandWorker`

A single persistent background thread that accepts arm movement jobs via a `queue.Queue`.
The main thread enqueues a job and immediately proceeds to TTS. The worker thread
executes `move_arms_to_offsets()` independently.

```python
import queue
import threading
from typing import Callable

class ArmCommandWorker:
    """
    Background worker that executes arm movement commands off the main thread.

    One instance is created at startup and kept alive for the session.
    The main thread calls dispatch() to enqueue a movement; the worker
    thread calls the provided callable (move_arms_to_offsets) asynchronously.
    """

    def __init__(self, cfg: LatencyConfig) -> None:
        self.cfg = cfg
        self._queue: queue.Queue[Callable[[], None] | None] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._current_job_done = threading.Event()
        self._current_job_done.set()  # initially "done"

    def start(self) -> None:
        """Start the background worker thread. Called once at startup."""
        self._thread = threading.Thread(
            target=self._run,
            name="arm-command-worker",
            daemon=True,
        )
        self._thread.start()

    def dispatch(self, job: Callable[[], None]) -> None:
        """
        Enqueue an arm movement job.

        If a previous job is still running, wait up to ARM_COMMAND_TIMEOUT seconds.
        If it hasn't finished by then, log a warning and proceed anyway (the new
        job will be queued and run after the current one finishes naturally).

        Args:
            job: A zero-argument callable, typically a lambda wrapping
                 move_arms_to_offsets(target_offsets, steps, step_delay).
        """
        finished = self._current_job_done.wait(timeout=self.cfg.arm_command_timeout)
        if not finished:
            print(
                f"[WARN] ArmCommandWorker: previous job still running after "
                f"{self.cfg.arm_command_timeout}s, proceeding anyway."
            )
        self._current_job_done.clear()
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            # Drop oldest, enqueue new (maxsize=1 means at most one pending job)
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(job)

    def stop(self) -> None:
        """Signal the worker to exit. Called at shutdown."""
        self._queue.put(None)  # sentinel
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
```

### Integration in main loop

```python
# In main() after startup:
arm_worker = ArmCommandWorker(cfg)
arm_worker.start()

# In conversation loop:
arm_response = hardware.execute_arm_voice_command(user_text)
if arm_response:
    # Dispatch arm movement to background thread
    arm_worker.dispatch(lambda: hardware.move_arms_to_offsets(target_offsets))
    # TTS starts immediately — arm moves concurrently
    run_speak(arm_response, cfg)
    continue
```

### ESP32 serial safety

`move_arms_to_offsets()` calls `controller.send_arm_offsets()` which calls
`controller.send_line()`. `send_line()` already acquires `self._lock` (a
`threading.Lock`) before writing to the serial port. The `ArmCommandWorker` thread
and any other thread (e.g. `FaceServoTracker`) therefore cannot interleave bytes.
No changes to `Esp32SerialController` are required.

---

## Component Design: Changed Modules

### `pipeline_core.py` (new file)

Full public API:

```python
# Config
class LatencyConfig: ...                          # dataclass, see Data Models
def load_latency_config() -> LatencyConfig: ...   # alias for LatencyConfig.load()

# Event loop
def get_tts_loop() -> asyncio.AbstractEventLoop: ...
def close_tts_loop() -> None: ...

# Timing
class LatencyTimer: ...                           # see Data Models

# TTS
class EarlyStartTTSPlayer: ...                    # see Early-Start TTS section
async def _async_speak(text: str, cfg: LatencyConfig) -> None: ...
def run_speak(text: str, cfg: LatencyConfig) -> None: ...

# Arm
class ArmCommandWorker: ...                       # see Arm section

# Helpers
def calibrate_once(recognizer, mic, cfg: LatencyConfig) -> None: ...
def configure_recognizer(recognizer, cfg: LatencyConfig) -> None: ...
def turn_cooldown(cfg: LatencyConfig) -> None: ...
```

### `main.py` — changes summary

| Location | Before | After |
|---|---|---|
| `listen()` | `adjust_for_ambient_noise(source, duration=0.5)` every call | Removed; calibration moved to `main()` startup |
| `listen()` | `timeout=10, phrase_time_limit=15` hard-coded | `timeout=cfg.vad_listen_timeout, phrase_time_limit=cfg.vad_phrase_time_limit` |
| `think()` | No timeout on `client.chat.completions.create()` | `timeout=cfg.ai_request_timeout` per model attempt |
| `speak()` / `speak_with_greeting_motion()` | `asyncio.run(speak(...))` | `run_speak(text, cfg)` |
| `main()` | `recognizer.pause_threshold = 1.0` hard-coded | `configure_recognizer(recognizer, cfg)` |
| `main()` | No startup calibration | `calibrate_once(recognizer, mic, cfg)` |
| `main()` | No `ArmCommandWorker` | `arm_worker = ArmCommandWorker(cfg); arm_worker.start()` |
| Main loop | `asyncio.run(speak(arm_response))` | `arm_worker.dispatch(...); run_speak(arm_response, cfg)` |
| Main loop | `time.sleep(0.3)` | `turn_cooldown(cfg)` |
| Main loop | No timing | `LatencyTimer` wraps each stage |
| `KeyboardInterrupt` | `asyncio.run(speak(farewell))` | `run_speak(farewell, cfg); close_tts_loop()` |

### `main_rpi.py` — identical changes

`main_rpi.py` receives the exact same set of changes as `main.py`. The only
platform-specific difference that already exists (`SDL_AUDIODRIVER=alsa`,
`recognizer.non_speaking_duration=0.5`) is preserved; `non_speaking_duration` is
now set via `configure_recognizer()` using `cfg.vad_non_speaking_duration`.

### `robot_hardware.py` — no changes

`robot_hardware.py` is not modified. `execute_arm_voice_command()` continues to
call `move_arms_to_offsets()` directly when invoked. The caller (`main.py` /
`main_rpi.py`) is responsible for wrapping the call in `ArmCommandWorker.dispatch()`.

The `FaceServoTracker`, `CameraRuntime`, `GreetingMotionRuntime`, and
`Esp32SerialController` classes are untouched.

### `.env.example` — additions

The following lines are appended to `.env.example` under a new `# Latency tuning` section:

```dotenv
# Latency tuning
VAD_AMBIENT_CALIBRATION_DURATION=1.0
VAD_PAUSE_THRESHOLD=0.6
VAD_NON_SPEAKING_DURATION=0.3
VAD_PHRASE_TIME_LIMIT=8
VAD_LISTEN_TIMEOUT=5
TTS_MIN_CHUNK_BYTES=4096
AI_REQUEST_TIMEOUT=15.0
ARM_COMMAND_TIMEOUT=5.0
TURN_COOLDOWN_SECONDS=0.0
LATENCY_LOGGING_ENABLED=true
LATENCY_LOG_LEVEL=summary
```

---

## How `main.py` and `main_rpi.py` Share New Logic

### Strategy: shared `pipeline_core.py`, thin entry points

```
pipeline_core.py          ← all new logic lives here
    ▲                ▲
    │                │
main.py          main_rpi.py
(Windows)        (Raspberry Pi / Linux)
```

Both entry points:
1. `from pipeline_core import (LatencyConfig, LatencyTimer, ArmCommandWorker, run_speak, turn_cooldown, calibrate_once, configure_recognizer)`
2. Call `cfg = LatencyConfig.load()` at the top of `main()`
3. Use the same `listen()`, `think()`, `speak_pipeline()` call sites

Platform differences that remain in each entry point:
- `main.py`: `pygame.mixer.init(buffer=2048)` (Windows buffer size)
- `main_rpi.py`: `os.environ.setdefault("SDL_AUDIODRIVER", "alsa")` before pygame import
- `main_rpi.py`: `pygame.mixer.init(buffer=4096)` (RPi needs larger buffer)

Neither entry point duplicates `LatencyConfig`, `LatencyTimer`, `EarlyStartTTSPlayer`,
`ArmCommandWorker`, or the persistent loop management.

### `speak_with_greeting_motion()` — updated in both entry points

```python
def speak_with_greeting_motion(text: str, cfg: LatencyConfig) -> None:
    """
    Start greeting arm motion, then run TTS on persistent loop.
    Arm motion and speech overlap in time (Requirement 10.2).
    """
    gesture = hardware.start_greeting_motion()
    try:
        run_speak(text, cfg)   # replaces asyncio.run(speak(text))
    finally:
        gesture.finish()
```

---

## Error Handling and Fallback Paths

### VAD / `listen()`

| Failure | Handling |
|---|---|
| `sr.WaitTimeoutError` | Return `None`; main loop continues to next turn |
| `sr.UnknownValueError` | Print `FALLBACK_STT_ERROR`; return `None` |
| Any other exception | Print `[XATO] Mikrofon xatosi: {exc}`; return `None` |
| `VAD_AMBIENT_CALIBRATION_DURATION=0` | Skip `adjust_for_ambient_noise()` entirely |

### AI / `think()`

| Failure | Handling |
|---|---|
| Single model timeout (`AI_REQUEST_TIMEOUT`) | Log warning with model name + elapsed ms; try next model |
| All models exhausted | Return `FALLBACK_API_ERROR` string; log last error |
| Non-numeric `AI_REQUEST_TIMEOUT` | `LatencyConfig.load()` logs warning; uses default 15.0 |

The `timeout` parameter is passed to `client.chat.completions.create()` via the
`openai` SDK's `timeout` keyword argument (supported since openai-python v1.x).
On timeout the SDK raises `openai.APITimeoutError` which is caught in the per-model
`except Exception` block.

### TTS / `EarlyStartTTSPlayer`

| Failure | Handling |
|---|---|
| `edge-tts` returns no audio chunks | Log `[WARN] TTS: no audio for segment`; skip segment |
| Exception mid-stream | Log `[XATO] {FALLBACK_TTS_ERROR}: {exc}`; print `FALLBACK_TEXT_ONLY`; return |
| Persistent loop closed / RuntimeError | `run_speak()` retries once with new loop; if retry fails, log and return |
| `pygame.mixer` not initialized | `_ensure_mixer()` called before every `_play_buffer()` |

### Arm / `ArmCommandWorker`

| Failure | Handling |
|---|---|
| Previous job still running at `ARM_COMMAND_TIMEOUT` | Log warning; proceed to enqueue new job |
| Job callable raises exception | Log `[WARN] ArmCommandWorker: job failed: {exc}`; set done event; continue |
| Worker thread dies unexpectedly | `dispatch()` will block on `_current_job_done.wait()` indefinitely; mitigated by daemon=True (process exit cleans up) |

### Shutdown / `KeyboardInterrupt`

```python
except KeyboardInterrupt:
    farewell = "Tanishganimdan xursandman. Suhbat uchun rahmat."
    print(f"[AI] {farewell}")
    run_speak(farewell, cfg)
    arm_worker.stop()
    close_tts_loop()
    print("[STOP] Dastur to'xtatildi.")
    break
```

`atexit.register(close_tts_loop)` provides a safety net for abnormal exits.
`atexit.register(arm_worker.stop)` ensures the arm worker sentinel is sent.

---

## Cleanup / Shutdown Sequence

```
KeyboardInterrupt or is_goodbye==True
    │
    ├─ run_speak(farewell, cfg)          ← plays farewell on persistent loop
    ├─ arm_worker.stop()                 ← sends None sentinel; joins thread (2s timeout)
    ├─ close_tts_loop()                  ← closes asyncio loop
    ├─ camera_runtime.stop()             ← if camera was started (existing behavior)
    └─ hardware.close_esp32_controller() ← via atexit (existing behavior)
```

`atexit` registrations (in order of registration):
1. `hardware.close_esp32_controller` — registered inside `get_esp32_controller()` (existing)
2. `close_tts_loop` — registered in `pipeline_core.py` at import time
3. `arm_worker.stop` — registered in `main()` after `arm_worker.start()`

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid
executions of a system — essentially, a formal statement about what the system should do.
Properties serve as the bridge between human-readable specifications and machine-verifiable
correctness guarantees.*

### Property 1: Calibration happens exactly once

*For any* number of conversation turns N ≥ 1, the `adjust_for_ambient_noise()` function
SHALL be called exactly once across the entire session, regardless of N.

**Validates: Requirements 1.1, 1.2**

---

### Property 2: VAD threshold configuration round-trip

*For any* valid float value V in [0.2, 3.0] assigned to `VAD_PAUSE_THRESHOLD`, the
`recognizer.pause_threshold` attribute SHALL equal V after `configure_recognizer()` is
called.

**Validates: Requirements 2.1, 2.3**

---

### Property 3: Invalid VAD threshold falls back to default

*For any* float value V outside [0.2, 3.0] (or any non-numeric string) assigned to
`VAD_PAUSE_THRESHOLD`, the resolved `LatencyConfig.vad_pause_threshold` SHALL equal
`0.6` and a warning SHALL be logged identifying the variable name and rejected value.

**Validates: Requirements 2.4, 2.5**

---

### Property 4: Non-speaking duration clamping invariant

*For any* pair of values (pause, non_speaking) where both are individually valid but
`non_speaking > pause`, the resolved `vad_non_speaking_duration` SHALL equal
`vad_pause_threshold` (i.e., be clamped down), and a warning SHALL be logged.

**Validates: Requirement 2.6**

---

### Property 5: Persistent TTS loop identity

*For any* number of `run_speak()` calls N ≥ 2 on a healthy loop, the `id()` of the
event loop used SHALL be the same for all N calls (i.e., no new loop is created
between calls).

**Validates: Requirements 3.1, 3.2**

---

### Property 6: Early-start playback threshold

*For any* `TTS_MIN_CHUNK_BYTES` value B and any mock audio stream whose chunks arrive
one at a time, `pygame.mixer.music.play()` SHALL be called for the first time only
after the accumulated buffer size first reaches or exceeds B bytes.

**Validates: Requirements 4.1, 4.3**

---

### Property 7: Remaining buffer is always played

*For any* audio stream that ends with a non-empty buffer smaller than
`TTS_MIN_CHUNK_BYTES`, `_play_buffer()` SHALL be called with those remaining bytes
before `stream_and_play()` returns.

**Validates: Requirement 4.5**

---

### Property 8: Empty or error stream does not propagate exception

*For any* edge-tts stream that produces zero audio bytes or raises an exception at
any point during iteration, `stream_and_play()` SHALL return normally (no exception
propagates to the caller) and SHALL log a warning.

**Validates: Requirement 4.4**

---

### Property 9: Text chunk length invariant

*For any* input text string of arbitrary length, every element of
`split_long_speech_into_chunks(text)` SHALL have length ≤ 280 characters.

**Validates: Requirement 4.6**

---

### Property 10: Arm command executes off main thread

*For any* arm command text that `execute_arm_voice_command()` recognizes, the
`move_arms_to_offsets()` call dispatched via `ArmCommandWorker` SHALL run in a thread
whose `threading.current_thread()` is NOT `threading.main_thread()`.

**Validates: Requirement 5.1**

---

### Property 11: TTS starts before arm thread completes

*For any* arm command that takes longer than 0 ms, the timestamp at which
`pygame.mixer.music.play()` is first called SHALL be less than the timestamp at which
the `ArmCommandWorker` job callable returns.

**Validates: Requirement 5.2**

---

### Property 12: AI timeout is applied per model attempt

*For any* valid `AI_REQUEST_TIMEOUT` value T in [0.1, 300.0], the `timeout` keyword
argument passed to each `client.chat.completions.create()` call SHALL equal T.

**Validates: Requirement 6.1**

---

### Property 13: Fast-path bypasses API for known patterns

*For any* input text that matches any entry in `SALOMLASHISH`, `XAYRLASHISH`,
`YORDAM`, `DATE_QUERY_KEYWORDS`, or `TIME_QUERY_KEYWORDS`, `think()` SHALL return
without calling `client.chat.completions.create()`.

**Validates: Requirement 6.4**

---

### Property 14: Turn cooldown matches configuration

*For any* valid `TURN_COOLDOWN_SECONDS` value S in [0.0, 5.0], the `time.sleep()`
call in `turn_cooldown()` SHALL be called with argument S (or not called at all when
S == 0.0).

**Validates: Requirement 7.2**

---

### Property 15: No listen() call while audio is playing

*For any* pipeline turn where `TURN_COOLDOWN_SECONDS == 0.0`, `listen()` SHALL NOT
be called while `pygame.mixer.music.get_busy()` returns `True`.

**Validates: Requirement 7.3**

---

### Property 16: Timing log format correctness

*For any* stage duration D seconds, the integer millisecond value logged in the
`[TIMING] <stage>: <ms>ms` line SHALL equal `round(D * 1000)`.

**Validates: Requirement 8.2**

---

### Property 17: No timing output when logging disabled

*For any* pipeline execution with `LATENCY_LOGGING_ENABLED=false`, the stdout output
SHALL contain zero lines matching the pattern `^\[TIMING\]`.

**Validates: Requirement 8.3**

---

### Property 18: Summary mode logs only total turn time

*For any* pipeline execution with `LATENCY_LOG_LEVEL=summary`, the stdout output
SHALL contain exactly one `[TIMING]` line and it SHALL contain the string
`turn_total`.

**Validates: Requirement 8.6**

---

### Property 19: Invalid latency config values fall back to defaults

*For any* environment variable in the latency config set to an invalid value (out of
range or wrong type), `LatencyConfig.load()` SHALL use the documented default value
for that variable and SHALL log a warning identifying the variable name and rejected
value.

**Validates: Requirements 1.5, 2.4, 2.5, 6.1, 7.2, 8.7, 9.3**

---

## Testing Strategy

### Dual Testing Approach

Unit tests cover specific examples, edge cases, and error conditions. Property-based
tests verify universal invariants across many generated inputs. Both are needed: unit
tests catch concrete bugs in known scenarios; property tests find edge cases that
example-based tests miss.

### Property-Based Testing Library

Use **Hypothesis** (Python) for all property-based tests. Hypothesis is already
compatible with the project's Python 3.12 environment and requires no new runtime
dependencies (test-only).

```
pip install hypothesis  # test dependency only
```

Each property test runs a minimum of **100 iterations** (Hypothesis default is 100;
increase with `@settings(max_examples=200)` for critical properties).

Tag format for each test:
```python
# Feature: low-latency-voice-pipeline, Property N: <property_text>
```

### Unit Tests

Focus areas:
- `LatencyConfig.load()` with specific valid and invalid env var combinations
- `LatencyTimer` output format (exact string matching)
- `turn_cooldown()` with `TURN_COOLDOWN_SECONDS=0.0` (no sleep called)
- `run_speak()` retry logic when loop raises `RuntimeError`
- `ArmCommandWorker.dispatch()` timeout warning path
- `speak_with_greeting_motion()` — arm motion starts before TTS returns
- Shutdown sequence — `close_tts_loop()` called on `KeyboardInterrupt`
- `think()` fast-path — no API call for greeting/farewell/date/time inputs

### Property-Based Tests

Each property from the Correctness Properties section maps to one Hypothesis test:

| Property | Hypothesis strategy |
|---|---|
| P1: Calibration once | `st.integers(min_value=1, max_value=20)` for turn count |
| P2: VAD threshold round-trip | `st.floats(min_value=0.2, max_value=3.0)` |
| P3: Invalid threshold fallback | `st.floats().filter(lambda x: not 0.2 <= x <= 3.0)` + `st.text()` |
| P4: Non-speaking clamping | `st.tuples(st.floats(0.2,3.0), st.floats(0.1,2.0)).filter(lambda p: p[1]>p[0])` |
| P5: Loop identity | `st.integers(min_value=2, max_value=10)` for call count |
| P6: Early-start threshold | `st.integers(512, 16384)` for chunk size; `st.lists(st.binary(...))` for stream |
| P7: Remaining buffer played | `st.binary(min_size=1, max_size=4095)` for leftover buffer |
| P8: Error stream no exception | `st.sampled_from([empty, exception_at_0, exception_at_mid])` |
| P9: Chunk length ≤ 280 | `st.text(min_size=0, max_size=2000)` |
| P10: Arm off main thread | `st.sampled_from(ARM_COMMAND_TEXTS)` |
| P11: TTS before arm completes | `st.floats(0.05, 0.5)` for arm duration |
| P12: AI timeout applied | `st.floats(0.1, 300.0)` for timeout value |
| P13: Fast-path no API call | `st.sampled_from(SALOMLASHISH + XAYRLASHISH + ...)` |
| P14: Cooldown matches config | `st.floats(0.0, 5.0)` for cooldown value |
| P15: No listen while playing | mock `get_busy()` returning True for N ticks |
| P16: Timing log format | `st.floats(0.0, 60.0)` for duration |
| P17: No timing when disabled | any pipeline execution |
| P18: Summary = one total line | any pipeline execution |
| P19: Invalid config fallback | `st.text()` for each env var |

### Integration Tests

- Full turn with real `edge-tts` (network): verify audio plays and timing logs appear
- `ArmCommandWorker` with real `move_arms_to_offsets()` mock: verify concurrent execution
- `LatencyConfig.load()` reading from a real `.env` file on disk

### Test File Layout

```
tests/
  test_latency_config.py       # LatencyConfig unit + property tests (P2, P3, P4, P19)
  test_latency_timer.py        # LatencyTimer unit + property tests (P16, P17, P18)
  test_tts_player.py           # EarlyStartTTSPlayer property tests (P6, P7, P8, P9)
  test_arm_worker.py           # ArmCommandWorker unit + property tests (P10, P11)
  test_pipeline_loop.py        # Persistent loop tests (P1, P5)
  test_think.py                # think() fast-path tests (P13)
  test_cooldown.py             # turn_cooldown() tests (P14, P15)
  test_ai_timeout.py           # AI timeout tests (P12)
```
