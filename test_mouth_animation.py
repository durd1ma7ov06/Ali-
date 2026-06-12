# -*- coding: utf-8 -*-
"""
Sohibqiron Amir Temur - 3D Mouth Animation Calibration
Bu skript 3D modelning og'zini topish va uni real vaqtda harakatlantirish uchun ishlatiladi.
Klaviatura tugmalari orqali ta'sir doirasini (og'iz koordinatasini) aniqlab olishingiz mumkin.
"""
import trimesh
import numpy as np
import pyglet
from pyglet.window import key
import time

# Asosiy sozlamalar
glb_path = "3D/rodin-v2_-0_8307e359-d517-41c2-a4ed-6e58825dc1f0.glb"

print("Model yuklanmoqda...")
scene = trimesh.load(glb_path)
mesh = scene.geometry['model']

# Asl nuqtalar koordinatalari nusxasi
orig_vertices = mesh.vertices.copy()
num_vertices = len(orig_vertices)

# Dastlabki ta'sir doirasi markazi (Centroid yaqinida)
# Centroid: [-0.0137, -0.3818, -0.3117]
center = np.array([-0.013, -0.38, -0.31], dtype=np.float32)
radius = 0.08
strength = 0.04
animate = True

# Qaysi o'q bo'yicha harakatlanishi (og'iz odatda oldinga/pastga harakatlanadi)
# Keling, og'izni pastga (Y yoki Z o'qi bo'yicha) tortamiz.
# O'qni aniqlash uchun displacement yo'nalishi:
displacement_dir = np.array([0.0, -0.8, -0.6], dtype=np.float32)
displacement_dir /= np.linalg.norm(displacement_dir)

print("\n" + "=" * 60)
# Klaviatura qo'llanmasi
print("Klaviatura orqali boshqarish:")
print("  Chap / O'ng Strelkalar: X o'qini sozlash (Chap/O'ng)")
print("  Tepadagi / Pastdagi Strelkalar: Y o'qini sozlash (Yaqin/Uzoq yoki Tepa/Past)")
print("  PAGE UP / PAGE DOWN: Z o'qini sozlash (Oldinga/Orqaga)")
print("  - / + (minus/plus): Ta'sir doirasi radiusi (Radius)")
print("  [ / ]: Harakat kuchini sozlash (Strength)")
print("  SPACE (Probel): Animatsiyani to'xtatish / yoqish")
print("  ENTER: Hozirgi koordinatalarni konsolda chop etish")
print("=" * 60)

def update_vertices(scene):
    global center, radius, strength, animate
    
    t = time.time()
    if animate:
        # Og'iz ochilish amplitudasi (0 dan 1 gacha sinusoide)
        amplitude = np.sin(t * 12.0) * 0.5 + 0.5
    else:
        amplitude = 1.0
        
    # Masofalarni hisoblash (vectorized NumPy)
    diff = orig_vertices - center
    dists = np.linalg.norm(diff, axis=1)
    
    # Faqat ta'sir doirasidagi nuqtalarni deformatsiya qilish
    mask = dists < radius
    
    # Yangi koordinatalarni hisoblash
    new_vertices = orig_vertices.copy()
    if np.any(mask):
        # Masofaga qarab yumshoq o'tish (smoothstep yoki quadratic)
        influence = (1.0 - dists[mask] / radius) ** 2
        
        # Deformatsiya effekti
        shift = displacement_dir * (strength * amplitude)
        new_vertices[mask] += np.outer(influence, shift)
        
    # Meshni yangilash
    mesh.vertices = new_vertices

# 3D oynani ochish (lekin hali loopni boshlamaslik)
viewer = scene.show(title="Amir Temur - Og'iz Sozlash", callback=update_vertices, callback_period=0.03, start_loop=False)

# Klaviatura hodisalarini tinglash
@viewer.event
def on_key_press(symbol, modifiers):
    global center, radius, strength, animate
    
    step = 0.01
    if symbol == key.LEFT:
        center[0] -= step
    elif symbol == key.RIGHT:
        center[0] += step
    elif symbol == key.UP:
        center[1] += step
    elif symbol == key.DOWN:
        center[1] -= step
    elif symbol == key.PAGEUP:
        center[2] += step
    elif symbol == key.PAGEDOWN:
        center[2] -= step
    elif symbol == key.MINUS:
        radius = max(0.01, radius - 0.005)
    elif symbol == key.EQUAL:  # Plus key
        radius += 0.005
    elif symbol == key.BRACKETLEFT:
        strength = max(0.001, strength - 0.002)
    elif symbol == key.BRACKETRIGHT:
        strength += 0.002
    elif symbol == key.SPACE:
        animate = not animate
        print(f"Animatsiya: {'YOQILDI' if animate else 'TO`XTATILDI'}")
    elif symbol == key.ENTER:
        print(f"\n--- ANIQLANGAN KOORDINATALAR ---")
        print(f"Markaz (Center): [{center[0]:.4f}, {center[1]:.4f}, {center[2]:.4f}]")
        print(f"Radius (Radius): {radius:.4f}")
        print(f"Kuch (Strength): {strength:.4f}")
        print(f"Displacement yo'nalishi: {list(displacement_dir)}")
        print(f"--------------------------------")
        
    print(f"Markaz: [{center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f}] | Radius: {radius:.3f} | Kuch: {strength:.3f}", end="\r")

# Dasturni ishga tushirish
pyglet.app.run()
