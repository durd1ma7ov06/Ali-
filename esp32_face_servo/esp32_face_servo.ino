/*
 * ESP32 Humanoid Robot Servo Controller
 * ======================================
 * 
 * UPLOAD INSTRUCTIONS:
 * -------------------
 * Arduino IDE: Tools > Board > ESP32 Dev Module
 * Arduino CLI: arduino-cli compile --fqbn esp32:esp32:esp32
 * 
 * HARDWARE SETUP:
 * --------------
 * 7 servos connected to GPIO pins (13, 12, 14, 27, 26, 25, 33)
 * Power: External 5V power supply for servos (ESP32 USB power not sufficient)
 * 
 * SERIAL PROTOCOL:
 * ---------------
 * Baud Rate: 115200
 * Line Ending: Newline (\n) or Carriage Return (\r)
 * 
 * Commands:
 * - HEAD:<angle>           Set head angle (0-180)
 * - SERVO:<angle>          Set head angle (legacy)
 * - ARMS:<r_sh>,<r_el>,<r_wr>,<l_sh>,<l_el>,<l_wr>  Set arm offsets (-180 to 180)
 * - HOME                   Move all servos to neutral position (90°)
 * - STATUS                 Get current servo angles
 * - CALIBRATE:<id>:<angle> Set neutral position for servo
 * 
 * Author: Humanoid ALI Team
 * Version: 2.0
 * Date: June 2026
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

const int SERVO_COUNT = 7;

// Servo IDs
const int HEAD = 0;
const int RIGHT_SHOULDER = 1;
const int RIGHT_ELBOW = 2;
const int RIGHT_WRIST = 3;
const int LEFT_SHOULDER = 4;
const int LEFT_ELBOW = 5;
const int LEFT_WRIST = 6;

// GPIO pins for each servo
const int SERVO_PINS[SERVO_COUNT] = {
  13,  // HEAD - Bosh harakati
  12,  // RIGHT_SHOULDER - O'ng yelka
  14,  // RIGHT_ELBOW - O'ng tirsak
  27,  // RIGHT_WRIST - O'ng bilak
  26,  // LEFT_SHOULDER - Chap yelka
  25,  // LEFT_ELBOW - Chap tirsak
  33   // LEFT_BILAK - Chap bilak
};

// Neutral positions (home position in degrees)
const int SERVO_NEUTRAL[SERVO_COUNT] = {
  90,  // HEAD
  90,  // RIGHT_SHOULDER
  90,  // RIGHT_ELBOW
  90,  // RIGHT_WRIST
  90,  // LEFT_SHOULDER
  90,  // LEFT_ELBOW
  90   // LEFT_WRIST
};

// Movement direction multiplier
// Left arm is mechanically mirrored, so direction = -1
const int SERVO_DIRECTION[SERVO_COUNT] = {
  1,   // HEAD
  1,   // RIGHT_SHOULDER
  1,   // RIGHT_ELBOW
  1,   // RIGHT_WRIST
  -1,  // LEFT_SHOULDER (mirrored)
  -1,  // LEFT_ELBOW (mirrored)
  -1   // LEFT_WRIST (mirrored)
};

// Angle limits for safety
const int SERVO_MIN_ANGLE[SERVO_COUNT] = {
  0, 0, 0, 0, 0, 0, 0
};

const int SERVO_MAX_ANGLE[SERVO_COUNT] = {
  180, 180, 180, 180, 180, 180, 180
};

// PWM configuration
const int SERVO_MIN_US = 500;      // Minimum pulse width (microseconds)
const int SERVO_MAX_US = 2400;     // Maximum pulse width (microseconds)
const int SERVO_PWM_FREQ = 50;     // 50 Hz for standard servos
const int SERVO_PWM_RESOLUTION = 16; // 16-bit resolution

// Movement smoothing
const int SMOOTH_DELAY_MS = 15;    // Delay between incremental moves
const int SMOOTH_STEP = 2;         // Degrees per step for smooth movement

// ============================================================================
// GLOBAL VARIABLES
// ============================================================================

String inputLine;
int currentAngles[SERVO_COUNT];
int targetAngles[SERVO_COUNT];
bool smoothMovementEnabled = true;
unsigned long lastMoveTime = 0;

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for serial port to connect (needed for some boards)
  }
  
  inputLine.reserve(128); // Reserve memory for input buffer

  // Initialize all servos
  for (int i = 0; i < SERVO_COUNT; i++) {
    // Setup PWM channel (ESP32 Arduino 3.x compatible)
    ledcAttach(SERVO_PINS[i], SERVO_PWM_FREQ, SERVO_PWM_RESOLUTION);
    
    // Set initial positions
    currentAngles[i] = SERVO_NEUTRAL[i];
    targetAngles[i] = SERVO_NEUTRAL[i];
    writeServoAngleDirect(i, currentAngles[i]);
    
    delay(50); // Small delay between servo initializations
  }

  // Send ready signal
  Serial.println("ESP32_HUMANOID_SERVO_READY");
  Serial.print("INFO:Servos initialized: ");
  Serial.println(SERVO_COUNT);
  Serial.println("INFO:Type 'HELP' for command list");
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  // Handle serial input
  while (Serial.available() > 0) {
    char ch = static_cast<char>(Serial.read());

    if (ch == '\n' || ch == '\r') {
      if (inputLine.length() > 0) {
        handleCommand(inputLine);
        inputLine = "";
      }
    } else if (inputLine.length() < 127) {
      inputLine += ch;
    }
  }
  
  // Handle smooth movement
  if (smoothMovementEnabled) {
    updateSmoothMovement();
  }
}

// ============================================================================
// COMMAND HANDLER
// ============================================================================

void handleCommand(String command) {
  command.trim();
  if (command.length() == 0) {
    return;
  }

  // Convert to uppercase for case-insensitive commands
  command.toUpperCase();

  // HELP command
  if (command == "HELP") {
    printHelp();
    return;
  }

  // STATUS command
  if (command == "STATUS") {
    printStatus();
    return;
  }

  // HOME command
  if (command == "HOME") {
    homeAllServos();
    Serial.println("OK:HOME");
    return;
  }

  // SMOOTH command (toggle smooth movement)
  if (command.startsWith("SMOOTH:")) {
    String value = command.substring(7);
    value.trim();
    if (value == "ON" || value == "1") {
      smoothMovementEnabled = true;
      Serial.println("OK:SMOOTH:ON");
    } else if (value == "OFF" || value == "0") {
      smoothMovementEnabled = false;
      Serial.println("OK:SMOOTH:OFF");
    } else {
      Serial.println("ERROR:Invalid SMOOTH value (use ON/OFF)");
    }
    return;
  }

  // HEAD command
  if (command.startsWith("HEAD:")) {
    int angle = command.substring(5).toInt();
    if (setServoAngle(HEAD, angle)) {
      printOk("HEAD", targetAngles[HEAD]);
    } else {
      Serial.println("ERROR:HEAD:Invalid angle");
    }
    return;
  }

  // SERVO command (legacy - same as HEAD)
  if (command.startsWith("SERVO:")) {
    int angle = command.substring(6).toInt();
    if (setServoAngle(HEAD, angle)) {
      printOk("HEAD", targetAngles[HEAD]);
    } else {
      Serial.println("ERROR:SERVO:Invalid angle");
    }
    return;
  }

  // ARMS command
  if (command.startsWith("ARMS:")) {
    if (applyArmOffsets(command.substring(5))) {
      Serial.println("OK:ARMS");
    } else {
      Serial.println("ERROR:ARMS:Invalid format");
    }
    return;
  }

  // SET command (direct servo control)
  if (command.startsWith("SET:")) {
    String payload = command.substring(4);
    int colonPos = payload.indexOf(':');
    if (colonPos > 0) {
      int servoId = payload.substring(0, colonPos).toInt();
      int angle = payload.substring(colonPos + 1).toInt();
      if (servoId >= 0 && servoId < SERVO_COUNT) {
        if (setServoAngle(servoId, angle)) {
          printOk("SET", targetAngles[servoId]);
        } else {
          Serial.println("ERROR:SET:Invalid angle");
        }
      } else {
        Serial.println("ERROR:SET:Invalid servo ID");
      }
    } else {
      Serial.println("ERROR:SET:Invalid format (use SET:ID:ANGLE)");
    }
    return;
  }

  // CALIBRATE command
  if (command.startsWith("CALIBRATE:")) {
    String payload = command.substring(10);
    int colonPos = payload.indexOf(':');
    if (colonPos > 0) {
      int servoId = payload.substring(0, colonPos).toInt();
      int angle = payload.substring(colonPos + 1).toInt();
      if (servoId >= 0 && servoId < SERVO_COUNT) {
        writeServoAngleDirect(servoId, angle);
        currentAngles[servoId] = angle;
        targetAngles[servoId] = angle;
        Serial.print("OK:CALIBRATE:");
        Serial.print(servoId);
        Serial.print(":");
        Serial.println(angle);
      } else {
        Serial.println("ERROR:CALIBRATE:Invalid servo ID");
      }
    } else {
      Serial.println("ERROR:CALIBRATE:Invalid format");
    }
    return;
  }

  // Unknown command
  Serial.print("ERROR:Unknown command: ");
  Serial.println(command);
}

// ============================================================================
// MOVEMENT FUNCTIONS
// ============================================================================

bool applyArmOffsets(String payload) {
  int offsets[6] = {0, 0, 0, 0, 0, 0};
  int startIndex = 0;
  int count = 0;

  // Parse comma-separated offsets
  for (int i = 0; i < 6; i++) {
    int commaIndex = payload.indexOf(',', startIndex);
    String part;
    
    if (commaIndex == -1) {
      part = payload.substring(startIndex);
    } else {
      part = payload.substring(startIndex, commaIndex);
      startIndex = commaIndex + 1;
    }
    
    part.trim();
    if (part.length() == 0) break;
    
    offsets[i] = constrain(part.toInt(), -180, 180);
    count++;
    
    if (commaIndex == -1) break;
  }

  // Validate we got 6 values
  if (count != 6) {
    return false;
  }

  // Apply offsets to arm servos
  setServoOffset(RIGHT_SHOULDER, offsets[0]);
  setServoOffset(RIGHT_ELBOW, offsets[1]);
  setServoOffset(RIGHT_WRIST, offsets[2]);
  setServoOffset(LEFT_SHOULDER, offsets[3]);
  setServoOffset(LEFT_ELBOW, offsets[4]);
  setServoOffset(LEFT_WRIST, offsets[5]);

  return true;
}

void homeAllServos() {
  for (int i = 0; i < SERVO_COUNT; i++) {
    setServoAngle(i, SERVO_NEUTRAL[i]);
  }
}

bool setServoAngle(int servoIndex, int angle) {
  if (servoIndex < 0 || servoIndex >= SERVO_COUNT) {
    return false;
  }
  
  angle = constrain(angle, SERVO_MIN_ANGLE[servoIndex], SERVO_MAX_ANGLE[servoIndex]);
  targetAngles[servoIndex] = angle;
  
  if (!smoothMovementEnabled) {
    currentAngles[servoIndex] = angle;
    writeServoAngleDirect(servoIndex, angle);
  }
  
  return true;
}

bool setServoOffset(int servoIndex, int offset) {
  if (servoIndex < 0 || servoIndex >= SERVO_COUNT) {
    return false;
  }
  
  offset = constrain(offset, -180, 180);
  int angle = SERVO_NEUTRAL[servoIndex] + (offset * SERVO_DIRECTION[servoIndex]);
  return setServoAngle(servoIndex, angle);
}

void writeServoAngleDirect(int servoIndex, int angle) {
  angle = constrain(angle, SERVO_MIN_ANGLE[servoIndex], SERVO_MAX_ANGLE[servoIndex]);
  
  int pulseWidthUs = map(angle, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  uint32_t maxDuty = (1UL << SERVO_PWM_RESOLUTION) - 1;
  uint32_t duty = (pulseWidthUs * maxDuty) / 20000;
  
  ledcWrite(SERVO_PINS[servoIndex], duty);
}

void updateSmoothMovement() {
  unsigned long currentTime = millis();
  
  if (currentTime - lastMoveTime < SMOOTH_DELAY_MS) {
    return;
  }
  
  lastMoveTime = currentTime;
  bool anyMoving = false;
  
  for (int i = 0; i < SERVO_COUNT; i++) {
    if (currentAngles[i] != targetAngles[i]) {
      anyMoving = true;
      int diff = targetAngles[i] - currentAngles[i];
      
      if (abs(diff) <= SMOOTH_STEP) {
        currentAngles[i] = targetAngles[i];
      } else {
        currentAngles[i] += (diff > 0) ? SMOOTH_STEP : -SMOOTH_STEP;
      }
      
      writeServoAngleDirect(i, currentAngles[i]);
    }
  }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

void printOk(const char *name, int angle) {
  Serial.print("OK:");
  Serial.print(name);
  Serial.print(":");
  Serial.println(angle);
}

void printStatus() {
  Serial.println("STATUS:BEGIN");
  
  const char* servoNames[] = {
    "HEAD", "R_SHOULDER", "R_ELBOW", "R_WRIST",
    "L_SHOULDER", "L_ELBOW", "L_WRIST"
  };
  
  for (int i = 0; i < SERVO_COUNT; i++) {
    Serial.print("SERVO:");
    Serial.print(i);
    Serial.print(":");
    Serial.print(servoNames[i]);
    Serial.print(":");
    Serial.print(currentAngles[i]);
    Serial.print(":");
    Serial.println(targetAngles[i]);
  }
  
  Serial.print("SMOOTH:");
  Serial.println(smoothMovementEnabled ? "ON" : "OFF");
  
  Serial.println("STATUS:END");
}

void printHelp() {
  Serial.println("HELP:BEGIN");
  Serial.println("Commands:");
  Serial.println("  HEAD:<angle>           - Move head (0-180)");
  Serial.println("  SERVO:<angle>          - Move head (legacy)");
  Serial.println("  ARMS:<r_sh>,<r_el>,<r_wr>,<l_sh>,<l_el>,<l_wr>");
  Serial.println("                         - Set arm offsets (-180 to 180)");
  Serial.println("  SET:<id>:<angle>       - Set specific servo angle");
  Serial.println("  HOME                   - Move all to neutral (90°)");
  Serial.println("  STATUS                 - Get current positions");
  Serial.println("  SMOOTH:<ON|OFF>        - Toggle smooth movement");
  Serial.println("  CALIBRATE:<id>:<angle> - Calibrate servo neutral");
  Serial.println("  HELP                   - Show this help");
  Serial.println("HELP:END");
}
