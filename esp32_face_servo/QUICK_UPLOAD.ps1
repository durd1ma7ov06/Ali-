# ESP32 Humanoid Servo Controller - Quick Upload Script
# ======================================================

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "ESP32 Humanoid Servo - Auto Upload" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$cliPath = "$env:USERPROFILE\arduino-cli\arduino-cli.exe"

# Check Arduino CLI
if (-not (Test-Path $cliPath)) {
    Write-Host "❌ Arduino CLI topilmadi!" -ForegroundColor Red
    Write-Host "   O'rnatish uchun: https://arduino.github.io/arduino-cli/" -ForegroundColor Yellow
    Read-Host "Davom etish uchun Enter bosing"
    exit 1
}

Write-Host "✅ Arduino CLI topildi" -ForegroundColor Green
Write-Host ""

# Find ESP32
Write-Host "🔍 ESP32 ni qidiryapman..." -ForegroundColor Yellow
Write-Host ""

$boardList = & $cliPath board list
$port = $null

foreach ($line in $boardList) {
    if ($line -match "(COM\d+)") {
        $port = $matches[1]
        break
    }
}

if (-not $port) {
    Write-Host "❌ ESP32 topilmadi!" -ForegroundColor Red
    Write-Host ""
    Write-Host "📋 Quyidagilarni tekshiring:" -ForegroundColor Yellow
    Write-Host "   1. ESP32 USB orqali ulangan bo'lishi kerak"
    Write-Host "   2. USB driver o'rnatilgan bo'lishi kerak"
    Write-Host "   3. Device Manager da COM port ko'rinishi kerak"
    Write-Host ""
    Write-Host "Barcha COM portlar:" -ForegroundColor Cyan
    Get-CimInstance -ClassName Win32_SerialPort | Select-Object DeviceID, Description | Format-Table
    Read-Host "Davom etish uchun Enter bosing"
    exit 1
}

Write-Host "✅ ESP32 topildi: $port" -ForegroundColor Green
Write-Host ""

# Compile
Write-Host "📦 Kodni compile qilyapman..." -ForegroundColor Yellow
$compileResult = & $cliPath compile --fqbn esp32:esp32:esp32 .

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Compile xatosi!" -ForegroundColor Red
    Read-Host "Davom etish uchun Enter bosing"
    exit 1
}

Write-Host "✅ Compile muvaffaqiyatli!" -ForegroundColor Green
Write-Host ""

# Upload
Write-Host "📤 ESP32 ga upload qilyapman..." -ForegroundColor Yellow
Write-Host "   Port: $port" -ForegroundColor Cyan
Write-Host "   Board: ESP32 Dev Module" -ForegroundColor Cyan
Write-Host ""
Write-Host "⏳ Iltimos kuting... (20-30 sekund)" -ForegroundColor Yellow
Write-Host ""

$uploadResult = & $cliPath upload -p $port --fqbn esp32:esp32:esp32 .

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ Upload xatosi!" -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 Xatoni tuzatish:" -ForegroundColor Yellow
    Write-Host "   1. BOOT tugmasini bosib turing"
    Write-Host "   2. Scripni qayta ishga tushiring"
    Write-Host "   3. 'Connecting...' paydo bo'lganda BOOT ni qo'yib yuboring"
    Write-Host ""
    Read-Host "Davom etish uchun Enter bosing"
    exit 1
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "✅ MUVAFFAQIYATLI UPLOAD BO'LDI!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "🔌 Serial Monitor ni ochish uchun:" -ForegroundColor Cyan
Write-Host "   Baud rate: 115200"
Write-Host "   Line ending: Newline"
Write-Host ""
Write-Host "🧪 Test komandalar:" -ForegroundColor Cyan
Write-Host "   HELP     - Barcha komandalar"
Write-Host "   STATUS   - Hozirgi holat"
Write-Host "   HOME     - Neutral pozitsiya"
Write-Host "   HEAD:90  - Boshni burish"
Write-Host ""
Write-Host "📚 To'liq yo'riqnoma: TEST_COMMANDS.txt" -ForegroundColor Yellow
Write-Host ""

Read-Host "Davom etish uchun Enter bosing"
