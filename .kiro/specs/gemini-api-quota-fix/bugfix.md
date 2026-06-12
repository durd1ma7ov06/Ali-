# Bugfix Requirements Document

## Introduction

Humanoid robot loyihasida Google Gemini API ulanish muammosi mavjud. Robot ishga tushganda yoki AI javob berishga harakat qilganda ikki xil xato yuz bermoqda:
1. **Error 429 (Quota Exceeded)**: API kalitining kunlik yoki daqiqalik limiti tugagan
2. **Error 404 (Model Not Found)**: Konfiguratsiyada ko'rsatilgan model nomlari (gemini-2.0-flash-exp, gemini-1.5-flash) topilmayapti

Natijada robot AI bilan suhbatlasha olmaydi va "[XATO] API ulanmadi" xabari chiqadi. Bu muammo foydalanuvchi tajribasini to'liq buzadi, chunki robotning asosiy funksiyasi - ovozli suhbat - ishlamaydi.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN robot ishga tushganda va `ping()` funksiyasi API ulanishni tekshirganda THEN sistema 429 (Quota Exceeded) yoki 404 (Model Not Found) xatolarini qaytaradi va "[XATO] API ulanmadi" xabari chiqadi

1.2 WHEN foydalanuvchi ovozli buyruq berganda va `chat_text()` funksiyasi AI javob olishga harakat qilganda THEN barcha 3 ta fallback model (gemini-2.0-flash-exp, gemini-1.5-flash, gemini-2.0-flash-001) ham 404 yoki 429 xatolarini qaytaradi

1.3 WHEN API kalitining kvotasi tugagan bo'lsa (429 xatosi) THEN sistema foydalanuvchiga aniq xato xabari bermasdan umumiy "API ulanmadi" xabarini ko'rsatadi

1.4 WHEN model nomi noto'g'ri yoki eskirgan bo'lsa (404 xatosi) THEN sistema avtomatik ravishda boshqa mavjud modelga o'tishga harakat qilmaydi

### Expected Behavior (Correct)

2.1 WHEN robot ishga tushganda va API ulanishni tekshirganda THEN sistema mavjud va ishlayotgan model nomlarini ishlatishi va muvaffaqiyatli ulanishi KERAK

2.2 WHEN foydalanuvchi ovozli buyruq berganda THEN AI tizimi javob berishi va robot ovozli suhbat qila olishi KERAK

2.3 WHEN API kalitining kvotasi tugagan bo'lsa (429 xatosi) THEN sistema foydalanuvchiga aniq va tushunarli xato xabari berishi KERAK: "API kalitining limiti tugagan. Yangi API kalit oling yoki keyinroq urinib ko'ring."

2.4 WHEN bitta model 404 xatosini qaytarsa THEN sistema avtomatik ravishda keyingi mavjud modelga o'tishi va ulanishni davom ettirishi KERAK

2.5 WHEN .env faylida model nomlari noto'g'ri yoki eskirgan bo'lsa THEN sistema to'g'ri va mavjud model nomlarini (masalan: gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro) ishlatishi KERAK

### Unchanged Behavior (Regression Prevention)

3.1 WHEN API kaliti to'g'ri va kvota yetarli bo'lsa THEN sistema avvalgidek muvaffaqiyatli ulanishi va AI javob berishi DAVOM ETISHI KERAK

3.2 WHEN OpenRouter yoki boshqa provayder ishlatilsa THEN sistema avvalgidek ishlashi DAVOM ETISHI KERAK

3.3 WHEN `chat_text()` funksiyasi to'g'ri model nomi bilan chaqirilsa THEN AI javob qaytarishi DAVOM ETISHI KERAK

3.4 WHEN fallback mexanizmi birinchi model ishlamasa THEN ikkinchi modelga o'tishi DAVOM ETISHI KERAK

3.5 WHEN xato xabarlari konsolga chiqarilsa THEN ular avvalgidek `print()` orqali ko'rsatilishi DAVOM ETISHI KERAK

3.6 WHEN timeout sozlamalari (AI_REQUEST_TIMEOUT) o'rnatilgan bo'lsa THEN ular avvalgidek ishlashi DAVOM ETISHI KERAK
