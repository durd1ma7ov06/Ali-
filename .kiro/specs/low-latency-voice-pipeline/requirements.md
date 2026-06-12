# Requirements Document

## Introduction

This feature refactors the humanoid robot voice assistant pipeline (both `main.py` for Windows and `main_rpi.py` for Raspberry Pi) to minimize end-to-end latency across every stage: microphone capture, voice activity detection (VAD), speech-to-text (STT), AI response generation, text-to-speech (TTS), audio playback, and ESP32 hardware command execution. The goal is to make the robot feel fast and responsive without rewriting the project or breaking existing behavior, environment variable compatibility, or ESP32 servo control.

## Glossary

- **Pipeline**: The sequential chain of stages — mic capture → VAD → STT → AI → TTS → playback → hardware command.
- **VAD**: Voice Activity Detection — detecting when the user starts and stops speaking.
- **STT**: Speech-to-Text — converting captured audio to a text string (Google Speech Recognition via `SpeechRecognition`).
- **AI**: The OpenRouter/Gemini API call that generates a text response.
- **TTS**: Text-to-Speech — converting the AI response text to audio using `edge-tts`.
- **Playback**: Playing the generated audio through `pygame.mixer`.
- **Hardware_Command**: An ESP32 serial command that moves robot arm servos.
- **Stage_Timer**: A per-stage wall-clock measurement logged to stdout.
- **Ambient_Noise_Calibration**: The `adjust_for_ambient_noise()` call that sets the energy threshold.
- **Pause_Threshold**: The duration of silence (in seconds) after which the recognizer considers speech ended.
- **Event_Loop**: The single persistent `asyncio` event loop used for all TTS calls.
- **TTS_Chunk**: A segment of text sent to `edge-tts` for streaming audio generation.
- **Arm_Thread**: A background thread that executes `move_arms_to_offsets()` independently of the main voice loop.

---

## Requirements

### Requirement 1: Eliminate Per-Turn Ambient Noise Calibration

**User Story:** As a robot operator, I want the microphone to be ready immediately each turn, so that the robot does not waste 500–800 ms recalibrating before it can hear me.

#### Acceptance Criteria

1. THE Pipeline SHALL perform `Ambient_Noise_Calibration` only once before the first call to `listen()`, not inside the main conversation loop.
2. IF `dynamic_energy_threshold` is `True`, THEN THE Pipeline SHALL rely on the recognizer's built-in dynamic adjustment between turns and SHALL NOT call `adjust_for_ambient_noise()` again after startup calibration.
3. THE Pipeline SHALL expose a configurable `VAD_AMBIENT_CALIBRATION_DURATION` environment variable (default `1.0` seconds) that controls the single startup calibration duration.
4. IF `VAD_AMBIENT_CALIBRATION_DURATION` is set to `0`, THEN THE Pipeline SHALL skip startup calibration entirely and use only the static `energy_threshold` value of `300`.
5. IF `VAD_AMBIENT_CALIBRATION_DURATION` is set to a value that is not a non-negative number, THEN THE Pipeline SHALL log a warning identifying the variable name and rejected value, and SHALL use the default value of `1.0` seconds.

---

### Requirement 2: Configurable and Reduced Pause Threshold

**User Story:** As a robot operator, I want the robot to stop recording and start processing as soon as I finish speaking, so that I do not wait a full second of silence before anything happens.

#### Acceptance Criteria

1. THE Pipeline SHALL expose a `VAD_PAUSE_THRESHOLD` environment variable (default `0.6` seconds) that sets `recognizer.pause_threshold`.
2. THE Pipeline SHALL expose a `VAD_NON_SPEAKING_DURATION` environment variable (default `0.3` seconds) that sets `recognizer.non_speaking_duration`.
3. IF `VAD_PAUSE_THRESHOLD` is present in `.env`, THEN THE Pipeline SHALL apply that value to `recognizer.pause_threshold` before the first `recognizer.listen()` call on both Windows (`main.py`) and Raspberry Pi (`main_rpi.py`) entry points.
4. IF `VAD_PAUSE_THRESHOLD` is set to a value outside the range `0.2`–`3.0`, THEN THE Pipeline SHALL log a warning identifying the variable name and rejected value, and SHALL use the default value of `0.6` seconds.
5. IF `VAD_NON_SPEAKING_DURATION` is set to a value outside the range `0.1`–`2.0`, THEN THE Pipeline SHALL log a warning identifying the variable name and rejected value, and SHALL use the default value of `0.3` seconds.
6. IF the resolved `VAD_NON_SPEAKING_DURATION` value exceeds the resolved `VAD_PAUSE_THRESHOLD` value, THEN THE Pipeline SHALL clamp `VAD_NON_SPEAKING_DURATION` to equal `VAD_PAUSE_THRESHOLD` and log a warning.

---

### Requirement 3: Persistent asyncio Event Loop for TTS

**User Story:** As a developer, I want TTS calls to reuse a single event loop, so that the overhead of creating a new event loop on every utterance is eliminated.

#### Acceptance Criteria

1. WHEN the Pipeline initializes, THE Pipeline SHALL create a single `asyncio` event loop and store it for reuse across all `speak()` calls throughout the session.
2. WHEN `speak()` is called from a non-async function, THE Pipeline SHALL use `loop.run_until_complete()` on the persistent loop instead of `asyncio.run()`.
3. IF the persistent event loop is closed or raises a `RuntimeError` during a `speak()` call, THEN THE Pipeline SHALL create a new event loop (at most one retry), log a warning, and retry the TTS call on the new loop; IF the retry also fails, THE Pipeline SHALL log the error and return without playing audio.
4. WHEN the program exits normally or via `KeyboardInterrupt`, THE Pipeline SHALL close the persistent event loop.

---

### Requirement 4: Early-Start TTS Playback (Chunk Streaming)

**User Story:** As a robot operator, I want the robot to start speaking as soon as the first audio chunk is ready, so that I hear a response faster rather than waiting for the entire audio to be generated first.

#### Acceptance Criteria

1. WHEN `edge-tts` streams audio chunks for a TTS segment and the accumulated buffer reaches `TTS_MIN_CHUNK_BYTES` bytes, THE Pipeline SHALL begin playback of the buffered audio without waiting for all chunks to arrive.
2. WHILE `edge-tts` is streaming remaining chunks for a TTS segment, THE Pipeline SHALL continue fetching and buffering the next audio data concurrently with playback of the current buffer.
3. THE Pipeline SHALL expose a `TTS_MIN_CHUNK_BYTES` environment variable (default `4096` bytes) that sets the minimum buffered audio size before playback of a chunk begins.
4. IF `edge-tts` returns no audio data for a segment, OR IF a mid-stream exception occurs, THEN THE Pipeline SHALL log a warning and skip that segment without raising an exception to the caller.
5. WHEN the `edge-tts` stream ends and the remaining buffer is non-empty but smaller than `TTS_MIN_CHUNK_BYTES`, THE Pipeline SHALL play the remaining buffered audio before returning.
6. THE Pipeline SHALL preserve the existing `split_long_speech_into_chunks()` text-splitting behavior, splitting text at sentence boundaries with a maximum segment length of `280` characters, before sending each segment to `edge-tts`.

---

### Requirement 5: Non-Blocking Hardware Command Execution

**User Story:** As a robot operator, I want arm movements and TTS playback to happen concurrently, so that the robot speaks and moves at the same time instead of one blocking the other.

#### Acceptance Criteria

1. WHEN `execute_arm_voice_command()` returns a non-`None` response, THE Pipeline SHALL dispatch `move_arms_to_offsets()` in a dedicated `Arm_Thread` so that the calling thread is not blocked.
2. WHEN an `Arm_Thread` is running, THE Pipeline SHALL start TTS playback before the `Arm_Thread` completes, so that speech and arm motion overlap in time.
3. IF a new arm command arrives while a previous `Arm_Thread` is still running, THEN THE Pipeline SHALL wait up to `ARM_COMMAND_TIMEOUT` seconds for the previous thread to finish before starting the new `Arm_Thread`.
4. IF the previous `Arm_Thread` has not finished within `ARM_COMMAND_TIMEOUT` seconds, THEN THE Pipeline SHALL log a warning and proceed to start the new `Arm_Thread` without waiting further.
5. THE Pipeline SHALL ensure that concurrent serial writes to the ESP32 do not interleave bytes; each complete command string SHALL be written atomically under the existing `threading.Lock` in `Esp32SerialController`.

---

### Requirement 6: AI API Timeout and Fast-Path Short-Circuit

**User Story:** As a robot operator, I want the AI call to have a timeout and for simple queries to be answered instantly, so that the robot never hangs indefinitely and responds to greetings without a network round-trip.

#### Acceptance Criteria

1. THE Pipeline SHALL expose an `AI_REQUEST_TIMEOUT` environment variable (default `15.0` seconds, valid range `0.1`–`300.0`) that is applied as the per-attempt timeout for each `client.chat.completions.create()` call; IF the value is outside the valid range or non-numeric, THE Pipeline SHALL log a warning and use the default.
2. WHEN a single `client.chat.completions.create()` call exceeds `AI_REQUEST_TIMEOUT` seconds, THE Pipeline SHALL abort that attempt, log a warning-level entry identifying the model name and elapsed time, and proceed to the next fallback model.
3. IF all models in `GEMINI_TEXT_FALLBACK_MODELS` are exhausted (whether by timeout or other error), THEN THE Pipeline SHALL return `FALLBACK_API_ERROR` and log the last error.
4. WHEN the user input matches a greeting, farewell, help, date, or time query pattern, THE Pipeline SHALL return the corresponding pre-computed response within `500` ms without making any network call to the AI API.

---

### Requirement 7: Removal of Unnecessary Inter-Turn Sleep

**User Story:** As a robot operator, I want the robot to start listening again immediately after finishing a response, so that there is no artificial delay between turns.

#### Acceptance Criteria

1. THE Pipeline SHALL remove the unconditional `time.sleep(0.3)` that currently appears at the end of each conversation turn in both `main.py` and `main_rpi.py`.
2. THE Pipeline SHALL expose a `TURN_COOLDOWN_SECONDS` environment variable (default `0.0` seconds, valid range `0.0`–`5.0`) that, IF greater than `0.0`, causes the Pipeline to sleep for that duration after TTS playback completes and before the next `listen()` call; IF the value is outside the valid range or non-numeric, THE Pipeline SHALL log a warning and use the default of `0.0`.
3. WHEN TTS playback completes and `TURN_COOLDOWN_SECONDS` is `0.0`, THE Pipeline SHALL call `listen()` only after `pygame.mixer.music.get_busy()` returns `False`, ensuring the speaker has finished playing before the microphone opens.

---

### Requirement 8: Per-Stage Latency Logging

**User Story:** As a developer, I want timing measurements logged for each pipeline stage, so that I can identify bottlenecks and verify that optimizations are working.

#### Acceptance Criteria

1. THE Pipeline SHALL record a wall-clock `Stage_Timer` at the start and end of each of the following stages: mic capture start, VAD/listen complete, STT complete, AI response complete, TTS first-chunk ready, TTS playback complete, and hardware command dispatch.
2. WHEN a stage completes, THE Pipeline SHALL log a line in the format `[TIMING] <stage_name>: <duration_ms>ms` to stdout, where `<duration_ms>` is an integer rounded to the nearest whole millisecond.
3. IF `LATENCY_LOGGING_ENABLED` is `false`, THEN THE Pipeline SHALL not emit any `[TIMING]` log lines and SHALL not alter pipeline behavior.
4. THE Pipeline SHALL expose a `LATENCY_LOG_LEVEL` environment variable (valid values: `summary`, `verbose`; default `summary`) that controls the verbosity of timing output.
5. WHEN `LATENCY_LOG_LEVEL=verbose`, THE Pipeline SHALL log individual stage durations for all stages listed in criterion 1.
6. WHEN `LATENCY_LOG_LEVEL=summary`, THE Pipeline SHALL log only the total elapsed time from the `VAD/listen complete` stage start to the `TTS playback complete` stage end.
7. IF `LATENCY_LOGGING_ENABLED` is set to a value other than `true` or `false`, OR IF `LATENCY_LOG_LEVEL` is set to a value other than `summary` or `verbose`, THEN THE Pipeline SHALL log a warning identifying the variable name and rejected value, and SHALL use the respective default value.

---

### Requirement 9: Latency Configuration via Environment Variables

**User Story:** As a robot operator, I want all latency-related settings to be configurable through `.env`, so that I can tune the pipeline for different hardware without changing code.

#### Acceptance Criteria

1. WHEN the Pipeline initializes, THE Pipeline SHALL read the following latency-related environment variables from `.env`: `VAD_AMBIENT_CALIBRATION_DURATION`, `VAD_PAUSE_THRESHOLD`, `VAD_NON_SPEAKING_DURATION`, `TTS_MIN_CHUNK_BYTES`, `AI_REQUEST_TIMEOUT`, `ARM_COMMAND_TIMEOUT`, `TURN_COOLDOWN_SECONDS`, `LATENCY_LOGGING_ENABLED`, `LATENCY_LOG_LEVEL`.
2. WHEN `LATENCY_LOGGING_ENABLED` is `true`, THE Pipeline SHALL print the active resolved values of all latency-related settings to stdout during startup, in the format `[LATENCY CONFIG] <variable_name>=<resolved_value>`, alongside the existing TTS voice/rate/pitch/volume log line.
3. IF a latency environment variable is missing or invalid, THEN THE Pipeline SHALL use the documented default value and log a notice identifying the variable name and the default being applied.
4. THE Pipeline SHALL add all new latency environment variables with their default values to `.env.example`.

---

### Requirement 10: Preserve Existing Features and Compatibility

**User Story:** As a developer, I want all existing features to continue working after the latency refactor, so that the robot's behavior, hardware control, and configuration are not broken.

#### Acceptance Criteria

1. THE Pipeline SHALL preserve all existing environment variables and their semantics as defined in `.env.example`; no existing variable SHALL be removed or have its default value changed.
2. WHEN `speak_with_greeting_motion()` is called, THE Pipeline SHALL start the greeting arm motion thread before TTS playback begins, so that arm motion and speech overlap in time.
3. THE Pipeline SHALL preserve the `execute_arm_voice_command()` keyword detection lists (`SALOMLASHISH`, `XAYRLASHISH`, `YORDAM`, etc.), response strings in `TAYYOR_JAVOBLAR`, and all arm movement offset profiles (raise, lower, chest, bend, straighten, wave) without modification.
4. THE Pipeline SHALL preserve the `FaceServoTracker` smoothing, dead-zone, and angle-clamping logic, and the `CameraRuntime` capture and face-detection loop, without modification.
5. THE Pipeline SHALL preserve the `Esp32SerialController` wire protocol: each command is a UTF-8 ASCII line terminated with `\n`, using the prefixes `HEAD:`, `ARMS:`, and `HOME`, at the configured baud rate.
6. WHEN running on Raspberry Pi (`main_rpi.py`), THE Pipeline SHALL apply all latency optimizations defined in Requirements 1–9, including the single startup ambient calibration and configurable pause threshold, using the same environment variables as `main.py`.
7. THE Pipeline SHALL preserve `conversation_history` (capped at `MAX_HISTORY * 2` entries) and the `build_gemini_persona_prompt()` function, including the injected local date/time string, without modification.
