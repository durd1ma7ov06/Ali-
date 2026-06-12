# -*- coding: utf-8 -*-
"""
Humanoid Robot AI - Self-Setup Launcher
========================================
Birinchi ishga tushganda:
  1. Python 3.12 topilmasa yuklab o'rnatadi
  2. Virtual environment yaratadi
  3. Barcha kutubxonalarni o'rnatadi
  4. .env sozlash wizard ishlatadi
  5. main.py ni ishga tushiradi

Keyingi ishga tushishlarda:
  - To'g'ridan main.py ni ishga tushiradi
"""

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import winreg
from pathlib import Path

# ─────────────────────────────────────────────
# KONSTANTALAR
# ─────────────────────────────────────────────
APP_NAME = "HumanoidRobotAI"
PYTHON_VERSION = "3.12.10"
PYTHON_INSTALLER_URL = (
    "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
)
PYTHON_INSTALLER_FILENAME = "python-3.12.10-amd64.exe"

REQUIREMENTS = [
    "edge-tts",
    "numpy",
    "insightface",
    "onnxruntime",
    "opencv-contrib-python",
    "openai",
    "PyAudio",
    "pygame-ce",
    "pyserial",
    "SpeechRecognition",
]

ENV_EXAMPLE = """\
OPENROUTER_API_KEY=your_openrouter_api_key_here
GEMINI_TEXT_MODEL=google/gemini-2.5-flash
GEMINI_TEXT_FALLBACK_MODELS=deepseek/deepseek-chat-v3-0324,google/gemini-2.0-flash-001
AI_BASE_URL=https://openrouter.ai/api/v1
AI_API_KEY=
AI_MODEL=google/gemini-2.5-flash
AI_FALLBACK_MODELS=deepseek/deepseek-chat-v3-0324:free
AI_PROVIDER=
EDGE_TTS_VOICE=uz-UZ-SardorNeural
EDGE_TTS_RATE=+0%
EDGE_TTS_PITCH=+0Hz
EDGE_TTS_VOLUME=+0%
STT_LANGUAGE=uz-UZ
LOCAL_TIMEZONE=Asia/Tashkent
GREETING_TEXT=Assalomu alaykum, bolam! Men Sohibqiron Amir Temurman. Senga o'z tarixim va saltanatim haqida so'zlab beraman.
MICROPHONE_NAME=camera,webcam,uvc,fhd,1080p,a4ech,a4tech
MICROPHONE_DEVICE_INDEX=
CAMERA_ENABLED=true
CAMERA_INDEX=0
CAMERA_PREVIEW=true
CAMERA_FRAME_WIDTH=640
CAMERA_FRAME_HEIGHT=480
CAMERA_FPS=30
ESP32_SERIAL_ENABLED=true
ESP32_PORT=
ESP32_BAUDRATE=115200
FACE_SERVO_ENABLED=true
FACE_SERVO_MIN_ANGLE=20
FACE_SERVO_CENTER_ANGLE=90
FACE_SERVO_MAX_ANGLE=160
FACE_SERVO_DEAD_ZONE=0.08
FACE_SERVO_SMOOTHING=0.45
FACE_SERVO_MAX_STEP=7
FACE_SERVO_SEND_MIN_DELTA=1
FACE_SERVO_SEND_INTERVAL=0.04
FACE_SERVO_INVERT=false
FACE_DETECT_WIDTH=320
FACE_DETECT_SCALE_FACTOR=1.08
FACE_DETECT_MIN_NEIGHBORS=4
FACE_DETECT_MIN_SIZE=55
ARM_REST_RIGHT_SHOULDER_OFFSET=0
ARM_REST_RIGHT_ELBOW_OFFSET=0
ARM_REST_RIGHT_WRIST_OFFSET=90
ARM_REST_LEFT_SHOULDER_OFFSET=0
ARM_REST_LEFT_ELBOW_OFFSET=0
ARM_REST_LEFT_WRIST_OFFSET=45
STARTUP_GREETING_MOTION_ENABLED=true
GREETING_RIGHT_SHOULDER_OFFSET=44
GREETING_RIGHT_ELBOW_OFFSET=56
GREETING_RIGHT_WRIST_OFFSET=0
GREETING_HEAD_NOD=8
GREETING_HEAD_DELAY=0.14
GREETING_ARM_STEPS=8
GREETING_ARM_RETURN_STEPS=14
GREETING_ARM_STEP_DELAY=0.05
GREETING_RIGHT_ELBOW_START_DELAY=0.18
GREETING_RIGHT_WRIST_START_DELAY=0.0
GREETING_RIGHT_ELBOW_RETURN_DELAY=0.18
GREETING_RETURN_ELBOW_TO_SHOULDER_GAP=0.25
GREETING_RIGHT_SHOULDER_RETURN_DELAY=0.35
GREETING_RIGHT_WRIST_RETURN_DELAY=0.0
ARM_COMMAND_STEPS=10
ARM_COMMAND_STEP_DELAY=0.045
ARM_COMMAND_RAISE_SHOULDER_OFFSET=85
ARM_COMMAND_RAISE_ELBOW_OFFSET=15
ARM_COMMAND_RAISE_WRIST_OFFSET=0
ARM_COMMAND_BEND_ELBOW_OFFSET=80
ARM_COMMAND_WAVE_COUNT=3
ARM_COMMAND_WAVE_WRIST_OFFSET=35
VAD_AMBIENT_CALIBRATION_DURATION=1.0
VAD_PAUSE_THRESHOLD=0.6
VAD_NON_SPEAKING_DURATION=0.3
VAD_PHRASE_TIME_LIMIT=8
VAD_LISTEN_TIMEOUT=5
TTS_MIN_CHUNK_BYTES=8192
AI_REQUEST_TIMEOUT=6.0
AI_MAX_MODEL_ATTEMPTS=1
ARM_COMMAND_TIMEOUT=5.0
TURN_COOLDOWN_SECONDS=0.0
LATENCY_LOGGING_ENABLED=true
LATENCY_LOG_LEVEL=summary
MIC_DEVICE_INDEX=
MIC_DEVICE_NAME=
VAD_DYNAMIC_ENERGY_THRESHOLD=true
VAD_ENERGY_THRESHOLD=300
INTERRUPT_LISTENER_ENABLED=true
INTERRUPT_STOP_WORDS=stop,cancel,enough,toxtat,to'xtat,yetarli,bas,bekor qil
INTERRUPT_LISTENER_TIMEOUT=0.25
INTERRUPT_LISTENER_PHRASE_LIMIT=2.0
TTS_MAX_TEXT_CHARS=0
ARM_RIGHT_SHOULDER_RAISE_OFFSET=55
ARM_LEFT_SHOULDER_RAISE_OFFSET=55
ARM_RIGHT_SHOULDER_CHEST_OFFSET=30
ARM_LEFT_SHOULDER_CHEST_OFFSET=30
ARM_RIGHT_ELBOW_BEND_OFFSET=45
ARM_LEFT_ELBOW_BEND_OFFSET=45
ARM_RIGHT_WRIST_WAVE_OFFSET=35
ARM_LEFT_WRIST_WAVE_OFFSET=35
ARM_RIGHT_WRIST_TURN_OFFSET=45
ARM_LEFT_WRIST_TURN_OFFSET=45
ARM_AUTO_RETURN_TO_NEUTRAL=true
MOVEMENT_DEFAULT_STEP_WAIT_MS=500
MOVEMENT_DELAY_MAX_SECONDS=30
MOVEMENT_AI_PLANNER_ENABLED=true
MOVEMENT_AI_PLANNER_TIMEOUT=8.0
MOVEMENT_CLARIFY_TEXT=Bu harakat buyrug'ini aniqroq ayting.
FACE_RECOGNITION_ENABLED=true
FACE_DATA_DIR=face_data
FACE_DB_PATH=face_data/faces.sqlite
FACE_MODEL_NAME=buffalo_l
FACE_DET_SIZE=640
FACE_MIN_DET_SCORE=0.65
FACE_MIN_FACE_PIXELS=50
FACE_MIN_SIMILARITY=0.45
FACE_MIN_MARGIN=0.08
FACE_RECOGNITION_INTERVAL=0.5
FACE_RECOGNITION_MIN_CONFIDENCE=0.50
FACE_GREETING_COOLDOWN_SECONDS=60
FACE_GREETING_TEXT_TEMPLATE=Assalomu alaykum, {display_name}!
FACE_GREETING_UNKNOWN_ENABLED=false
FACE_GREETING_UNKNOWN_TEXT=Assalomu alaykum!
FACE_LBPH_THRESHOLD=115
FACE_RECOGNITION_MAX_DISTANCE=0.65
FACE_RECOGNITION_MIN_MARGIN_LBPH=15
FACE_RECOGNITION_MIN_MARGIN_HIST=0.08
FACE_RECOGNITION_VOTE_WINDOW=5
FACE_RECOGNITION_VOTE_MIN_MATCHES=3
FACE_SESSION_RESET_SECONDS=2.0
FACE_RECOGNITION_DEBUG=false
UNIVERSITY_KNOWLEDGE_ENABLED=true
UNIVERSITY_KNOWLEDGE_TOP_K=5
UNIVERSITY_KNOWLEDGE_MIN_SCORE=0.30
UNIVERSITY_KNOWLEDGE_MAX_CONTEXT_CHARS=4500
UNIVERSITY_KNOWLEDGE_NO_ANSWER_TEXT=Mening tarixim va faoliyatim haqida bunday ma'lumot topilmadi, bolam.
UNIVERSITY_KNOWLEDGE_ANSWER_STYLE=short
UNIVERSITY_KNOWLEDGE_REQUIRE_SOURCE=true
UNIVERSITY_KNOWLEDGE_USE_AI=true
UNIVERSITY_KNOWLEDGE_AI_TIMEOUT=8.0
"""


# ─────────────────────────────────────────────
# EMBEDDED FAYLLAR (PyInstaller sys._MEIPASS)
# ─────────────────────────────────────────────

def get_bundle_dir() -> Path:
    """
    PyInstaller bilan build qilingan EXE ichida fayllar
    sys._MEIPASS papkasida bo'ladi.
    Oddiy Python skript sifatida ishlaganda __file__ papkasi.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def get_embedded_file_content(filename: str) -> str:
    """Bundle ichidagi faylni o'qiydi."""
    bundle = get_bundle_dir()
    p = bundle / filename
    if p.exists():
        return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Embedded fayl topilmadi: {filename}")


EMBEDDED_PY_FILES = [
    "main.py",
    "main_rpi.py",
    "robot_hardware.py",
    "pipeline_core.py",
    "movement_commands.py",
    "ai_client.py",
    "face_recognition_db.py",
    "build_face_db.py",
    "knowledge_crawler.py",
    "knowledge_index.py",
    "knowledge_qa.py",
    "knowledge_maintenance.py",
    "arm_servo_test.py",
    "face_servo_test.py",
]


# ─────────────────────────────────────────────
# PRINT YORDAMCHILARI
# ─────────────────────────────────────────────

def print_banner():
    print("=" * 60)
    print("   HUMANOID ROBOT AI - LAUNCHER v1.0")
    print("=" * 60)
    print()


def print_step(msg):
    print(f"\n>>> {msg}")


def print_ok(msg):
    print(f"    [OK] {msg}")


def print_warn(msg):
    print(f"    [!]  {msg}")


def print_err(msg):
    print(f"    [XATO] {msg}")


# ─────────────────────────────────────────────
# PAPKALAR
# ─────────────────────────────────────────────

def get_app_dir() -> Path:
    """Dastur uchun asosiy papka: %APPDATA%/HumanoidRobotAI"""
    appdata = os.environ.get("APPDATA", str(Path.home()))
    app_dir = Path(appdata) / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_venv_dir(app_dir: Path) -> Path:
    return app_dir / "venv"


def get_venv_python(app_dir: Path) -> Path:
    return get_venv_dir(app_dir) / "Scripts" / "python.exe"


def get_setup_done_flag(app_dir: Path) -> Path:
    return app_dir / ".setup_done"


# ─────────────────────────────────────────────
# ADMIN TEKSHIRISH
# ─────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin():
    """Dasturni administrator sifatida qayta ishga tushiradi."""
    script = sys.executable
    params = " ".join([f'"{a}"' for a in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
    sys.exit(0)


# ─────────────────────────────────────────────
# PYTHON 3.12 TOPISH
# ─────────────────────────────────────────────

def _find_python_registry() -> str | None:
    keys = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Python\PythonCore\3.12\InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Python\PythonCore\3.12\InstallPath"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Python\PythonCore\3.12\InstallPath"),
    ]
    for hive, key_path in keys:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, "ExecutablePath")
                    if val and Path(val).exists():
                        return str(val)
                except FileNotFoundError:
                    pass
                try:
                    val, _ = winreg.QueryValueEx(key, "")
                    candidate = Path(val) / "python.exe"
                    if candidate.exists():
                        return str(candidate)
                except FileNotFoundError:
                    pass
        except Exception:
            continue
    return None


def _find_python_path() -> str | None:
    for cmd in ["py", "python3.12", "python3", "python"]:
        found = shutil.which(cmd)
        if not found:
            continue
        try:
            r = subprocess.run(
                [found, "--version"],
                capture_output=True, text=True, timeout=10
            )
            ver = (r.stdout + r.stderr).strip()
            if "3.12" in ver:
                return found
        except Exception:
            continue
    return None


def _find_python_localappdata() -> str | None:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for sub in ["Python312", "Python3.12"]:
        c = local / "Programs" / "Python" / sub / "python.exe"
        if c.exists():
            return str(c)
    return None


def _find_python_py_launcher() -> str | None:
    """py -3.12 launcher orqali topadi."""
    try:
        r = subprocess.run(
            ["py", "-3.12", "-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            exe = r.stdout.strip()
            if exe and Path(exe).exists():
                return exe
    except Exception:
        pass
    return None


def find_python312() -> str | None:
    for finder in [
        _find_python_registry,
        _find_python_py_launcher,
        _find_python_path,
        _find_python_localappdata,
    ]:
        result = finder()
        if result:
            return result
    return None


# ─────────────────────────────────────────────
# PYTHON O'RNATISH
# ─────────────────────────────────────────────

def download_python_installer(dest_dir: Path) -> Path:
    dest = dest_dir / PYTHON_INSTALLER_FILENAME
    if dest.exists():
        print_ok(f"Installer allaqachon yuklab olingan.")
        return dest

    print_step(f"Python {PYTHON_VERSION} yuklab olinmoqda...")
    print(f"    URL: {PYTHON_INSTALLER_URL}")
    print("    Bu bir necha daqiqa olishi mumkin...")

    def _progress(block_num, block_size, total_size):
        if total_size > 0:
            downloaded = block_num * block_size
            pct = min(100, int(downloaded * 100 / total_size))
            mb = downloaded / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            print(f"\r    {pct}%  {mb:.1f}/{total_mb:.1f} MB", end="", flush=True)

    try:
        urllib.request.urlretrieve(PYTHON_INSTALLER_URL, dest, _progress)
        print()
        print_ok("Yuklab olindi.")
        return dest
    except Exception as e:
        print()
        raise RuntimeError(f"Python yuklab olinmadi: {e}")


def install_python(installer_path: Path):
    print_step("Python o'rnatilmoqda (2-5 daqiqa)...")
    print("    Iltimos kuting...")
    cmd = [
        str(installer_path),
        "/quiet",
        "InstallAllUsers=0",
        "PrependPath=1",
        "Include_test=0",
        "Include_doc=0",
        "Include_launcher=1",
        "InstallLauncherAllUsers=0",
    ]
    result = subprocess.run(cmd, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(
            f"Python o'rnatilmadi. Exit code: {result.returncode}"
        )
    print_ok("Python o'rnatildi.")


def ensure_python312() -> str:
    print_step("Python 3.12 tekshirilmoqda...")
    python_exe = find_python312()
    if python_exe:
        print_ok(f"Python 3.12 topildi: {python_exe}")
        return python_exe

    print_warn("Python 3.12 topilmadi. O'rnatilmoqda...")

    if not is_admin():
        print_warn("Python o'rnatish uchun administrator huquqi kerak.")
        print("    Dastur administrator sifatida qayta ishga tushirilmoqda...")
        run_as_admin()

    tmp_dir = Path(tempfile.mkdtemp(prefix="robot_setup_"))
    try:
        installer = download_python_installer(tmp_dir)
        install_python(installer)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # O'rnatgandan keyin qayta qidirish
    python_exe = find_python312()
    if not python_exe:
        python_exe = _find_python_py_launcher()

    if not python_exe:
        raise RuntimeError(
            "Python o'rnatildi, lekin topilmadi.\n"
            "Kompyuterni qayta yoqib, dasturni qayta ishga tushiring."
        )

    print_ok(f"Python 3.12 tayyor: {python_exe}")
    return python_exe


# ─────────────────────────────────────────────
# VIRTUAL ENVIRONMENT
# ─────────────────────────────────────────────

def create_venv(python_exe: str, app_dir: Path) -> str:
    venv_dir = get_venv_dir(app_dir)
    venv_python = get_venv_python(app_dir)

    if venv_dir.exists() and venv_python.exists():
        print_ok("Virtual environment allaqachon mavjud.")
        return str(venv_python)

    if venv_dir.exists():
        print_warn("Venv buzilgan. Qayta yaratilmoqda...")
        shutil.rmtree(venv_dir, ignore_errors=True)

    print_step("Virtual environment yaratilmoqda...")
    result = subprocess.run(
        [python_exe, "-m", "venv", str(venv_dir)],
        timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError("Virtual environment yaratilmadi.")

    print_ok(f"Venv yaratildi: {venv_dir}")
    return str(venv_python)


def install_packages(venv_python: str):
    print_step("Kutubxonalar o'rnatilmoqda...")
    print("    Bu 3-10 daqiqa olishi mumkin...")

    # pip yangilash
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        timeout=120
    )

    failed = []
    for pkg in REQUIREMENTS:
        print(f"    {pkg} ...", end="", flush=True)
        r = subprocess.run(
            [venv_python, "-m", "pip", "install", pkg, "--quiet"],
            timeout=300,
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            print(" OK")
        else:
            print(" XATO")
            # PyAudio uchun maxsus urinish (pipwin wheel)
            if "PyAudio" in pkg:
                print("    PyAudio: pipwin orqali sinab ko'rilmoqda...")
                r2 = subprocess.run(
                    [venv_python, "-m", "pip", "install", "pipwin", "--quiet"],
                    timeout=120, capture_output=True, text=True
                )
                r3 = subprocess.run(
                    [venv_python, "-m", "pipwin", "install", "pyaudio"],
                    timeout=300, capture_output=True, text=True
                )
                if r3.returncode == 0:
                    print("    PyAudio OK (pipwin)")
                else:
                    print_warn("PyAudio o'rnatilmadi. Mikrofon ishlamasligi mumkin.")
                    failed.append(pkg)
            else:
                failed.append(pkg)
                print(f"      {r.stderr.strip()[:150]}")

    if failed:
        print_warn(f"O'rnatilmagan paketlar: {failed}")
        print_warn("Dastur qisman ishlashi mumkin.")
    else:
        print_ok("Barcha kutubxonalar o'rnatildi.")


# ─────────────────────────────────────────────
# DASTUR FAYLLARINI CHIQARISH
# ─────────────────────────────────────────────

def extract_app_files(app_dir: Path):
    print_step("Dastur fayllari chiqarilmoqda...")

    for filename in EMBEDDED_PY_FILES:
        try:
            content = get_embedded_file_content(filename)
            dest = app_dir / filename
            dest.write_text(content, encoding="utf-8")
            print_ok(f"  {filename}")
        except FileNotFoundError as e:
            print_warn(str(e))

    # .env.example
    env_example = app_dir / ".env.example"
    env_example.write_text(ENV_EXAMPLE, encoding="utf-8")
    print_ok("  .env.example")

    print_ok("Fayllar chiqarildi.")


def update_app_files(app_dir: Path):
    """Fayllarni yangilaydi (agar launcher yangi versiya bo'lsa)."""
    updated = False
    for filename in EMBEDDED_PY_FILES:
        try:
            new_content = get_embedded_file_content(filename)
            dest = app_dir / filename
            if not dest.exists() or dest.read_text(encoding="utf-8") != new_content:
                dest.write_text(new_content, encoding="utf-8")
                updated = True
                print_ok(f"Yangilandi: {filename}")
        except Exception:
            pass
    if not updated:
        print_ok("Fayllar yangi, yangilash shart emas.")


# ─────────────────────────────────────────────
# .ENV SOZLASH WIZARD
# ─────────────────────────────────────────────

def _read_env_key(env_file: Path, key: str) -> str:
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _write_env_key(env_file: Path, key: str, value: str):
    content = env_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []
    replaced = False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")
    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def setup_env_wizard(app_dir: Path):
    env_file = app_dir / ".env"

    # Mavjud .env da API kalit borligini tekshirish
    if env_file.exists():
        api_key = _read_env_key(env_file, "OPENROUTER_API_KEY")
        if api_key and api_key != "your_openrouter_api_key_here":
            print_ok(".env sozlangan. API kalit mavjud.")
            return

    # .env yo'q yoki kalit kiritilmagan
    if not env_file.exists():
        env_file.write_text(ENV_EXAMPLE, encoding="utf-8")

    print()
    print("=" * 60)
    print("  SOZLASH WIZARD")
    print("=" * 60)
    print()
    print("  Dastur ishlashi uchun OpenRouter API kaliti kerak.")
    print("  Kalit olish uchun: https://openrouter.ai/keys")
    print("  (Bepul ro'yxatdan o'tib kalit olishingiz mumkin)")
    print()

    api_key = ""
    while not api_key or api_key == "your_openrouter_api_key_here":
        try:
            api_key = input("  API kalitni kiriting: ").strip()
        except EOFError:
            api_key = ""
        if not api_key:
            print("  Kalit bo'sh bo'lishi mumkin emas.")
        elif api_key == "your_openrouter_api_key_here":
            print("  Haqiqiy API kalitni kiriting.")

    _write_env_key(env_file, "OPENROUTER_API_KEY", api_key)
    print_ok("API kalit saqlandi.")

    print()
    print("  Qo'shimcha sozlamalar (Enter = default):")
    print()

    # ESP32 port
    try:
        esp32_port = input(
            "  ESP32 port (masalan COM3, bo'sh = avtomatik): "
        ).strip()
    except EOFError:
        esp32_port = ""
    if esp32_port:
        _write_env_key(env_file, "ESP32_PORT", esp32_port)
        print_ok(f"ESP32_PORT={esp32_port}")

    # Kamera
    try:
        cam = input(
            "  Kamera yoqilsinmi? (ha/yo'q, default=ha): "
        ).strip().lower()
    except EOFError:
        cam = ""
    if cam in ("yo'q", "yoq", "no", "n", "false", "0"):
        _write_env_key(env_file, "CAMERA_ENABLED", "false")
        print_ok("Kamera o'chirildi.")

    print()
    print_ok("Sozlash tugadi!")
    print(f"    .env fayli: {env_file}")
    print("    Keyinchalik sozlamalarni to'g'ridan shu faylda o'zgartiring.")


# ─────────────────────────────────────────────
# DASTURNI ISHGA TUSHIRISH
# ─────────────────────────────────────────────

def run_main_app(venv_python: str, app_dir: Path) -> int:
    main_py = app_dir / "main.py"
    if not main_py.exists():
        raise RuntimeError(f"main.py topilmadi: {main_py}")

    print()
    print("=" * 60)
    print("  DASTUR ISHGA TUSHMOQDA")
    print("=" * 60)
    print()

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [venv_python, str(main_py)],
        cwd=str(app_dir),
        env=env,
    )
    return result.returncode


# ─────────────────────────────────────────────
# SETUP HOLATI
# ─────────────────────────────────────────────

def is_setup_done(app_dir: Path) -> bool:
    if not get_setup_done_flag(app_dir).exists():
        return False
    if not get_venv_python(app_dir).exists():
        return False
    if not (app_dir / "main.py").exists():
        return False
    return True


def mark_setup_done(app_dir: Path):
    get_setup_done_flag(app_dir).write_text("1", encoding="utf-8")


def full_setup(app_dir: Path) -> str:
    print_step("Birinchi marta o'rnatish boshlandi...")

    python_exe = ensure_python312()
    venv_python = create_venv(python_exe, app_dir)
    extract_app_files(app_dir)
    install_packages(venv_python)
    mark_setup_done(app_dir)

    print()
    print("=" * 60)
    print("  O'RNATISH TUGADI!")
    print("=" * 60)

    return venv_python


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    # Windows encoding
    if sys.platform == "win32":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print_banner()

    app_dir = get_app_dir()
    print(f"    Dastur papkasi: {app_dir}")

    try:
        if not is_setup_done(app_dir):
            venv_python = full_setup(app_dir)
        else:
            print_ok("O'rnatish allaqachon tugallangan.")
            venv_python = str(get_venv_python(app_dir))
            update_app_files(app_dir)

        setup_env_wizard(app_dir)
        exit_code = run_main_app(venv_python, app_dir)
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n\n    Foydalanuvchi tomonidan to'xtatildi.")
        sys.exit(0)
    except Exception as e:
        print()
        print_err(str(e))
        print()
        print("  Muammo yuzaga keldi.")
        print("  Qayta urinish uchun dasturni qayta ishga tushiring.")
        print()
        try:
            input("  Davom etish uchun Enter bosing...")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
