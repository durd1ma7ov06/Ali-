# ESP32 Humanoid Robot Servo Controller

Mukammal servo controller ESP32 uchun. 7 ta servo boshqaradi (bosh va ikki qo'l).

## Xususiyatlar ✨

- **7 ta servo boshqaruvi**: Bosh, ikki qo'l (yelka, tirsak, bilak)
- **Yumshoq harakat**: Smooth movement avtomatik
- **Serial protokol**: Oddiy komandalar orqali boshqarish
- **Xavfsizlik**: Angle limits, error handling
- **Kalibrlash**: Har bir servo uchun
- **Status monitoring**: Real-time holat ko'rish

## Hardware Ulanishi 🔌

### Servo Pinlar

| Servo | GPIO Pin | Tavsif |
|-------|----------|--------|
| Bosh | 13 | Head servo |
| O'ng yelka | 12 | Right shoulder |
| O'ng tirsak | 14 | Right elbow |
| O'ng bilak | 27 | Right wrist |
| Chap yelka | 26 | Left shoulder |
| Chap tirsak | 25 | Left elbow |
| Chap bilak | 33 | Left wrist |

### Quvvat Ta'minoti ⚡

**MUHIM**: Servolarga alohida 5V power supply ulang!
- ESP32 USB power servolarga yetmaydi
- External 5V adapter (3A yoki ko'proq) kerak
- Ground (GND) umumiy bo'lishi kerak

## Upload Qilish 📤

### Arduino IDE

1. **Board tanlash**:
   - Tools > Board > ESP32 Arduino > **ESP32 Dev Module**
   - Port: Kompyuteringizga ulangan COM port

2. **Settings**:
   - Upload Speed: 115200
   - Flash Frequency: 80MHz
   - Flash Mode: QIO

3. **Upload**:
   - Sketch > Upload yoki Ctrl+U

### Arduino CLI

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 esp32_face_servo
arduino-cli upload -p COM3 --fqbn esp32:esp32:esp32 esp32_face_servo
```

## Komandalar 📋

### Asosiy Komandalar

#### 1. Boshni burish
```
HEAD:90
```
Boshni 90° ga buradi (0-180 oralig'ida).

#### 2. Qo'llarni boshqarish
```
ARMS:0,30,-15,0,30,-15
```
Format: `ARMS:<r_sh>,<r_el>,<r_wr>,<l_sh>,<l_el>,<l_wr>`
- Offset qiymatlar: -180 dan 180 gacha
- 0 = neutral pozitsiya

#### 3. Home pozitsiyaga qaytish
```
HOME
```
Barcha servolarni 90° ga qaytaradi.

#### 4. Status ko'rish
```
STATUS
```
Hozirgi va target burchaklarni ko'rsatadi.

### Qo'shimcha Komandalar

#### 5. Bitta servoni boshqarish
```
SET:0:45
```
Format: `SET:<servo_id>:<angle>`
- servo_id: 0-6 (0=bosh, 1-3=o'ng qo'l, 4-6=chap qo'l)

#### 6. Smooth movement o'chirish/yoqish
```
SMOOTH:ON
SMOOTH:OFF
```

#### 7. Kalibrlash
```
CALIBRATE:0:95
```
Servo neutral pozitsiyasini sozlaydi.

#### 8. Yordam
```
HELP
```
Barcha komandalar ro'yxatini ko'rsatadi.

## Javoblar 📡

### Muvaffaqiyatli
```
OK:HEAD:90
OK:ARMS
OK:HOME
```

### Xatolik
```
ERROR:Invalid angle
ERROR:Unknown command
```

### Info
```
STATUS:BEGIN
SERVO:0:HEAD:90:90
SERVO:1:R_SHOULDER:90:90
...
STATUS:END
```

## Test Qilish 🧪

### 1. Serial Monitor Ochish

Arduino IDE: Tools > Serial Monitor
- Baud rate: **115200**
- Line ending: **Newline**

### 2. Tayyor Signal

Upload bo'lgandan keyin ko'rinadi:
```
ESP32_HUMANOID_SERVO_READY
INFO:Servos initialized: 7
INFO:Type 'HELP' for command list
```

### 3. Test Komandalar

```
HELP          # Barcha komandalar
STATUS        # Hozirgi holat
HOME          # Neutral pozitsiya
HEAD:45       # Boshni 45° ga
HEAD:135      # Boshni 135° ga
ARMS:30,0,0,30,0,0  # Ikki yelkani ko'tarish
HOME          # Qaytish
```

## Python Integration 🐍

`main.py` da ESP32 bilan avtomatik ulanadi:

```python
# Boshni burish
esp32.move_head_servo(90)

# Qo'l gestures
esp32.wave_hand()
esp32.point()
esp32.gesture_welcome()

# Home
esp32.home()
```

## Troubleshooting 🔧

### Upload xatosi

**"This chip is ESP32 not ESP32-S2"**
- Board: ESP32 Dev Module tanlang (S2/S3/C3 emas)

**"Serial port busy"**
- Serial Monitor yoping
- Boshqa dasturlarni yoping (Putty, etc.)

**"Failed to connect"**
- BOOT tugmasini bosib turing
- Upload boshlanganda qo'yib yuboring

### Servo ishlamaydi

**Servo qimirlamaydi**
- Power supply tekshiring (5V, 3A)
- Ground umumiyligini tekshiring
- Pin ulanishlarini tekshiring

**Servo titrashyapti**
- Power yetarli emas
- Capacitor qo'shing (1000µF, 5V)

**Bir servo ishlaydi, boshqalari yo'q**
- Har bir servo ulanishini alohida tekshiring
- Servo buzilgan bo'lishi mumkin

### Serial aloqa

**"No response from ESP32"**
- Baud rate: 115200 ekanligini tekshiring
- USB cable buzilgan bo'lishi mumkin
- Port to'g'ri tanlanganligini tekshiring

**Komandalar ishlamayapti**
- Line ending: Newline yoki Both NL & CR
- Komandalar UPPERCASE bo'lishi shart emas

## Konfiguratsiya ⚙️

### Servo Parametrlar

```cpp
const int SERVO_MIN_US = 500;      // Pulse min
const int SERVO_MAX_US = 2400;     // Pulse max
const int SERVO_PWM_FREQ = 50;     // 50 Hz
```

### Smooth Movement

```cpp
const int SMOOTH_DELAY_MS = 15;    // Delay (ms)
const int SMOOTH_STEP = 2;         // Step (degrees)
```

### Angle Limits

```cpp
const int SERVO_MIN_ANGLE[7] = {0, 0, 0, 0, 0, 0, 0};
const int SERVO_MAX_ANGLE[7] = {180, 180, 180, 180, 180, 180, 180};
```

## Yangilanishlar 🆕

### Version 2.0 (2026-06-02)

- ✅ Smooth movement qo'shildi
- ✅ STATUS komandasi
- ✅ HELP komandasi
- ✅ Error handling yaxshilandi
- ✅ Kalibrlash funksiyasi
- ✅ Direct servo control (SET)
- ✅ Batafsil dokumentatsiya

### Version 1.0

- Asosiy servo boshqaruv
- HEAD va ARMS komandalar
- HOME funksiyasi

## Muallif 👨‍💻

**Humanoid ALI Team**
- Project: Humanoid Robot Ali
- University: Urganch State University
- Date: June 2026

## Litsenziya 📄

MIT License - Erkin foydalaning!

---

**Savol yoki muammo bo'lsa, murojaat qiling!** 🤖✨
