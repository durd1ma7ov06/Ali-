# Humanoid Robot Voice Assistant

Uzbek tilida gaplashuvchi ovozli yordamchi loyiha. Dastur mikrofon orqali gapni eshitadi, OpenRouter orqali modeldan javob oladi va `edge-tts` yordamida ovoz chiqaradi.

## Asosiy fayllar
- `main.py` - Windows uchun asosiy ishga tushirish fayli.
- `main_rpi.py` - Raspberry Pi yoki Linux muhiti uchun variant.

## Qaysi muhitda ishlatilgan
Loyiha lokalda turli muhitlarda sinab ko'rilgan, lekin hozirgi repodagi mavjud virtual environment quyidagiga mos:

- Python `3.12.10`
- Virtual environment nomi: `venv312`
- Windows muhitida ishlatilgan

Repo ichidagi `venv312/pyvenv.cfg` fayliga ko'ra loyiha aynan `Python 3.12` bilan yaratilgan. Shu sababli eng xavfsiz tavsiya:

- Windows uchun: `Python 3.12.x`
- Raspberry Pi / Linux uchun: imkon qadar `Python 3.12.x`

`PyAudio` kabi kutubxonalar sabab `Python 3.12` bu loyiha uchun eng mos variant hisoblanadi.

## Ishlash mantig'i
Loyiha quyidagi paketlarga tayanadi:

- `openai`
- `edge-tts`
- `opencv-contrib-python`
- `insightface` + `onnxruntime` (yuz tanish — ArcFace embeddinglar)
- `numpy`
- `SpeechRecognition`
- `PyAudio`
- `pygame-ce`
- `pyserial`

Qo'shimcha ravishda internet ulanishi (faqat birinchi marta InsightFace modelini yuklab olish uchun), mikrofon va audio chiqish qurilmasi kerak bo'ladi. Model bir marta yuklab olingach, yuz tanish offline ishlaydi.

## Tavsiya etilgan o'rnatish

### 1. Python versiyasini tayyorlash
Kompyuteringizda `Python 3.12.x` o'rnatilgan bo'lsin.

Tekshirish:

```bash
python --version
```

Agar tizimda bir nechta Python versiya bo'lsa, aynan `3.12` bilan virtual environment yaratgan ma'qul.

Windows misol:

```bash
py -3.12 -m venv .venv
```

Linux yoki Raspberry Pi misol:

```bash
python3.12 -m venv .venv
```

### 2. Virtual environment'ni yoqish
Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Windows CMD:

```bat
.venv\Scripts\activate.bat
```

Linux / Raspberry Pi:

```bash
source .venv/bin/activate
```

### 3. Kutubxonalarni o'rnatish
Avval `pip` ni yangilang:

```bash
python -m pip install --upgrade pip
```

So'ng dependency'larni o'rnating:

```bash
pip install -r requirements.txt
```

## Platformaga qarab muhim eslatmalar

### Windows
`main.py` Windows uchun moslangan. Kodda Windows encoding bilan bog'liq qo'shimcha sozlashlar bor, shuning uchun Windows'da odatda shu faylni ishlatish tavsiya qilinadi.

Ishga tushirish:

```bash
python main.py
```

Faqat kamera, yuz aniqlash va ESP32 servoni test qilish:

```bash
python face_servo_test.py
```

Faqat startup salomlashish harakatini test qilish:

```bash
python arm_servo_test.py
```

### Linux / Raspberry Pi
`main_rpi.py` Linux tomonini hisobga olgan. Kod ichida `SDL_AUDIODRIVER=alsa` kabi sozlamalar ishlatiladi.

Ishga tushirish:

```bash
python main_rpi.py
```

Raspberry Pi yoki Debian/Ubuntu asosidagi tizimlarda `PyAudio` va audio kutubxonalari uchun tizim paketlari kerak bo'lishi mumkin:

```bash
sudo apt update
sudo apt install portaudio19-dev python3-dev ffmpeg libsdl2-mixer-2.0-0
```

Agar `PyAudio` o'rnatishda xato chiqsa, odatda muammo Python paketida emas, tizimdagi `portaudio` kutubxonasida bo'ladi.

## .env sozlash
Repo ichida `.env.example` bor. Uni asos qilib `.env` yarating.

Namunaviy qiymatlar:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
GEMINI_TEXT_MODEL=google/gemini-2.5-flash
GEMINI_TEXT_FALLBACK_MODELS=deepseek/deepseek-chat-v3-0324,google/gemini-2.0-flash-001
EDGE_TTS_VOICE=uz-UZ-SardorNeural
EDGE_TTS_RATE=+15%
EDGE_TTS_PITCH=+50Hz
EDGE_TTS_VOLUME=+18%
STT_LANGUAGE=uz-UZ
LOCAL_TIMEZONE=Asia/Tashkent
GREETING_TEXT=Assalomu alaykum! Tanishsak bo'ladimi? Ismingiz nima?
MICROPHONE_NAME=camera,webcam,uvc,fhd,1080p,a4ech,a4tech
MICROPHONE_DEVICE_INDEX=
CAMERA_ENABLED=true
CAMERA_INDEX=0
CAMERA_PREVIEW=true
CAMERA_FRAME_WIDTH=640
CAMERA_FRAME_HEIGHT=480
CAMERA_FPS=30
ESP32_SERIAL_ENABLED=true
ESP32_PORT=
ESP32_BAUDRATE=115200
FACE_SERVO_ENABLED=true
FACE_SERVO_MIN_ANGLE=20
FACE_SERVO_CENTER_ANGLE=90
FACE_SERVO_MAX_ANGLE=160
FACE_SERVO_DEAD_ZONE=0.08
FACE_SERVO_SMOOTHING=0.45
FACE_SERVO_MAX_STEP=7
FACE_SERVO_SEND_MIN_DELTA=1
FACE_SERVO_SEND_INTERVAL=0.04
FACE_SERVO_INVERT=false
FACE_DETECT_WIDTH=320
FACE_DETECT_SCALE_FACTOR=1.08
FACE_DETECT_MIN_NEIGHBORS=4
FACE_DETECT_MIN_SIZE=55
ARM_REST_RIGHT_SHOULDER_OFFSET=0
ARM_REST_RIGHT_ELBOW_OFFSET=0
ARM_REST_RIGHT_WRIST_OFFSET=90
ARM_REST_LEFT_SHOULDER_OFFSET=0
ARM_REST_LEFT_ELBOW_OFFSET=0
ARM_REST_LEFT_WRIST_OFFSET=45
STARTUP_GREETING_MOTION_ENABLED=true
GREETING_RIGHT_SHOULDER_OFFSET=44
GREETING_RIGHT_ELBOW_OFFSET=56
GREETING_RIGHT_WRIST_OFFSET=0
GREETING_HEAD_NOD=8
GREETING_HEAD_DELAY=0.14
GREETING_ARM_STEPS=8
GREETING_ARM_RETURN_STEPS=14
GREETING_ARM_STEP_DELAY=0.05
GREETING_RIGHT_ELBOW_START_DELAY=0.18
GREETING_RIGHT_WRIST_START_DELAY=0.0
GREETING_RIGHT_ELBOW_RETURN_DELAY=0.18
GREETING_RETURN_ELBOW_TO_SHOULDER_GAP=0.25
GREETING_RIGHT_SHOULDER_RETURN_DELAY=0.35
GREETING_RIGHT_WRIST_RETURN_DELAY=0.0
ARM_COMMAND_STEPS=10
ARM_COMMAND_STEP_DELAY=0.045
ARM_COMMAND_RAISE_SHOULDER_OFFSET=85
ARM_COMMAND_RAISE_ELBOW_OFFSET=15
ARM_COMMAND_RAISE_WRIST_OFFSET=0
ARM_COMMAND_BEND_ELBOW_OFFSET=80
ARM_COMMAND_WAVE_COUNT=3
ARM_COMMAND_WAVE_WRIST_OFFSET=35
```

## Muhim sozlamalar izohi
- `OPENROUTER_API_KEY` - OpenRouter API kaliti.
- `GEMINI_TEXT_MODEL` - birinchi ishlatiladigan model nomi.
- `GEMINI_TEXT_FALLBACK_MODELS` - asosiy model ishlamasa sinab ko'riladigan qo'shimcha model nomlari.
- `EDGE_TTS_VOICE` - ovoz modeli.
- `EDGE_TTS_RATE` - gapirish tezligi.
- `EDGE_TTS_PITCH` - ovoz balandligi / tonalligi.
- `EDGE_TTS_VOLUME` - ovoz darajasi.
- `STT_LANGUAGE` - speech-to-text tili.
- `LOCAL_TIMEZONE` - bugungi sana va vaqt uchun ishlatiladigan lokal vaqt zonasi.
- `GREETING_TEXT` - dastur ishga tushganda aytiladigan kirish matni.
- `MICROPHONE_NAME` - tanlashda ustunlik beriladigan mikrofon nom bo'laklari. USB kamera mikrofoni uchun `camera`, `webcam`, `uvc`, `fhd`, `1080p` kabi so'zlar foydali.
- `MICROPHONE_DEVICE_INDEX` - kerak bo'lsa mikrofon ID sini majburan tanlash. Bo'sh qoldirilsa dastur avtomatik tanlaydi.
- `CAMERA_ENABLED` - kamera ishga tushsin yoki yo'q.
- `CAMERA_INDEX` - OpenCV kamerasi indeksi. Odatda `0`.
- `CAMERA_PREVIEW` - kamera oynasi ko'rinsin yoki kamera fon rejimida ochilsin.
- `CAMERA_FRAME_WIDTH`, `CAMERA_FRAME_HEIGHT`, `CAMERA_FPS` - kamera oqimi o'lchami va FPS.
- `ESP32_SERIAL_ENABLED` - ESP32 ga USB Serial orqali komanda yuborishni yoqadi.
- `ESP32_PORT` - ESP32 porti. Bo'sh bo'lsa dastur avtomatik topishga harakat qiladi. Windows misol: `COM3`.
- `ESP32_BAUDRATE` - ESP32 Serial tezligi. Sketch bilan bir xil bo'lishi kerak.
- `FACE_SERVO_ENABLED` - kamera yuzni ko'rsa servoni yuzga mos harakatlantirishni yoqadi.
- `FACE_SERVO_MIN_ANGLE`, `FACE_SERVO_CENTER_ANGLE`, `FACE_SERVO_MAX_ANGLE` - servo harakat chegaralari.
- `FACE_SERVO_DEAD_ZONE` - yuz markazga yaqin bo'lsa servo qimirlamaydigan zona.
- `FACE_SERVO_SMOOTHING` - servo harakatini yumshatish koeffitsiyenti.
- `FACE_SERVO_MAX_STEP` - bitta yangilanishda servo eng ko'p necha gradus siljishi.
- `FACE_SERVO_SEND_MIN_DELTA`, `FACE_SERVO_SEND_INTERVAL` - ESP32 ga komanda yuborish sezgirligi va oralig'i.
- `FACE_SERVO_INVERT` - servo teskari tomonga burilsa `true` qiling.
- `FACE_DETECT_WIDTH`, `FACE_DETECT_SCALE_FACTOR`, `FACE_DETECT_MIN_NEIGHBORS`, `FACE_DETECT_MIN_SIZE` - yuz aniqlash tezligi va sezgirligi.
- `ARM_REST_*_OFFSET` - dastur davomida qo'llar saqlaydigan asosiy resting offsetlar.
- `STARTUP_GREETING_MOTION_ENABLED` - dastur boshlanganda o'ng qo'lni ko'ksiga olib salomlashish harakatini yoqadi.
- `GREETING_RIGHT_SHOULDER_OFFSET`, `GREETING_RIGHT_ELBOW_OFFSET`, `GREETING_RIGHT_WRIST_OFFSET` - salomlashishdagi o'ng qo'l pozasi.
- `GREETING_HEAD_NOD`, `GREETING_HEAD_DELAY` - salomlashishda boshning kichik smooth harakati.
- `GREETING_ARM_STEPS`, `GREETING_ARM_RETURN_STEPS`, `GREETING_ARM_STEP_DELAY` - salomlashishda qo'lning smooth borib-qaytish tezligi.
- `GREETING_RIGHT_ELBOW_START_DELAY`, `GREETING_RIGHT_WRIST_START_DELAY` - salomlashishda o'ng tirsak/bilak harakati yelkadan qancha keyin boshlanishi.
- `GREETING_RIGHT_SHOULDER_RETURN_DELAY`, `GREETING_RIGHT_ELBOW_RETURN_DELAY`, `GREETING_RIGHT_WRIST_RETURN_DELAY` - salomlashish tugaganda yelka/tirsak/bilak qancha kechikib resting holatga qaytishi.
- `GREETING_RETURN_ELBOW_TO_SHOULDER_GAP` - qaytishda tirsak boshlanganidan keyin yelka qancha kechikib qaytishi.
- `ARM_COMMAND_*` - ovozli qo'l buyruqlari uchun smooth qadamlar va ko'tarish/bukish/silkitish offsetlari.

## ESP32 servo ulanishi
ESP32 uchun sketch: `esp32_face_servo/esp32_face_servo.ino`.

Ulanish:
- Bosh servo signal: ESP32 `GPIO 13`
- O'ng yelka: ESP32 `GPIO 12`
- O'ng tirsak: ESP32 `GPIO 14`
- O'ng bilak: ESP32 `GPIO 27`
- Chap yelka: ESP32 `GPIO 26`
- Chap tirsak: ESP32 `GPIO 25`
- Chap bilak: ESP32 `GPIO 33`
- Servolar `VCC`: tashqi `5V` quvvat manbai
- Servolar `GND`: tashqi quvvat `GND`
- ESP32 `GND`: tashqi quvvat `GND` bilan umumiy bo'lishi kerak

Kompyuter dasturi ESP32 ga USB orqali `HEAD:90`, `ARMS:...` va `HOME` formatida komandalar yuboradi.

Qo'l servolarida `0` holat ESP32 sketch ichidagi `SERVO_NEUTRAL` qiymatlari bilan belgilanadi. Hozir hammasi `90` ga teng. `ARMS` komandasi absolyut burchak emas, shu neutral holatdan offset yuboradi. Offsetlar `-180` dan `180` gacha qabul qilinadi: manfiy qiymat teskari tomonga aylantiradi. Servo yakuniy burchagi xavfsizlik uchun `0..180` oralig'ida cheklanadi. Chap qo'l servolari sketch ichidagi `SERVO_DIRECTION` orqali teskari qilingan, shuning uchun chap va o'ng qo'l bir xil anatomik harakat qiladi. Agar biror joint teskari yurib qolsa, `esp32_face_servo.ino` ichidagi o'sha servo uchun `SERVO_DIRECTION` qiymatini `1` yoki `-1` qilib almashtiring.

## Ehtimoliy muammolar

### 1. `OPENROUTER_API_KEY topilmadi`
`.env` fayli yaratilmagan yoki kalit noto'g'ri kiritilgan.

### 2. Mikrofon ishlamayapti
- Operatsion tizimda microphone permission yoqilganini tekshiring.
- To'g'ri input device ulanganini tekshiring.
- Bluetooth yoki USB mikrofon ishlatsa, dastur uni avtomatik tanlashga harakat qiladi.

### 3. `PyAudio` install bo'lmayapti
- Windows'da `Python 3.12` ishlatayotganingizni tekshiring.
- Linux'da `portaudio19-dev` o'rnatilganini tekshiring.

### 4. Ovoz chiqmayapti
- `pygame` audio driver va tizim audio qurilmalarini tekshiring.
- Linux'da ALSA/PulseAudio sozlamalarini tekshiring.

## Xavfsizlik
- Haqiqiy API kalitlarini hech qachon kod ichiga yozmang.
- `.env`, `deepseek`, `venv312`, `__pycache__` fayllari `.gitignore` orqali ignore qilinadi.
- Push qilishdan oldin `git status` bilan qaysi fayllar commit bo'layotganini tekshirib chiqing.

## Universitet bilim bazasi (RAG)

Robotning universitetga oid savollarga javob berishi lokal RAG tizimi orqali ishlaydi (`knowledge_crawler.py` → `knowledge_index.py` → `knowledge_qa.py`). Bu bazani yangilash, holatini tekshirish va sinov savollarini yuborish uchun maxsus maintenance CLI mavjud:

```powershell
.\venv312\Scripts\python.exe knowledge_maintenance.py --status
.\venv312\Scripts\python.exe knowledge_maintenance.py --update
.\venv312\Scripts\python.exe knowledge_maintenance.py --test-only
```

To'liq qo'llanma — buyruqlar, troubleshooting, `--reset` xavfsizligi, qachon yangilash kerak — alohida hujjatda: [`UNIVERSITY_KNOWLEDGE_MAINTENANCE.md`](./UNIVERSITY_KNOWLEDGE_MAINTENANCE.md).

## Yuz tanish (Face Recognition)

Robot kameradagi yuzni ArcFace embedding'lari yordamida taniydi. Tan olingan
odamga shaxsiy salom beradi (`Assalomu alaykum, {display_name}!`). Recognizer
quyidagi pipeline asosida ishlaydi:

```
Camera frame → SCRFD detector → 5-point alignment → ArcFace 512-d embedding →
SQLite cosine search → top1/top2 margin → vote window → greeting event
```

### 1. Birinchi marta sozlash

```bash
# venvni faollashtiring
.\venv312\Scripts\activate

# Kutubxonalarni o'rnating
pip install -r requirements.txt
```

InsightFace `buffalo_l` paketi birinchi ishga tushganda avtomatik yuklab
olinadi (~280MB). Keyingi ishga tushishlarda offline ishlaydi.

### 2. Ma'lumot bazasini tayyorlash

`face_data/people.csv` fayliga odamlar ro'yxatini yozing va har bir
odam uchun `face_data/photos/<person_id>/01.jpg` … `05.jpg` rasmlarini
joylashtiring. Buni grafik shaklda qilish uchun:

```bash
python face_dataset_builder.py
```

So'ng embedding bazasini yarating:

```bash
python build_face_db.py --rebuild --self-test
```

Skript shu hisobotni chiqaradi:

- nechta odam yuklandi
- nechta rasm tahlil qilindi
- nechta embedding yaratildi
- skip qilingan rasmlar va sabablari (no_face, low_det_score, ambiguous_multiple_faces, va h.k.)
- 3 dan kam rasmga ega odamlar uchun ogohlantirish
- self-test natijalari (har bir rasm o'z `person_id`siga mos kelishi kerak)

Faqat bitta odam uchun qayta build qilish:

```bash
python build_face_db.py --person-id ali_valiyev --rebuild
```

### 3. Tavsiya etilgan rasm to'plash

Yaxshi sifat uchun har bir odamga **kamida 5 ta rasm**:

- frontal yuz (markazga qaragan)
- biroz chapga qaragan
- biroz o'ngga qaragan
- turli yorug'lik sharoitlarida
- iloji bo'lsa robotning **o'z kamerasidan** olingan (passport rasmi
  bilan emas — yorug'lik va lens xususiyatlari boshqacha)

Yuz `FACE_MIN_FACE_PIXELS=50` (ya'ni qisqa tomon kamida 50 piksel) va
`FACE_MIN_DET_SCORE=0.65` ga javob bersin. Ko'zoynak/yopilmagan yuz tavsiya etiladi.

### 4. Threshold sozlash (real-world calibration)

Hammasi `.env` orqali sozlanadi. Konservativ qiymatlar standart:

| Variable | Default | Qachon o'zgartiriladi |
|----------|---------|----------------------|
| `FACE_MIN_SIMILARITY` | `0.45` | Tanish odamlar rad etilsa → **pasaytiring** (0.40 → 0.35). Notanish odamlar tanildi deb hisoblansa → **ko'taring** (0.50 → 0.55). |
| `FACE_MIN_MARGIN` | `0.08` | Bir-biriga o'xshash odamlar bo'lsa, marginni **ko'taring** (0.10 → 0.15). |
| `FACE_MIN_DET_SCORE` | `0.65` | Yuz topilsa-da, detektor ishonchsiz bo'lsa → 0.55 ga pasaytiring. |
| `FACE_RECOGNITION_VOTE_WINDOW` | `5` | Sezgirlikni oshirish uchun 7 ga ko'taring. |
| `FACE_RECOGNITION_VOTE_MIN_MATCHES` | `3` | Ko'proq frame'larda bir xil odam chiqishini talab qilsa → 4 yoki 5. |
| `FACE_SESSION_RESET_SECONDS` | `2.0` | Bir odamni ikki marta salomlashishidan saqlash uchun. |
| `FACE_GREETING_COOLDOWN_SECONDS` | `60` | Bir odamni qayta-qayta salomlashishidan saqlaydi. |
| `FACE_RECOGNITION_DEBUG` | `false` | `true` qilinsa har frame'da top1/top2/margin loglanadi. |

Asosiy qoida: **agar shubha bo'lsa — jim turish noto'g'ri salomlashishdan yaxshi**.

### 5. Yuz tanishni o'chirish

```env
FACE_RECOGNITION_ENABLED=false
```

### 6. Foydali loglar

Log namunalari:

```
[FACE-DB] InsightFace loaded model=buffalo_l det_size=640 ...
[FACE-DB] Ready. recognizer=insightface people=10 embeddings=30 dim=512
[FACE-REC] candidate top1=ali_valiyev sim=0.74 top2=bobur sim2=0.32 margin=0.42
[FACE-GREET] queued greeting for ali_valiyev votes=3/5
[FACE-REC] session reset (no face for 2.0s), was confirmed=ali_valiyev
```

Notanish yoki shubhali frame:

```
[FACE-REC] rejected reason=low_similarity:0.31<0.45
[FACE-REC] unstable votes={'ali': 2, 'bobur': 1} need 3/5
```

### 7. SQLite bazasi

Embedding'lar `face_data/faces.sqlite` ichida saqlanadi (`people`,
`face_embeddings`, `meta` jadvallari). Bazani o'chirib, qayta build qilish
xavfsiz: `--rebuild` flag o'rniga shunchaki faylni o'chiring:

```powershell
Remove-Item face_data\faces.sqlite
python build_face_db.py
```

### 8. Fallback rejim

Agar InsightFace yoki onnxruntime mavjud bo'lmasa, dastur avtomatik
LBPH/histogram fallback'ga o'tadi (eski API bilan to'liq mos). Bu rejim
to'liq xususiyatli emas, lekin robot to'xtab qolmaydi.
