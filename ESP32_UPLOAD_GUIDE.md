# ESP32 Sketch Yuklash Qo'llanmasi

## 1. Arduino IDE ni o'rnating
- https://www.arduino.cc/en/software dan yuklab oling
- Yoki Arduino CLI ishlatishingiz mumkin

## 2. ESP32 Board Support qo'shing
Arduino IDE da:
- File → Preferences
- Additional Board Manager URLs ga qo'shing:
  ```
  https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
  ```
- Tools → Board → Boards Manager
- "esp32" ni qidiring va o'rnating

## 3. Board va Port tanlang
- Tools → Board → ESP32 Arduino → **ESP32 Dev Module**
- Tools → Port → **COM12** (sizning portingiz)
- Tools → Upload Speed → **115200**

## 4. Sketch ni oching va yuklang
- File → Open → `esp32_face_servo/esp32_face_servo.ino`
- Upload tugmasini bosing (→)
- Kutib turing: "Hard resetting via RTS pin..."

## 5. Serial Monitor orqali test qiling
- Tools → Serial Monitor
- Baud rate: **115200**
- Ko'rishingiz kerak: `ESP32_HUMANOID_SERVO_READY`

## Test komandalar:
```
HEAD:90        → Boshni markazga
ARMS:0,0,0,0,0,0 → Barcha qo'llar neytral
HOME           → Hammasi neytral
```

## Muammolar:
- **"Chip is ESP32-S2 not ESP32"** → Board ni "ESP32 Dev Module" ga o'zgartiring
- **Port topilmadi** → USB kabelni qayta ulang
- **Permission denied** → Arduino IDE ni admin sifatida ishga tushiring
