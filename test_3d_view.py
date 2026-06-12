# -*- coding: utf-8 -*-
"""
Sohibqiron Amir Temur - 3D Model Viewer
Interaktiv 3D modelni ekranda ko'rish va boshqarish skripti.
"""
import trimesh
import sys

def main():
    glb_path = "3D/rodin-v2_-0_8307e359-d517-41c2-a4ed-6e58825dc1f0.glb"
    print("=" * 60)
    print("      SOHIBQIRON AMIR TEMUR - 3D MODEL VIEWER")
    print("=" * 60)
    print(f"Loading 3D model: {glb_path}...")
    
    try:
        scene = trimesh.load(glb_path)
        print("Model muvaffaqiyatli yuklandi!")
        print(f"Mesh nomi: model")
        print(f"Nuqtalar soni (Vertices): {len(scene.geometry['model'].vertices)}")
        print(f"Yuzalar soni (Faces): {len(scene.geometry['model'].faces)}")
        print("\nEkranda interaktiv 3D oyna ochilmoqda...")
        print("Sichqonchaning chap tugmasi: Modelni aylantirish (Rotate)")
        print("Sichqonchaning o'ng tugmasi: Modelni surish (Pan)")
        print("Sichqoncha g'ildiragi: Yaqinlashtirish / Uzoqlashtirish (Zoom)")
        print("-" * 60)
        
        # Oynani ochish
        scene.show(title="Sohibqiron Amir Temur 3D")
        
    except Exception as e:
        print(f"\nXato yuz berdi: {e}")
        print("Iltimos, kutubxonalar to'g'ri o'rnatilganligini tekshiring.")

if __name__ == "__main__":
    main()
