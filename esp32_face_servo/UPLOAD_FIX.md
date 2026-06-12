# ESP32 upload xatosini tuzatish

Sizdagi xato:

```text
A fatal error occurred: This chip is ESP32 not ESP32-S2. Wrong --chip argument?
Failed uploading: uploading error: exit status 2
```

Bu sketch xatosi emas. Sketch kompilyatsiyadan o'tgan, xato upload vaqtida chiqyapti. Arduino IDE yoki Arduino CLI `--chip esp32s2` bilan yuklashga urinmoqda, lekin ulangan plata oddiy `ESP32`.

## Arduino IDE da tuzatish

1. `Tools > Board > esp32` menyusidan `ESP32 Dev Module` ni tanlang.
2. `ESP32S2 Dev Module`, `ESP32-S2`, `ESP32S3`, `ESP32-C3` kabi boshqa chip oilalarini tanlamang.
3. `Tools > Port` dan ESP32 portini tanlang, masalan `COM3`.
4. `Upload` ni qayta bosing.

## Arduino CLI ishlatilsa

Oddiy ESP32 uchun FQBN odatda shunday bo'ladi:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 .\esp32_face_servo
arduino-cli upload -p COM3 --fqbn esp32:esp32:esp32 .\esp32_face_servo
```

Agar sizning plata nomingiz boshqa bo'lsa, avval quyidagini tekshiring:

```powershell
arduino-cli board list
arduino-cli board listall esp32
```

Muhimi: FQBN ichida `esp32s2`, `esp32s3` yoki `esp32c3` bo'lmasin, agar platangiz oddiy ESP32 bo'lsa.
