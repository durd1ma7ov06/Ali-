# -*- coding: utf-8 -*-
"""
Sohibqiron Amir Temur - 2D Talking Avatar Test
Bu skript 2D rasmning og'iz va iyak qismini dasturiy ravishda qimirlatib,
gapirish effektini yaratadi.
"""
import cv2
import numpy as np
import time
import os

def main():
    img_path = "amir_temur_portrait.png"
    if not os.path.exists(img_path):
        print(f"Xato: {img_path} topilmadi!")
        return

    print("Rasm yuklanmoqda...")
    img = cv2.imread(img_path)
    h_orig, w_orig = img.shape[:2]
    
    # Rasmni ekranga sig'adigan o'lchamga keltiramiz (masalan, 600x600)
    display_size = 600
    img_disp = cv2.resize(img, (display_size, display_size))
    h, w = display_size, display_size
    
    # Yuzni aniqlash
    cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    face_cascade = cv2.CascadeClassifier(cascade_path)
    
    gray = cv2.cvtColor(img_disp, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(100, 100))
    
    if len(faces) > 0:
        # Eng katta yuzni olamiz
        fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
        print(f"Yuz topildi: X={fx}, Y={fy}, W={fw}, H={fh}")
        
        # Geometrik nisbatlar orqali og'iz koordinatalarini aniqlaymiz
        mx = fx + int(fw * 0.33)
        my = fy + int(fh * 0.70)
        mw = int(fw * 0.34)
        mh = int(fh * 0.12)
    else:
        print("Yuz aniqlanmadi, standart koordinatalardan foydalaniladi.")
        # Standart (600x600 o'lchamdagi rasm uchun taxminiy markaz)
        mx, my, mw, mh = 260, 410, 80, 50

    print(f"Og'iz koordinatalari: X={mx}, Y={my}, W={mw}, H={mh}")
    
    # Asl iyak (chin) va og'iz osti sohasini kesib olamiz (pastga siljitish uchun)
    # Og'iz markazidan iyak oxirigacha bo'lgan qism
    iyak_y1 = my + mh // 2
    iyak_y2 = min(h, fy + fh + int(fh * 0.1)) # Yuzdan bir oz pastroqgacha
    iyak_x1 = max(0, fx)
    iyak_x2 = min(w, fx + fw)
    
    # Iyak tasviri
    iyak_roi = img_disp[iyak_y1:iyak_y2, iyak_x1:iyak_x2].copy()
    iyak_h, iyak_w = iyak_roi.shape[:2]

    print("Interaktiv oyna ochilmoqda. Chiqish uchun 'q' tugmasini bosing.")
    window_name = "Sohibqiron Amir Temur 2D Avatar"
    cv2.namedWindow(window_name)

    start_time = time.time()
    
    while True:
        t = time.time() - start_time
        
        # Animatsiya: 0 dan 12 pikselgacha og'iz ochilishi
        # Gapirish tezligiga o'xshash tartibsiz tebranish
        open_amount = int((np.sin(t * 15.0) * 0.4 + np.sin(t * 7.0) * 0.4 + 0.2) * 12.0)
        open_amount = max(0, open_amount) # Salbiy qiymatlarni yo'qotamiz
        
        # Kadroviy rasm nusxasi
        frame = img_disp.copy()
        
        if open_amount > 0:
            # 1. Og'iz ichi bo'shlig'ini chizamiz (to'q rangli ellips)
            # Bu iyak pastga surilganda ochiladigan bo'shliq bo'ladi
            cavity_color = (15, 15, 35) # To'q qizg'ish/qora rang
            cv2.rectangle(
                frame, 
                (iyak_x1, iyak_y1), 
                (iyak_x2, iyak_y1 + open_amount + 2), 
                cavity_color, 
                -1
            )
            
            # 2. Iyak (pastki jag') qismini pastga surib chizamiz
            # Tepadan ochilgan bo'shliqni yopmasligi uchun iyakni open_amount piksellar pastga joylashtiramiz
            shift_y = iyak_y1 + open_amount
            dest_h = min(h - shift_y, iyak_h)
            
            if dest_h > 0:
                frame[shift_y:shift_y + dest_h, iyak_x1:iyak_x2] = iyak_roi[0:dest_h, :]
                
            # 3. Yondan chiziqlar ajralib qolmasligi uchun iyak atrofini biroz yumshatamiz (smooth transition)
            # (Oddiy ko'rinish uchun chekkalarni asliga qaytaramiz)
            # Iyakning chap va o'ng chetlarini asl rasm bilan yumshoq aralashtiramiz (blending)
            blend_w = 10
            if iyak_w > 2 * blend_w:
                # Chap chet
                frame[shift_y:shift_y + dest_h, iyak_x1:iyak_x1 + blend_w] = cv2.addWeighted(
                    frame[shift_y:shift_y + dest_h, iyak_x1:iyak_x1 + blend_w], 0.5,
                    img_disp[shift_y:shift_y + dest_h, iyak_x1:iyak_x1 + blend_w], 0.5, 0
                )
                # O'ng chet
                frame[shift_y:shift_y + dest_h, iyak_x2 - blend_w:iyak_x2] = cv2.addWeighted(
                    frame[shift_y:shift_y + dest_h, iyak_x2 - blend_w:iyak_x2], 0.5,
                    img_disp[shift_y:shift_y + dest_h, iyak_x2 - blend_w:iyak_x2], 0.5, 0
                )

        cv2.imshow(window_name, frame)
        
        # 30 FPS atrofida ushlab turamiz
        if cv2.waitKey(33) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
