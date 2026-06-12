#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hardware Test Script - Ali Robot
Barcha qurilmalarni tekshirish uchun
"""
import sys
import os

# UTF-8 encoding
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

print("=" * 60)
print("   ALI ROBOT - HARDWARE TEST")
print("=" * 60)
print()

# 1. Python kutubxonalari
print("[1/6] Python kutubxonalari tekshirilmoqda...")
try:
    import speech_recognition as sr
    print("  ✓ SpeechRecognition")
except ImportError:
    print("  ✗ SpeechRecognition - pip install SpeechRecognition")

try:
    import edge_tts
    print("  ✓ edge-tts")
except ImportError:
    print("  ✗ edge-tts - pip install edge-tts")

try:
    import pygame
    print("  ✓ pygame")
except ImportError:
    print("  ✗ pygame - pip install pygame-ce")

try:
    import cv2
    print("  ✓ OpenCV")
except ImportError:
    print("  ✗ OpenCV - pip install opencv-contrib-python")

try:
    import serial
    print("  ✓ pyserial")
except ImportError:
    print("  ✗ pyserial - pip install pyserial")

try:
    from openai import OpenAI
    print("  ✓ openai")
except ImportError:
    print("  ✗ openai - pip install openai")

print()

# 2. Mikrofon
print("[2/6] Mikrofonlar tekshirilmoqda...")
try:
    import pyaudio
    pa = pyaudio.PyAudio()
    mic_count = 0
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            mic_count += 1
            print(f"  ✓ [{i}] {info['name']} ({info['maxInputChannels']}ch, {int(info['defaultSampleRate'])}Hz)")
    pa.terminate()
    if mic_count == 0:
        print("  ✗ Mikrofon topilmadi!")
except Exception as e:
    print(f"  ✗ Xato: {e}")

print()

# 3. Kamera
print("[3/6] Kamera tekshirilmoqda...")
try:
    import cv2
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            h, w = frame.shape[:2]
            print(f"  ✓ Kamera ishlayapti ({w}x{h})")
        else:
            print("  ✗ Kamera ochildi, lekin rasm olinmadi")
        cap.release()
    else:
        print("  ✗ Kamera ochilmadi")
except Exception as e:
    print(f"  ✗ Xato: {e}")

print()

# 4. ESP32 Serial
print("[4/6] ESP32 Serial tekshirilmoqda...")
try:
    import serial.tools.list_ports
    ports = list(serial.tools.list_ports.comports())
    if ports:
        for port in ports:
            print(f"  ✓ {port.device}: {port.description}")
            # ESP32 ni topishga harakat
            if any(word in port.description.lower() for word in ["ch340", "cp210", "esp32", "usb serial"]):
                print(f"    → ESP32 bo'lishi mumkin!")
    else:
        print("  ✗ Serial port topilmadi")
except Exception as e:
    print(f"  ✗ Xato: {e}")

print()

# 5. .env fayli
print("[5/6] .env fayli tekshirilmoqda...")
if os.path.exists(".env"):
    print("  ✓ .env fayli mavjud")
    with open(".env", "r", encoding="utf-8") as f:
        content = f.read()
        if "AI_API_KEY=" in content and "your_api_key_here" not in content:
            print("  ✓ AI_API_KEY sozlangan")
        else:
            print("  ⚠ AI_API_KEY sozlanmagan")
        
        if "ESP32_PORT=" in content:
            import re
            match = re.search(r"ESP32_PORT=(.+)", content)
            if match:
                port = match.group(1).strip()
                print(f"  ✓ ESP32_PORT={port}")
else:
    print("  ✗ .env fayli topilmadi")
    print("    .env.example dan nusxa oling")

print()

# 6. Yuz tanish bazasi
print("[6/6] Yuz tanish bazasi tekshirilmoqda...")
if os.path.exists("face_data/faces.sqlite"):
    print("  ✓ faces.sqlite mavjud")
    try:
        import sqlite3
        conn = sqlite3.connect("face_data/faces.sqlite")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM people")
        people_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM face_embeddings")
        embeddings_count = cursor.fetchone()[0]
        conn.close()
        print(f"  ✓ {people_count} odam, {embeddings_count} embedding")
    except Exception as e:
        print(f"  ⚠ Baza ochilmadi: {e}")
else:
    print("  ⚠ faces.sqlite topilmadi")
    print("    python build_face_db.py --rebuild")

print()
print("=" * 60)
print("   TEST TUGADI")
print("=" * 60)
print()
print("Agar barcha ✓ bo'lsa, robot ishga tushirishga tayyor!")
print("Ishga tushirish: python main.py")
print()
