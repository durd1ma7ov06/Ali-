@echo off
chcp 65001 > nul
echo ========================================
echo    KUTUBXONALARNI O'RNATISH
echo ========================================
echo.

echo Virtual environment faollashtirilmoqda...
call venv312\Scripts\activate.bat

echo.
echo pip yangilanmoqda...
python -m pip install --upgrade pip

echo.
echo Kutubxonalar o'rnatilmoqda (bu 5-10 daqiqa davom etishi mumkin)...
pip install -r requirements.txt

echo.
echo ========================================
echo    O'RNATISH TUGADI!
echo ========================================
echo.
echo Test qilish uchun:
echo   python TEST_HARDWARE.py
echo.
pause
