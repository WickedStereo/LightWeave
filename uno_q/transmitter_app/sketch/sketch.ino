#include <Arduino_RouterBridge.h>
#include "lightweave_optical_frame.h"

const int laserPin = 9;
const unsigned long bitDurationMs = 25;
const unsigned long bitDurationUs = bitDurationMs * 1000UL;
const int maximumPayloadBytes = 2048;

uint8_t imageBuffer[maximumPayloadBytes];
bool byteLoaded[maximumPayloadBytes];
int activePayloadBytes = 0;
int loadedByteCount = 0;
bool transmissionInProgress = false;
int activeWireMode = 1;
uint8_t activeProfileId = 0;
uint32_t activeMediaParameter = 0;

void waitUntil(unsigned long targetTime) {
  while ((long)(micros() - targetTime) < 0) {
  }
}

void setLaserBit(int bitValue) {
  digitalWrite(laserPin, bitValue == 1 ? HIGH : LOW);
}

bool prepareTransmission(int payloadLength, int wireMode, int profileId,
                         int mediaParameter) {
  if (transmissionInProgress) {
    Serial.println("Cannot prepare buffer during transmission");
    return false;
  }
  if (payloadLength < 1 || payloadLength > maximumPayloadBytes) {
    Serial.println("Payload length must be between 1 and 2048 bytes");
    return false;
  }
  if (wireMode != 0 && wireMode != 1) {
    Serial.println("Wire mode must be raw-v0 (0) or LWF1 (1)");
    return false;
  }
  if (profileId < 0 || profileId > 255 || mediaParameter < 0) {
    Serial.println("Invalid profile or media parameter");
    return false;
  }
  if (wireMode == 1 &&
      !LightWeaveFrame::validateFields(static_cast<uint8_t>(profileId),
                                       payloadLength,
                                       static_cast<uint32_t>(mediaParameter))) {
    Serial.println("Invalid LWF1 profile contract");
    return false;
  }

  activePayloadBytes = payloadLength;
  activeWireMode = wireMode;
  activeProfileId = static_cast<uint8_t>(profileId);
  activeMediaParameter = static_cast<uint32_t>(mediaParameter);
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

void sendByteMsbFirst(uint8_t value, unsigned long &nextBitBoundary) {
  for (int bitIndex = 7; bitIndex >= 0; bitIndex--) {
    setLaserBit((value >> bitIndex) & 1);
    nextBitBoundary += bitDurationUs;
    waitUntil(nextBitBoundary);
  }
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
  Serial.print("Wire mode: ");
  Serial.println(activeWireMode == 1 ? "LWF1" : "raw-v0");
  Serial.print("Bit duration: ");
  Serial.print(bitDurationMs);
  Serial.println(" ms");
  Serial.flush();

  unsigned long nextBitBoundary = micros() + bitDurationUs;
  setLaserBit(1);
  waitUntil(nextBitBoundary);

  if (activeWireMode == 1) {
    uint8_t header[LightWeaveFrame::kHeaderBytes];
    LightWeaveFrame::writeHeader(header, activeProfileId, activePayloadBytes,
                                 activeMediaParameter);
    uint16_t crc = 0xffff;
    for (int index = 0; index < LightWeaveFrame::kHeaderBytes; ++index) {
      crc = LightWeaveFrame::updateCrc(crc, header[index]);
      sendByteMsbFirst(header[index], nextBitBoundary);
    }
    for (int index = 0; index < activePayloadBytes; ++index) {
      crc = LightWeaveFrame::updateCrc(crc, imageBuffer[index]);
      sendByteMsbFirst(imageBuffer[index], nextBitBoundary);
    }
    sendByteMsbFirst(static_cast<uint8_t>(crc & 0xff), nextBitBoundary);
    sendByteMsbFirst(static_cast<uint8_t>((crc >> 8) & 0xff), nextBitBoundary);
    Serial.print("LWF1 CRC16: 0x");
    Serial.println(crc, HEX);
  } else {
    for (int index = 0; index < activePayloadBytes; ++index) {
      sendByteMsbFirst(imageBuffer[index], nextBitBoundary);
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
  Bridge.provide("prepare_transmission", prepareTransmission);
  Bridge.provide("store_image_byte", storeImageByte);
  Bridge.provide("is_image_buffer_complete", isImageBufferComplete);
  Bridge.provide("transmit_payload", transmitImage);
  Bridge.provide("transmit_image", transmitImage);
  Bridge.provide("get_loaded_byte_count", getLoadedByteCount);
  Serial.println("LightWeave text/image/audio LWF1 transmitter ready");
}

void loop() {
}
