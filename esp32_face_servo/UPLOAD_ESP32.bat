@echo off
chcp 65001 >nul
echo ================================================
echo ESP32 Humanoid Servo Controller - Auto Upload
echo ================================================
echo.

set CLI_PATH=%USERPROFILE%\arduino-cli\arduino-cli.exe

if not exist "%CLI_PATH%" (
    echo ❌ Arduino CLI topilmadi!
    echo    O'rnatish uchun: https://arduino.github.io/arduino-cli/
    pause
    exit /b 1
)

echo ✅ Arduino CLI topildi
echo.

echo 🔍 ESP32 ni qidiryapman...
echo.

REM COM portlarni qidirish
for /f "tokens=1" %%a in ('"%CLI_PATH%" board list ^| findstr /R "COM[0-9]"') do (
    set ESP32_PORT=%%a
)

if not defined ESP32_PORT (
    echo ❌ ESP32 topilmadi!
    echo.
    echo 📋 Quyidagilarni tekshiring:
    echo    1. ESP32 USB orqali ulangan bo'lishi kerak
    echo    2. USB driver o'rnatilgan bo'lishi kerak
    echo    3. Device Manager da COM port ko'rinishi kerak
    echo.
    echo Barcha COM portlar:
    "%CLI_PATH%" board list
    echo.
    pause
    exit /b 1
)

echo ✅ ESP32 topildi: %ESP32_PORT%
echo.

echo 📦 Kodni compile qilyapman...
"%CLI_PATH%" compile --fqbn esp32:esp32:esp32 .
if errorlevel 1 (
    echo ❌ Compile xatosi!
    pause
    exit /b 1
)

echo ✅ Compile muvaffaqiyatli!
echo.

echo 📤 ESP32 ga upload qilyapman...
echo    Port: %ESP32_PORT%
echo    Board: ESP32 Dev Module
echo.
echo ⏳ Iltimos kuting... (20-30 sekund)
echo.

"%CLI_PATH%" upload -p %ESP32_PORT% --fqbn esp32:esp32:esp32 .
if errorlevel 1 (
    echo.
    echo ❌ Upload xatosi!
    echo.
    echo 💡 Xatoni tuzatish:
    echo    1. BOOT tugmasini bosib turing
    echo    2. Scripni qayta ishga tushiring
    echo    3. "Connecting..." paydo bo'lganda BOOT ni qo'yib yuboring
    echo.
    pause
    exit /b 1
)

echo.
echo ================================================
echo ✅ MUVAFFAQIYATLI UPLOAD BO'LDI!
echo ================================================
echo.
echo 🔌 Serial Monitor ni ochish uchun:
echo    Baud rate: 115200
echo    Line ending: Newline
echo.
echo 🧪 Test komandalar:
echo    HELP     - Barcha komandalar
echo    STATUS   - Hozirgi holat
echo    HOME     - Neutral pozitsiya
echo    HEAD:90  - Boshni burish
echo.
echo 📚 To'liq yo'riqnoma: TEST_COMMANDS.txt
echo.
pause
