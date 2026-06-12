import serial
import time
import os
import sys
import asyncio  # asyncio import qilamiz


class RobotController:
    def __init__(self):
        self.port = os.getenv("ROBOT_SERIAL_PORT", "COM11")
        if sys.platform.startswith("linux"):
            self.port = os.getenv("ROBOT_SERIAL_PORT", "/dev/ttyUSB0")

        self.baud_rate = int(os.getenv("ROBOT_BAUD_RATE", "115200"))
        self.ser = None
        self.connect()

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baud_rate)
            print(f"Connected to robot on {self.port} with baud rate {self.baud_rate}")
        except serial.SerialException as e:
            print(f"Error connecting to robot on {self.port}: {e}")
            self.ser = None

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"Disconnected from robot on {self.port}")

    async def move_robot(self, b, oy, ot, ob, cy, ct, cb):  # async qildim
        if not self.ser or not self.ser.is_open:
            print("Robot not connected. Attempting to reconnect...")
            self.connect()
            if not self.ser or not self.ser.is_open:
                print("Failed to reconnect. Skipping movement command.")
                return

        packet = f"<{b},{oy},{ot},{ob},{cy},{ct},{cb}>"
        try:
            self.ser.write(packet.encode())
            print(f"[ROBOT] Sent: {packet}")
        except serial.SerialException as e:
            print(f"Error sending command to robot: {e}")
            self.disconnect()
            self.connect()

    async def execute_movements(self, movements):  # async qildim
        """
        Harakatlar ketma-ketligini bajaradi.
        movements = [
            {"command": [b, oy, ot, ob, cy, ct, cb], "wait": 0.5},
            ...
        ]
        """
        if not self.ser or not self.ser.is_open:
            print("Robot not connected. Attempting to reconnect...")
            self.connect()
            if not self.ser or not self.ser.is_open:
                print("Failed to reconnect. Skipping movement execution.")
                return

        for move in movements:
            command = move["command"]
            wait_time = move.get("wait", 0.1)
            await self.move_robot(*command)  # await dan foydalandim
            await asyncio.sleep(wait_time)  # asyncio.sleep dan foydalandim

        # Harakatlar tugagandan so'ng default holatga qaytarish
        await self.move_robot(90, 90, 90, 90, 90, 90, 90)  # await dan foydalandim
        await asyncio.sleep(0.1)  # asyncio.sleep dan foydalandim


# Test uchun
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    import sys


    async def test_movements():  # Test funksiyasini ham async qildim
        controller = RobotController()
        if controller.ser and controller.ser.is_open:
            try:
                print("Moving to neutral position...")
                await controller.move_robot(90, 90, 90, 90, 90, 90, 90)
                await asyncio.sleep(1)

                print("Moving right arm up...")
                await controller.execute_movements([
                    {"command": [90, 180, 90, 90, 90, 90, 90], "wait": 0.5},
                    {"command": [90, 180, 180, 90, 90, 90, 90], "wait": 0.5},
                ])
                await asyncio.sleep(1)

                print("Moving left arm up...")
                await controller.execute_movements([
                    {"command": [90, 90, 90, 90, 0, 90, 90], "wait": 0.5},
                    {"command": [90, 90, 90, 90, 0, 180, 90], "wait": 0.5},
                ])
                await asyncio.sleep(1)

                print("Returning to neutral position...")
                await controller.move_robot(90, 90, 90, 90, 90, 90, 90)
                await asyncio.sleep(1)

            except KeyboardInterrupt:
                print("Test interrupted.")
            finally:
                controller.disconnect()
        else:
            print("Could not connect to robot. Check port and connection.")


    asyncio.run(test_movements())  # async funksiyani ishga tushirdim