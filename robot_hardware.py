import atexit
import os
import re
import sys
import threading
import time

import pyaudio
import speech_recognition as sr


CAMERA_MIC_KEYWORDS = [
    "camera",
    "webcam",
    "web cam",
    "uvc",
    "fhd",
    "1080p",
    "720p",
    "a4ech",
    "a4tech",
]

EXTERNAL_MIC_KEYWORDS = [
    "usb",
    "headset",
    "hands-free",
    "bluetooth",
    "external",
    "microphone",
    "mic",
    "audio",
]

IGNORE_INPUT_KEYWORDS = [
    "stereo mix",
    "loopback",
    "monitor",
    "output",
    "speaker",
    "mapper",
    "primary sound capture driver",
]


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


load_env_file()


def get_bool_env(name, default=False):
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on", "ha"}


def get_int_env(name, default=None):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        print(f"[WARN] {name} butun son emas: {raw_value!r}. E'tiborsiz qoldirildi.")
        return default


def get_float_env(name, default):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError:
        print(f"[WARN] {name} son emas: {raw_value!r}. E'tiborsiz qoldirildi.")
        return default


def normalize_device_name(name):
    return " ".join(str(name or "").lower().split())


def _host_api_name(pa, host_api_index):
    try:
        return pa.get_host_api_info_by_index(int(host_api_index)).get("name", "")
    except Exception:
        return ""


def _list_input_devices(pa):
    devices = []
    for index in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(index)
        if info.get("maxInputChannels", 0) <= 0:
            continue
        item = dict(info)
        item["index"] = int(info["index"])
        item["name"] = str(info.get("name", ""))
        item["normalized_name"] = normalize_device_name(info.get("name", ""))
        item["hostApiName"] = _host_api_name(pa, info.get("hostApi", -1))
        item["defaultSampleRate"] = int(float(info.get("defaultSampleRate", 16000) or 16000))
        devices.append(item)
    return devices


def _get_default_input_index(pa):
    try:
        return int(pa.get_default_input_device_info()["index"])
    except Exception:
        return None


def _score_input_device(device, default_index, preferred_names):
    name = device["normalized_name"]
    host_api = normalize_device_name(device.get("hostApiName", ""))

    if any(word in name for word in IGNORE_INPUT_KEYWORDS):
        return -1000

    score = 0
    if preferred_names and any(preferred in name for preferred in preferred_names):
        score += 500

    if any(word in name for word in CAMERA_MIC_KEYWORDS):
        score += 220
    if any(word in name for word in EXTERNAL_MIC_KEYWORDS):
        score += 80
    if "realtek" in name or "internal" in name or "built-in" in name:
        score -= 60
    if default_index is not None and device["index"] == default_index:
        score += 10

    channels = int(device.get("maxInputChannels", 0) or 0)
    if channels == 1:
        score += 12
    elif channels > 1:
        score += 4

    sample_rate = int(device.get("defaultSampleRate", 0) or 0)
    if 16000 <= sample_rate <= 48000:
        score += 10
    elif sample_rate > 48000:
        score += 2

    if sys.platform == "win32":
        if "mme" in host_api:
            score += 8
        elif "wasapi" in host_api:
            score += 5
        elif "directsound" in host_api:
            score += 3

    return score


def _print_input_device_table(scored_devices):
    print("[TIZIM] Topilgan input qurilmalar:")
    for score, device in scored_devices:
        marker = "*" if score >= 0 else "-"
        print(
            f"  {marker} ID:{device['index']} | score={score} | "
            f"{device['name']} | {device.get('hostApiName', 'unknown')} | "
            f"{device.get('maxInputChannels', 0)}ch | {device['defaultSampleRate']}Hz"
        )


def get_optimal_microphone():
    preferred_names = [normalize_device_name(item) for item in os.getenv(
        "MICROPHONE_NAME",
        "camera,webcam,uvc,fhd,1080p,a4ech,a4tech",
    ).split(",") if item.strip()]
    forced_index = get_int_env("MICROPHONE_DEVICE_INDEX")

    print("[TIZIM] Mikrofonlar tekshirilmoqda...")
    pa = pyaudio.PyAudio()
    try:
        devices = _list_input_devices(pa)
        if not devices:
            print("[TIZIM] Mikrofon topilmadi. Tizim default qurilmasi ishlatiladi.")
            return None, None

        if forced_index is not None:
            forced = next((device for device in devices if device["index"] == forced_index), None)
            if forced is not None:
                print(f"[TIZIM] .env bo'yicha mikrofon tanlandi: {forced['name']} (ID:{forced_index})")
                return forced["index"], forced["defaultSampleRate"]
            print(f"[WARN] MICROPHONE_DEVICE_INDEX={forced_index} topilmadi. Avtomatik tanlash davom etadi.")

        default_index = _get_default_input_index(pa)
        scored_devices = [
            (_score_input_device(device, default_index, preferred_names), device)
            for device in devices
        ]
        scored_devices.sort(key=lambda item: (-item[0], item[1]["index"]))
        _print_input_device_table(scored_devices)

        best_score, best_device = scored_devices[0]
        if best_score < 0 and default_index is not None:
            best_device = next(
                (device for device in devices if device["index"] == default_index),
                best_device,
            )

        print(
            f"[TIZIM] Tanlangan mikrofon: {best_device['name']} "
            f"(ID:{best_device['index']}, {best_device['defaultSampleRate']}Hz)"
        )
        return best_device["index"], best_device["defaultSampleRate"]
    finally:
        pa.terminate()


def create_microphone(device_index, sample_rate=None):
    if device_index is None:
        return sr.Microphone()

    attempts = []
    if sample_rate:
        attempts.append({"device_index": device_index, "sample_rate": sample_rate})
    attempts.append({"device_index": device_index})
    attempts.append({})

    last_error = None
    for kwargs in attempts:
        try:
            return sr.Microphone(**kwargs)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Mikrofon ishga tushmadi: {last_error}")


class Esp32SerialController:
    def __init__(self, port=None, baudrate=115200, enabled=True):
        self.port = port
        self.baudrate = baudrate
        self.enabled = enabled
        self._serial = None
        self._lock = threading.Lock()
        self._last_command = None
        self._last_sent_at = 0
        self._last_connect_attempt_at = 0
        self._disabled_reported = False

    def connect(self):
        if not self.enabled:
            if not self._disabled_reported:
                print("[ESP32] ESP32_SERIAL_ENABLED=false. Serial ulanmaydi.")
                self._disabled_reported = True
            return False
        if self._serial and self._serial.is_open:
            return True

        now = time.monotonic()
        if now - self._last_connect_attempt_at < 3.0:
            return False
        self._last_connect_attempt_at = now

        try:
            import serial
        except Exception as exc:
            print(f"[WARN] pyserial topilmadi: {exc}")
            return False

        port = self.port or self._auto_detect_port()
        if not port:
            print("[WARN] ESP32 port topilmadi. ESP32_PORT ni .env ichida kiriting.")
            return False

        try:
            self._serial = serial.Serial(port, self.baudrate, timeout=0.1, write_timeout=0.2)
            time.sleep(2.0)
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            print(f"[ESP32] Ulandi: {port} @ {self.baudrate}")
            return True
        except Exception as exc:
            print(f"[WARN] ESP32 serial ulanmadi ({port}): {exc}")
            self._serial = None
            return False

    def close(self):
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def send_servo_angle(self, angle, min_delta=2, min_interval=0.08):
        angle = max(0, min(180, int(round(angle))))
        now = time.monotonic()
        if self._last_command is not None:
            if abs(angle - self._last_command) < min_delta and now - self._last_sent_at < min_interval:
                return False
            if now - self._last_sent_at < min_interval:
                return False

        if self.send_line(f"HEAD:{angle}"):
            self._last_command = angle
            self._last_sent_at = now
            return True
        return False

    def send_arm_offsets(self, right_shoulder, right_elbow, right_wrist, left_shoulder, left_elbow, left_wrist):
        values = [
            right_shoulder,
            right_elbow,
            right_wrist,
            left_shoulder,
            left_elbow,
            left_wrist,
        ]
        safe_values = [max(-180, min(180, int(round(value)))) for value in values]
        payload = ",".join(str(value) for value in safe_values)
        return self.send_line(f"ARMS:{payload}")

    def send_head_angle(self, angle):
        return self.send_line(f"HEAD:{max(0, min(180, int(round(angle))))}")

    def send_home(self):
        return self.send_line("HOME")

    def send_line(self, line):
        if not self.connect():
            return False

        try:
            with self._lock:
                self._serial.write(f"{line}\n".encode("ascii"))
            return True
        except Exception as exc:
            print(f"[WARN] ESP32 ga komanda yuborilmadi: {exc}")
            self.close()
            return False

    def _auto_detect_port(self):
        try:
            from serial.tools import list_ports
        except Exception:
            return None

        ports = list(list_ports.comports())
        if not ports:
            return None

        preferred_words = [
            "esp32",
            "cp210",
            "ch340",
            "ch910",
            "silicon labs",
            "usb serial",
            "uart",
        ]
        scored_ports = []
        for port in ports:
            text = normalize_device_name(
                f"{port.device} {port.description} {port.manufacturer} {port.hwid}"
            )
            score = 0
            for word in preferred_words:
                if word in text:
                    score += 10
            if "bluetooth" in text:
                score -= 50
            scored_ports.append((score, port.device, port.description))

        scored_ports.sort(key=lambda item: (-item[0], item[1]))
        best_score, best_port, description = scored_ports[0]
        if best_score <= 0 and len(scored_ports) > 1:
            print("[ESP32] Serial portlar topildi, lekin ESP32 aniq bilinmadi:")
            for score, device, desc in scored_ports:
                print(f"  {device} | score={score} | {desc}")
            return None

        print(f"[ESP32] Avtomatik port tanlandi: {best_port} ({description})")
        return best_port


_esp32_controller = None
_esp32_controller_lock = threading.Lock()


def get_esp32_controller():
    global _esp32_controller
    with _esp32_controller_lock:
        if _esp32_controller is None:
            _esp32_controller = Esp32SerialController(
                port=os.getenv("ESP32_PORT", "").strip() or None,
                baudrate=get_int_env("ESP32_BAUDRATE", 115200),
                enabled=get_bool_env("ESP32_SERIAL_ENABLED", True),
            )
            atexit.register(close_esp32_controller)
        return _esp32_controller


def close_esp32_controller():
    global _esp32_controller
    with _esp32_controller_lock:
        if _esp32_controller is not None:
            _esp32_controller.close()
            _esp32_controller = None


def get_resting_arm_offsets():
    return (
        get_int_env("ARM_REST_RIGHT_SHOULDER_OFFSET", 0),
        get_int_env("ARM_REST_RIGHT_ELBOW_OFFSET", 0),
        get_int_env("ARM_REST_RIGHT_WRIST_OFFSET", 90),
        get_int_env("ARM_REST_LEFT_SHOULDER_OFFSET", 0),
        get_int_env("ARM_REST_LEFT_ELBOW_OFFSET", 0),
        get_int_env("ARM_REST_LEFT_WRIST_OFFSET", 45),
    )


_arm_pose_lock = threading.Lock()
_current_arm_offsets = None


def _get_current_arm_offsets():
    global _current_arm_offsets
    with _arm_pose_lock:
        if _current_arm_offsets is None:
            _current_arm_offsets = get_resting_arm_offsets()
        return _current_arm_offsets


def _set_current_arm_offsets(offsets):
    global _current_arm_offsets
    with _arm_pose_lock:
        _current_arm_offsets = tuple(int(round(value)) for value in offsets)


def move_arms_to_offsets(target_offsets, steps=None, step_delay=None):
    current = _get_current_arm_offsets()
    target = tuple(max(-180, min(180, int(round(value)))) for value in target_offsets)
    steps = max(1, steps or get_int_env("ARM_COMMAND_STEPS", 10))
    step_delay = max(0.02, step_delay or get_float_env("ARM_COMMAND_STEP_DELAY", 0.045))
    controller = get_esp32_controller()

    for step in range(1, steps + 1):
        ratio = step / steps
        frame = tuple(
            current[index] + ((target[index] - current[index]) * ratio)
            for index in range(6)
        )
        controller.send_arm_offsets(*frame)
        time.sleep(step_delay)

    _set_current_arm_offsets(target)


def apply_resting_arm_pose():
    resting = get_resting_arm_offsets()
    get_esp32_controller().send_arm_offsets(*resting)
    _set_current_arm_offsets(resting)


def play_startup_greeting_motion():
    if not get_bool_env("STARTUP_GREETING_MOTION_ENABLED", True):
        return

    controller = get_esp32_controller()
    rest = get_resting_arm_offsets()
    right_shoulder = get_int_env("GREETING_RIGHT_SHOULDER_OFFSET", 44)
    right_elbow = get_int_env("GREETING_RIGHT_ELBOW_OFFSET", 56)
    right_wrist = rest[2]
    steps = max(1, get_int_env("GREETING_ARM_STEPS", 8))
    step_delay = max(0.02, get_float_env("GREETING_ARM_STEP_DELAY", 0.055))
    elbow_start_delay = max(0.0, get_float_env("GREETING_RIGHT_ELBOW_START_DELAY", 0.18))
    wrist_start_delay = max(0.0, get_float_env("GREETING_RIGHT_WRIST_START_DELAY", 0.0))
    started_at = time.monotonic()

    for step in range(1, steps + 1):
        ratio = step / steps
        elapsed = time.monotonic() - started_at
        elbow_ratio = ratio if elapsed >= elbow_start_delay else 0
        wrist_ratio = ratio if elapsed >= wrist_start_delay else 0
        controller.send_arm_offsets(
            rest[0] + (right_shoulder * ratio),
            rest[1] + (right_elbow * elbow_ratio),
            rest[2] + ((right_wrist - rest[2]) * wrist_ratio),
            rest[3],
            rest[4],
            rest[5],
        )
        time.sleep(step_delay)

    head_center = get_int_env("FACE_SERVO_CENTER_ANGLE", 90)
    head_nod = max(1, get_int_env("GREETING_HEAD_NOD", 8))
    head_delay = max(0.04, get_float_env("GREETING_HEAD_DELAY", 0.14))
    for angle in [
        head_center,
        head_center - head_nod,
        head_center + head_nod,
        head_center,
    ]:
        controller.send_head_angle(angle)
        time.sleep(head_delay)


def finish_startup_greeting_motion():
    controller = get_esp32_controller()
    rest = get_resting_arm_offsets()
    right_shoulder = get_int_env("GREETING_RIGHT_SHOULDER_OFFSET", 44)
    right_elbow = get_int_env("GREETING_RIGHT_ELBOW_OFFSET", 56)
    right_wrist = rest[2]
    steps = max(1, get_int_env("GREETING_ARM_RETURN_STEPS", 8))
    step_delay = max(0.02, get_float_env("GREETING_ARM_STEP_DELAY", 0.055))
    elbow_return_delay = max(0.0, get_float_env("GREETING_RIGHT_ELBOW_RETURN_DELAY", 0.0))
    shoulder_return_delay = max(0.0, get_float_env("GREETING_RIGHT_SHOULDER_RETURN_DELAY", 0.35))
    wrist_return_delay = max(0.0, get_float_env("GREETING_RIGHT_WRIST_RETURN_DELAY", 0.0))
    shoulder_elbow_gap = max(0.0, get_float_env("GREETING_RETURN_ELBOW_TO_SHOULDER_GAP", 0.25))
    shoulder_return_delay = max(shoulder_return_delay, elbow_return_delay + shoulder_elbow_gap)
    total_duration = shoulder_return_delay + (steps * step_delay)
    started_at = time.monotonic()

    while True:
        elapsed = time.monotonic() - started_at
        shoulder_progress = max(0.0, min(1.0, (elapsed - shoulder_return_delay) / (steps * step_delay)))
        elbow_progress = max(0.0, min(1.0, (elapsed - elbow_return_delay) / (steps * step_delay)))
        wrist_progress = max(0.0, min(1.0, (elapsed - wrist_return_delay) / (steps * step_delay)))
        shoulder_ratio = 1.0 - shoulder_progress
        elbow_ratio = 1.0 - elbow_progress
        wrist_ratio = 1.0 - wrist_progress
        controller.send_arm_offsets(
            rest[0] + (right_shoulder * shoulder_ratio),
            rest[1] + (right_elbow * elbow_ratio),
            rest[2] + ((right_wrist - rest[2]) * wrist_ratio),
            rest[3],
            rest[4],
            rest[5],
        )
        if elapsed >= total_duration:
            break
        time.sleep(step_delay)


class GreetingMotionRuntime:
    def __init__(self):
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=play_startup_greeting_motion,
            name="startup-greeting-motion",
            daemon=True,
        )
        self._thread.start()

    def finish(self):
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        finish_startup_greeting_motion()


def start_greeting_motion():
    runtime = GreetingMotionRuntime()
    runtime.start()
    return runtime


def _normalize_command_text(text):
    text = text.lower()
    text = text.replace("o'ng", "ong").replace("o‘ng", "ong").replace("o`ng", "ong")
    text = text.replace("qo'l", "qol").replace("qo‘ l", "qol").replace("qo‘li", "qoli")
    text = text.replace("qo‘", "qo").replace("`", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _detect_arm_sides(text):
    right = any(word in text for word in ["ong", "ung"])
    left = "chap" in text
    both = any(word in text for word in ["ikkala", "baravar", "birga", "har ikkala", "ikki qol", "ikkala qol"])

    if both or (right and left):
        return {"right", "left"}
    if right:
        return {"right"}
    if left:
        return {"left"}
    return {"right", "left"}


def _detect_arm_action(text):
    if any(word in text for word in ["kotar", "ko'tar", "yuqoriga", "baland", "tepaga"]):
        return "raise"
    if any(word in text for word in ["tushir", "pastga", "pasaytir", "past"]):
        return "lower"
    if any(word in text for word in ["koks", "ko'ks", "kokrak", "ko'krak"]):
        return "chest"
    if any(word in text for word in ["silkit", "tebrat", "qimirlat", "hilpirat"]):
        return "wave"
    if any(word in text for word in ["buk", "bukib", "eg"]):
        return "bend"
    if any(word in text for word in ["togirla", "to'g'irla", "tekisla", "yoz"]):
        return "straighten"
    return None


def _is_arm_command_text(text):
    return any(word in text for word in ["qol", "yelka", "yelk", "tirsak", "tirsag", "bilak", "bilag"])


def _with_sides(base_offsets, sides, right_values, left_values=None):
    values = list(base_offsets)
    if "right" in sides:
        values[0], values[1], values[2] = right_values
    if "left" in sides:
        left_values = left_values if left_values is not None else right_values
        values[3], values[4], values[5] = left_values
    return tuple(values)


def _arm_response(action, sides):
    if sides == {"right", "left"}:
        target = "ikkala qo'limni"
    elif "right" in sides:
        target = "o'ng qo'limni"
    else:
        target = "chap qo'limni"

    responses = {
        "raise": f"Mayli, {target} ko'tardim.",
        "lower": f"Mayli, {target} tushirdim.",
        "chest": f"Mayli, {target} ko'ksimga qo'ydim.",
        "wave": f"Mayli, {target} qimirlatdim.",
        "bend": f"Mayli, {target} tirsagidan bukdim.",
        "straighten": f"Mayli, {target} to'g'riladim.",
    }
    return responses.get(action, "Mayli, qo'l harakatini bajardim.")


def execute_arm_voice_command(text):
    normalized = _normalize_command_text(text)
    if not _is_arm_command_text(normalized):
        return None

    action = _detect_arm_action(normalized)
    if action is None:
        return None

    sides = _detect_arm_sides(normalized)
    rest = get_resting_arm_offsets()
    current = _get_current_arm_offsets()

    raise_shoulder = get_int_env("ARM_COMMAND_RAISE_SHOULDER_OFFSET", 85)
    raise_elbow = get_int_env("ARM_COMMAND_RAISE_ELBOW_OFFSET", 15)
    raise_wrist = get_int_env("ARM_COMMAND_RAISE_WRIST_OFFSET", 0)
    chest_shoulder = get_int_env("GREETING_RIGHT_SHOULDER_OFFSET", 65)
    chest_elbow = get_int_env("GREETING_RIGHT_ELBOW_OFFSET", 75)
    bend_elbow = get_int_env("ARM_COMMAND_BEND_ELBOW_OFFSET", 80)
    steps = max(1, get_int_env("ARM_COMMAND_STEPS", 10))
    step_delay = max(0.02, get_float_env("ARM_COMMAND_STEP_DELAY", 0.045))

    if action == "raise":
        target = _with_sides(
            current,
            sides,
            (raise_shoulder, raise_elbow, rest[2] + raise_wrist),
            (raise_shoulder, raise_elbow, rest[5] + raise_wrist),
        )
        move_arms_to_offsets(target, steps, step_delay)
    elif action == "lower":
        target = _with_sides(current, sides, (rest[0], rest[1], rest[2]), (rest[3], rest[4], rest[5]))
        move_arms_to_offsets(target, steps, step_delay)
    elif action == "chest":
        target = _with_sides(
            current,
            sides,
            (chest_shoulder, chest_elbow, rest[2]),
            (chest_shoulder, chest_elbow, rest[5]),
        )
        move_arms_to_offsets(target, steps, step_delay)
    elif action == "bend":
        target = list(current)
        if "right" in sides:
            target[1] = bend_elbow
        if "left" in sides:
            target[4] = bend_elbow
        move_arms_to_offsets(tuple(target), steps, step_delay)
    elif action == "straighten":
        target = list(current)
        if "right" in sides:
            target[1] = rest[1]
        if "left" in sides:
            target[4] = rest[4]
        move_arms_to_offsets(tuple(target), steps, step_delay)
    elif action == "wave":
        wave_count = max(1, get_int_env("ARM_COMMAND_WAVE_COUNT", 3))
        wave_size = get_int_env("ARM_COMMAND_WAVE_WRIST_OFFSET", 35)
        base = _with_sides(current, sides, (raise_shoulder, raise_elbow, rest[2]), (raise_shoulder, raise_elbow, rest[5]))
        move_arms_to_offsets(base, steps, step_delay)
        for index in range(wave_count):
            sign = 1 if index % 2 == 0 else -1
            target = list(base)
            if "right" in sides:
                target[2] = rest[2] + (wave_size * sign)
            if "left" in sides:
                target[5] = rest[5] + (wave_size * sign)
            move_arms_to_offsets(tuple(target), max(2, steps // 2), step_delay)
        move_arms_to_offsets(base, max(2, steps // 2), step_delay)

    return _arm_response(action, sides)


class FaceServoTracker:
    def __init__(self, frame_width, serial_controller):
        self.frame_width = frame_width
        self.serial_controller = serial_controller
        self.enabled = get_bool_env("FACE_SERVO_ENABLED", True)
        self.invert = get_bool_env("FACE_SERVO_INVERT", False)
        self.direction = -1 if self.invert else 1
        self.servo_min = get_int_env("FACE_SERVO_MIN_ANGLE", 20)
        self.servo_max = get_int_env("FACE_SERVO_MAX_ANGLE", 160)
        self.servo_center = get_int_env("FACE_SERVO_CENTER_ANGLE", 90)
        self.dead_zone = get_float_env("FACE_SERVO_DEAD_ZONE", 0.08)
        self.smoothing = min(0.95, max(0.0, get_float_env("FACE_SERVO_SMOOTHING", 0.45)))
        self.max_step = max(1, get_int_env("FACE_SERVO_MAX_STEP", 7))
        self.send_min_delta = max(1, get_int_env("FACE_SERVO_SEND_MIN_DELTA", 1))
        self.send_interval = max(0.02, get_float_env("FACE_SERVO_SEND_INTERVAL", 0.04))
        self._smoothed_angle = float(self.servo_center)
        self._last_output_angle = int(self.servo_center)
        self._last_face_seen_at = time.monotonic()
        print(
            "[SERVO] Face tracking config: "
            f"invert={self.invert}, center={self.servo_center}, "
            f"range={self.servo_min}-{self.servo_max}, smoothing={self.smoothing}"
        )

    def update(self, face_box):
        if not self.enabled or face_box is None or self.frame_width <= 0:
            return None

        x, _y, w, _h = face_box
        face_center_x = x + (w / 2.0)
        normalized_offset = (face_center_x - (self.frame_width / 2.0)) / (self.frame_width / 2.0)
        normalized_offset = max(-1.0, min(1.0, normalized_offset))

        if abs(normalized_offset) < self.dead_zone:
            target_angle = self.servo_center
        else:
            half_range = min(self.servo_center - self.servo_min, self.servo_max - self.servo_center)
            target_angle = self.servo_center + (normalized_offset * self.direction * half_range)

        target_angle = max(self.servo_min, min(self.servo_max, target_angle))
        self._smoothed_angle = (
            self._smoothed_angle * self.smoothing
            + target_angle * (1.0 - self.smoothing)
        )
        self._last_face_seen_at = time.monotonic()
        angle = int(round(self._smoothed_angle))
        angle_delta = angle - self._last_output_angle
        if abs(angle_delta) > self.max_step:
            angle = self._last_output_angle + (self.max_step if angle_delta > 0 else -self.max_step)

        self.serial_controller.send_servo_angle(
            angle,
            min_delta=self.send_min_delta,
            min_interval=self.send_interval,
        )
        self._last_output_angle = angle
        return angle


class CameraRuntime:
    def __init__(self, camera_index=0, preview=True, face_servo_enabled=True):
        self.camera_index = camera_index
        self.preview = preview
        self.face_servo_enabled = face_servo_enabled
        self.frame_width = get_int_env("CAMERA_FRAME_WIDTH", 640)
        self.frame_height = get_int_env("CAMERA_FRAME_HEIGHT", 480)
        self.frame_fps = get_int_env("CAMERA_FPS", 30)
        self.detect_width = max(160, get_int_env("FACE_DETECT_WIDTH", 320))
        self.detect_scale_factor = get_float_env("FACE_DETECT_SCALE_FACTOR", 1.08)
        self.detect_min_neighbors = max(3, get_int_env("FACE_DETECT_MIN_NEIGHBORS", 4))
        self.detect_min_size = max(30, get_int_env("FACE_DETECT_MIN_SIZE", 55))
        self._stop_event = threading.Event()
        self._thread = None
        self._capture = None
        self._serial_controller = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="camera-preview", daemon=True)
        self._thread.start()
        atexit.register(self.stop)

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._release()
        if self._serial_controller is not None:
            self._serial_controller.close()

    def _open_capture(self, cv2):
        if sys.platform == "win32":
            capture = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if capture.isOpened():
                self._configure_capture(cv2, capture)
                return capture
            capture.release()
        capture = cv2.VideoCapture(self.camera_index)
        if capture.isOpened():
            self._configure_capture(cv2, capture)
        return capture

    def _configure_capture(self, cv2, capture):
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        capture.set(cv2.CAP_PROP_FPS, self.frame_fps)

    def _detect_faces(self, cv2, face_cascade, frame):
        frame_height, frame_width = frame.shape[:2]
        scale = 1.0
        detection_frame = frame

        if frame_width > self.detect_width:
            scale = self.detect_width / float(frame_width)
            target_height = max(1, int(frame_height * scale))
            detection_frame = cv2.resize(frame, (self.detect_width, target_height))

        gray = cv2.cvtColor(detection_frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        min_size = max(20, int(self.detect_min_size * scale))
        detected = face_cascade.detectMultiScale(
            gray,
            scaleFactor=self.detect_scale_factor,
            minNeighbors=self.detect_min_neighbors,
            minSize=(min_size, min_size),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        if scale == 1.0:
            return detected

        faces = []
        inverse_scale = 1.0 / scale
        for x, y, w, h in detected:
            faces.append((
                int(x * inverse_scale),
                int(y * inverse_scale),
                int(w * inverse_scale),
                int(h * inverse_scale),
            ))
        return faces

    def _release(self):
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _run(self):
        try:
            import cv2
        except Exception as exc:
            print(f"[WARN] Kamera uchun OpenCV topilmadi: {exc}")
            return

        self._capture = self._open_capture(cv2)
        if not self._capture or not self._capture.isOpened():
            print(f"[WARN] Kamera ochilmadi: index={self.camera_index}")
            self._release()
            return

        print(f"[KAMERA] Kamera yoqildi: index={self.camera_index}")
        window_name = "Robot Camera"
        face_cascade = None
        face_tracker = None

        if self.face_servo_enabled:
            cascade_path = os.path.join(
                cv2.data.haarcascades,
                "haarcascade_frontalface_default.xml",
            )
            face_cascade = cv2.CascadeClassifier(cascade_path)
            if face_cascade.empty():
                print("[WARN] Yuz aniqlash cascade fayli ochilmadi.")
                face_cascade = None
            else:
                self._serial_controller = get_esp32_controller()
                frame_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH) or self.frame_width)
                face_tracker = FaceServoTracker(frame_width, self._serial_controller)
                print(
                    "[KAMERA] Yuz kuzatish va servo boshqaruv yoqildi. "
                    f"detect_width={self.detect_width}, fps={self.frame_fps}"
                )

        # ── Face recognition setup ────────────────────────────────────────
        _rec_enabled  = get_bool_env("FACE_RECOGNITION_ENABLED", True)
        _rec_interval = get_float_env("FACE_RECOGNITION_INTERVAL", 1.0)
        _rec_min_conf = get_float_env("FACE_RECOGNITION_MIN_CONFIDENCE", 0.50)
        _greet_cooldown     = get_float_env("FACE_GREETING_COOLDOWN_SECONDS", 60.0)
        _greet_unknown      = get_bool_env("FACE_GREETING_UNKNOWN_ENABLED", False)
        _greet_unknown_text = os.environ.get("FACE_GREETING_UNKNOWN_TEXT", "Assalomu alaykum!")
        _debug_mode         = get_bool_env("FACE_RECOGNITION_DEBUG", False)

        # Stability / voting
        _vote_window    = max(1, get_int_env("FACE_RECOGNITION_VOTE_WINDOW", 7))
        _vote_min       = max(1, get_int_env("FACE_RECOGNITION_VOTE_MIN_MATCHES", 5))
        _session_reset  = get_float_env("FACE_SESSION_RESET_SECONDS", 2.0)

        _face_db = None
        if _rec_enabled:
            try:
                from face_recognition_db import get_face_db
                _face_db = get_face_db()
                if not _face_db.is_ready:
                    print("[KAMERA] Face DB not ready — recognition disabled.")
                    _face_db = None
            except Exception as exc:
                print(f"[KAMERA] Face recognition DB load error: {exc}")
                _face_db = None

        # Per-frame timing
        _last_rec_at: float = 0.0

        # Vote window: rolling list of accepted person_ids
        from collections import deque, Counter
        _vote_deque: deque = deque(maxlen=_vote_window)

        # Face session state
        _last_face_seen_at: float = 0.0   # monotonic; 0 = no face yet
        _session_confirmed_pid: str = ""  # person greeted in current session
        _no_face_since: float = 0.0       # when face last disappeared

        # Last per-frame recognition result (for preview overlay)
        _last_rec_result: dict | None = None

        # If InsightFace is the active backend, prefer running recognition on
        # the full frame so we use SCRFD detection + ArcFace alignment instead
        # of the legacy Haar crop. Falls back to recognize(crop) otherwise.
        _use_full_frame_rec = (
            _face_db is not None
            and getattr(_face_db, "recognizer_type", "") == "insightface"
        )

        # Global cooldown: person_id → last greeted monotonic time
        _last_greeted: dict[str, float] = {}

        try:
            while not self._stop_event.is_set():
                ok, frame = self._capture.read()
                if not ok:
                    time.sleep(0.1)
                    continue

                servo_angle = None
                faces = []
                face_box = None
                if face_cascade is not None and face_tracker is not None:
                    faces = self._detect_faces(cv2, face_cascade, frame)
                    if len(faces) > 0:
                        face_box = max(faces, key=lambda box: box[2] * box[3])
                        servo_angle = face_tracker.update(face_box)

                # ── Periodic face recognition ─────────────────────────────
                now = time.monotonic()
                if (
                    _face_db is not None
                    and face_box is not None
                    and (now - _last_rec_at) >= _rec_interval
                ):
                    _last_rec_at = now
                    _last_face_seen_at = now
                    x, y, w, h = face_box
                    face_crop = frame[y:y + h, x:x + w]
                    try:
                        if _use_full_frame_rec:
                            result = _face_db.recognize_frame(frame)
                        else:
                            result = _face_db.recognize(face_crop)
                    except Exception as exc:
                        print(f"[FACE-REC] recognize error: {exc}")
                        result = None
                    _last_rec_result = result

                    # Count stable nearest-person votes. A low top1/top2 margin is
                    # too weak for a single-frame greeting, but it is still useful
                    # evidence when the same person wins repeatedly in the vote
                    # window. Distance/threshold is still enforced by face_db.
                    rejection_reason = result.get("rejection_reason", "") if result is not None else ""
                    can_vote = (
                        result is not None
                        and result.get("person_id")
                        and result.get("confidence", 0.0) >= _rec_min_conf
                        and (
                            result.get("accepted")
                            or rejection_reason.startswith("margin_too_small")
                        )
                    )
                    if can_vote:
                        _vote_deque.append(result["person_id"])
                        if _debug_mode:
                            print(f"[FACE-REC] vote_candidate={result['person_id']} "
                                  f"accepted={result.get('accepted')} "
                                  f"reason={rejection_reason or 'ok'} "
                                  f"vote_window={list(_vote_deque)}")
                    else:
                        # Rejected frame: add a None-equivalent by not appending,
                        # but we still need to fill the window to avoid stale votes.
                        # Append a sentinel so the window advances.
                        _vote_deque.append("")
                        if result is not None and _debug_mode:
                            print(f"[FACE-REC] rejected reason={result.get('rejection_reason','?')} "
                                  f"dist={result.get('distance','?')}")

                    # Check vote stability
                    if len(_vote_deque) >= _vote_window:
                        counts = Counter(pid for pid in _vote_deque if pid)
                        if counts:
                            top_pid, top_count = counts.most_common(1)[0]
                            if top_count >= _vote_min:
                                # Stable identity confirmed
                                if _session_confirmed_pid == top_pid:
                                    # Already greeted this person in current session
                                    pass
                                else:
                                    # Check global cooldown
                                    last_t = _last_greeted.get(top_pid, 0.0)
                                    if (now - last_t) >= _greet_cooldown:
                                        _session_confirmed_pid = top_pid
                                        _last_greeted[top_pid] = now
                                        person = _face_db.people.get(top_pid, {})
                                        event = {
                                            "person_id":    top_pid,
                                            "fio":          person.get("fio", top_pid),
                                            "display_name": person.get("display_name", top_pid),
                                            "confidence":   counts[top_pid] / _vote_window,
                                            "timestamp":    now,
                                        }
                                        put_face_greeting_event(event)
                                        print(f"[FACE-GREET] queued greeting for {top_pid} "
                                              f"votes={top_count}/{_vote_window}")
                                    else:
                                        remaining = _greet_cooldown - (now - last_t)
                                        print(f"[FACE-GREET] skipped cooldown for {top_pid} "
                                              f"({remaining:.0f}s remaining)")
                            else:
                                if _debug_mode:
                                    print(f"[FACE-REC] unstable votes={dict(counts)} "
                                          f"need {_vote_min}/{_vote_window}")

                elif _face_db is not None and face_box is None:
                    # No face visible — check if session should reset
                    now = time.monotonic()
                    if _last_face_seen_at > 0 and (now - _last_face_seen_at) >= _session_reset:
                        if _session_confirmed_pid:
                            print(f"[FACE-REC] session reset (no face for {_session_reset:.1f}s), "
                                  f"was confirmed={_session_confirmed_pid}")
                        _session_confirmed_pid = ""
                        _vote_deque.clear()
                        _last_face_seen_at = 0.0

                elif _face_db is not None and face_box is not None:
                    # Face visible but not yet time to recognize — update last seen
                    _last_face_seen_at = time.monotonic()

                if _greet_unknown and _face_db is not None and face_box is not None:
                    # Unknown face greeting (disabled by default)
                    pass  # handled above via vote window with empty pid

                if self.preview:
                    for x, y, w, h in faces:
                        color = (0, 255, 0) if face_box is not None and (x, y, w, h) == tuple(face_box) else (120, 120, 120)
                        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
                    center_x = frame.shape[1] // 2
                    cv2.line(frame, (center_x, 0), (center_x, frame.shape[0]), (255, 180, 0), 1)
                    if servo_angle is not None:
                        cv2.putText(
                            frame,
                            f"Servo: {servo_angle}",
                            (12, 32),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.8,
                            (0, 255, 255),
                            2,
                        )

                    # ── Recognition overlay ───────────────────────────────
                    if _face_db is not None and _last_rec_result is not None:
                        r = _last_rec_result
                        if r.get("accepted"):
                            label = (f"{r.get('display_name', r.get('person_id',''))} "
                                     f"sim={r.get('similarity', 0.0):.2f}")
                            color = (0, 255, 0)
                        else:
                            label = (f"unknown ({r.get('rejection_reason','?')[:24]}) "
                                     f"sim={r.get('similarity', 0.0):.2f}")
                            color = (40, 200, 220)
                        votes_label = f"votes={len(_vote_deque)}/{_vote_window} " \
                                      f"confirmed={_session_confirmed_pid or '-'}"
                        cv2.putText(frame, label, (12, 60),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
                        cv2.putText(frame, votes_label, (12, 84),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                                    (180, 255, 180), 1)
                        bbox = r.get("bbox") or []
                        if len(bbox) == 4:
                            bx1, by1, bx2, by2 = bbox
                            cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 2)

                if self.preview:
                    cv2.imshow(window_name, frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self._stop_event.set()
                        break
                else:
                    time.sleep(0.03)
        except Exception as exc:
            print(f"[WARN] Kamera oqimida xato: {exc}")
        finally:
            self._release()
            if self.preview:
                try:
                    cv2.destroyWindow(window_name)
                except Exception:
                    pass
            print("[KAMERA] Kamera to'xtatildi.")


def start_camera_if_enabled():
    enabled = get_bool_env("CAMERA_ENABLED", True)
    if not enabled:
        print("[KAMERA] CAMERA_ENABLED=false. Kamera yoqilmadi.")
        return None

    default_preview = sys.platform == "win32"
    camera_index = get_int_env("CAMERA_INDEX", 0)
    preview = get_bool_env("CAMERA_PREVIEW", default_preview)
    face_servo_enabled = get_bool_env("FACE_SERVO_ENABLED", True)

    runtime = CameraRuntime(
        camera_index=camera_index,
        preview=preview,
        face_servo_enabled=face_servo_enabled,
    )
    runtime.start()
    return runtime


# ─────────────────────────────────────────────────────────────────────────────
# Face recognition greeting queue
# ─────────────────────────────────────────────────────────────────────────────
import queue as _queue

# Thread-safe queue for face greeting events.
# Camera thread pushes; main loop pops.
face_greeting_queue: _queue.Queue = _queue.Queue(maxsize=8)


def put_face_greeting_event(event: dict) -> None:
    """Push a greeting event (non-blocking; drops if queue is full)."""
    try:
        face_greeting_queue.put_nowait(event)
    except _queue.Full:
        pass


def get_face_greeting_event(timeout: float = 0) -> dict | None:
    """
    Pop the next greeting event.
    Returns None immediately if queue is empty (timeout=0).
    """
    try:
        return face_greeting_queue.get(block=(timeout > 0), timeout=timeout)
    except _queue.Empty:
        return None


def clear_face_greeting_events() -> None:
    """Drain all pending greeting events."""
    while not face_greeting_queue.empty():
        try:
            face_greeting_queue.get_nowait()
        except _queue.Empty:
            break
