import time

import robot_hardware as hardware


def main():
    print("[TEST] Startup salomlashish harakati testi boshlandi.")
    print("[TEST] O'ng qo'l ko'ksiga boradi, bosh biroz qimirlaydi, keyin qo'l neutral holatga qaytadi.")

    controller = hardware.get_esp32_controller()
    hardware.apply_resting_arm_pose()
    time.sleep(1)

    try:
        hardware.play_startup_greeting_motion()
        time.sleep(2)
    finally:
        hardware.finish_startup_greeting_motion()
        hardware.apply_resting_arm_pose()
        print("[TEST] Tugadi. Qo'llar resting holatga qaytarildi.")


if __name__ == "__main__":
    main()
