# 🛠️ Ali Robot - O'rnatish qo'llanmasi

## Tizim talablari

| Komponent | Minimal | Tavsiya |
|-----------|---------|---------|
| Python | 3.10 | 3.12 |
| RAM | 4 GB | 8 GB+ |
| OS | Windows 10 / RPi OS | Windows 11 / RPi OS 64-bit |
| Mikrofon | Har qanday USB | A4Tech/Logitech |
| Kamera | 720p | 1080p USB |
| ESP32 | DevKit v1 | DevKit v1 |

## Tezkor o'rnatish

### 1. Klonlash
```bash
git clone https://github.com/durd1ma7ov06/Ali-.git
cd Ali-
```

### 2. Virtual muhit
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/RPi:
source venv/bin/activate
```

### 3. Kutubxonalar
```bash
pip install -r requirements.txt
```

### 4. Konfiguratsiya
```bash
cp .env.example .env
# .env faylni o'z sozlamalaringiz bilan to'ldiring
```

### 5. AI kaliti
[OpenRouter](https://openrouter.ai/) saytida ro'yxatdan o'ting va API kalit oling:
```env
AI_API_KEY=your_key_here
AI_MODEL=google/gemini-2.5-flash
```

### 6. Ishga tushirish
```bash
# Windows
python main.py

# Raspberry Pi
python main_rpi.py
```

## ESP32 firmware yuklash

1. Arduino IDE o'rnating
2. ESP32 board manager qo'shing
3. `esp32_face_servo/esp32_face_servo.ino` oching
4. Board: "ESP32 Dev Module" tanlang
5. Upload bosing

Batafsil: [ESP32 Upload Guide](../ESP32_UPLOAD_GUIDE.md)

## Face Recognition sozlash

1. `face_data/photos/ism_familiya/` papka yarating
2. 3-8 ta rasm joylashtiring (turli burchaklardan)
3. `python build_face_db.py` ishga tushiring

## Muammo hal qilish

| Muammo | Yechim |
|--------|--------|
| Mikrofon topilmadi | `MICROPHONE_DEVICE_INDEX` ni tekshiring |
| ESP32 ulanmadi | `ESP32_PORT` ni to'g'ri COM portga o'zgartiring |
| AI javob bermaydi | `AI_API_KEY` tekshiring, internet borligini bilishing |
| Yuz tanilmadi | `build_face_db.py` qayta ishga tushiring |
