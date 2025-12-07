/* ServeSense Classifier - Real-time Tennis Serve Classification
 * 
 * Collects 6-axis IMU data (ax, ay, az, gx, gy, gz) from ICM-20600
 * Uses switch on D1 pin to start/stop recording
 * Runs TensorFlow Lite inference to classify serve type
 * 
 * Model expects: (160, 6) int8 input
 * Classes: good-serve, jerky-motion, lacks-pronation, short-swing
 */

#include <Arduino.h>
#include <ArduinoBLE.h>

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/version.h"

#include "imu_provider.h"
#include "serve_model_data.h"

// BLE UUIDs matching ServeSense logger protocol
#define SERVICE_UUID "0000ff00-0000-1000-8000-00805f9b34fb"
#define IMU_CHAR_UUID "0000ff01-0000-1000-8000-00805f9b34fb"     // IMU data packets
#define CTRL_CHAR_UUID "0000ff02-0000-1000-8000-00805f9b34fb"    // Control commands
#define SWITCH_CHAR_UUID "0000ff04-0000-1000-8000-00805f9b34fb"  // Switch state
#define RESULT_CHAR_UUID "0000ff05-0000-1000-8000-00805f9b34fb"  // Classification result

#define PIN_RECORD_SWITCH D1  // D1 on XIAO ESP32S3 (switch: ON=LOW, OFF=HIGH with pullup)
#define LED_BUILTIN LED_BUILTIN  // Built-in LED on XIAO ESP32S3
#define PIN_VIBRATION_MOTOR A0  // Vibration motor on A0

// ===== Model Configuration =====
constexpr int kSequenceLength = 160;  // 160 samples @ 40Hz = 4 seconds
constexpr int kNumFeatures = 6;       // ax, ay, az, gx, gy, gz
constexpr int kNumClasses = 4;        // good-serve, jerky-motion, lacks-pronation, short-swing

const char* labels[kNumClasses] = {
  "good-serve",
  "jerky-motion", 
  "lacks-pronation",
  "short-swing"
};

// ===== IMU Data Buffer =====
float imu_buffer[kSequenceLength][kNumFeatures];
int sample_count = 0;
bool is_recording = false;
bool last_switch_state = HIGH;

// ===== BLE Services =====
BLEService        service              (SERVICE_UUID);
BLECharacteristic imuCharacteristic    (IMU_CHAR_UUID, BLERead | BLENotify, 36);      // IMU packet stream
BLECharacteristic ctrlCharacteristic   (CTRL_CHAR_UUID, BLEWrite, 1);                 // Control (0x00=stop, 0x01=start)
BLECharacteristic switchCharacteristic (SWITCH_CHAR_UUID, BLERead | BLENotify, 1);    // Switch state
BLECharacteristic resultCharacteristic (RESULT_CHAR_UUID, BLERead | BLENotify, 64);   // Classification result

// ===== TensorFlow Lite Setup =====
namespace {
  const tflite::Model* model = nullptr;
  tflite::MicroInterpreter* interpreter = nullptr;
  TfLiteTensor* model_input = nullptr;
  TfLiteTensor* model_output = nullptr;

  constexpr int kTensorArenaSize = 80 * 1024;  // 80KB
  uint8_t tensor_arena[kTensorArenaSize];
}

void classifyServe();
void hapticGoodServe();
void hapticJerkyMotion();
void hapticLacksPronation();
void hapticShortSwing();
void hapticStartup();

void setup() {
  delay(1000);
  
  tflite::InitializeTarget();
  
  Serial.println("\n=== ServeSense Classifier ===");
  
  // Setup LED pin
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);  // LED off initially
  
  // Setup vibration motor
  pinMode(PIN_VIBRATION_MOTOR, OUTPUT);
  digitalWrite(PIN_VIBRATION_MOTOR, LOW);
  hapticStartup();  // Startup pulse
  
  // Setup switch pin (start in ON position)
  pinMode(PIN_RECORD_SWITCH, INPUT_PULLUP);
  last_switch_state = LOW;  // Initialize as if switch is ON
  
  // Initialize IMU
  if (!SetupIMU()) {
    Serial.println("ERROR: IMU initialization failed!");
    while (1) delay(100);
  }
  Serial.println("✓ IMU initialized");
  
  // Setup BLE
  if (!BLE.begin()) {
    Serial.println("ERROR: BLE initialization failed!");
    while (1) delay(100);
  }
  
  BLE.setLocalName("ServeSense");
  BLE.setAdvertisedService(service);
  service.addCharacteristic(imuCharacteristic);
  service.addCharacteristic(ctrlCharacteristic);
  service.addCharacteristic(switchCharacteristic);
  service.addCharacteristic(resultCharacteristic);
  BLE.addService(service);
  BLE.advertise();
  Serial.println("✓ BLE advertising as 'ServeSense'");
  
  // Load TensorFlow Lite model
  model = tflite::GetModel(g_serve_model_data);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    Serial.print("ERROR: Model version mismatch! Expected ");
    Serial.print(TFLITE_SCHEMA_VERSION);
    Serial.print(", got ");
    Serial.println(model->version());
    while (1) delay(100);
  }
  Serial.println("✓ Model loaded");
  
  // Setup TensorFlow Lite interpreter
  static tflite::MicroMutableOpResolver<10> resolver;
  resolver.AddConv2D();
  resolver.AddMaxPool2D();
  resolver.AddReshape();
  resolver.AddFullyConnected();
  resolver.AddSoftmax();
  resolver.AddQuantize();
  resolver.AddDequantize();
  resolver.AddMean();
  resolver.AddPad();
  resolver.AddExpandDims();
  
  static tflite::MicroInterpreter static_interpreter(
    model, resolver, tensor_arena, kTensorArenaSize);
  interpreter = &static_interpreter;
  
  if (interpreter->AllocateTensors() != kTfLiteOk) {
    Serial.println("ERROR: Tensor allocation failed!");
    while (1) delay(100);
  }
  
  model_input = interpreter->input(0);
  model_output = interpreter->output(0);
  
  Serial.print("✓ Model ready - Input shape: (");
  Serial.print(model_input->dims->data[1]);
  Serial.print(", ");
  Serial.print(model_input->dims->data[2]);
  Serial.print("), Output classes: ");
  Serial.println(kNumClasses);
  
  Serial.println("\n[Ready - flip switch to D1 to record serve]");
}

void loop() {
  BLE.poll();
  
  // Check switch state
  bool switch_on = (digitalRead(PIN_RECORD_SWITCH) == LOW);
  
  // Detect switch state changes
  if (switch_on && !last_switch_state) {
    // Switch turned ON: start recording
    is_recording = true;
    sample_count = 0;
    digitalWrite(LED_BUILTIN, LOW);  // Turn LED on
    Serial.println("\n[RECORDING STARTED]");
    
    // Notify BLE
    uint8_t state = 1;
    switchCharacteristic.writeValue(state);
    
  } else if (!switch_on && last_switch_state && is_recording) {
    // Switch turned OFF: stop recording and classify
    is_recording = false;
    digitalWrite(LED_BUILTIN, HIGH);  // Turn LED off
    Serial.print("[RECORDING STOPPED] ");
    Serial.print(sample_count);
    Serial.println(" samples collected");
    
    // Notify BLE
    uint8_t state = 0;
    switchCharacteristic.writeValue(state);
    
    // Run classification
    if (sample_count > 0) {
      classifyServe();
    }
  }
  
  last_switch_state = switch_on;
  
  // Read IMU data while recording
  if (is_recording && sample_count < kSequenceLength) {
    float accel[3], gyro[3];
    if (ReadIMU(accel, gyro)) {
      // Store in buffer: ax, ay, az, gx, gy, gz
      imu_buffer[sample_count][0] = accel[0];
      imu_buffer[sample_count][1] = accel[1];
      imu_buffer[sample_count][2] = accel[2];
      imu_buffer[sample_count][3] = gyro[0];
      imu_buffer[sample_count][4] = gyro[1];
      imu_buffer[sample_count][5] = gyro[2];
      
      sample_count++;
      
      // Print progress every 20 samples
      if (sample_count % 20 == 0) {
        Serial.print(".");
      }
    }
    delay(25);  // ~40Hz sampling rate
  }
  
  delay(5);
}

void classifyServe() {
  Serial.println("\n>>> CLASSIFYING SERVE <<<");
  
  // Pad or truncate to exactly 160 samples
  int actual_samples = min(sample_count, kSequenceLength);
  
  // Get quantization parameters
  const float input_scale = model_input->params.scale;
  const int input_zp = model_input->params.zero_point;
  
  Serial.print("Quantization - scale: ");
  Serial.print(input_scale, 6);
  Serial.print(", zero_point: ");
  Serial.println(input_zp);
  
  // Fill model input with quantized IMU data
  for (int i = 0; i < kSequenceLength; i++) {
    for (int j = 0; j < kNumFeatures; j++) {
      float value;
      if (i < actual_samples) {
        value = imu_buffer[i][j];
      } else {
        value = 0.0f;  // Pad with zeros if needed
      }
      
      // Quantize: q = round(value / scale) + zero_point
      int32_t quantized = static_cast<int32_t>(roundf(value / input_scale)) + input_zp;
      
      // Clamp to int8 range
      if (quantized < -128) quantized = -128;
      if (quantized > 127) quantized = 127;
      
      model_input->data.int8[i * kNumFeatures + j] = static_cast<int8_t>(quantized);
    }
  }
  
  // Run inference
  if (interpreter->Invoke() != kTfLiteOk) {
    Serial.println("ERROR: Inference failed!");
    return;
  }
  
  // Dequantize outputs
  const float output_scale = model_output->params.scale;
  const int output_zp = model_output->params.zero_point;
  
  float probabilities[kNumClasses];
  int best_idx = 0;
  float max_prob = -1.0f;
  
  Serial.println("\nResults:");
  for (int i = 0; i < kNumClasses; i++) {
    // Dequantize: value = (q - zero_point) * scale
    float prob = (model_output->data.int8[i] - output_zp) * output_scale;
    probabilities[i] = prob;
    
    Serial.print("  ");
    Serial.print(labels[i]);
    Serial.print(": ");
    Serial.print(prob * 100, 1);
    Serial.println("%");
    
    if (prob > max_prob) {
      max_prob = prob;
      best_idx = i;
    }
  }
  
  // Determine if confident enough
  const float kMinConfidence = 0.35f;
  bool is_confident = max_prob >= kMinConfidence;
  
  char result_msg[64];
  if (is_confident) {
    Serial.print("\n✓ Prediction: ");
    Serial.print(labels[best_idx]);
    Serial.print(" (");
    Serial.print(max_prob * 100, 1);
    Serial.println("%)");
    
    // Send all probabilities: "best_class:conf1,conf2,conf3,conf4"
    snprintf(result_msg, sizeof(result_msg), "%s:%.1f,%.1f,%.1f,%.1f", 
             labels[best_idx], 
             probabilities[0] * 100, 
             probabilities[1] * 100, 
             probabilities[2] * 100, 
             probabilities[3] * 100);
  } else {
    Serial.print("\n? Prediction: UNKNOWN (max confidence: ");
    Serial.print(max_prob * 100, 1);
    Serial.println("%)");
    
    // Send all probabilities even for UNKNOWN
    snprintf(result_msg, sizeof(result_msg), "UNKNOWN:%.1f,%.1f,%.1f,%.1f", 
             probabilities[0] * 100, 
             probabilities[1] * 100, 
             probabilities[2] * 100, 
             probabilities[3] * 100);
  }
  
  // Send result over BLE
  resultCharacteristic.writeValue((uint8_t*)result_msg, strlen(result_msg));
  
  // Haptic feedback based on classification
  if (is_confident) {
    if (best_idx == 0) {  // good-serve
      hapticGoodServe();
    } else if (best_idx == 1) {  // jerky-motion
      hapticJerkyMotion();
    } else if (best_idx == 2) {  // lacks-pronation
      hapticLacksPronation();
    } else if (best_idx == 3) {  // short-swing
      hapticShortSwing();
    }
  }
  
  // Ensure LED is off after feedback
  digitalWrite(LED_BUILTIN, HIGH);
  
  Serial.println("\n[Ready - flip switch to record another serve]");
}

// ===== Haptic Feedback Functions =====
void hapticStartup() {
  // Startup: 1 second continuous pulse
  digitalWrite(PIN_VIBRATION_MOTOR, HIGH);
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1000);
  digitalWrite(PIN_VIBRATION_MOTOR, LOW);
  digitalWrite(LED_BUILTIN, LOW);
}

void hapticGoodServe() {
  // Good serve: 3 quick happy pulses (short-short-short)
  for (int i = 0; i < 3; i++) {
    digitalWrite(PIN_VIBRATION_MOTOR, HIGH);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
    digitalWrite(PIN_VIBRATION_MOTOR, LOW);
    digitalWrite(LED_BUILTIN, LOW);
    delay(100);
  }
}

void hapticJerkyMotion() {
  // Jerky motion: 2 long pulses (rough/jerky feeling)
  for (int i = 0; i < 2; i++) {
    digitalWrite(PIN_VIBRATION_MOTOR, HIGH);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(400);
    digitalWrite(PIN_VIBRATION_MOTOR, LOW);
    digitalWrite(LED_BUILTIN, LOW);
    delay(200);
  }
}

void hapticLacksPronation() {
  // Lacks pronation: 1 long pulse + 2 short (warning pattern)
  digitalWrite(PIN_VIBRATION_MOTOR, HIGH);
  digitalWrite(LED_BUILTIN, HIGH);
  delay(500);
  digitalWrite(PIN_VIBRATION_MOTOR, LOW);
  digitalWrite(LED_BUILTIN, LOW);
  delay(150);
  for (int i = 0; i < 2; i++) {
    digitalWrite(PIN_VIBRATION_MOTOR, HIGH);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
    digitalWrite(PIN_VIBRATION_MOTOR, LOW);
    digitalWrite(LED_BUILTIN, LOW);
    delay(100);
  }
}

void hapticShortSwing() {
  // Short swing: 4 very short rapid pulses (short-short-short-short)
  for (int i = 0; i < 4; i++) {
    digitalWrite(PIN_VIBRATION_MOTOR, HIGH);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(80);
    digitalWrite(PIN_VIBRATION_MOTOR, LOW);
    digitalWrite(LED_BUILTIN, LOW);
    delay(80);
  }
}
