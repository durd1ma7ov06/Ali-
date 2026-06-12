# SOHIBQIRON AMIR TEMUR HUMANOID ROBOT - PowerShell Ishga Tushirish Skripti
# UTF-8 encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   SOHIBQIRON AMIR TEMUR - ISHGA TUSHIRISH" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Virtual environment
Write-Host "[1/5] Virtual environment faollashtirilmoqda..." -ForegroundColor Yellow
if (Test-Path ".\venv312\Scripts\Activate.ps1") {
    & ".\venv312\Scripts\Activate.ps1"
    Write-Host "✓ Virtual environment faollashtirildi" -ForegroundColor Green
} else {
    Write-Host "✗ XATO: venv312 topilmadi!" -ForegroundColor Red
    Write-Host "Iltimos, avval virtual environment yarating:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv312" -ForegroundColor White
    Write-Host "  .\venv312\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  pip install -r requirements.txt" -ForegroundColor White
    pause
    exit 1
}

# 2. Python versiyasi
Write-Host ""
Write-Host "[2/5] Python versiyasi tekshirilmoqda..." -ForegroundColor Yellow
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ XATO: Python topilmadi!" -ForegroundColor Red
    pause
    exit 1
}

# 3. Kutubxonalar
Write-Host ""
Write-Host "[3/5] Kutubxonalar tekshirilmoqda..." -ForegroundColor Yellow
$testScript = @"
try:
    import speech_recognition
    import edge_tts
    import pygame
    import cv2
    import openai
    import serial
    import insightface
    print('✓ Barcha asosiy kutubxonalar o''rnatilgan')
except ImportError as e:
    print(f'✗ Kutubxona topilmadi: {e}')
    exit(1)
"@

python -c $testScript
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "✗ XATO: Ba'zi kutubxonalar o'rnatilmagan!" -ForegroundColor Red
    Write-Host "Iltimos, quyidagi buyruqni bajaring:" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements.txt" -ForegroundColor White
    pause
    exit 1
}

# 4. Hardware tekshiruvi
Write-Host ""
Write-Host "[4/5] Hardware tekshirilmoqda..." -ForegroundColor Yellow

# COM portlar
Write-Host "  • COM portlar:" -ForegroundColor Cyan
$ports = Get-PnpDevice -Class "Ports" | Where-Object {$_.Status -eq "OK"}
foreach ($port in $ports) {
    Write-Host "    - $($port.FriendlyName)" -ForegroundColor White
}

# Kameralar
Write-Host "  • Kameralar:" -ForegroundColor Cyan
$cameras = Get-PnpDevice -Class "Camera" | Where-Object {$_.Status -eq "OK"}
foreach ($camera in $cameras) {
    Write-Host "    - $($camera.FriendlyName)" -ForegroundColor White
}

# Audio qurilmalar
Write-Host "  • Audio qurilmalar:" -ForegroundColor Cyan
$audioDevices = Get-PnpDevice -Class "AudioEndpoint" | Where-Object {$_.Status -eq "OK"} | Select-Object -First 3
foreach ($device in $audioDevices) {
    Write-Host "    - $($device.FriendlyName)" -ForegroundColor White
}

# 5. .env fayli tekshiruvi
Write-Host ""
Write-Host "[5/5] Sozlamalar tekshirilmoqda..." -ForegroundColor Yellow
if (Test-Path ".\.env") {
    Write-Host "✓ .env fayli topildi" -ForegroundColor Green
    
    # API key tekshiruvi
    $envContent = Get-Content ".\.env" -Raw
    if ($envContent -match "AI_API_KEY=(.+)") {
        $apiKey = $matches[1].Trim()
        if ($apiKey -and $apiKey -ne "your_api_key_here") {
            Write-Host "✓ AI_API_KEY sozlangan" -ForegroundColor Green
        } else {
            Write-Host "⚠ OGOHLANTIRISH: AI_API_KEY sozlanmagan!" -ForegroundColor Yellow
            Write-Host "  Robot ishlaydi, lekin AI javoblar bo'lmaydi." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "⚠ OGOHLANTIRISH: .env fayli topilmadi!" -ForegroundColor Yellow
    Write-Host "  .env.example dan nusxa oling va sozlang." -ForegroundColor Yellow
}

# Ishga tushirish
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   ROBOT ISHGA TUSHIRILMOQDA..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Ctrl+C bilan to'xtatish mumkin" -ForegroundColor Yellow
Write-Host ""

# Main dasturni ishga tushirish
python main.py

# Xato bo'lsa
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "✗ Dastur xato bilan to'xtadi!" -ForegroundColor Red
    Write-Host "Yuqoridagi xato xabarlarini o'qing." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Dastur to'xtadi. Oynani yopish uchun Enter bosing..." -ForegroundColor Gray
Read-Host
