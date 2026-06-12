# -*- coding: utf-8 -*-
"""
Sohibqiron Amir Temur - 2D speaking Avatar (Smooth Warping)
Tizimda gapirganda og'zini silliq deformatsiya orqali qimirlatuvchi, 
gapirmaganda esa to'liq yopiq turuvchi interfeys.
"""
import cv2
import numpy as np
import time
import os
import threading

_avatar_thread = None
_stop_event = threading.Event()

def is_currently_speaking() -> bool:
    """Check if pygame mixer is currently playing speech."""
    try:
        import pygame
        return pygame.mixer.music.get_busy()
    except Exception:
        return False

def smooth_warp_mouth(img, cx, cy, W, H_up, H_down, open_amount):
    """
    Silliq deformatsiya yordamida og'izni tabiiy ochish.
    Iyak va jag' sohasini qattiq tanacha kabi siljitadi.
    """
    h, w = img.shape[:2]
    
    # OpenCV remap uchun koordinatalar xaritasi
    grid_y, grid_x = np.mgrid[0:h, 0:w]
    map_x = grid_x.astype(np.float32)
    map_y = grid_y.astype(np.float32)
    
    if open_amount <= 0:
        return img.copy()
        
    x_min = max(0, cx - W)
    x_max = min(w, cx + W)
    y_min = max(0, cy - H_up)
    y_max = min(h, cy + H_down)
    
    # Jag' (iyak/soqol) qismining qattiq harakatlanadigan balandligi
    H_chin = int(H_down * 0.70)
    
    for y in range(y_min, y_max):
        if y < cy:
            # Yuqori lab tepaga siljiydi (manba koordinatasi pastroqdan olinadi: y + dy)
            w_y = (y - y_min) / H_up
            w_y = w_y ** 2
            dy = open_amount * 0.25 * w_y
        else:
            # Pastki jag' va iyak pastga siljiydi (manba koordinatasi teparoqdan olinadi: y - dy)
            if y <= cy + H_chin:
                # Butun soqol va iyak yaxlit holda pastga siljiydi
                w_y = 1.0
            else:
                # Bo'yin qismi silliq cho'ziladi
                w_y = 1.0 - (y - (cy + H_chin)) / (H_down - H_chin)
                w_y = max(0.0, min(1.0, w_y))
                w_y = w_y ** 2
            dy = -open_amount * 1.0 * w_y
            
        for x in range(x_min, x_max):
            w_x = 1.0 - abs(x - cx) / W
            w_x = max(0.0, w_x) ** 2
            
            # Y o'qi bo'yicha surish
            map_y[y, x] = y + dy * w_x

    # Remap yordamida tasvirni deformatsiya qilamiz
    warped = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    
    # Lablar ochilganda ichidagi qorong'u bo'shliqni chizish
    if open_amount > 2:
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(
            mask,
            (cx, cy + int(open_amount * 0.15)),
            (int(W * 0.45), int(open_amount * 0.35)),
            0, 0, 360, 255, -1
        )
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        
        cavity = np.zeros_like(img)
        cavity[:] = (15, 15, 30) # Oral cavity color (dark dark-red/black)
        
        mask_normalized = np.expand_dims(mask.astype(np.float32) / 255.0, axis=2)
        warped = (warped * (1.0 - mask_normalized) + cavity * mask_normalized).astype(np.uint8)
        
    return warped

def _run_avatar():
    img_path = "amir_temur_portrait.png"
    if not os.path.exists(img_path):
        print(f"[WARN] Avatar rasm topilmadi: {img_path}.")
        return

    img = cv2.imread(img_path)
    if img is None:
        print("[WARN] Avatar rasmini yuklab bo'lmadi.")
        return

    h_orig, w_orig = img.shape[:2]
    
    # Tasvirni kvadrat qilib kesish (aspekt nisbatini saqlab qolish uchun)
    min_dim = min(h_orig, w_orig)
    dy = (h_orig - min_dim) // 2
    dx = (w_orig - min_dim) // 2
    cropped = img[dy:dy+min_dim, dx:dx+min_dim]

    # Oyna o'lchami 500x500
    display_size = 500
    img_disp = cv2.resize(cropped, (display_size, display_size))
    h, w = display_size, display_size

    # O'ta aniq o'lchangan koordinatalar (500x500 o'lcham uchun)
    cx, cy = 253, 110
    W = 16        # Og'iz kengligi yarmi (kattaroq)
    H_up = 10     # Burungacha bo'lgan masofa
    H_down = 37    # Iyak va soqolning oxirigacha masofa
    
    # Ko'zlar (pirpirash uchun)
    eye_y, eye_h = 82, 6
    le_x1, le_x2 = 230, 245
    re_x1, re_x2 = 255, 270
    
    # Ko'z usti terisini nusxalash (ko'zni yopganda ishlatiladi)
    eyelid_source_y = max(0, eye_y - eye_h)
    le_eyelid = img_disp[eyelid_source_y:eyelid_source_y + eye_h, le_x1:le_x2].copy()
    re_eyelid = img_disp[eyelid_source_y:eyelid_source_y + eye_h, re_x1:re_x2].copy()

    window_name = "Amir Temur Avatar"
    cv2.namedWindow(window_name)

    print("[AVATAR] 2D Avatar oynasi ochildi.")
    
    last_blink_time = time.time()
    blink_duration = 0.12
    blink_interval = 4.0
    is_blinking = False
    
    current_open_amount = 0.0
    
    while not _stop_event.is_set():
        now = time.time()
        speaking = is_currently_speaking()
        
        # ── PIRPIRASH LOGIKASI ───────────────────────────────────
        if not is_blinking and (now - last_blink_time) > blink_interval:
            is_blinking = True
            blink_start = now
            blink_interval = np.random.uniform(3.0, 7.0)
            
        if is_blinking:
            if (now - blink_start) > blink_duration:
                is_blinking = False
                last_blink_time = now
                
        # ── OG'IZ HARAKATI LOGIKASI (FAQAT GAPIRGANDA!) ─────────
        if speaking:
            # Tasodifiy gapirish ritmi (0 dan 6.0 pikselgacha ochilish - kattaroq)
            target_open = (np.sin(now * 15.0) * 0.45 + np.sin(now * 7.5) * 0.4 + 0.25) * 6.0
            target_open = max(0.0, target_open)
        else:
            # Gapirmaganda og'iz yopiq qoladi
            target_open = 0.0
            
        # Harakatni silliqlashtirish
        current_open_amount = current_open_amount * 0.6 + target_open * 0.4
        
        # Tasvirni deformatsiya qilish
        frame = smooth_warp_mouth(img_disp, cx, cy, W, H_up, H_down, current_open_amount)
        
        # Ko'z pirpiratishni chizish
        if is_blinking:
            frame[eye_y:eye_y + eye_h, le_x1:le_x2] = le_eyelid
            frame[eye_y:eye_y + eye_h, re_x1:re_x2] = re_eyelid

        cv2.imshow(window_name, frame)
        
        # 30 FPS kutish
        if cv2.waitKey(33) & 0xFF == ord('q'):
            break

    cv2.destroyWindow(window_name)
    print("[AVATAR] 2D Avatar oynasi yopildi.")

def start_avatar():
    """Start the 2D speaking avatar in a background thread."""
    global _avatar_thread, _stop_event
    if _avatar_thread and _avatar_thread.is_alive():
        return
    _stop_event.clear()
    _avatar_thread = threading.Thread(target=_run_avatar, name="avatar-preview", daemon=True)
    _avatar_thread.start()

def stop_avatar():
    """Stop the 2D speaking avatar."""
    global _avatar_thread, _stop_event
    _stop_event.set()
    if _avatar_thread and _avatar_thread.is_alive():
        _avatar_thread.join(timeout=2.0)
