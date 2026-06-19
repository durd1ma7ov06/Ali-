# -*- coding: utf-8 -*-
"""
Sohibqiron Amir Temur - 3D speaking Avatar
Interaktiv 3D modelni yuklab, gapirganda og'zini silliq qimirlatuvchi,
gapirmaganda esa to'liq yopiq turuvchi va tabiiy nafas olish/tebranish
harakatlarini bajaruvchi 3D interfeys.
"""
import trimesh
import numpy as np
import time
import os
import threading
import pyglet

_avatar_thread = None
_stop_event = threading.Event()

def is_currently_speaking() -> bool:
    """Pygame mixer orqali ovoz chiqayotganini tekshirish."""
    try:
        import pygame
        return pygame.mixer.music.get_busy()
    except Exception:
        return False

def _run_avatar():
    glb_path = "3D/rodin-v2_-0_8307e359-d517-41c2-a4ed-6e58825dc1f0.glb"
    if not os.path.exists(glb_path):
        print(f"[WARN] 3D Model topilmadi: {glb_path}.")
        return

    print(f"[3D-AVATAR] 3D model yuklanmoqda: {glb_path}...")
    try:
        scene = trimesh.load(glb_path)
    except Exception as e:
        print(f"[WARN] 3D modelni yuklashda xato: {e}")
        return

    mesh = scene.geometry['model']
    centroid = mesh.centroid
    
    # Asl nuqtalarni (vertices) saqlab olamiz
    original_vertices = mesh.vertices.copy()
    
    # Og'iz koordinatalar markazi va ta'sir doirasi (ellipsoid)
    C_x, C_y, C_z = 0.0, 0.21, -0.19
    W_x, W_y, W_z = 0.08, 0.04, 0.05
    
    # Oldindan masofalar va indekslarni hisoblab olamiz
    dx = original_vertices[:, 0] - C_x
    dy = original_vertices[:, 1] - C_y
    dz = original_vertices[:, 2] - C_z
    
    d = np.sqrt((dx / W_x)**2 + (dy / W_y)**2 + (dz / W_z)**2)
    mask = d < 1.0
    deform_indices = np.where(mask)[0]
    deform_d = d[deform_indices]
    deform_y = original_vertices[deform_indices, 1]
    
    print(f"[3D-AVATAR] Og'iz sohasi uchun {len(deform_indices)} ta nuqta aniqlandi.")
    
    current_open_amount = 0.0
    
    def update_callback(scene_obj):
        nonlocal current_open_amount
        
        now = time.time()
        speaking = is_currently_speaking()
        
        # 1. OG'IZ HARAKATI LOGIKASI
        if speaking:
            # Ritmik gapirish harakati (sinusoidlar yordamida)
            target_open = (np.sin(now * 15.0) * 0.45 + np.sin(now * 7.5) * 0.4 + 0.25) * 0.015
            target_open = max(0.0, target_open)
        else:
            target_open = 0.0
            
        # Silliqlash (interpolation)
        current_open_amount = current_open_amount * 0.6 + target_open * 0.4
        
        # Nuqtalarni deformatsiya qilish
        new_y = deform_y.copy()
        
        # Pastki lab va jag' (pastga harakatlanadi)
        lower_mask = deform_y < C_y
        new_y[lower_mask] -= current_open_amount * (1.0 - deform_d[lower_mask])**2
        
        # Yuqori lab (pastroq koeffitsient bilan tepaga harakatlanadi)
        upper_mask = deform_y >= C_y
        new_y[upper_mask] += current_open_amount * 0.25 * (1.0 - deform_d[upper_mask])**2
        
        mesh.vertices[deform_indices, 1] = new_y
        mesh._cache.clear()
        
        # 2. NAVAS OLISH VA TEBRANISH LOGIKASI
        # Nafas olish (Y o'qi bo'yicha yuqoriga va pastga mayda siljish)
        breath_y = np.sin(now * 1.5) * 0.003
        # Boshni ozgina tebratish (Y o'qi atrofida aylantirish)
        sway_angle = np.sin(now * 0.8) * 0.015
        
        # Centroid atrofida aylantirish matritsasi
        R = trimesh.transformations.rotation_matrix(sway_angle, [0, 1, 0], point=centroid)
        R[1, 3] += breath_y # Nafas olish siljishi
        
        # Sahnadagi model tugunini yangilash
        nodes = list(scene_obj.graph.nodes_geometry)
        if nodes:
            scene_obj.graph.update(nodes[0], matrix=R)
            
        # 3. VIEWER VIZUALIZATSIYASINI YANGILASH
        windows = list(pyglet.app.windows)
        if windows:
            viewer = windows[0]
            if 'model' in viewer.vertex_list:
                try:
                    viewer.vertex_list['model'].delete()
                    viewer.add_geometry('model', mesh, smooth=bool(viewer._smooth))
                except Exception:
                    pass
                    
        # Agar stop event chaqirilgan bo'lsa, oynani yopamiz
        if _stop_event.is_set():
            if windows:
                windows[0].close()

    print("[3D-AVATAR] 3D Avatar oynasi ochilmoqda...")
    try:
        # Premium ko'rinish uchun fonni to'q ko'k/kulrang rangda [20, 20, 30] chizamiz
        scene.show(
            callback=update_callback, 
            callback_period=1.0/30.0, 
            title="Sohibqiron Amir Temur 3D",
            background=[20, 20, 30]
        )
    except Exception as e:
        print(f"[WARN] 3D oynada xato yuz berdi: {e}")
    finally:
        print("[3D-AVATAR] 3D Avatar oynasi yopildi.")

def start_avatar():
    """3D avatar oynasini fondagi oqimda ishga tushirish."""
    global _avatar_thread, _stop_event
    if _avatar_thread and _avatar_thread.is_alive():
        return
    _stop_event.clear()
    _avatar_thread = threading.Thread(target=_run_avatar, name="avatar-3d-preview", daemon=True)
    _avatar_thread.start()

def stop_avatar():
    """3D avatar oynasini yopish va to'xtatish."""
    global _avatar_thread, _stop_event
    _stop_event.set()
    if _avatar_thread and _avatar_thread.is_alive():
        _avatar_thread.join(timeout=2.0)
