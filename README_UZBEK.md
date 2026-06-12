# 👑 SOHIBQIRON AMIR TEMUR - HUMANOID ROBOT

**Sohibqiron Amir Temur qiyofasidagi interaktiv humanoid robot**

---

## 🎯 ROBOT HAQIDA

**Sohibqiron Amir Temur** - bu o'zbek tilida gaplashuvchi, yuz tanib salomlashadigan va jismoniy harakatlar qiladigan humanoid robot. U buyuk bobomiz shaxsi, uning hayoti, harbiy yurishlari va Temuriylar davri tarixi haqida savollarga javob beradi.

> [!IMPORTANT]
> Robot faqat va faqat **"Sohibqiron Amir Temur"** (yoki uning variantlari: *Sohipqiron*, *Amir Temur*, va hokazo) kalit so'zi bilan boshlangan gaplarga javob beradi. Agar kalit so'z ishlatilmasa, robot javob bermaydi (ignore qiladi).

### Asosiy Imkoniyatlar:
- ✅ **Ovozli Suhbat** - Buyuk sarkarda shaxsiyatida o'zbek tilida muloqot qiladi
- ✅ **Wake-Word Himoyasi** - Faqat o'z nomiga murojaat qilingandagina javob beradi
- ✅ **Yuz Tanish** - Mehmonlarni yuzidan tanib, shaxsan salomlashadi
- ✅ **Jismoniy Harakatlar** - 7 servo motor yordamida bosh va qo'llarni boshqarish
- ✅ **Tarixiy Bilimlar** - Amir Temur hayoti va Temuriylar davlatiga oid aniq tarixiy ma'lumotlar
- ✅ **Vaqt/Sana** - Lokal vaqt zonasi (Asia/Tashkent)

---

## 🚀 TEZKOR ISHGA TUSHIRISH

### 1️⃣ Birinchi Marta (Kutubxonalarni o'rnatish):
```powershell
cd "c:\Users\Windows_11\Desktop\Proektla\Humanoid-ALI--master"
.\INSTALL_DEPENDENCIES.bat
```
⏱ 5-10 daqiqa kutib turing

### 2️⃣ Hardware Test (Tavsiya etiladi):
```powershell
python TEST_HARDWARE.py
```

### 3️⃣ Robotni Ishga Tushirish:
```powershell
# Kompyuter/Server uchun:
python main.py

# Raspberry Pi uchun:
python main_rpi.py
```

### 4️⃣ To'xtatish:
```
Ctrl+C
```

---

## 📁 MUHIM FAYLLAR

### Ishga Tushirish Skriptlari:
- `START_ROBOT.ps1` - PowerShell ishga tushirish (tavsiya)
- `START_ROBOT.bat` - CMD ishga tushirish
- `INSTALL_DEPENDENCIES.bat` - Kutubxonalarni o'rnatish
- `TEST_HARDWARE.py` - Hardware test

### Asosiy Kod:
- `main.py` - Asosiy kompyuter dasturi
- `main_rpi.py` - Raspberry Pi uchun asosiy dastur
- `ai_client.py` - AI provider client (Gemini/Deepseek)
- `robot_hardware.py` - Hardware boshqaruv
- `movement_commands.py` - Harakat parseri
- `knowledge_qa.py` - Tarixiy QA tizimi

---

## 🎤 BUYRUQLAR VA MULOKOT QOIDALARI

### Wake Word (Kalit So'z) Qoidasi:
Har bir gapning boshida quyidagi so'zlardan biri bo'lishi shart:
* `"Sohibqiron Amir Temur..."`
* `"Amir Temur..."`
* `"Sohibqiron..."`

*Misol:*
* ❌ `"Bugun havo qanday?"` -> *Robot e'tibor bermaydi (javob bermaydi).*
*  `"Sohibqiron Amir Temur, salom!"` -> *Robot salomlashadi.*
*  `"Amir Temur, chap qo'lingni ko'tar."` -> *Robot o'ng yoki chap qo'lini ko'taradi.*
*  `"Sohibqiron, siz qachon tug'ilgansiz?"` -> *Robot tarixiy ma'lumot beradi.*

### Universitet Savollari Intercepti:
Robot universitet haqidagi savollarga javob bermaydi. Agar shunday savol berilsa, u darhol quyidagicha rad etadi:
> "Men universitet yordamchisi emasman. Men buyuk Sohibqiron Amir Temurman! Faqat o'z tarixim, hayotim va saltanatim haqidagi savollarga javob beraman."

---

## 🎭 SOHIBQIRON AMIR TEMUR SHAXSIYATI

```
Ism: Sohibqiron Amir Temur
Unvon: Buyuk sarkarda, saltanat asoschisi
Til: O'zbek (Latin)
Ohang: Mag'rur, dono, tarixiy va salobatli
Xarakter: Donishmand, qat'iyatli, hurmatli
Mavzular: Faqat shaxsiy hayoti, g'azotlari, Temuriylar saltanati va tarixiy faktlar
```

---

## 🎉 TAYYOR!

**Sohibqiron Amir Temur** sizni kutmoqda! 👑✨

```
Muloqot boshlash:
"Sohibqiron Amir Temur, salom!"
"Amir Temur, tarixingiz haqida so'zlab bering."
"Sohibqiron, o'ng qo'lingizni ko'taring."
```
