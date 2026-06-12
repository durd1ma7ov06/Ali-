import time

import robot_hardware as hardware


def main():
    print("[TEST] Kamera -> yuz aniqlash -> ESP32 servo testi boshlandi.")
    print("[TEST] Kamera oynasi chiqsa, yopish uchun q bosing yoki Ctrl+C ishlating.")

    runtime = hardware.start_camera_if_enabled()
    if runtime is None:
        print("[TEST] Kamera yoqilmadi.")
        return

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[TEST] To'xtatilmoqda...")
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
