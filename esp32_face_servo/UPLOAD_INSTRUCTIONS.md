# ESP32 ga Upload Qilish Yo'riqnomasi

## ✅ Kod Muvaffaqiyatli Compile Bo'ldi!

**Build ma'lumotlari:**
- Program hajmi: 295,359 bytes (22% flash)
- Global variables: 22,352 bytes (6% RAM)
- Qolgan RAM: 305,328 bytes

**Compiled .bin fayl joylashuvi:**
```
C:\Users\Windows_11\AppData\Local\Temp\arduino\sketches\<sketch_id>\esp32_face_servo.ino.bin
```

---

## Variant 1: Arduino CLI orqali upload (Eng oson) ⚡

### 1. ESP32 ni ulang
- USB kabel orqali kompyuterga ulang
- Device Manager da COM port paydo bo'ladi (COM3, COM4, va h.k.)

### 2. Port raqamini aniqlang

PowerShell da:
```powershell
Get-CimInstance -ClassName Win32_SerialPort | Select-Object DeviceID, Description
```

### 3. Upload qiling

```powershell
$cliPath = "$env:USERPROFILE\arduino-cli\arduino-cli.exe"
cd "C:\Users\Windows_11\Desktop\humanoid ali\humanoid robot\esp32_face_servo"
& $cliPath upload -p COM3 --fqbn esp32:esp32:esp32 .
```

**COM3** ni o'zingizning port raqamingizga o'zgartiring!

---

## Variant 2: Arduino IDE orqali (Tavsiya etiladi) 🎯

### 1. Arduino IDE ni oching
- File > Open > `esp32_face_servo.ino` ni tanlang

### 2. Board sozlamalari
- Tools > Board > ESP32 Arduino > **ESP32 Dev Module**
- Tools > Port > **COM3** (yoki siznikini tanlang)

### 3. Upload sozlamalari
```
Board: ESP32 Dev Module
Upload Speed: 115200
Flash Frequency: 80MHz
Flash Mode: QIO
Flash Size: 4MB (32Mb)
Partition Scheme: Default 4MB with spiffs
```

### 4. Upload qiling
- Sketch > Upload (yoki Ctrl+U)
- BOOT tugmasini bosib turing (agar xato bo'lsa)

---

## Variant 3: esptool.py orqali (Advanced) 💻

### 1. esptool.py o'rnatish

```powershell
pip install esptool
```

### 2. .bin faylni topish

```powershell
$tempPath = "$env:LOCALAPPDATA\Temp\arduino\sketches"
Get-ChildItem -Path $tempPath -Recurse -Filter "esp32_face_servo.ino.bin" | Select-Object FullName -First 1
```

### 3. Upload qilish

```powershell
esptool.py --chip esp32 --port COM3 --baud 460800 write_flash -z 0x10000 "C:\Path\To\esp32_face_servo.ino.bin"
```

---

## Variant 4: Tayyor batch fayl ishlatish 📦

Men sizga tayyor batch fayl yaratib berdim. Faqat ESP32 ni ulab, `UPLOAD_ESP32.bat` ni ishga tushiring!

---

## Troubleshooting 🔧

### "Serial port not found"
- ESP32 ulangan bo'lishi kerak
- USB driver o'rnatilganligini tekshiring: [CP210x driver](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers)

### "Failed to connect to ESP32"
- BOOT tugmasini bosib turing
- Upload tugmasini bosing
- Upload boshlanganida BOOT ni qo'yib yuboring

### "Permission denied"
- Serial Monitor yopiq bo'lishi kerak
- Boshqa dasturlar (Putty, etc.) yopiq bo'lishi kerak

### "Sketch too big"
- Partition Scheme: **Default 4MB with spiffs** ni tanlang
- Yoki: **Minimal SPIFFS (1.9MB APP with OTA)**

---

## Agar hamma narsa ishlasa 🎉

Serial Monitor da (115200 baud) ko'rinadi:

```
ESP32_HUMANOID_SERVO_READY
INFO:Servos initialized: 7
INFO:Type 'HELP' for command list
```

Endi `HELP` yoki `STATUS` komandalarini yuboring!

---

## Qisqa yo'l: Avtomatik upload scripti

```powershell
# ESP32 portini avtomatik topish va upload qilish
$cliPath = "$env:USERPROFILE\arduino-cli\arduino-cli.exe"
$port = (& $cliPath board list | Select-String -Pattern "COM\d+").Matches.Value | Select-Object -First 1

if ($port) {
    Write-Host "ESP32 topildi: $port" -ForegroundColor Green
    cd "C:\Users\Windows_11\Desktop\humanoid ali\humanoid robot\esp32_face_servo"
    & $cliPath upload -p $port --fqbn esp32:esp32:esp32 .
} else {
    Write-Host "ESP32 topilmadi! USB ni tekshiring." -ForegroundColor Red
}
```

Muvaffaqiyatli upload! 🚀
