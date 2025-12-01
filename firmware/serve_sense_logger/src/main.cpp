#include <Arduino.h>
#include <Wire.h>
#include <NimBLEDevice.h>

// ============================================================
// Hardware configuration (ICM-20600 breakout wired to XIAO)
// ============================================================
constexpr uint8_t PIN_I2C_SDA   = 5;   // D4 on XIAO ESP32S3
constexpr uint8_t PIN_I2C_SCL   = 6;   // D5 on XIAO ESP32S3
constexpr uint8_t PIN_STATUS_LED = 21; // built-in RGB green channel
constexpr uint8_t PIN_CAPTURE_BTN = 0; // BOOT button (active low)

constexpr uint8_t ICM20600_ADDR = 0x69;

constexpr uint8_t REG_PWR_MGMT_1   = 0x6B;
constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
constexpr uint8_t REG_GYRO_CONFIG  = 0x1B;
constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
constexpr uint8_t REG_WHO_AM_I     = 0x75;

constexpr float ACC_LSB_PER_G   = 16384.0f; // ±2 g
constexpr float GYR_LSB_PER_DPS = 131.0f;   // ±250 dps

// ============================================================
// BLE layout (mirrors Magic Wand for compatibility)
// ============================================================
static const NimBLEUUID SVC_UUID  ((uint16_t)0xFF00);
static const NimBLEUUID IMU_UUID  ((uint16_t)0xFF01); // notify
static const NimBLEUUID CTRL_UUID ((uint16_t)0xFF02); // write

static NimBLECharacteristic* imuChar  = nullptr;
static NimBLECharacteristic* ctrlChar = nullptr;

// ============================================================
// Logging state
// ============================================================
constexpr uint32_t SAMPLE_PERIOD_MS = 10; // 100 Hz

volatile bool captureEnabled = false;
volatile bool serveMarker    = false;
uint16_t sessionId           = 0;
uint32_t sampleSerial        = 0;

// Packet shared with desktop collector (packed = 36 bytes)
struct __attribute__((packed)) ServePacket {
  uint32_t millis_ms;
  uint16_t session;
  uint16_t sequence;
  float ax, ay, az;
  float gx, gy, gz;
  uint8_t flags;  // bit0: capture on, bit1: serve marker edge
  uint8_t reserved[3];
};

// ============================================================
// I2C helpers
// ============================================================
bool i2cWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(ICM20600_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool i2cReadBytes(uint8_t reg, uint8_t* buf, size_t len) {
  Wire.beginTransmission(ICM20600_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(ICM20600_ADDR, static_cast<uint8_t>(len)) != static_cast<int>(len)) {
    return false;
  }
  for (size_t i = 0; i < len; ++i) {
    buf[i] = Wire.read();
  }
  return true;
}

bool icmInit(uint8_t& who) {
  who = 0;
  if (!i2cWrite(REG_PWR_MGMT_1, 0x01)) return false; // wake, PLL
  delay(50);
  if (!i2cWrite(REG_ACCEL_CONFIG, 0x00)) return false; // ±2 g
  if (!i2cWrite(REG_GYRO_CONFIG,  0x00)) return false; // ±250 dps
  delay(10);
  return i2cReadBytes(REG_WHO_AM_I, &who, 1);
}

bool icmRead(float& ax, float& ay, float& az, float& gx, float& gy, float& gz) {
  uint8_t raw[14];
  if (!i2cReadBytes(REG_ACCEL_XOUT_H, raw, sizeof(raw))) return false;

  auto s16 = [&](int idx)->int16_t {
    return static_cast<int16_t>((raw[idx] << 8) | raw[idx + 1]);
  };

  ax = s16(0)  / ACC_LSB_PER_G;
  ay = s16(2)  / ACC_LSB_PER_G;
  az = s16(4)  / ACC_LSB_PER_G;
  gx = s16(8)  / GYR_LSB_PER_DPS;
  gy = s16(10) / GYR_LSB_PER_DPS;
  gz = s16(12) / GYR_LSB_PER_DPS;
  return true;
}

// ============================================================
// BLE callbacks
// ============================================================
class ServerCallbacks : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*) override {
    Serial.println("[BLE] Central connected");
  }
  void onDisconnect(NimBLEServer*) override {
    Serial.println("[BLE] Central disconnected → restart advertising");
    NimBLEDevice::startAdvertising();
  }
};

class ControlCallbacks : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c) override {
    auto value = c->getValue();
    if (value.empty()) return;
    uint8_t cmd = value[0];
    switch (cmd) {
      case 0x00: // stop
        captureEnabled = false;
        digitalWrite(PIN_STATUS_LED, LOW);
        Serial.println("[CTRL] capture OFF");
        break;
      case 0x01: // start new session
        captureEnabled = true;
        serveMarker    = true; // mark boundary
        sessionId++;
        sampleSerial   = 0;
        digitalWrite(PIN_STATUS_LED, HIGH);
        Serial.printf("[CTRL] capture ON (session %u)\r\n", sessionId);
        break;
      case 0x02: // toggle marker
        serveMarker = true;
        Serial.println("[CTRL] serve marker");
        break;
      default:
        Serial.printf("[CTRL] unknown cmd 0x%02X\r\n", cmd);
        break;
    }
  }
};

void IRAM_ATTR onButtonFalling() {
  static uint32_t last = 0;
  uint32_t now = millis();
  if (now - last < 200) return; // debounce
  last = now;
  captureEnabled = !captureEnabled;
  if (captureEnabled) {
    sessionId++;
    sampleSerial = 0;
  }
  serveMarker = true;
  digitalWrite(PIN_STATUS_LED, captureEnabled ? HIGH : LOW);
}

// ============================================================
// Setup
// ============================================================
void setup() {
  pinMode(PIN_CAPTURE_BTN, INPUT_PULLUP);
  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, LOW);

  attachInterrupt(digitalPinToInterrupt(PIN_CAPTURE_BTN), onButtonFalling, FALLING);

  Serial.begin(115200);
  while (!Serial && millis() < 3000) delay(10);
  Serial.println("\n[BOOT] Serve Sense logger");

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
  uint8_t who = 0;
  if (!icmInit(who)) {
    Serial.println("[I2C] ICM20600 init failed");
  } else {
    Serial.printf("[I2C] ICM20600 ready (WHO_AM_I=0x%02X)\r\n", who);
  }

  NimBLEDevice::init("ServeSense");
  NimBLEDevice::setPower(ESP_PWR_LVL_P9);
  NimBLEDevice::setMTU(185);

  auto server = NimBLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  auto service = server->createService(SVC_UUID);

  imuChar = service->createCharacteristic(
      IMU_UUID,
      NIMBLE_PROPERTY::NOTIFY
  );
  ctrlChar = service->createCharacteristic(
      CTRL_UUID,
      NIMBLE_PROPERTY::WRITE
  );
  ctrlChar->setCallbacks(new ControlCallbacks());

  service->start();
  auto adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(SVC_UUID);
  adv->setMinInterval(32);
  adv->setMaxInterval(96);
  adv->setName("ServeSense");
  adv->start();

  Serial.println("[BLE] Advertising as ServeSense");
}

// ============================================================
// Main loop
// ============================================================
void loop() {
  static uint32_t lastSampleMs = 0;
  uint32_t now = millis();
  if (now - lastSampleMs < SAMPLE_PERIOD_MS) {
    delay(1);
    return;
  }
  lastSampleMs = now;

  float ax, ay, az, gx, gy, gz;
  if (!icmRead(ax, ay, az, gx, gy, gz)) {
    Serial.println("[IMU] read failed");
    return;
  }

  // Print CSV for quick debugging even when BLE disconnected.
  Serial.printf("t=%lu,%u,%u,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%u\r\n",
                now, sessionId, sampleSerial, ax, ay, az, gx, gy, gz, captureEnabled ? 1 : 0);

  if (!captureEnabled && !serveMarker) {
    return; // skip BLE churn when idle
  }

  ServePacket pkt{};
  pkt.millis_ms = now;
  pkt.session   = sessionId;
  pkt.sequence  = sampleSerial++;
  pkt.ax = ax; pkt.ay = ay; pkt.az = az;
  pkt.gx = gx; pkt.gy = gy; pkt.gz = gz;
  pkt.flags = (captureEnabled ? 0x01 : 0x00) | (serveMarker ? 0x02 : 0x00);

  serveMarker = false;

  if (NimBLEDevice::getServer()->getConnectedCount() == 0) {
    return;
  }

  imuChar->setValue(reinterpret_cast<uint8_t*>(&pkt), sizeof(pkt));
  imuChar->notify();
}

