#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <ctype.h>
#include <esp_system.h>

#include "BluetoothSerial.h"

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/micro/system_setup.h"

#include "driver_behavior_model.h"
#include "driver_behavior_preprocessing.h"
#include "ftms_lilygo_config.h"

// ======================================================
// FTMS LILYGO-002 COMBINED TELEMETRY FIRMWARE
// Phase 2:
//   - Existing MPU6050 + TensorFlow Lite Micro behavior AI
//   - Bluetooth Classic Vgate ELM327 connected to ECUSimGUI bench ECU
//   - A7670E + DITO LTE
//   - GNSS primary position
//   - Cellular LBS fallback
//   - HTTPS POST to FTMS telemetry schema 1.2
//
// IMPORTANT:
//   - ECUSimGUI-generated OBD values are SIMULATED TEST OBD DATA.
//   - OBD PID 010D speed is NEVER mapped to gnss_speed_kph.
//   - LBS has no GNSS speed.
//   - Telemetry is published every 5 seconds while the last verified
//     real GNSS/LBS position remains fresh.
//   - OBD PID changes do NOT wait for a new position observation.
// ======================================================

// ======================================================
// DEVICE / BOARD CONFIGURATION
// ======================================================

#define SYS_LED 23
#define MPU_ADDR 0x68
#define SOS_BUTTON_PIN 32
#define GNSS_LED_PIN 19
#define VGATE_LED_PIN 18

// LILYGO T-A7670E modem pins
#define BOARD_POWERON_PIN 12
#define MODEM_PWRKEY_PIN  4
#define MODEM_RESET_PIN   5
#define MODEM_DTR_PIN     25
#define MODEM_RX_PIN      27
#define MODEM_TX_PIN      26

HardwareSerial SerialAT(1);

bool modemTimeSynchronized = false;

// ======================================================
// BLUETOOTH CLASSIC SPP
// ======================================================

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled!
#endif

#if !defined(CONFIG_BT_SPP_ENABLED)
#error Bluetooth SPP is not available!
#endif

BluetoothSerial SerialBT;

// ======================================================
// VGATE BLUETOOTH CONFIGURATION
// ======================================================
//
// ECUSimGUI -> Arduino Mega -> MCP2515 -> OBD-II -> Vgate
// -> Bluetooth Classic -> LILYGO -> LTE -> FTMS
//
// The OBD values still originate from ECUSimGUI, so FTMS
// truthfully publishes obd_source = SIMULATED_TEST.
//
bool obdBluetoothConnected = false;
bool elmInitialized = false;

unsigned long lastReconnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL_MS = 5000;

// ======================================================
// OBD POLLING
// ======================================================

unsigned long lastOBDPoll = 0;
const unsigned long OBD_POLL_INTERVAL_MS = 3000;

// FTMS telemetry publishing is independent from position acquisition.
// This lets ECUSimGUI PID changes reach the dashboard quickly.
unsigned long lastTelemetrySend = 0;
const unsigned long TELEMETRY_SEND_INTERVAL_MS = 5000;

float obdEngineRPM = 0.0f;
float obdEngineLoadPercent = 0.0f;
float obdCoolantC = 0.0f;

int obdVehicleSpeedKph = 0;
int obdMapKpa = 0;
float obdThrottlePercent = 0.0f;

bool obdRPMValid = false;
bool obdEngineLoadValid = false;
bool obdCoolantValid = false;

bool obdSpeedValid = false;
bool obdMapValid = false;
bool obdThrottleValid = false;

// ======================================================
// DRIVER BEHAVIOR TIMING
// ======================================================

unsigned long lastDriverBehaviorRun = 0;
const unsigned long DRIVER_BEHAVIOR_INTERVAL_MS = 1000;

// Latest raw model observation.
// We do not map class labels to backend values here yet.
// That mapping will be verified before telemetry publishing.
bool latestBehaviorAvailable = false;
String latestBehaviorClass = "";
float latestBehaviorConfidence = 0.0f;

// ======================================================
// POSITION TIMING
// ======================================================

unsigned long lastPositionCheck = 0;
unsigned long lastLBSCheck = 0;

const unsigned long POSITION_CHECK_INTERVAL_MS = 15000;

// LBS fallback is intentionally slower than GNSS, but frequent enough
// for a near-real-time development demo using fresh LBS observations.
const unsigned long LBS_CHECK_INTERVAL_MS = 30000;

const unsigned long POSITION_MAX_SEND_AGE_MS = 120000;

// ======================================================
// POSITION STATE
// ======================================================

enum PositionSource {
  POSITION_NONE,
  POSITION_GNSS,
  POSITION_CELLULAR_LBS
};

struct PositionData {
  bool valid = false;
  PositionSource source = POSITION_NONE;

  double latitude = 0.0;
  double longitude = 0.0;

  bool gnssSpeedValid = false;
  float gnssSpeedKph = 0.0f;

  bool accuracyValid = false;
  float accuracyMeters = 0.0f;

  unsigned long observedAtMillis = 0;
};

PositionData latestPosition;

uint32_t positionGeneration = 0;
uint32_t telemetrySequence = 0;

// ======================================================
// STATUS LED + PHYSICAL SOS STATE
// ======================================================

const unsigned long SOS_DEBOUNCE_MS = 40;
const unsigned long SOS_PRESS_WINDOW_MS = 1000;
const unsigned long SOS_CLEAR_HOLD_MS = 5000;
const unsigned long SOS_RETRY_INTERVAL_MS = 15000;

bool sosActive = false;
bool sosRawPressed = false;
bool sosDebouncedPressed = false;
bool sosLongHoldHandled = false;
uint8_t sosShortPressCount = 0;
unsigned long sosRawChangedAt = 0;
unsigned long sosPressedAt = 0;
unsigned long sosLastShortPressAt = 0;
unsigned long sosLastTransmitAttempt = 0;

enum SOSPendingAction { SOS_PENDING_NONE, SOS_PENDING_ACTIVATE, SOS_PENDING_CLEAR };
SOSPendingAction sosPendingAction = SOS_PENDING_NONE;

// ======================================================
// TENSORFLOW LITE
// ======================================================

constexpr int kTensorArenaSize = 30 * 1024;

alignas(16) uint8_t tensor_arena[kTensorArenaSize];

const tflite::Model* tflite_model = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
bool tfliteReady = false;

TfLiteTensor* input = nullptr;
TfLiteTensor* output = nullptr;

// ======================================================
// TENSORFLOW PREPROCESSING
// ======================================================

float scaleFeature(float value, int index) {
  return (
    value - driver_behavior_scaler_mean[index]
  ) / driver_behavior_scaler_scale[index];
}

int8_t quantizeInput(float value) {
  int32_t quantized =
    round(value / input->params.scale)
    + input->params.zero_point;

  if (quantized > 127) {
    quantized = 127;
  }

  if (quantized < -128) {
    quantized = -128;
  }

  return (int8_t)quantized;
}

float dequantizeOutput(int8_t value) {
  return (
    value - output->params.zero_point
  ) * output->params.scale;
}

// ======================================================
// MPU6050
// ======================================================

bool readMPU6050(
  float &accX,
  float &accY,
  float &accZ,
  float &gyroX,
  float &gyroY,
  float &gyroZ
) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  Wire.requestFrom(MPU_ADDR, 14, true);

  if (Wire.available() < 14) {
    return false;
  }

  int16_t rawAccX = Wire.read() << 8 | Wire.read();
  int16_t rawAccY = Wire.read() << 8 | Wire.read();
  int16_t rawAccZ = Wire.read() << 8 | Wire.read();

  Wire.read();
  Wire.read();

  int16_t rawGyroX = Wire.read() << 8 | Wire.read();
  int16_t rawGyroY = Wire.read() << 8 | Wire.read();
  int16_t rawGyroZ = Wire.read() << 8 | Wire.read();

  accX = rawAccX / 16384.0f;
  accY = rawAccY / 16384.0f;
  accZ = rawAccZ / 16384.0f;

  gyroX = rawGyroX / 131.0f;
  gyroY = rawGyroY / 131.0f;
  gyroZ = rawGyroZ / 131.0f;

  return true;
}

// ======================================================
// SENSOR PRINTING
// ======================================================

void printSensorValues(
  float accX,
  float accY,
  float accZ,
  float gyroX,
  float gyroY,
  float gyroZ
) {
  Serial.print("[MPU] Acc: ");

  Serial.print(accX, 3);
  Serial.print(", ");
  Serial.print(accY, 3);
  Serial.print(", ");
  Serial.print(accZ, 3);

  Serial.print(" | Gyro: ");

  Serial.print(gyroX, 3);
  Serial.print(", ");
  Serial.print(gyroY, 3);
  Serial.print(", ");
  Serial.print(gyroZ, 3);
}

// ======================================================
// DRIVER BEHAVIOR INFERENCE
// ======================================================

void runPrediction() {
  if (!tfliteReady) {
    latestBehaviorAvailable = false;
    return;
  }

  float accX;
  float accY;
  float accZ;

  float gyroX;
  float gyroY;
  float gyroZ;

  if (!readMPU6050(
    accX,
    accY,
    accZ,
    gyroX,
    gyroY,
    gyroZ
  )) {
    latestBehaviorAvailable = false;
    Serial.println("[MPU] Read failed.");
    return;
  }

  float accMagnitude =
    sqrt(
      accX * accX +
      accY * accY +
      accZ * accZ
    );

  float gyroMagnitude =
    sqrt(
      gyroX * gyroX +
      gyroY * gyroY +
      gyroZ * gyroZ
    );

  float accDelta =
    fabs(accMagnitude - 1.0f);

  // Existing prototype motion gate.
  if (
    accDelta < 0.18f &&
    gyroMagnitude < 20.0f
  ) {
    latestBehaviorAvailable = false;

    printSensorValues(
      accX,
      accY,
      accZ,
      gyroX,
      gyroY,
      gyroZ
    );

    Serial.println(" | Status: no_event");
    return;
  }

  float features[DRIVER_BEHAVIOR_FEATURE_COUNT] = {
    accX,
    accY,
    accZ,
    gyroX,
    gyroY,
    gyroZ,
    accMagnitude,
    gyroMagnitude
  };

  for (
    int i = 0;
    i < DRIVER_BEHAVIOR_FEATURE_COUNT;
    i++
  ) {
    float scaledValue =
      scaleFeature(features[i], i);

    input->data.int8[i] =
      quantizeInput(scaledValue);
  }

  if (interpreter->Invoke() != kTfLiteOk) {
    latestBehaviorAvailable = false;
    Serial.println("[TFLITE] Inference failed.");
    return;
  }

  int bestIndex = 0;

  float bestScore =
    dequantizeOutput(
      output->data.int8[0]
    );

  for (
    int i = 1;
    i < DRIVER_BEHAVIOR_CLASS_COUNT;
    i++
  ) {
    float score =
      dequantizeOutput(
        output->data.int8[i]
      );

    if (score > bestScore) {
      bestScore = score;
      bestIndex = i;
    }
  }

  latestBehaviorAvailable = true;
  latestBehaviorClass =
    driver_behavior_class_names[bestIndex];
  latestBehaviorConfidence =
    bestScore;

  printSensorValues(
    accX,
    accY,
    accZ,
    gyroX,
    gyroY,
    gyroZ
  );

  Serial.print(" | Prediction: ");
  Serial.print(latestBehaviorClass);

  Serial.print(" | Confidence: ");
  Serial.println(latestBehaviorConfidence, 3);
}

// ======================================================
// ELM327 COMMUNICATION
// ======================================================

String sendELMCommand(
  const char* command,
  unsigned long timeoutMs = 1500
) {
  String response = "";

  if (!SerialBT.connected()) {
    return response;
  }

  while (SerialBT.available()) {
    SerialBT.read();
  }

  Serial.print("[ELM TX] ");
  Serial.println(command);

  SerialBT.print(command);
  SerialBT.write('\r');

  unsigned long startTime = millis();

  while (millis() - startTime < timeoutMs) {
    while (SerialBT.available()) {
      char c = SerialBT.read();

      if (c == '>') {
        return response;
      }

      response += c;
    }

    delay(5);
  }

  return response;
}

// ======================================================
// ELM327 INITIALIZATION
// ======================================================

bool initializeELM327() {
  if (!SerialBT.connected()) {
    return false;
  }

  Serial.println();
  Serial.println("================================");
  Serial.println("Initializing physical Vgate ELM327");
  Serial.println("ECUSim CAN: ISO 15765-4 / 11-bit / 500 kbps");
  Serial.println("================================");

  String response;

  // Reset ELM327/Vgate.
  response = sendELMCommand("ATZ", 3500);
  Serial.print("[ELM RX] ");
  Serial.println(response);

  delay(800);

  // Disable command echo.
  response = sendELMCommand("ATE0");
  Serial.print("[ELM RX] ");
  Serial.println(response);

  // Disable line feeds.
  response = sendELMCommand("ATL0");
  Serial.print("[ELM RX] ");
  Serial.println(response);

  // Remove spaces from ELM responses.
  response = sendELMCommand("ATS0");
  Serial.print("[ELM RX] ");
  Serial.println(response);

  // Hide CAN headers so PID parsers continue to receive compact 41xx data.
  response = sendELMCommand("ATH0");
  Serial.print("[ELM RX] ");
  Serial.println(response);

  // Keep CAN automatic formatting enabled.
  response = sendELMCommand("ATCAF1");
  Serial.print("[ELM RX] ");
  Serial.println(response);

  // Adaptive timing helps physical ELM327/Vgate adapters.
  response = sendELMCommand("ATAT1");
  Serial.print("[ELM RX] ");
  Serial.println(response);

  // Protocol 6:
  // ISO 15765-4 CAN, 11-bit identifier, 500 kbps.
  // This matches the working Arduino Mega + MCP2515 ECUSim bench.
  response = sendELMCommand("ATSP6", 2500);
  Serial.print("[ELM RX] ");
  Serial.println(response);

  // Print selected protocol for diagnostics.
  response = sendELMCommand("ATDP", 2500);
  Serial.print("[ELM PROTOCOL] ");
  Serial.println(response);

  // Basic ECU communication check.
  response = sendELMCommand("0100", 3000);
  Serial.print("[ELM PID 0100] ");
  Serial.println(response);

  String upperResponse = response;
  upperResponse.toUpperCase();

  if (
    upperResponse.length() == 0
    ||
    upperResponse.indexOf("NO DATA") >= 0
    ||
    upperResponse.indexOf("UNABLE TO CONNECT") >= 0
    ||
    upperResponse.indexOf("ERROR") >= 0
  ) {
    Serial.println("[ELM] ECU PID check failed.");
    Serial.println("[ELM] Verify Vgate power, CAN wiring, ECUSim firmware, and protocol.");
    return false;
  }

  Serial.println("Vgate ELM327 initialization finished.");
  Serial.println("================================");
  Serial.println();

  return true;
}

// ======================================================
// BLUETOOTH CONNECTION
// ======================================================

void printVgateAddress() {
  Serial.print(
    "[BT] Target Vgate MAC: "
  );

  for (
    int i = 0;
    i < 6;
    i++
  ) {
    if (
      VGATE_BT_ADDRESS[i] < 0x10
    ) {
      Serial.print("0");
    }

    Serial.print(
      VGATE_BT_ADDRESS[i],
      HEX
    );

    if (
      i < 5
    ) {
      Serial.print(":");
    }
  }

  Serial.println();
}

bool connectVgateDevice() {
  if (
    SerialBT.connected()
  ) {
    return true;
  }

  Serial.println();
  Serial.println(
    "[BT] Connecting directly to physical Vgate..."
  );

  printVgateAddress();

  // First choice: deterministic connection to the exact paired
  // Bluetooth Classic hardware address.
  bool connected =
    SerialBT.connect(
      VGATE_BT_ADDRESS
    );

  if (
    connected
  ) {
    Serial.println();
    Serial.println(
      "*** VGATE BLUETOOTH CONNECTED BY MAC! ***"
    );

    Serial.print(
      "[BT] Device name: "
    );

    Serial.println(
      VGATE_BT_NAME
    );

    Serial.println();

    return true;
  }

  Serial.println(
    "[BT] Direct MAC connection failed."
  );

  // Safe fallback for adapters that resolve their RFCOMM/SPP
  // service more reliably by paired Bluetooth name.
  Serial.print(
    "[BT] Trying fallback device name: "
  );

  Serial.println(
    VGATE_BT_NAME
  );

  connected =
    SerialBT.connect(
      String(
        VGATE_BT_NAME
      )
    );

  if (
    connected
  ) {
    Serial.println();
    Serial.println(
      "*** VGATE BLUETOOTH CONNECTED BY NAME! ***"
    );

    Serial.println();

    return true;
  }

  SerialBT.disconnect();

  Serial.println();
  Serial.println(
    "*** VGATE BLUETOOTH CONNECTION FAILED ***"
  );

  Serial.println(
    "[BT] Make sure the phone OBD scanner is disconnected."
  );

  Serial.println(
    "[BT] Verify Vgate power and pairing PIN."
  );

  Serial.println();

  return false;
}

bool connectVgateOBD() {
  Serial.println();
  Serial.println(
    "================================"
  );

  Serial.println(
    "FTMS Bluetooth Classic SPP"
  );

  Serial.println(
    "Vgate V-LINK + ECUSimGUI Bench"
  );

  Serial.println(
    "================================"
  );

  // ESP32 acts as Bluetooth Classic master/client.
  if (
    !SerialBT.begin(
      "FTMS-LILYGO",
      true
    )
  ) {
    Serial.println(
      "*** Bluetooth initialization FAILED ***"
    );

    return false;
  }

  // ESP32 Arduino Core 3.x requires both the PIN pointer
  // and the PIN length.
  bool pinConfigured =
    SerialBT.setPin(
      VGATE_BT_PIN,
      static_cast<uint8_t>(
        strlen(
          VGATE_BT_PIN
        )
      )
    );

  if (
    pinConfigured
  ) {
    Serial.println(
      "[BT] Pairing PIN configured."
    );
  } else {
    Serial.println(
      "[BT] Warning: pairing PIN configuration failed."
    );
  }

  Serial.println(
    "Bluetooth initialized in master mode."
  );

  Serial.println(
    "Phone OBD scanner must be DISCONNECTED from Vgate."
  );

  bool connected =
    connectVgateDevice();

  Serial.println(
    "================================"
  );

  return connected;
}

// ======================================================
// HEX HELPERS
// ======================================================

String compactHexResponse(const String &raw) {
  String result = "";

  for (unsigned int i = 0; i < raw.length(); i++) {
    char c = raw[i];

    if (isxdigit((unsigned char)c)) {
      result += (char)toupper(c);
    }
  }

  return result;
}

int parseHexByte(
  const String &hex,
  int index
) {
  if (index < 0) {
    return -1;
  }

  if (index + 2 > (int)hex.length()) {
    return -1;
  }

  String byteText =
    hex.substring(
      index,
      index + 2
    );

  return (int)strtol(
    byteText.c_str(),
    nullptr,
    16
  );
}

// ======================================================
// PID PARSERS
// ======================================================

bool parseEngineRPM(
  const String &raw,
  float &rpm
) {
  String hex =
    compactHexResponse(raw);

  int position =
    hex.indexOf("410C");

  if (position < 0) {
    return false;
  }

  int a =
    parseHexByte(
      hex,
      position + 4
    );

  int b =
    parseHexByte(
      hex,
      position + 6
    );

  if (a < 0 || b < 0) {
    return false;
  }

  rpm =
    ((a * 256.0f) + b) / 4.0f;

  return true;
}

bool parseEngineLoad(
  const String &raw,
  float &loadPercent
) {
  String hex =
    compactHexResponse(raw);

  int position =
    hex.indexOf("4104");

  if (position < 0) {
    return false;
  }

  int a =
    parseHexByte(
      hex,
      position + 4
    );

  if (a < 0) {
    return false;
  }

  loadPercent =
    (a * 100.0f) / 255.0f;

  return true;
}

bool parseCoolantTemperature(
  const String &raw,
  float &coolantC
) {
  String hex =
    compactHexResponse(raw);

  int position =
    hex.indexOf("4105");

  if (position < 0) {
    return false;
  }

  int a =
    parseHexByte(
      hex,
      position + 4
    );

  if (a < 0) {
    return false;
  }

  coolantC =
    a - 40.0f;

  return true;
}

bool parseVehicleSpeed(
  const String &raw,
  int &speedKph
) {
  String hex =
    compactHexResponse(raw);

  int position =
    hex.indexOf("410D");

  if (position < 0) {
    return false;
  }

  int a =
    parseHexByte(
      hex,
      position + 4
    );

  if (a < 0) {
    return false;
  }

  speedKph = a;
  return true;
}

bool parseMAP(
  const String &raw,
  int &mapKpa
) {
  String hex =
    compactHexResponse(raw);

  int position =
    hex.indexOf("410B");

  if (position < 0) {
    return false;
  }

  int a =
    parseHexByte(
      hex,
      position + 4
    );

  if (a < 0) {
    return false;
  }

  mapKpa = a;
  return true;
}

bool parseThrottlePosition(
  const String &raw,
  float &throttlePercent
) {
  String hex =
    compactHexResponse(raw);

  int position =
    hex.indexOf("4111");

  if (position < 0) {
    return false;
  }

  int a =
    parseHexByte(
      hex,
      position + 4
    );

  if (a < 0) {
    return false;
  }

  throttlePercent =
    (a * 100.0f) / 255.0f;

  return true;
}

// ======================================================
// AUTOMATIC OBD POLLING
// ======================================================

void pollOBD() {
  if (!SerialBT.connected()) {
    return;
  }

  Serial.println();
  Serial.println("========== OBD POLL ==========");

  String rpmResponse =
    sendELMCommand("010C");

  obdRPMValid =
    parseEngineRPM(
      rpmResponse,
      obdEngineRPM
    );

  if (obdRPMValid) {
    Serial.print("[OBD] Engine RPM: ");
    Serial.print(obdEngineRPM, 2);
    Serial.println(" rpm");
  } else {
    Serial.print("[OBD] RPM parse failed. Raw: ");
    Serial.println(rpmResponse);
  }

  // --------------------------------------------------
  // ENGINE LOAD
  // PID 01 04
  // FTMS schema-supported simulated OBD field.
  // --------------------------------------------------

  String engineLoadResponse =
    sendELMCommand("0104");

  obdEngineLoadValid =
    parseEngineLoad(
      engineLoadResponse,
      obdEngineLoadPercent
    );

  if (obdEngineLoadValid) {
    Serial.print("[OBD] Engine Load: ");
    Serial.print(obdEngineLoadPercent, 1);
    Serial.println(" %");
  } else {
    Serial.print("[OBD] Engine Load parse failed. Raw: ");
    Serial.println(engineLoadResponse);
  }

  // --------------------------------------------------
  // COOLANT TEMPERATURE
  // PID 01 05
  // FTMS schema-supported simulated OBD field.
  // --------------------------------------------------

  String coolantResponse =
    sendELMCommand("0105");

  obdCoolantValid =
    parseCoolantTemperature(
      coolantResponse,
      obdCoolantC
    );

  if (obdCoolantValid) {
    Serial.print("[OBD] Coolant Temperature: ");
    Serial.print(obdCoolantC, 1);
    Serial.println(" C");
  } else {
    Serial.print("[OBD] Coolant parse failed. Raw: ");
    Serial.println(coolantResponse);
  }

  String speedResponse =
    sendELMCommand("010D");

  obdSpeedValid =
    parseVehicleSpeed(
      speedResponse,
      obdVehicleSpeedKph
    );

  if (obdSpeedValid) {
    Serial.print("[OBD] Vehicle Speed: ");
    Serial.print(obdVehicleSpeedKph);
    Serial.println(" km/h");
  } else {
    Serial.print("[OBD] Speed parse failed. Raw: ");
    Serial.println(speedResponse);
  }

  String mapResponse =
    sendELMCommand("010B");

  obdMapValid =
    parseMAP(
      mapResponse,
      obdMapKpa
    );

  if (obdMapValid) {
    Serial.print("[OBD] MAP: ");
    Serial.print(obdMapKpa);
    Serial.println(" kPa");
  } else {
    Serial.print("[OBD] MAP parse failed. Raw: ");
    Serial.println(mapResponse);
  }

  String throttleResponse =
    sendELMCommand("0111");

  obdThrottleValid =
    parseThrottlePosition(
      throttleResponse,
      obdThrottlePercent
    );

  if (obdThrottleValid) {
    Serial.print("[OBD] Throttle Position: ");
    Serial.print(obdThrottlePercent, 1);
    Serial.println(" %");
  } else {
    Serial.print("[OBD] Throttle parse failed. Raw: ");
    Serial.println(throttleResponse);
  }

  Serial.println();
  Serial.println("------ FTMS OBD SUMMARY ------");

  Serial.print("RPM: ");
  if (obdRPMValid) {
    Serial.print(obdEngineRPM, 2);
    Serial.print(" rpm");
  } else {
    Serial.print("unavailable");
  }

  Serial.print(" | Engine Load: ");
  if (obdEngineLoadValid) {
    Serial.print(obdEngineLoadPercent, 1);
    Serial.print(" %");
  } else {
    Serial.print("unavailable");
  }

  Serial.print(" | Coolant: ");
  if (obdCoolantValid) {
    Serial.print(obdCoolantC, 1);
    Serial.print(" C");
  } else {
    Serial.print("unavailable");
  }

  Serial.print(" | OBD Speed: ");
  if (obdSpeedValid) {
    Serial.print(obdVehicleSpeedKph);
    Serial.print(" km/h");
  } else {
    Serial.print("unavailable");
  }

  Serial.print(" | MAP: ");
  if (obdMapValid) {
    Serial.print(obdMapKpa);
    Serial.print(" kPa");
  } else {
    Serial.print("unavailable");
  }

  Serial.print(" | Throttle: ");
  if (obdThrottleValid) {
    Serial.print(obdThrottlePercent, 1);
    Serial.print(" %");
  } else {
    Serial.print("unavailable");
  }

  Serial.println();
  Serial.println("------------------------------");
  Serial.println();
}

// ======================================================
// MODEM HELPERS
// ======================================================

String readModem(
  unsigned long timeoutMs = 2000
) {
  String response = "";

  unsigned long start =
    millis();

  while (
    millis() - start < timeoutMs
  ) {
    while (
      SerialAT.available()
    ) {
      char c =
        SerialAT.read();

      response += c;
      Serial.write(c);
    }

    delay(5);
  }

  return response;
}

String sendAT(
  const String& command,
  unsigned long timeoutMs = 2000
) {
  while (
    SerialAT.available()
  ) {
    SerialAT.read();
  }

  Serial.println();
  Serial.print(">> ");
  Serial.println(command);

  SerialAT.print(command);
  SerialAT.print("\r\n");

  String response =
    readModem(timeoutMs);

  Serial.println();

  return response;
}


// ======================================================
// FAST MODEM COMMAND HELPER
// ======================================================
//
// For commands whose useful response finishes with OK/ERROR.
// This avoids waiting for the whole timeout on every 5-second
// telemetry cycle.
//
// Do not use this for asynchronous-result commands such as
// AT+CLBS=1 because +CLBS arrives after the initial OK.
//
String sendATQuick(
  const String& command,
  unsigned long timeoutMs = 3000
) {
  while (
    SerialAT.available()
  ) {
    SerialAT.read();
  }

  Serial.println();
  Serial.print(">> ");
  Serial.println(command);

  SerialAT.print(command);
  SerialAT.print("\r\n");

  String response = "";
  unsigned long startedAt =
    millis();

  while (
    millis() - startedAt < timeoutMs
  ) {
    while (
      SerialAT.available()
    ) {
      char c =
        SerialAT.read();

      response += c;
      Serial.write(c);

      if (
        response.indexOf("\r\nOK\r\n") >= 0
        ||
        response.indexOf("\nOK\r\n") >= 0
        ||
        response.indexOf("\r\nERROR\r\n") >= 0
        ||
        response.indexOf("\nERROR\r\n") >= 0
        ||
        response.indexOf("+CME ERROR:") >= 0
        ||
        response.indexOf("+CMS ERROR:") >= 0
      ) {
        Serial.println();
        return response;
      }
    }

    delay(5);
  }

  Serial.println();
  return response;
}

// Forward declaration. The implementation is below in HTTP helpers.
String sendATUntilMarker(
  const String& command,
  const String& marker,
  unsigned long timeoutMs
);

// ======================================================
// MODEM STARTUP
// ======================================================

bool testAT() {
  for (
    int attempt = 0;
    attempt < 5;
    attempt++
  ) {
    String response =
      sendAT(
        "AT",
        1000
      );

    if (
      response.indexOf("OK")
      >= 0
    ) {
      return true;
    }

    delay(500);
  }

  return false;
}

bool startModem() {
  pinMode(
    BOARD_POWERON_PIN,
    OUTPUT
  );

  digitalWrite(
    BOARD_POWERON_PIN,
    HIGH
  );

  pinMode(
    MODEM_DTR_PIN,
    OUTPUT
  );

  digitalWrite(
    MODEM_DTR_PIN,
    LOW
  );

  SerialAT.begin(
    115200,
    SERIAL_8N1,
    MODEM_RX_PIN,
    MODEM_TX_PIN
  );

  delay(500);

  pinMode(
    MODEM_RESET_PIN,
    OUTPUT
  );

  digitalWrite(
    MODEM_RESET_PIN,
    LOW
  );

  delay(100);

  digitalWrite(
    MODEM_RESET_PIN,
    HIGH
  );

  delay(2600);

  digitalWrite(
    MODEM_RESET_PIN,
    LOW
  );

  pinMode(
    MODEM_PWRKEY_PIN,
    OUTPUT
  );

  digitalWrite(
    MODEM_PWRKEY_PIN,
    LOW
  );

  delay(100);

  digitalWrite(
    MODEM_PWRKEY_PIN,
    HIGH
  );

  delay(100);

  digitalWrite(
    MODEM_PWRKEY_PIN,
    LOW
  );

  Serial.println("[MODEM] Waiting for A7670E...");
  delay(5000);

  return testAT();
}

// ======================================================
// LTE / DITO
// ======================================================

void configureLTE() {
  Serial.println();
  Serial.println("================================");
  Serial.println("LTE / DITO INITIALIZATION");
  Serial.println("================================");

  sendAT("AT+CPIN?", 2000);
  sendAT("AT+CSQ", 2000);
  sendAT("AT+CEREG?", 3000);
  sendAT("AT+COPS?", 5000);

  String command =
    String("AT+CGDCONT=1,\"IP\",\"")
    + APN
    + "\"";

  sendAT(command, 3000);
  sendAT("AT+CGATT=1", 7000);
  sendAT("AT+CGATT?", 3000);
  sendAT("AT+CGACT=1,1", 7000);
  sendAT("AT+CGPADDR=1", 3000);

  // Keep automatic network time-zone updates enabled when the carrier provides them.
  sendAT("AT+CTZU=1", 3000);

  // Explicitly synchronize the modem clock through NTP.
  // A76XX timezone uses quarter-hours. +8 hours = 32 quarter-hours.
  sendAT("AT+CNTPCFG=\"CID\",1", 3000);
  sendAT("AT+CNTP=\"pool.ntp.org\",32", 3000);

  String ntpResponse =
    sendAT(
      "AT+CNTP",
      15000
    );

  modemTimeSynchronized =
    ntpResponse.indexOf("+CNTP: 0") >= 0;

  if (modemTimeSynchronized) {
    Serial.println("[TIME] NTP synchronization succeeded.");
  } else {
    Serial.println("[TIME] NTP synchronization failed.");
    Serial.println("[TIME] Telemetry transmission will remain blocked.");
  }

  sendAT("AT+CCLK?", 3000);
}

// ======================================================
// GNSS
// ======================================================

void startGNSS() {
  Serial.println();
  Serial.println("================================");
  Serial.println("GNSS INITIALIZATION");
  Serial.println("================================");

  // Do not force CGNSSMODE here.
  // The exact modem firmware previously rejected CGNSSMODE=3.
  sendAT("AT+CGNSSPWR=1", 8000);
  sendAT("AT+CGNSSPWR?", 3000);
}

// ======================================================
// CSV HELPER
// ======================================================

String csvField(
  const String& text,
  int fieldIndex
) {
  int currentField = 0;
  int start = 0;

  for (
    int i = 0;
    i <= text.length();
    i++
  ) {
    bool separator =
      (
        i == text.length()
        ||
        text[i] == ','
      );

    if (separator) {
      if (
        currentField
        == fieldIndex
      ) {
        String value =
          text.substring(
            start,
            i
          );

        value.trim();
        return value;
      }

      currentField++;
      start = i + 1;
    }
  }

  return "";
}

// ======================================================
// GNSS COORDINATE CONVERSION
// ======================================================

double gnssToDecimalDegrees(
  double rawCoordinate
) {
  int degrees =
    (int)(
      rawCoordinate / 100.0
    );

  double minutes =
    rawCoordinate
    -
    (
      degrees * 100.0
    );

  return
    degrees
    +
    (
      minutes / 60.0
    );
}

// ======================================================
// GNSS PARSER
// ======================================================

bool parseGNSS(
  const String& response,
  PositionData& position
) {
  int prefix =
    response.indexOf(
      "+CGNSSINFO:"
    );

  if (
    prefix < 0
  ) {
    return false;
  }

  int lineStart =
    prefix
    +
    String(
      "+CGNSSINFO:"
    ).length();

  int lineEnd =
    response.indexOf(
      '\n',
      lineStart
    );

  if (
    lineEnd < 0
  ) {
    lineEnd =
      response.length();
  }

  String line =
    response.substring(
      lineStart,
      lineEnd
    );

  line.trim();

  // A76XX CGNSSINFO fields:
  // 0 mode
  // 1 GPS-SVs
  // 2 GLONASS-SVs
  // 3 BEIDOU-SVs
  // 4 latitude (ddmm.mmmmmm)
  // 5 N/S
  // 6 longitude (dddmm.mmmmmm)
  // 7 E/W
  // 8 date
  // 9 UTC time
  // 10 altitude
  // 11 speed over ground in knots
  // 12 course
  // 13 PDOP
  // 14 HDOP
  // 15 VDOP

  String latitudeText =
    csvField(
      line,
      4
    );

  String latitudeDirection =
    csvField(
      line,
      5
    );

  String longitudeText =
    csvField(
      line,
      6
    );

  String longitudeDirection =
    csvField(
      line,
      7
    );

  String speedText =
    csvField(
      line,
      11
    );

  if (
    latitudeText.length() == 0
    ||
    longitudeText.length() == 0
  ) {
    return false;
  }

  double latitudeRaw =
    latitudeText.toDouble();

  double longitudeRaw =
    longitudeText.toDouble();

  double latitude =
    gnssToDecimalDegrees(
      latitudeRaw
    );

  double longitude =
    gnssToDecimalDegrees(
      longitudeRaw
    );

  if (
    latitudeDirection == "S"
  ) {
    latitude =
      -latitude;
  }

  if (
    longitudeDirection == "W"
  ) {
    longitude =
      -longitude;
  }

  // If a GNSS fix exists but speed text is unexpectedly absent,
  // keep the position but mark GNSS speed unavailable rather than inventing 0.
  bool speedAvailable =
    speedText.length() > 0;

  float speedKph = 0.0f;

  if (
    speedAvailable
  ) {
    float speedKnots =
      speedText.toFloat();

    speedKph =
      speedKnots * 1.852f;
  }

  position.valid = true;
  position.source = POSITION_GNSS;
  position.latitude = latitude;
  position.longitude = longitude;
  position.gnssSpeedValid = speedAvailable;
  position.gnssSpeedKph = speedKph;
  position.accuracyValid = false;
  position.accuracyMeters = 0.0f;
  position.observedAtMillis = millis();

  return true;
}

// ======================================================
// READ GNSS
// ======================================================

bool tryGNSS(
  PositionData& position
) {
  Serial.println();
  Serial.println("[POSITION] Trying GNSS...");

  String response =
    sendATUntilMarker(
      "AT+CGNSSINFO",
      "+CGNSSINFO:",
      4000
    );

  if (
    parseGNSS(
      response,
      position
    )
  ) {
    Serial.println();
    Serial.println("******** GNSS FIX ********");
    Serial.println("[POSITION] SOURCE: GNSS");

    Serial.print("[POSITION] Latitude: ");
    Serial.println(position.latitude, 6);

    Serial.print("[POSITION] Longitude: ");
    Serial.println(position.longitude, 6);

    Serial.print("[POSITION] GNSS Speed: ");

    if (
      position.gnssSpeedValid
    ) {
      Serial.print(position.gnssSpeedKph, 2);
      Serial.println(" km/h");
    } else {
      Serial.println("unavailable");
    }

    Serial.println("**************************");

    return true;
  }

  Serial.println("[POSITION] GNSS fix unavailable.");
  return false;
}

// ======================================================
// LBS PARSER
// ======================================================

bool parseLBS(
  const String& response,
  PositionData& position
) {
  int prefix =
    response.indexOf(
      "+CLBS:"
    );

  if (
    prefix < 0
  ) {
    return false;
  }

  int lineStart =
    prefix
    +
    String(
      "+CLBS:"
    ).length();

  int lineEnd =
    response.indexOf(
      '\n',
      lineStart
    );

  if (
    lineEnd < 0
  ) {
    lineEnd =
      response.length();
  }

  String line =
    response.substring(
      lineStart,
      lineEnd
    );

  line.trim();

  String resultCode =
    csvField(
      line,
      0
    );

  if (
    resultCode != "0"
  ) {
    return false;
  }

  String latitudeText =
    csvField(
      line,
      1
    );

  String longitudeText =
    csvField(
      line,
      2
    );

  String accuracyText =
    csvField(
      line,
      3
    );

  if (
    latitudeText.length() == 0
    ||
    longitudeText.length() == 0
    ||
    accuracyText.length() == 0
  ) {
    return false;
  }

  float accuracy =
    accuracyText.toFloat();

  if (
    accuracy <= 0.0f
  ) {
    return false;
  }

  position.valid = true;
  position.source = POSITION_CELLULAR_LBS;
  position.latitude = latitudeText.toDouble();
  position.longitude = longitudeText.toDouble();

  // Cellular LBS is not GNSS and does not supply GNSS speed.
  position.gnssSpeedValid = false;
  position.gnssSpeedKph = 0.0f;

  position.accuracyValid = true;
  position.accuracyMeters = accuracy;
  position.observedAtMillis = millis();

  return true;
}

// ======================================================
// READ CELLULAR LBS
// ======================================================

bool tryCellularLBS(
  PositionData& position
) {
  Serial.println();
  Serial.println("[POSITION] Trying Cellular LBS...");

  String response =
    sendATUntilMarker(
      "AT+CLBS=1",
      "+CLBS:",
      12000
    );

  if (
    parseLBS(
      response,
      position
    )
  ) {
    Serial.println();
    Serial.println("***** CELLULAR LBS FIX *****");
    Serial.println("[POSITION] SOURCE: CELLULAR_LBS");

    Serial.print("[POSITION] Latitude: ");
    Serial.println(position.latitude, 6);

    Serial.print("[POSITION] Longitude: ");
    Serial.println(position.longitude, 6);

    Serial.print("[POSITION] Accuracy: ~");
    Serial.print(position.accuracyMeters, 0);
    Serial.println(" m");

    Serial.println("[POSITION] GNSS speed: unavailable");
    Serial.println("****************************");

    return true;
  }

  Serial.println("[POSITION] Cellular LBS unavailable.");
  return false;
}

// ======================================================
// POSITION MANAGER
// ======================================================

bool updatePosition() {
  PositionData newPosition;

  // 1. Always prefer a fresh real GNSS fix.
  if (
    tryGNSS(
      newPosition
    )
  ) {
    latestPosition =
      newPosition;

    positionGeneration++;

    return true;
  }

  // 2. GNSS unavailable: rate-limited cellular LBS fallback.
  unsigned long now =
    millis();

  if (
    lastLBSCheck == 0
    ||
    now - lastLBSCheck
      >= LBS_CHECK_INTERVAL_MS
  ) {
    lastLBSCheck =
      now;

    if (
      tryCellularLBS(
        newPosition
      )
    ) {
      latestPosition =
        newPosition;

      positionGeneration++;

      return true;
    }
  }

  // 3. No new position: preserve last verified one locally.
  Serial.println();
  Serial.println("[POSITION] No new position.");

  if (
    latestPosition.valid
  ) {
    Serial.println(
      "[POSITION] Preserving last verified position locally."
    );
  } else {
    Serial.println(
      "[POSITION] No verified position available yet."
    );
  }

  return false;
}

// ======================================================
// NETWORK TIME
// ======================================================

bool getNetworkTimestampISO8601(
  String &isoTimestamp
) {
  String response =
    sendATQuick(
      "AT+CCLK?",
      2000
    );

  int prefix =
    response.indexOf(
      "+CCLK:"
    );

  if (
    prefix < 0
  ) {
    return false;
  }

  int firstQuote =
    response.indexOf(
      '"',
      prefix
    );

  int secondQuote =
    response.indexOf(
      '"',
      firstQuote + 1
    );

  if (
    firstQuote < 0
    ||
    secondQuote < 0
  ) {
    return false;
  }

  String clockText =
    response.substring(
      firstQuote + 1,
      secondQuote
    );

  // Expected:
  // yy/MM/dd,hh:mm:ss+zz
  // where zz is quarter-hours from UTC.

  if (
    clockText.length() < 20
  ) {
    return false;
  }

  int year =
    clockText.substring(
      0,
      2
    ).toInt();

  int month =
    clockText.substring(
      3,
      5
    ).toInt();

  int day =
    clockText.substring(
      6,
      8
    ).toInt();

  int hour =
    clockText.substring(
      9,
      11
    ).toInt();

  int minute =
    clockText.substring(
      12,
      14
    ).toInt();

  int second =
    clockText.substring(
      15,
      17
    ).toInt();

  char tzSign =
    clockText.charAt(
      17
    );

  int tzQuarterHours =
    clockText.substring(
      18
    ).toInt();

  // A valid modem/network clock is acceptable even when the
  // explicit AT+CNTP success flag was not captured during startup.
  //
  // The A7670E can receive a correct clock from the cellular network
  // (CTZU/network time) even if the explicit CNTP response was missed.
  // We still reject obviously invalid/reset clocks below.
  if (!modemTimeSynchronized) {
    Serial.println(
      "[TIME] NTP success flag not set; validating modem CCLK directly."
    );
  }

  // Reject obviously unsynchronized/invalid modem clocks.
  // This also prevents the modem reset value 70/01/01 from becoming year 2070.
  if (
    year < 24
    ||
    year > 49
    ||
    month < 1
    ||
    month > 12
    ||
    day < 1
    ||
    day > 31
    ||
    hour < 0
    ||
    hour > 23
    ||
    minute < 0
    ||
    minute > 59
    ||
    second < 0
    ||
    second > 59
    ||
    (
      tzSign != '+'
      &&
      tzSign != '-'
    )
  ) {
    return false;
  }

  // At this point the modem clock has passed sanity validation.
  // Treat it as usable for telemetry timestamps.
  if (!modemTimeSynchronized) {
    modemTimeSynchronized = true;
    Serial.println(
      "[TIME] Valid modem/network clock accepted for telemetry."
    );
  }

  int tzMinutes =
    tzQuarterHours * 15;

  int tzHoursPart =
    tzMinutes / 60;

  int tzMinutesPart =
    tzMinutes % 60;

  char timestampBuffer[40];

  snprintf(
    timestampBuffer,
    sizeof(timestampBuffer),
    "20%02d-%02d-%02dT%02d:%02d:%02d%c%02d:%02d",
    year,
    month,
    day,
    hour,
    minute,
    second,
    tzSign,
    tzHoursPart,
    tzMinutesPart
  );

  isoTimestamp =
    String(
      timestampBuffer
    );

  return true;
}

// ======================================================
// DRIVING EVENT MAPPING
// ======================================================

String currentDrivingEventJson() {
  if (
    !latestBehaviorAvailable
  ) {
    return "null";
  }

  String normalized =
    latestBehaviorClass;

  normalized.trim();
  normalized.toUpperCase();
  normalized.replace(" ", "_");
  normalized.replace("-", "_");

  if (normalized == "SUDDEN_ACCELERATION") {
    return "\"HARSH_ACCELERATION\"";
  }

  if (normalized == "SUDDEN_BRAKING") {
    return "\"HARSH_BRAKING\"";
  }

  if (
    normalized == "SUDDEN_LEFT_TURN"
    ||
    normalized == "SUDDEN_RIGHT_TURN"
  ) {
    return "\"SHARP_TURN\"";
  }

  // Unknown model labels must not be fabricated into backend choices.
  Serial.print(
    "[TFLITE] Prediction label not mapped to FTMS enum: "
  );

  Serial.println(
    latestBehaviorClass
  );

  return "null";
}

// ======================================================
// JSON HELPERS
// ======================================================

String jsonFloatOrNull(
  bool valid,
  float value,
  int decimals
) {
  if (
    !valid
  ) {
    return "null";
  }

  return
    String(
      value,
      decimals
    );
}

String positionSourceJson() {
  if (
    latestPosition.source
    == POSITION_GNSS
  ) {
    return "\"GNSS\"";
  }

  if (
    latestPosition.source
    == POSITION_CELLULAR_LBS
  ) {
    return "\"CELLULAR_LBS\"";
  }

  return "null";
}

// ======================================================
// HTTP(S) HELPERS
// ======================================================

String sendATUntilMarker(
  const String& command,
  const String& marker,
  unsigned long timeoutMs
) {
  while (
    SerialAT.available()
  ) {
    SerialAT.read();
  }

  Serial.println();
  Serial.print(">> ");
  Serial.println(command);

  SerialAT.print(command);
  SerialAT.print("\r\n");

  String response = "";

  unsigned long startedAt =
    millis();

  bool markerSeen =
    false;

  while (
    millis() - startedAt
      < timeoutMs
  ) {
    while (
      SerialAT.available()
    ) {
      char c =
        SerialAT.read();

      response += c;
      Serial.write(c);

      if (
        !markerSeen
        &&
        response.indexOf(
          marker
        ) >= 0
      ) {
        markerSeen =
          true;
      }

      if (
        markerSeen
        &&
        c == '\n'
      ) {
        Serial.println();
        return response;
      }
    }

    delay(5);
  }

  Serial.println();
  return response;
}

bool uploadHTTPBody(
  const String& payload
) {
  while (
    SerialAT.available()
  ) {
    SerialAT.read();
  }

  String command =
    String("AT+HTTPDATA=")
    +
    payload.length()
    +
    ",10000";

  Serial.println();
  Serial.print(">> ");
  Serial.println(command);

  SerialAT.print(command);
  SerialAT.print("\r\n");

  String downloadResponse = "";

  unsigned long startedAt =
    millis();

  while (
    millis() - startedAt
      < 5000
  ) {
    while (
      SerialAT.available()
    ) {
      char c =
        SerialAT.read();

      downloadResponse += c;
      Serial.write(c);

      if (
        downloadResponse.indexOf(
          "DOWNLOAD"
        ) >= 0
      ) {
        Serial.println();
        Serial.println(
          "[HTTP] Modem ready for JSON payload."
        );

        SerialAT.print(
          payload
        );

        String bodyResponse = "";
        unsigned long bodyStartedAt =
          millis();

        while (
          millis() - bodyStartedAt < 5000
        ) {
          while (
            SerialAT.available()
          ) {
            char bodyChar =
              SerialAT.read();

            bodyResponse +=
              bodyChar;

            Serial.write(
              bodyChar
            );

            if (
              bodyResponse.indexOf("\r\nOK\r\n") >= 0
              ||
              bodyResponse.indexOf("\nOK\r\n") >= 0
            ) {
              return true;
            }

            if (
              bodyResponse.indexOf("\r\nERROR\r\n") >= 0
              ||
              bodyResponse.indexOf("\nERROR\r\n") >= 0
              ||
              bodyResponse.indexOf("+CME ERROR:") >= 0
            ) {
              return false;
            }
          }

          delay(5);
        }

        return false;
      }

      if (
        downloadResponse.indexOf(
          "ERROR"
        ) >= 0
      ) {
        Serial.println();
        return false;
      }
    }

    delay(5);
  }

  Serial.println();
  return false;
}

int parseHTTPStatusCode(
  const String& response
) {
  int prefix =
    response.indexOf(
      "+HTTPACTION:"
    );

  if (
    prefix < 0
  ) {
    return -1;
  }

  int lineStart =
    prefix
    +
    String(
      "+HTTPACTION:"
    ).length();

  int lineEnd =
    response.indexOf(
      '\n',
      lineStart
    );

  if (
    lineEnd < 0
  ) {
    lineEnd =
      response.length();
  }

  String line =
    response.substring(
      lineStart,
      lineEnd
    );

  line.trim();

  // method,status,datalen
  String statusText =
    csvField(
      line,
      1
    );

  return
    statusText.toInt();
}

bool httpPostJson(
  const String& payload,
  const String& targetUrl,
  const char* operationLabel
) {
  Serial.println();
  Serial.println(
    "========== FTMS HTTPS POST =========="
  );

  // Make the routine re-entrant after a previous interrupted session.
  // ERROR here is harmless when there is no active HTTP session yet.
  sendATQuick(
    "AT+HTTPTERM",
    1500
  );

  String initResponse =
    sendATQuick(
      "AT+HTTPINIT",
      5000
    );

  if (
    initResponse.indexOf(
      "OK"
    ) < 0
  ) {
    Serial.println(
      "[HTTP] HTTPINIT failed."
    );

    return false;
  }

  // HTTPS context 0.
  // SNI is important for hostname-based HTTPS services such as Cloudflare.
  // This temporary development tunnel uses encrypted HTTPS, but production
  // should use a stable endpoint with proper server-certificate validation.
  String sslVersionResponse =
    sendATQuick(
      "AT+CSSLCFG=\"sslversion\",0,3",
      3000
    );

  String sniResponse =
    sendATQuick(
      "AT+CSSLCFG=\"enableSNI\",0,1",
      3000
    );

  String httpSslResponse =
    sendATQuick(
      "AT+HTTPPARA=\"SSLCFG\",0",
      3000
    );

  if (
    sslVersionResponse.indexOf("OK") < 0
    ||
    sniResponse.indexOf("OK") < 0
    ||
    httpSslResponse.indexOf("OK") < 0
  ) {
    Serial.println("[HTTP] HTTPS SSL/SNI configuration failed.");
    sendAT("AT+HTTPTERM", 1500);
    return false;
  }

  String urlCommand =
    String(
      "AT+HTTPPARA=\"URL\",\""
    )
    +
    targetUrl
    +
    "\"";

  String urlResponse =
    sendATQuick(
      urlCommand,
      5000
    );

  if (
    urlResponse.indexOf(
      "OK"
    ) < 0
  ) {
    Serial.println(
      "[HTTP] URL configuration failed."
    );

    sendATQuick(
      "AT+HTTPTERM",
      1500
    );

    return false;
  }

  String contentResponse =
    sendATQuick(
      "AT+HTTPPARA=\"CONTENT\",\"application/json\"",
      3000
    );

  if (
    contentResponse.indexOf(
      "OK"
    ) < 0
  ) {
    Serial.println(
      "[HTTP] Content-Type configuration failed."
    );

    sendATQuick(
      "AT+HTTPTERM",
      1500
    );

    return false;
  }

  sendATQuick(
    "AT+HTTPPARA=\"ACCEPT\",\"application/json\"",
    3000
  );

  sendATQuick(
    "AT+HTTPPARA=\"CONNECTTO\",60",
    3000
  );

  sendATQuick(
    "AT+HTTPPARA=\"RECVTO\",30",
    3000
  );

  if (
    !uploadHTTPBody(
      payload
    )
  ) {
    Serial.println(
      "[HTTP] HTTPDATA upload failed."
    );

    sendATQuick(
      "AT+HTTPTERM",
      1500
    );

    return false;
  }

  String actionResponse =
    sendATUntilMarker(
      "AT+HTTPACTION=1",
      "+HTTPACTION:",
      70000
    );

  int statusCode =
    parseHTTPStatusCode(
      actionResponse
    );

  Serial.print(
    "[HTTP] FTMS status code: "
  );

  Serial.println(
    statusCode
  );

  // +HTTPACTION status is authoritative for this telemetry POST.
  // This A7670E firmware returned ERROR for plain AT+HTTPREAD even
  // after a successful HTTP 201, so skip that unnecessary read.
  sendATQuick(
    "AT+HTTPTERM",
    2000
  );

  bool success =
    (
      statusCode == 200
      ||
      statusCode == 201
    );

  if (
    success
  ) {
    Serial.println(
      String("[HTTP] FTMS ") + operationLabel + " accepted."
    );
  } else {
    Serial.println(
      String("[HTTP] FTMS ") + operationLabel + " POST failed."
    );
  }

  Serial.println(
    "====================================="
  );

  return success;
}

bool httpPostTelemetryJson(const String& payload) {
  return httpPostJson(payload, String(FTMS_TELEMETRY_URL), "telemetry");
}

String sosEndpointUrl() {
  String url = String(FTMS_TELEMETRY_URL);
  int telemetryPath = url.lastIndexOf("/telemetry/");
  if (telemetryPath >= 0) url = url.substring(0, telemetryPath) + "/sos/";
  return url;
}

bool sendSOSAction(const char* action) {
  String payload = String("{\"device_id\":\"") + DEVICE_ID
    + "\",\"action\":\"" + action + "\"}";
  return httpPostJson(payload, sosEndpointUrl(), "SOS");
}

void processSOSButton(unsigned long now) {
  bool rawPressed = digitalRead(SOS_BUTTON_PIN) == LOW;
  if (rawPressed != sosRawPressed) {
    sosRawPressed = rawPressed;
    sosRawChangedAt = now;
  }
  if (now - sosRawChangedAt < SOS_DEBOUNCE_MS || rawPressed == sosDebouncedPressed) return;

  sosDebouncedPressed = rawPressed;
  if (sosDebouncedPressed) {
    sosPressedAt = now;
    sosLongHoldHandled = false;
    if (sosActive) Serial.println("[SOS] Clear hold started");
    return;
  }

  unsigned long heldFor = now - sosPressedAt;
  if (sosLongHoldHandled || heldFor >= SOS_CLEAR_HOLD_MS || sosActive) return;
  if (sosShortPressCount > 0 && now - sosLastShortPressAt > SOS_PRESS_WINDOW_MS)
    sosShortPressCount = 0;
  sosShortPressCount++;
  sosLastShortPressAt = now;
  Serial.print("[SOS] Press ");
  Serial.print(sosShortPressCount);
  Serial.println("/3");
  if (sosShortPressCount == 3) {
    sosShortPressCount = 0;
    sosActive = true;
    sosPendingAction = SOS_PENDING_ACTIVATE;
    sosLastTransmitAttempt = 0;
    Serial.println("[SOS] Emergency activated");
  }
}

void processSOSLongHold(unsigned long now) {
  if (!sosDebouncedPressed || sosLongHoldHandled
      || now - sosPressedAt < SOS_CLEAR_HOLD_MS) return;
  sosLongHoldHandled = true;
  sosShortPressCount = 0;
  sosPendingAction = SOS_PENDING_CLEAR;
  sosLastTransmitAttempt = 0;
  Serial.println("[SOS] Emergency clear requested");
}

void serviceSOSTransmission(unsigned long now) {
  if (sosPendingAction == SOS_PENDING_NONE) return;
  if (sosLastTransmitAttempt != 0 && now - sosLastTransmitAttempt < SOS_RETRY_INTERVAL_MS) return;
  sosLastTransmitAttempt = now;
  bool clearing = sosPendingAction == SOS_PENDING_CLEAR;
  if (sendSOSAction(clearing ? "CLEAR" : "ACTIVATE")) {
    sosPendingAction = SOS_PENDING_NONE;
    if (clearing) {
      sosActive = false;
      Serial.println("[SOS] Emergency cleared");
      Serial.println("[SOS] Emergency clear acknowledged");
    } else {
      Serial.println("[SOS] Emergency activation acknowledged");
    }
  } else {
    Serial.println(clearing
      ? "[SOS] Emergency clear pending retry"
      : "[SOS] Emergency activation pending retry");
  }
}

void updateStatusLEDs(unsigned long now) {
  bool freshPosition = latestPosition.valid
    && (
      latestPosition.source == POSITION_GNSS
      || latestPosition.source == POSITION_CELLULAR_LBS
    )
    && now - latestPosition.observedAtMillis <= POSITION_MAX_SEND_AGE_MS;
  digitalWrite(GNSS_LED_PIN, freshPosition ? HIGH : LOW);
  digitalWrite(VGATE_LED_PIN, SerialBT.connected() ? HIGH : LOW);
}

// ======================================================
// FTMS TELEMETRY PAYLOAD
// ======================================================

bool sendCurrentTelemetryToFTMS() {
  if (
    !latestPosition.valid
  ) {
    Serial.println(
      "[TELEMETRY] No verified position. POST skipped."
    );

    return false;
  }

  unsigned long positionAge =
    millis()
    -
    latestPosition.observedAtMillis;

  if (
    positionAge
    >
    POSITION_MAX_SEND_AGE_MS
  ) {
    Serial.println(
      "[TELEMETRY] Position observation is stale. POST skipped."
    );

    return false;
  }

  String recordedAt;

  if (
    !getNetworkTimestampISO8601(
      recordedAt
    )
  ) {
    Serial.println(
      "[TELEMETRY] Network clock unavailable/invalid. POST skipped."
    );

    return false;
  }

  telemetrySequence++;

  uint32_t randomSuffix =
    esp_random();

  String eventId =
    String("evt-")
    +
    DEVICE_ID
    +
    "-"
    +
    String(randomSuffix, HEX)
    +
    "-"
    +
    telemetrySequence;

  bool hasSupportedOBD =
    (
      obdRPMValid
      ||
      obdCoolantValid
      ||
      obdEngineLoadValid
    );

  String payload;

  payload.reserve(
    900
  );

  payload += "{";

  payload +=
    "\"schema_version\":\"1.2\",";

  payload +=
    "\"event_id\":\""
    +
    eventId
    +
    "\",";

  payload +=
    "\"sequence_number\":"
    +
    String(telemetrySequence)
    +
    ",";

  payload +=
    "\"device_id\":\""
    +
    String(DEVICE_ID)
    +
    "\",";

  payload +=
    "\"recorded_at\":\""
    +
    recordedAt
    +
    "\",";

  payload +=
    "\"latitude\":"
    +
    String(
      latestPosition.latitude,
      6
    )
    +
    ",";

  payload +=
    "\"longitude\":"
    +
    String(
      latestPosition.longitude,
      6
    )
    +
    ",";

  payload +=
    "\"position_source\":"
    +
    positionSourceJson()
    +
    ",";

  payload +=
    "\"position_accuracy_m\":";

  if (
    latestPosition.accuracyValid
  ) {
    payload +=
      String(
        latestPosition.accuracyMeters,
        2
      );
  } else {
    payload +=
      "null";
  }

  payload += ",";

  payload +=
    "\"gnss_speed_kph\":"
    +
    jsonFloatOrNull(
      latestPosition.gnssSpeedValid,
      latestPosition.gnssSpeedKph,
      2
    )
    +
    ",";

  payload +=
    "\"rpm\":";

  if (
    obdRPMValid
  ) {
    payload +=
      String(
        (int)lroundf(
          obdEngineRPM
        )
      );
  } else {
    payload +=
      "null";
  }

  payload += ",";

  payload +=
    "\"coolant_c\":"
    +
    jsonFloatOrNull(
      obdCoolantValid,
      obdCoolantC,
      2
    )
    +
    ",";

  payload +=
    "\"engine_load_pct\":"
    +
    jsonFloatOrNull(
      obdEngineLoadValid,
      obdEngineLoadPercent,
      2
    )
    +
    ",";

  payload +=
    "\"driving_event\":"
    +
    currentDrivingEventJson()
    +
    ",";

  payload +=
    "\"obd_source\":";

  if (
    hasSupportedOBD
  ) {
    payload +=
      "\"SIMULATED_TEST\"";
  } else {
    payload +=
      "null";
  }

  payload += "}";

  Serial.println();
  Serial.println(
    "========== FTMS PAYLOAD =========="
  );

  Serial.println(
    payload
  );

  Serial.println(
    "=================================="
  );

  bool accepted =
    httpPostTelemetryJson(
      payload
    );

  return accepted;
}

// ======================================================
// INITIALIZE MPU6050
// ======================================================

void initializeMPU6050() {
  Wire.begin(
    21,
    22
  );

  Wire.beginTransmission(
    MPU_ADDR
  );

  Wire.write(
    0x6B
  );

  Wire.write(
    0
  );

  uint8_t result =
    Wire.endTransmission(
      true
    );

  if (
    result == 0
  ) {
    Serial.println("MPU6050 initialized.");
  } else {
    Serial.print("MPU6050 initialization warning. I2C error: ");
    Serial.println(result);
  }
}

// ======================================================
// INITIALIZE TFLITE
// ======================================================

bool initializeTFLite() {
  Serial.println("Initializing TensorFlow Lite...");

  tflite::InitializeTarget();

  tflite_model =
    tflite::GetModel(
      driver_behavior_model
    );

  if (
    tflite_model->version()
    != TFLITE_SCHEMA_VERSION
  ) {
    Serial.println("Model schema version mismatch.");
    return false;
  }

  static
  tflite::MicroMutableOpResolver<4>
  resolver;

  resolver.AddFullyConnected();
  resolver.AddSoftmax();

  static
  tflite::MicroInterpreter
  static_interpreter(
    tflite_model,
    resolver,
    tensor_arena,
    kTensorArenaSize
  );

  interpreter =
    &static_interpreter;

  if (
    interpreter->AllocateTensors()
    != kTfLiteOk
  ) {
    Serial.println("AllocateTensors failed.");
    return false;
  }

  input =
    interpreter->input(0);

  output =
    interpreter->output(0);

  Serial.println(
    "TensorFlow Lite model initialized successfully."
  );

  return true;
}

// ======================================================
// SETUP
// ======================================================

void setup() {
  Serial.begin(
    115200
  );

  delay(
    1500
  );

  Serial.println();
  Serial.println(
    "========================================"
  );

  Serial.println(
    "FTMS LILYGO-002 COMBINED TELEMETRY"
  );

  Serial.println(
    "TFLite + Vgate ECUSim OBD + GNSS/LBS + HTTPS"
  );

  Serial.println(
    "========================================"
  );

  Serial.print("Device ID: ");
  Serial.println(DEVICE_ID);

  // --------------------------------------------------
  // LED
  // --------------------------------------------------

  pinMode(
    SYS_LED,
    OUTPUT
  );
  pinMode(SOS_BUTTON_PIN, INPUT_PULLUP);
  pinMode(GNSS_LED_PIN, OUTPUT);
  pinMode(VGATE_LED_PIN, OUTPUT);
  digitalWrite(GNSS_LED_PIN, LOW);
  digitalWrite(VGATE_LED_PIN, LOW);

  // --------------------------------------------------
  // MPU + TFLITE
  // --------------------------------------------------

  initializeMPU6050();

  tfliteReady = initializeTFLite();

  if (
    !tfliteReady
  ) {
    Serial.println(
      "[ERROR] TFLite initialization failed."
    );
  }

  // --------------------------------------------------
  // MODEM + LTE + GNSS
  // --------------------------------------------------

  bool modemReady =
    startModem();

  if (
    modemReady
  ) {
    Serial.println();
    Serial.println(
      "[MODEM] A7670E responding."
    );

    sendAT(
      "AT+CGMM",
      3000
    );

    configureLTE();
    startGNSS();

    // First fresh location observation immediately.
    updatePosition();

    lastPositionCheck =
      millis();
  } else {
    Serial.println();
    Serial.println(
      "[ERROR] A7670E modem failed to start."
    );
  }

  // --------------------------------------------------
  // BLUETOOTH / OBD
  // --------------------------------------------------

  obdBluetoothConnected =
    connectVgateOBD();

  if (
    obdBluetoothConnected
  ) {
    delay(
      1000
    );

    elmInitialized =
      initializeELM327();

    if (
      elmInitialized
    ) {
      pollOBD();
      lastOBDPoll =
        millis();
    }
  }

  // If startup already obtained a fresh GNSS/LBS observation,
  // publish one truthful schema 1.2 event now.
  if (
    latestPosition.valid
  ) {
    sendCurrentTelemetryToFTMS();

    lastTelemetrySend =
      millis();
  }

  Serial.println();
  Serial.println(
    "========================================"
  );

  Serial.println(
    "FTMS COMBINED TELEMETRY RUNNING"
  );

  Serial.println(
    "Telemetry publishes every 5s while verified position is fresh."
  );

  Serial.println(
    "ECUSimGUI OBD values are marked SIMULATED_TEST."
  );

  Serial.println(
    "========================================"
  );

  Serial.println();
}

// ======================================================
// LOOP
// ======================================================

void loop() {
  unsigned long now =
    millis();

  processSOSButton(now);
  processSOSLongHold(now);
  updateStatusLEDs(now);

  // ==================================================
  // BLUETOOTH STATUS / RECONNECT
  // ==================================================

  if (
    !SerialBT.connected()
  ) {
    obdBluetoothConnected =
      false;

    elmInitialized =
      false;

    if (
      now - lastReconnectAttempt
      >= RECONNECT_INTERVAL_MS
    ) {
      lastReconnectAttempt =
        now;

      Serial.println();
      Serial.println(
        "[BT] OBD connection lost."
      );

      Serial.println(
        "[BT] Attempting reconnect..."
      );

      obdBluetoothConnected =
        connectVgateDevice();

      if (
        obdBluetoothConnected
      ) {
        Serial.println(
          "[BT] Reconnected successfully."
        );

        delay(
          500
        );

        elmInitialized =
          initializeELM327();
      } else {
        Serial.println(
          "[BT] Reconnect failed."
        );
      }
    }
  } else {
    obdBluetoothConnected =
      true;
  }

  // ==================================================
  // AUTOMATIC OBD POLLING
  // ==================================================

  if (
    obdBluetoothConnected
    &&
    elmInitialized
    &&
    now - lastOBDPoll
      >= OBD_POLL_INTERVAL_MS
  ) {
    lastOBDPoll =
      now;

    pollOBD();
  }

  // ==================================================
  // DRIVER BEHAVIOR TFLITE
  // ==================================================

  if (
    now - lastDriverBehaviorRun
      >= DRIVER_BEHAVIOR_INTERVAL_MS
  ) {
    lastDriverBehaviorRun =
      now;

    runPrediction();
  }

  // ==================================================
  // GNSS PRIMARY / LBS FALLBACK
  // ==================================================

  if (
    now - lastPositionCheck
      >= POSITION_CHECK_INTERVAL_MS
  ) {
    lastPositionCheck =
      now;

    // Refresh the verified real position independently.
    // OBD telemetry no longer waits for a new location fix.
    updatePosition();
  }

  // ==================================================
  // PERIODIC FTMS TELEMETRY PUBLISH
  // ==================================================

  if (
    now - lastTelemetrySend
      >= TELEMETRY_SEND_INTERVAL_MS
  ) {
    lastTelemetrySend =
      now;

    // Uses the newest OBD poll plus the last verified GNSS/LBS
    // position, provided that position is still within the
    // configured freshness window.
    sendCurrentTelemetryToFTMS();
  }

  serviceSOSTransmission(now);

  // ==================================================
  // SYSTEM LED
  // ==================================================

  static bool ledState =
    false;

  static unsigned long lastLedToggle =
    0;

  if (
    now - lastLedToggle
      >= 500
  ) {
    lastLedToggle =
      now;

    ledState =
      !ledState;

    digitalWrite(
      SYS_LED,
      ledState
    );
  }

  delay(
    5
  );
}
