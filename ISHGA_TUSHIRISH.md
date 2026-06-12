# 🚀 ALI ROBOT - TO'LIQ ISHGA TUSHIRISH QO'LLANMASI

## 📋 BOSQICHMA-BOSQICH YO'RIQNOMA

---

## ✅ **1-BOSQICH: HARDWARE ULANISHLAR**

### Kerakli Qurilmalar:
- ✓ **ESP32** (USB orqali kompyuterga)
- ✓ **7 ta Servo Motor** (ESP32 ga ulangan)
- ✓ **USB Kamera** (mikrofon bilan)
- ✓ **Kolonka/Speaker** (audio chiqish)
- ✓ **5V Quvvat Manbai** (servolar uchun)

### Ulanish Sxemasi:
```
ESP32 Pinlar:
├─ GPIO 13 → Bosh servo
├─ GPIO 12 → O'ng yelka
├─ GPIO 14 → O'ng tirsak
├─ GPIO 27 → O'ng bilak
├─ GPIO 26 → Chap yelka
├─ GPIO 25 → Chap tirsak
└─ GPIO 33 → Chap bilak

Quvvat:
├─ Servolar VCC → 5V quvvat manbai
├─ Servolar GND → Quvvat GND
└─ ESP32 GND → Quvvat GND (umumiy)
```

### Tekshirish:
1. ESP32 ni USB orqali ulang
2. Kamerani USB ga ulang
3. Kolonkani audio chiqishga ulang
4. Servolarni 5V quvvatga ulang

**Hozirgi Holatda:**
- ✅ ESP32: **COM12** (CH340)
- ✅ Kamera: **A4ech FHD 1080P PC Camera**
- ✅ Yuz bazasi: **12 odam, 30 embedding**

---

## ✅ **2-BOSQICH: ESP32 GA SKETCH YUKLASH**

### Arduino IDE orqali:

1. **Arduino IDE ni o'rnating**
   - https://www.arduino.cc/en/software

2. **ESP32 Board Support qo'shing**
   - File → Preferences
   - Additional Board Manager URLs:
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Tools → Board → Boards Manager → "esp32" ni o'rnating

3. **Sozlamalar**
   - Tools → Board → **ESP32 Dev Module**
   - Tools → Port → **COM12**
   - Tools → Upload Speed → **115200**

4. **Sketch ni yuklang**
   - File → Open → `esp32_face_servo/esp32_face_servo.ino`
   - Upload tugmasini bosing (→)
   - Kutib turing: "Hard resetting via RTS pin..."

5. **Test qiling**
   - Tools → Serial Monitor
   - Baud rate: **115200**
   - Ko'rishingiz kerak: `ESP32_HUMANOID_SERVO_READY`

### Test Komandalar:
```
HEAD:90              → Boshni markazga
ARMS:0,0,0,0,0,0     → Barcha qo'llar neytral
ARMS:55,0,0,55,0,0   → Ikkala yelka ko'tariladi
HOME                 → Hammasi neytral
```

---

## ✅ **3-BOSQICH: PYTHON KUTUBXONALARINI O'RNATISH**

### Avtomatik O'rnatish (Tavsiya etiladi):

**Windows CMD yoki PowerShell da:**
```cmd
INSTALL_DEPENDENCIES.bat
```

Yoki qo'lda:
```cmd
venv312\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### O'rnatilishi Kerak Bo'lgan Kutubxonalar:
- ✓ edge-tts (Ovoz sintezi)
- ✓ SpeechRecognition (Ovozni tanish)
- ✓ PyAudio (Mikrofon)
- ✓ pygame-ce (Audio playback)
- ✓ opencv-contrib-python (Kamera va yuz aniqlash)
- ✓ insightface + onnxruntime (Yuz tanish)
- ✓ openai (AI client)
- ✓ pyserial (ESP32 aloqa)
- ✓ sentence-transformers (Universitet bilim bazasi)

**Eslatma:** O'rnatish 5-10 daqiqa davom etishi mumkin.

---

## ✅ **4-BOSQICH: SOZLAMALARNI TEKSHIRISH**

### .env Fayli:

Muhim sozlamalar:
```env
# AI Provider (Google AI Studio)
AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
AI_API_KEY=AIza...  ← Sizning API kalitingiz
AI_MODEL=gemini-3.1-flash-lite

# ESP32 Serial
ESP32_SERIAL_ENABLED=true
ESP32_PORT=COM12  ← Avtomatik yangilandi
ESP32_BAUDRATE=115200

# Kamera
CAMERA_ENABLED=true
CAMERA_INDEX=0

# Yuz Tanish
FACE_RECOGNITION_ENABLED=true
FACE_MIN_SIMILARITY=0.45

# Universitet Bilim Bazasi
UNIVERSITY_KNOWLEDGE_ENABLED=true
```

### Hardware Test:
```cmd
python TEST_HARDWARE.py
```

Barcha ✓ bo'lishi kerak!

---

## ✅ **5-BOSQICH: ROBOTNI ISHGA TUSHIRISH**

### Avtomatik Ishga Tushirish:

**PowerShell (Tavsiya etiladi):**
```powershell
.\START_ROBOT.ps1
```

**CMD:**
```cmd
START_ROBOT.bat
```

### Qo'lda Ishga Tushirish:
```cmd
venv312\Scripts\activate
python main.py
```

---

## 🎯 **ISHGA TUSHGANDAN KEYIN**

### Robot Nima Qiladi:

1. **Salomlashish**
   - O'ng qo'lni ko'ksiga olib salomlashadi
   - "Assalomu alaykum, ishlaringiz qalay?" deydi

2. **Yuz Tanish**
   - Kamerada yuz ko'rsa, tanishga harakat qiladi
   - Tanilgan odamga: "Assalomu alaykum, {ism}!"

3. **Ovozli Suhbat**
   - Mikrofondan tinglaydi
   - Savolga javob beradi
   - Harakat qiladi

### Buyruqlar:

**Harakat Buyruqlari:**
```
"qo'l ko'tar"           → Qo'lni ko'taradi
"o'ng qo'l ko'tar"      → O'ng qo'lni ko'taradi
"tirsak buk"            → Tirsagini bukadi
"ko'krakka qo'y"        → Qo'lni ko'krakka qo'yadi
"salom ber"             → Qo'l silkitadi
"boshni chapga bur"     → Boshni chapga buradi
```

**Universitet Savollari:**
```
"Universitet qayerda joylashgan?"
"Qabul haqida ma'lumot bering"
"Fakultetlar haqida aytib bering"
"Rektor kim?"
```

**Umumiy Suhbat:**
```
"Salom"
"Bugun qaysi kun?"
"Soat nechi?"
"Yordam kerak"
```

**To'xtatish:**
```
"stop"
"toxtat"
"to'xtat"
"bas"
```

---

## 🔧 **MUAMMOLARNI HAL QILISH**

### 1. ESP32 topilmadi
```
✗ Sabab: USB ulanmagan yoki driver yo'q
✓ Yechim: 
  - USB kabelni qayta ulang
  - CH340 driver o'rnating
  - Device Manager da tekshiring
```

### 2. Mikrofon ishlamayapti
```
✗ Sabab: Permission yoki driver muammosi
✓ Yechim:
  - Windows Settings → Privacy → Microphone → On
  - Mikrofon ulanganini tekshiring
  - TEST_HARDWARE.py ni ishga tushiring
```

### 3. Kamera ochilmadi
```
✗ Sabab: Boshqa dastur ishlatmoqda
✓ Yechim:
  - Zoom, Skype, Teams ni yoping
  - Kamerani qayta ulang
  - CAMERA_INDEX=1 qilib ko'ring (.env da)
```

### 4. AI javob bermayapti
```
✗ Sabab: API key noto'g'ri yoki internet yo'q
✓ Yechim:
  - .env da AI_API_KEY ni tekshiring
  - Internet ulanishini tekshiring
  - python ai_client.py (test)
```

### 5. Servolar harakatlanmayapti
```
✗ Sabab: ESP32 sketch yuklanmagan
✓ Yechim:
  - Arduino IDE da sketch yuklang
  - Serial Monitor da test qiling
  - Quvvat manbai ulanganini tekshiring
```

### 6. Yuz tanish ishlamayapti
```
✗ Sabab: Baza bo'sh yoki model yuklanmagan
✓ Yechim:
  - python build_face_db.py --rebuild
  - Birinchi ishga tushganda InsightFace yuklanadi (~280MB)
  - Internet kerak (faqat birinchi marta)
```

---

## 📊 **TERMINAL BUYRUQLARI XULASASI**

### To'liq Ishga Tushirish Ketma-ketligi:

```powershell
# 1. Loyiha papkasiga o'ting
cd "c:\Users\Windows_11\Desktop\humanoid ali\humanoid robot"

# 2. Kutubxonalarni o'rnating (faqat birinchi marta)
.\INSTALL_DEPENDENCIES.bat

# 3. Hardware test
python TEST_HARDWARE.py

# 4. Robotni ishga tushiring
.\START_ROBOT.ps1
```

### Yoki Qisqa Variant:
```powershell
cd "c:\Users\Windows_11\Desktop\humanoid ali\humanoid robot"
.\START_ROBOT.ps1
```

---

## 🎉 **TAYYOR!**

Agar barcha bosqichlar muvaffaqiyatli bo'lsa:

```
========================================
   ROBOT TAYYOR! Ctrl+C bilan to'xtating
========================================

[READY] Suhbatga tayyor. Ctrl+C bilan chiqasiz.
[TTS] Ovoz: uz-UZ-SardorNeural
[INPUT] Gapiring...
```

**Ali** endi sizni tinglaydi va javob beradi! 🤖✨

---

## 📞 **YORDAM**

Agar muammo bo'lsa:
1. TEST_HARDWARE.py ni ishga tushiring
2. Xato xabarlarini o'qing
3. Yuqoridagi "Muammolarni Hal Qilish" bo'limiga qarang
4. .env faylini tekshiring
5. ESP32 Serial Monitor da test qiling

**Omad!** 🚀
