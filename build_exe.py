# -*- coding: utf-8 -*-
"""
HumanoidRobotAI.exe yaratish skripti.

Talablar:
    - Python 3.12 o'rnatilgan bo'lsin
    - Internet ulanishi bo'lsin
    - Ushbu skript loyiha papkasida ishga tushirilsin

Ishlatish:
    python build_exe.py

Natija:
    dist/HumanoidRobotAI.exe
"""

import os
import subprocess
import sys
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent


def run(cmd, **kwargs):
    print(f"    $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def check_pyinstaller():
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__}")
        return True
    except ImportError:
        return False


def install_pyinstaller():
    print("[...] PyInstaller o'rnatilmoqda...")
    r = run([sys.executable, "-m", "pip", "install", "pyinstaller"], timeout=180)
    if r.returncode != 0:
        raise RuntimeError("PyInstaller o'rnatilmadi.")
    print("[OK] PyInstaller o'rnatildi.")


def check_required_files():
    required = [
        "launcher.py",
        "main.py",
        "main_rpi.py",
        "robot_hardware.py",
        "arm_servo_test.py",
        "face_servo_test.py",
        ".env.example",
    ]
    missing = []
    for f in required:
        p = BASE_DIR / f
        if p.exists():
            print(f"[OK] {f}")
        else:
            print(f"[!!] TOPILMADI: {f}")
            missing.append(f)
    if missing:
        raise FileNotFoundError(
            f"Quyidagi fayllar topilmadi: {missing}\n"
            "Iltimos loyiha papkasida ishga tushiring."
        )


def clean_old_build():
    for d in ["build", "dist"]:
        p = BASE_DIR / d
        if p.exists():
            shutil.rmtree(p)
            print(f"[OK] Eski {d}/ o'chirildi.")
    spec = BASE_DIR / "HumanoidRobotAI.spec"
    if spec.exists():
        spec.unlink()
        print("[OK] Eski .spec o'chirildi.")


def build():
    print()
    print("=" * 60)
    print("  HumanoidRobotAI.exe YARATILMOQDA")
    print("=" * 60)
    print()

    print("[1/4] Fayllar tekshirilmoqda...")
    check_required_files()
    print()

    print("[2/4] Eski build tozalanmoqda...")
    clean_old_build()
    print()

    print("[3/4] PyInstaller ishga tushirilmoqda...")
    print()

    # --add-data separator: Windows = ";" , Linux/Mac = ":"
    sep = ";" if sys.platform == "win32" else ":"

    def add_data(src_name):
        return f"{BASE_DIR / src_name}{sep}."

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", "HumanoidRobotAI",
        "--distpath", str(BASE_DIR / "dist"),
        "--workpath", str(BASE_DIR / "build"),
        "--specpath", str(BASE_DIR),

        # Embed qilinadigan fayllar
        "--add-data", add_data("main.py"),
        "--add-data", add_data("main_rpi.py"),
        "--add-data", add_data("robot_hardware.py"),
        "--add-data", add_data("arm_servo_test.py"),
        "--add-data", add_data("face_servo_test.py"),
        "--add-data", add_data(".env.example"),

        # Yashirin importlar
        "--hidden-import", "zoneinfo",
        "--hidden-import", "winreg",
        "--hidden-import", "ctypes",
        "--hidden-import", "urllib.request",
        "--hidden-import", "urllib.parse",
        "--hidden-import", "urllib.error",
        "--hidden-import", "email.mime.text",
        "--hidden-import", "email.mime.multipart",

        # Keraksiz modullarni chiqarib tashlash
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "notebook",
        "--exclude-module", "IPython",

        str(BASE_DIR / "launcher.py"),
    ]

    result = run(cmd, cwd=str(BASE_DIR))

    if result.returncode != 0:
        raise RuntimeError("EXE yaratishda xato. Yuqoridagi xatolarni ko'ring.")

    print()
    print("[4/4] Natija tekshirilmoqda...")
    exe_path = BASE_DIR / "dist" / "HumanoidRobotAI.exe"
    if not exe_path.exists():
        raise RuntimeError(f"EXE topilmadi: {exe_path}")

    size_mb = exe_path.stat().st_size / (1024 * 1024)

    print()
    print("=" * 60)
    print("  MUVAFFAQIYATLI YARATILDI!")
    print("=" * 60)
    print(f"  Fayl: {exe_path}")
    print(f"  Hajm: {size_mb:.1f} MB")
    print()
    print("  Foydalanish:")
    print("  1. dist/HumanoidRobotAI.exe ni boshqa kompyuterga ko'chiring")
    print("  2. Ikki marta bosib ishga tushiring")
    print("  3. Birinchi marta: Python + kutubxonalar avtomatik o'rnatiladi")
    print("  4. API kalitni kiriting")
    print("  5. Dastur ishga tushadi")
    print()


def main():
    print()
    print("Python:", sys.version)
    print("Papka:", BASE_DIR)
    print()

    if not check_pyinstaller():
        install_pyinstaller()

    build()


if __name__ == "__main__":
    main()
