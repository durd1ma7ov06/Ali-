@echo off
chcp 65001 > nul
echo ========================================
echo    SOHIBQIRON AMIR TEMUR - ISHGA TUSHIRISH
echo ========================================
echo.

echo [1/5] Virtual environment faollashtirilmoqda...
call venv312\Scripts\activate.bat
if errorlevel 1 (
    echo XATO: Virtual environment topilmadi!
    echo Iltimos, avval venv312 ni yarating.
    pause
    exit /b 1
)

echo [2/5] Python versiyasi tekshirilmoqda...
python --version

echo [3/5] Kutubxonalar tekshirilmoqda...
python -c "import speech_recognition; import edge_tts; import pygame; import cv2; import openai; print('✓ Barcha kutubxonalar o''rnatilgan')"
if errorlevel 1 (
    echo.
    echo XATO: Ba'zi kutubxonalar o'rnatilmagan!
    echo Iltimos, quyidagi buyruqni bajaring:
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

echo [4/5] ESP32 ulanishi tekshirilmoqda...
python -c "import serial.tools.list_ports; ports = list(serial.tools.list_ports.comports()); print(f'Topilgan portlar: {len(ports)}'); [print(f'  - {p.device}: {p.description}') for p in ports]"

echo [5/5] Sohibqiron Amir Temur ishga tushirilmoqda...
echo.
echo ========================================
echo    ROBOT TAYYOR! Ctrl+C bilan to'xtating
echo ========================================
echo.

python main.py

pause
