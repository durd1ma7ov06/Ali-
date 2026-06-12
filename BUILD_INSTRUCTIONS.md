# HumanoidRobotAI.exe Yaratish Ko'rsatmasi

## Talablar (build qiladigan kompyuterda)

- Python 3.12 o'rnatilgan bo'lsin
- Internet ulanishi bo'lsin
- Loyiha papkasida barcha fayllar mavjud bo'lsin

## Build qilish (1 qadam)

Loyiha papkasida terminal oching va:

```bash
python build_exe.py
```

Yoki venv bilan:

```bash
venv312\Scripts\python.exe build_exe.py
```

## Natija

```
dist/
  HumanoidRobotAI.exe   ← shu faylni boshqa kompyuterga ko'chiring
```

---

## Boshqa kompyuterda ishlatish

1. `HumanoidRobotAI.exe` faylini istalgan joyga ko'chiring
2. Ikki marta bosib ishga tushiring
3. **Birinchi marta** (avtomatik):
   - Python 3.12 yuklab o'rnatiladi (~25 MB)
   - Virtual environment yaratiladi
   - Barcha kutubxonalar o'rnatiladi (edge-tts, opencv, openai, PyAudio, pygame-ce, pyserial, SpeechRecognition)
   - API kalit so'raladi
4. **Keyingi marta**: to'g'ridan dastur ishga tushadi

## Dastur fayllari qayerda saqlanadi

```
%APPDATA%\HumanoidRobotAI\
  main.py
  robot_hardware.py
  ...
  .env          ← API kalit va sozlamalar shu yerda
  venv\         ← virtual environment
```

## .env sozlamalarini o'zgartirish

```
%APPDATA%\HumanoidRobotAI\.env
```
Shu faylni istalgan matn muharririda oching va o'zgartiring.

## Muammolar

### "Python o'rnatilmadi"
- Internet ulanishini tekshiring
- Administrator sifatida ishga tushiring

### "PyAudio o'rnatilmadi"
- Dastur ishlaydi, lekin mikrofon ishlamasligi mumkin
- `%APPDATA%\HumanoidRobotAI\venv\Scripts\pip.exe install PyAudio` qo'lda bajaring

### "API kalit topilmadi"
- `%APPDATA%\HumanoidRobotAI\.env` faylini oching
- `OPENROUTER_API_KEY=` qatoriga kalitni kiriting
