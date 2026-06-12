# 🤖 Humanoid Robot Mini - API Boshqaruv Qo'llanmasi

Ushbu hujjat tashqi dasturlar (Raspberry Pi, PC va h.k.) orqali robotni USB Serial port orqali qanday boshqarishni tushuntiradi.

---

## 1. Ulanish Sozlamalari (Serial Port)

Robot bilan aloqa o'rnatish uchun quyidagi parametrlardan foydalaning:
- **Baud Rate:** `115200`
- **Data Bits:** `8`
- **Parity:** `None`
- **Stop Bits:** `1`
- **Flow Control:** `None`

---

## 2. Ma'lumot Uzatish Formati

Robot bitta qatordan iborat, vergul bilan ajratilgan ASCII paketlarini qabul qiladi. Har bir paket `<` belgisi bilan boshlanishi va `>` belgisi bilan tugashi shart.

**Paket strukturasi:**
` <b,oy,ot,ob,cy,ct,cb> `

| Tartib | Kod | Tavsif | Diapazon |
|:---:|:---:|:---|:---:|
| 1 | `b` | Bosh (Head) | 0 - 180° |
| 2 | `oy` | O'ng Yelka (Right Shoulder) | 0 - 180° |
| 3 | `ot` | O'ng Tirsak (Right Elbow) | 0 - 180° |
| 4 | `ob` | O'ng Bilak (Right Wrist) | 0 - 180° |
| 5 | `cy` | Chap Yelka (Left Shoulder) | 0 - 180° |
| 6 | `ct` | Chap Tirsak (Left Elbow) | 0 - 180° |
| 7 | `cb` | Chap Bilak (Left Wrist) | 0 - 180° |

**Misol (Neytral holat):**
` <90,90,90,90,90,90,90> `

---

## 3. Muhim Xavfsizlik Cheklovlari (Hard-coded)

Robot dasturiy ta'minotida apparatni himoya qilish uchun quyidagi cheklovlar o'rnatilgan:

### 🛡️ To'qnashuvdan Himoya (Collision Avoidance)
Yelka harakati ma'lum diapazonga kirganda, tirsak avtomatik ravishda qulflanadi:
- **Xavfli Hudud:** Yelka (oy/cy) burchagi **30° va 150°** oralig'ida bo'lsa.
- **Natija:** Tirsak (ot/ct) yuborilgan qiymatdan qat'i nazar **90°** holatida ushlab turiladi.
- **Maqsad:** Qo'lning robot tanasiga (gavdasiga) urilib ketishi yoki servolarning qisilib qolishini oldini olish.

### ⏱️ Watchdog Timer (Xavfsizlik To'xtashi)
- **Timeout:** 200 ms.
- **Tavsif:** Agar 200 millisekund ichida yangi paket kelmasa, robot xavfsizlik holatiga o'tadi va barcha motorlarni to'xtatadi.
- **Tavsiya:** Dasturingizdan har **50-100 ms** oralig'ida kamida bitta paket yuborib turish tavsiya etiladi.

---

## 4. Dasturlash misoli (Python)

```python
import serial
import time

# Portni ochish
ser = serial.Serial('COM11', 115200) # Linuxda '/dev/ttyUSB0'

def move_robot(b, oy, ot, ob, cy, ct, cb):
    packet = f"<{b},{oy},{ot},{ob},{cy},{ct},{cb}>"
    ser.write(packet.encode())

try:
    while True:
        # Robotni neytral holatga keltirish
        move_robot(90, 90, 90, 90, 90, 90, 90)
        time.sleep(0.1) # Watchdog uchun 100ms interval
except KeyboardInterrupt:
    ser.close()
```

---

## 5. Kalibratsiya Ma'lumotlari

- **90°:** Barcha bo'g'inlar uchun markaziy (neytral) holat.
- **oy=180°:** O'ng yelka to'g'riga ko'tarilgan.
- **cy=0°:** Chap yelka to'g'riga ko'tarilgan.
- **ot/ct=180°:** Tirsaklar to'liq bukilgan (faqat yelka xavfsiz hududda bo'lmaganda).
