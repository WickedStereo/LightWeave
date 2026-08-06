#include <Arduino_RouterBridge.h>

const int laserPin = 9;
const unsigned long bitDurationMs = 25;
const unsigned long bitDurationUs = bitDurationMs * 1000UL;
const int maximumPayloadBytes = 2048;

uint8_t imageBuffer[maximumPayloadBytes];
bool byteLoaded[maximumPayloadBytes];
int activePayloadBytes = 0;
int loadedByteCount = 0;
bool transmissionInProgress = false;

void waitUntil(unsigned long targetTime) {
  while ((long)(micros() - targetTime) < 0) {
  }
}

void setLaserBit(int bitValue) {
  digitalWrite(laserPin, bitValue == 1 ? HIGH : LOW);
}

bool prepareImageBuffer(int payloadLength) {
  if (transmissionInProgress) {
    Serial.println("Cannot prepare buffer during transmission");
    return false;
  }
  if (payloadLength < 1 || payloadLength > maximumPayloadBytes) {
    Serial.println("Payload length must be between 1 and 2048 bytes");
    return false;
  }

  activePayloadBytes = payloadLength;
  loadedByteCount = 0;
  for (int i = 0; i < maximumPayloadBytes; i++) {
    imageBuffer[i] = 0;
    byteLoaded[i] = false;
  }
  digitalWrite(laserPin, LOW);
  Serial.print("Payload buffer prepared for ");
  Serial.print(activePayloadBytes);
  Serial.println(" bytes");
  return true;
}

bool storeImageByte(int index, int value) {
  if (transmissionInProgress) {
    return false;
  }
  if (index < 0 || index >= activePayloadBytes) {
    return false;
  }
  if (value < 0 || value > 255) {
    return false;
  }

  imageBuffer[index] = (uint8_t)value;
  if (!byteLoaded[index]) {
    byteLoaded[index] = true;
    loadedByteCount++;
  }
  return true;
}

bool isImageBufferComplete() {
  return activePayloadBytes > 0 && loadedByteCount == activePayloadBytes;
}

int getLoadedByteCount() {
  return loadedByteCount;
}

bool transmitImage() {
  if (transmissionInProgress) {
    Serial.println("Transmission is already running");
    return false;
  }
  if (!isImageBufferComplete()) {
    Serial.println("Payload buffer is incomplete");
    return false;
  }

  transmissionInProgress = true;
  Serial.print("LightWeave transmission starting: ");
  Serial.print(activePayloadBytes);
  Serial.println(" bytes");
  Serial.print("Bit duration: ");
  Serial.print(bitDurationMs);
  Serial.println(" ms");
  Serial.flush();

  unsigned long nextBitBoundary = micros() + bitDurationUs;
  setLaserBit(1);
  waitUntil(nextBitBoundary);

  for (int byteIndex = 0; byteIndex < activePayloadBytes; byteIndex++) {
    uint8_t byteValue = imageBuffer[byteIndex];
    for (int bitIndex = 7; bitIndex >= 0; bitIndex--) {
      setLaserBit((byteValue >> bitIndex) & 1);
      nextBitBoundary += bitDurationUs;
      waitUntil(nextBitBoundary);
    }
  }

  setLaserBit(0);
  nextBitBoundary += bitDurationUs;
  waitUntil(nextBitBoundary);
  digitalWrite(laserPin, LOW);
  transmissionInProgress = false;

  Serial.println("LightWeave transmission complete");
  Serial.println("Laser OFF");
  return true;
}

void setup() {
  Serial.begin(9600);
  pinMode(laserPin, OUTPUT);
  digitalWrite(laserPin, LOW);
  Bridge.begin();
  Bridge.provide("prepare_image_buffer", prepareImageBuffer);
  Bridge.provide("store_image_byte", storeImageByte);
  Bridge.provide("is_image_buffer_complete", isImageBufferComplete);
  Bridge.provide("transmit_image", transmitImage);
  Bridge.provide("get_loaded_byte_count", getLoadedByteCount);
  Serial.println("LightWeave variable-length laser transmitter ready");
}

void loop() {
}
