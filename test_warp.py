# -*- coding: utf-8 -*-
"""
Sohibqiron Amir Temur - Smooth Warp Test V11 (Slightly Right and Larger)
"""
import cv2
import numpy as np
import time
import os

def smooth_warp_mouth(img, cx, cy, W, H_up, H_down, open_amount):
    h, w = img.shape[:2]
    
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

def main():
    img_path = "amir_temur_portrait.png"
    if not os.path.exists(img_path):
        print(f"Rasm topilmadi: {img_path}")
        return
        
    img = cv2.imread(img_path)
    h_orig, w_orig = img.shape[:2]
    
    # Kvadrat qilib kesish
    min_dim = min(h_orig, w_orig)
    dy = (h_orig - min_dim) // 2
    dx = (w_orig - min_dim) // 2
    cropped = img[dy:dy+min_dim, dx:dx+min_dim]
    
    img_disp = cv2.resize(cropped, (500, 500))
    
    # Yangilangan koordinatalar (Sal o'ngga va kattaroq: cx=253, W=16)
    cx, cy = 253, 110
    W = 16        # Og'iz kengligi yarmi
    H_up = 10     # Burungacha bo'lgan masofa
    H_down = 37    # Iyak va soqolning oxirigacha masofa
    
    window_name = "Smooth Warp Test V11"
    cv2.namedWindow(window_name)
    
    start_time = time.time()
    while True:
        t = time.time() - start_time
        # Animatsiya: 0 dan 6 pikselgacha ochilish (kattaroq)
        open_amount = (np.sin(t * 12.0) * 0.5 + 0.5) * 6.0
        
        warped = smooth_warp_mouth(img_disp, cx, cy, W, H_up, H_down, open_amount)
        
        cv2.imshow(window_name, warped)
        if cv2.waitKey(33) & 0xFF == ord('q'):
            break
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
