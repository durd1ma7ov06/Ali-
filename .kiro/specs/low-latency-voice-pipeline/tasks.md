# Implementation Plan: Low-Latency Voice Pipeline

## Overview

Refactor the humanoid robot voice pipeline by introducing `pipeline_core.py` (all new shared logic), updating `main.py` and `main_rpi.py` to use it, and adding test coverage. Tasks are ordered so each step builds on the previous one, ending with full integration.

## Tasks

- [x] 1. Create `pipeline_core.py` with `LatencyConfig` dataclass and `load()` classmethod
  - Create `pipeline_core.py` in the project root
  - Define the `LatencyConfig` dataclass with all 11 fields and documented defaults
  - Implement `LatencyConfig.load()`: read each env var, validate ranges, apply clamping rules, log `[WARN]` for invalid values, log `[LATENCY CONFIG]` lines when enabled
  - Implement `configure_recognizer(recognizer, cfg)` and `calibrate_once(recognizer, mic, cfg)` helper functions
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 6.1, 7.2, 8.3, 8.4, 8.7, 9.1, 9.2, 9.3_

  - [x] 1.1 Implement `LatencyConfig` dataclass and `load()` in `pipeline_core.py`
    - Write the dataclass with all 11 fields
    - Implement full validation, clamping, and warning logic in `load()`
    - _Requirements: 1.3, 1.4, 1.5, 2.1, 2.2, 2.4, 2.5, 2.6, 9.1, 9.2, 9.3_

  - [ ]* 1.2 Write property tests for `LatencyConfig` validation
    - **Property 2: VAD threshold round-trip** — `st.floats(min_value=0.2, max_value=3.0)`
    - **Property 3: Invalid threshold falls back to default** — `st.floats().filter(lambda x: not 0.2 <= x <= 3.0)` + `st.text()`
    - **Property 4: Non-speaking duration clamping invariant** — `st.tuples(st.floats(0.2,3.0), st.floats(0.1,2.0)).filter(lambda p: p[1]>p[0])`
    - **Property 19: Invalid latency config values fall back to defaults** — `st.text()` for each env var
    - Place tests in `tests/test_latency_config.py`
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 9.3_

  - [x] 1.3 Implement `configure_recognizer()` and `calibrate_once()` helpers
    - `configure_recognizer()` applies `pause_threshold`, `non_speaking_duration`, `dynamic_energy_threshold` from cfg
    - `calibrate_once()` calls `adjust_for_ambient_noise()` once; skips if `vad_ambient_calibration_duration == 0`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3_

- [x] 2. Add `LatencyTimer` to `pipeline_core.py`
  - Implement the `LatencyTimer` class with `start()`, `stop()`, `elapsed_ms()`, `_maybe_log()`, and context manager support
  - Define `SUMMARY_STAGES = {"listen_complete", "tts_playback_complete"}`
  - Implement summary-mode derived `[TIMING] turn_total: <ms>ms` log line
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 2.1 Implement `LatencyTimer` class in `pipeline_core.py`
    - Write all methods and context manager protocol
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 2.2 Write property tests for `LatencyTimer`
    - **Property 16: Timing log format correctness** — `st.floats(0.0, 60.0)` for duration; assert logged integer equals `round(D * 1000)`
    - **Property 17: No timing output when logging disabled** — any execution with `LATENCY_LOGGING_ENABLED=false`; assert zero `[TIMING]` lines
    - **Property 18: Summary mode logs only total turn time** — any execution with `LATENCY_LOG_LEVEL=summary`; assert exactly one `[TIMING]` line containing `turn_total`
    - Place tests in `tests/test_latency_timer.py`
    - _Requirements: 8.2, 8.3, 8.6_

- [x] 3. Add persistent TTS event loop management to `pipeline_core.py`
  - Implement module-level `_tts_loop` and `_tts_loop_lock`
  - Implement `get_tts_loop()` (thread-safe, creates loop if closed/None)
  - Implement `close_tts_loop()` (thread-safe close + None assignment)
  - Register `close_tts_loop` with `atexit`
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 3.1 Implement `get_tts_loop()` and `close_tts_loop()` in `pipeline_core.py`
    - Write thread-safe loop creation and teardown
    - Add `atexit.register(close_tts_loop)`
    - _Requirements: 3.1, 3.2, 3.4_

  - [ ]* 3.2 Write property tests for persistent loop identity and retry
    - **Property 5: Persistent TTS loop identity** — `st.integers(min_value=2, max_value=10)` for call count; assert `id()` is same across all calls
    - **Property 1: Calibration happens exactly once** — `st.integers(min_value=1, max_value=20)` for turn count; mock `adjust_for_ambient_noise` and assert call count == 1
    - Place tests in `tests/test_pipeline_loop.py`
    - _Requirements: 1.1, 1.2, 3.1, 3.2_

- [x] 4. Implement `EarlyStartTTSPlayer` and `run_speak()` in `pipeline_core.py`
  - Implement `EarlyStartTTSPlayer` class with `stream_and_play()` async coroutine and `_play_buffer()` method
  - Implement `_async_speak(text, cfg)` async function (splits text, iterates segments via player)
  - Implement `run_speak(text, cfg)` with one-retry logic on `RuntimeError`
  - Move `prepare_uzbek_spoken_text()` and `split_long_speech_into_chunks()` to `pipeline_core.py` so `_async_speak()` can call them; keep re-exports in `main.py`/`main_rpi.py` for backward compatibility
  - _Requirements: 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 4.1 Implement `EarlyStartTTSPlayer.stream_and_play()` and `_play_buffer()`
    - Buffer chunks from `edge_tts.Communicate.stream()`; call `_play_buffer()` when buffer >= `TTS_MIN_CHUNK_BYTES`
    - After stream ends, play any remaining non-empty buffer
    - Handle zero-audio and mid-stream exceptions with warning log, no propagation
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 4.2 Write property tests for `EarlyStartTTSPlayer` buffering
    - **Property 6: Early-start playback threshold** — `st.integers(512, 16384)` for chunk size; mock stream; assert `play()` first called only after buffer >= threshold
    - **Property 7: Remaining buffer is always played** — `st.binary(min_size=1, max_size=4095)` for leftover; assert `_play_buffer()` called with those bytes
    - **Property 8: Empty or error stream does not propagate exception** — `st.sampled_from([empty, exception_at_0, exception_at_mid])`; assert no exception raised
    - Place tests in `tests/test_tts_player.py`
    - _Requirements: 4.1, 4.3, 4.4, 4.5_

  - [x] 4.3 Implement `run_speak()` with retry logic
    - Call `_tts_loop.run_until_complete(_async_speak(text, cfg))`
    - On `RuntimeError`: log warning, call `close_tts_loop()`, get new loop, retry once; on second failure log and return
    - _Requirements: 3.2, 3.3_

  - [ ]* 4.4 Write property test for text chunk length invariant
    - **Property 9: Text chunk length invariant** — `st.text(min_size=0, max_size=2000)`; assert every element of `split_long_speech_into_chunks(text)` has `len <= 280`
    - Place in `tests/test_tts_player.py`
    - _Requirements: 4.6_

- [x] 5. Implement `ArmCommandWorker` in `pipeline_core.py`
  - Implement `ArmCommandWorker` class with `__init__()`, `start()`, `dispatch()`, `stop()`, and `_run()` methods
  - Use `queue.Queue(maxsize=1)` and `threading.Event` for job tracking
  - Implement timeout warning and queue-full drop logic in `dispatch()`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 5.1 Implement `ArmCommandWorker` class in `pipeline_core.py`
    - Write all methods per design spec
    - _Requirements: 5.1, 5.3, 5.4, 5.5_

  - [ ]* 5.2 Write property tests for `ArmCommandWorker`
    - **Property 10: Arm command executes off main thread** — assert `threading.current_thread() is not threading.main_thread()` inside job
    - **Property 11: TTS starts before arm thread completes** — `st.floats(0.05, 0.5)` for arm duration; assert `play()` timestamp < arm-job-return timestamp
    - Place tests in `tests/test_arm_worker.py`
    - _Requirements: 5.1, 5.2_

- [x] 6. Implement `turn_cooldown()` in `pipeline_core.py`
  - Wait for `pygame.mixer.music.get_busy() == False`
  - If `cfg.turn_cooldown_seconds > 0.0`, call `time.sleep(cfg.turn_cooldown_seconds)`
  - _Requirements: 7.1, 7.2, 7.3_

  - [x] 6.1 Implement `turn_cooldown()` in `pipeline_core.py`
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 6.2 Write property tests for `turn_cooldown()`
    - **Property 14: Turn cooldown matches configuration** — `st.floats(0.0, 5.0)` for cooldown; mock `time.sleep`; assert called with S (or not called when S == 0.0)
    - **Property 15: No listen() call while audio is playing** — mock `get_busy()` returning True for N ticks; assert `listen()` not called until `get_busy()` returns False
    - Place tests in `tests/test_cooldown.py`
    - _Requirements: 7.2, 7.3_

- [x] 7. Checkpoint — verify `pipeline_core.py` is complete and importable
  - Run `python -c "import pipeline_core"` to verify no syntax errors
  - Ensure all non-optional tests pass
  - _Requirements: all above_

- [x] 8. Update `main.py` to use `pipeline_core`
  - Add import: `from pipeline_core import (LatencyConfig, LatencyTimer, ArmCommandWorker, run_speak, turn_cooldown, calibrate_once, configure_recognizer, close_tts_loop)`
  - Update `listen()`: remove `adjust_for_ambient_noise()` call; replace hard-coded `timeout=10, phrase_time_limit=15` with `cfg.vad_listen_timeout` and `cfg.vad_phrase_time_limit`; wrap with `LatencyTimer`
  - Update `think()`: add `timeout=cfg.ai_request_timeout` to each `client.chat.completions.create()` call; wrap with `LatencyTimer`
  - Update `speak_with_greeting_motion()`: replace `asyncio.run(speak(text))` with `run_speak(text, cfg)`; add `cfg` parameter
  - Update `main()`: call `cfg = LatencyConfig.load()`; call `configure_recognizer(recognizer, cfg)`; call `calibrate_once(recognizer, mic, cfg)`; create and start `arm_worker = ArmCommandWorker(cfg)`; register `atexit.register(arm_worker.stop)`
  - Update main loop: replace `asyncio.run(speak(arm_response))` with `arm_worker.dispatch(...)` + `run_speak(arm_response, cfg)`; replace `asyncio.run(speak(ai_response))` with `run_speak(ai_response, cfg)`; replace `time.sleep(0.3)` with `turn_cooldown(cfg)`; wrap each stage with `LatencyTimer`
  - Update `KeyboardInterrupt` handler: replace `asyncio.run(speak(farewell))` with `run_speak(farewell, cfg)`; add `arm_worker.stop()` and `close_tts_loop()` calls
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.4, 4.1, 5.1, 5.2, 6.1, 7.1, 7.3, 8.1, 9.1, 10.1, 10.2, 10.3, 10.7_

  - [x] 8.1 Update imports and `listen()` in `main.py`
    - Add `pipeline_core` imports; remove `adjust_for_ambient_noise()` from `listen()`; apply cfg-based timeouts; add `LatencyTimer` wrapping
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 8.1_

  - [x] 8.2 Update `think()` in `main.py`
    - Add `timeout=cfg.ai_request_timeout` to each model attempt; add `LatencyTimer` wrapping
    - _Requirements: 6.1, 6.2, 8.1_

  - [x] 8.3 Update `speak_with_greeting_motion()` and TTS call sites in `main.py`
    - Replace all `asyncio.run(speak(...))` with `run_speak(text, cfg)`; update `speak_with_greeting_motion` signature
    - _Requirements: 3.2, 4.1, 10.2_

  - [x] 8.4 Update `main()` startup and main loop in `main.py`
    - Add `LatencyConfig.load()`, `configure_recognizer()`, `calibrate_once()`, `ArmCommandWorker` creation/start/atexit; update arm dispatch and cooldown in loop; update `KeyboardInterrupt` handler
    - _Requirements: 1.1, 1.3, 2.1, 5.1, 5.2, 7.1, 7.3, 9.1, 9.2_

  - [ ]* 8.5 Write unit tests for `think()` fast-path (no API call)
    - **Property 13: Fast-path bypasses API for known patterns** — `st.sampled_from(SALOMLASHISH + XAYRLASHISH + YORDAM + DATE_QUERY_KEYWORDS + TIME_QUERY_KEYWORDS)`; mock `client.chat.completions.create`; assert it is never called
    - Place tests in `tests/test_think.py`
    - _Requirements: 6.4_

  - [ ]* 8.6 Write unit tests for AI timeout application
    - **Property 12: AI timeout is applied per model attempt** — `st.floats(0.1, 300.0)` for timeout; mock `client.chat.completions.create`; assert `timeout` kwarg equals cfg value
    - Place tests in `tests/test_ai_timeout.py`
    - _Requirements: 6.1_

- [x] 9. Update `main_rpi.py` with identical changes
  - Apply the exact same set of changes as task 8 to `main_rpi.py`
  - Preserve `SDL_AUDIODRIVER=alsa` env default and `buffer=4096` in `pygame.mixer.init()`
  - Preserve `recognizer.non_speaking_duration` — now set via `configure_recognizer()` using `cfg.vad_non_speaking_duration`
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.4, 4.1, 5.1, 5.2, 6.1, 7.1, 7.3, 8.1, 9.1, 10.1, 10.2, 10.6_

  - [x] 9.1 Apply all `main.py` changes to `main_rpi.py`
    - Mirror tasks 8.1–8.4 for `main_rpi.py`; preserve platform-specific `SDL_AUDIODRIVER` and `buffer=4096`
    - _Requirements: 10.6_

- [x] 10. Append latency tuning section to `.env.example`
  - Append the `# Latency tuning` block with all 11 new variables and their defaults
  - _Requirements: 9.4_

  - [x] 10.1 Update `.env.example` with latency tuning variables
    - Add `VAD_AMBIENT_CALIBRATION_DURATION`, `VAD_PAUSE_THRESHOLD`, `VAD_NON_SPEAKING_DURATION`, `VAD_PHRASE_TIME_LIMIT`, `VAD_LISTEN_TIMEOUT`, `TTS_MIN_CHUNK_BYTES`, `AI_REQUEST_TIMEOUT`, `ARM_COMMAND_TIMEOUT`, `TURN_COOLDOWN_SECONDS`, `LATENCY_LOGGING_ENABLED`, `LATENCY_LOG_LEVEL`
    - _Requirements: 9.4, 10.1_

- [x] 11. Final checkpoint — run import and syntax checks
  - Run `python -c "import pipeline_core; import main"` to verify no import errors
  - Run all non-optional tests
  - Verify `.env.example` contains all 11 new variables
  - _Requirements: all_
