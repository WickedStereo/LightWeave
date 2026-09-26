#include <Arduino_RouterBridge.h>
#include "lightweave_optical_frame.h"
#include "lightweave_parallel_optical.h"

const int laserPins[LightWeaveParallel::kLaneCount] = {5, 7, 9};
const unsigned long bitDurationMs = 25;
const unsigned long bitDurationUs = bitDurationMs * 1000UL;
const int maximumPayloadBytes = 2048;

uint8_t payloadBuffer[maximumPayloadBytes];
bool byteLoaded[maximumPayloadBytes];
int activePayloadBytes = 0;
int loadedByteCount = 0;
bool transmissionInProgress = false;
uint8_t activeProfileId = 0;
uint32_t activeMediaParameter = 0;

void waitUntil(unsigned long targetTime) {
  while ((long)(micros() - targetTime) < 0) {
  }
}

void setAllLanes(int bitValue) {
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    digitalWrite(laserPins[lane], bitValue == 1 ? HIGH : LOW);
  }
}

bool prepareTransmission(int payloadLength, int wireMode, int profileId,
                         int mediaParameter) {
  if (transmissionInProgress) return false;
  if (payloadLength < 1 || payloadLength > maximumPayloadBytes) return false;
  if (wireMode != 1) {
    Serial.println("Parallel transmitter supports LWF1 only");
    return false;
  }
  if (profileId < 0 || profileId > 255 || mediaParameter < 0) return false;
  if (!LightWeaveFrame::validateFields(static_cast<uint8_t>(profileId),
                                        payloadLength,
                                        static_cast<uint32_t>(mediaParameter))) {
    return false;
  }

  activePayloadBytes = payloadLength;
  activeProfileId = static_cast<uint8_t>(profileId);
  activeMediaParameter = static_cast<uint32_t>(mediaParameter);
  loadedByteCount = 0;
  for (int index = 0; index < maximumPayloadBytes; ++index) {
    payloadBuffer[index] = 0;
    byteLoaded[index] = false;
  }
  setAllLanes(0);
  Serial.print("Three-lane payload buffer prepared for ");
  Serial.print(activePayloadBytes);
  Serial.println(" bytes");
  return true;
}

bool storeImageByte(int index, int value) {
  if (transmissionInProgress) return false;
  if (index < 0 || index >= activePayloadBytes) return false;
  if (value < 0 || value > 255) return false;
  payloadBuffer[index] = static_cast<uint8_t>(value);
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

int getLaneCount() {
  return LightWeaveParallel::kLaneCount;
}

bool setLaneTestMask(int mask) {
  if (transmissionInProgress || mask < 0 || mask >= (1 << LightWeaveParallel::kLaneCount)) {
    return false;
  }
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    digitalWrite(laserPins[lane], (mask & (1 << lane)) ? HIGH : LOW);
  }
  Serial.print("Three-lane test mask set to 0x");
  Serial.println(mask, HEX);
  return true;
}

uint8_t wireByteAt(int index, const uint8_t *header, uint16_t crc) {
  if (index < LightWeaveFrame::kHeaderBytes) return header[index];
  index -= LightWeaveFrame::kHeaderBytes;
  if (index < activePayloadBytes) return payloadBuffer[index];
  index -= activePayloadBytes;
  return index == 0 ? static_cast<uint8_t>(crc & 0xff)
                    : static_cast<uint8_t>((crc >> 8) & 0xff);
}

void sendByteSlot(const uint8_t laneValues[LightWeaveParallel::kLaneCount],
                  unsigned long &nextBitBoundary) {
  for (int bitIndex = 7; bitIndex >= 0; --bitIndex) {
    for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
      const int value = (laneValues[lane] >> bitIndex) & 1;
      digitalWrite(laserPins[lane], value == 1 ? HIGH : LOW);
    }
    nextBitBoundary += bitDurationUs;
    waitUntil(nextBitBoundary);
  }
}

bool transmitPayload() {
  if (transmissionInProgress || !isImageBufferComplete()) return false;
  transmissionInProgress = true;

  uint8_t header[LightWeaveFrame::kHeaderBytes];
  LightWeaveFrame::writeHeader(header, activeProfileId, activePayloadBytes,
                               activeMediaParameter);
  uint16_t crc = 0xffff;
  for (int index = 0; index < LightWeaveFrame::kHeaderBytes; ++index) {
    crc = LightWeaveFrame::updateCrc(crc, header[index]);
  }
  for (int index = 0; index < activePayloadBytes; ++index) {
    crc = LightWeaveFrame::updateCrc(crc, payloadBuffer[index]);
  }

  const int frameBytes = LightWeaveFrame::kHeaderBytes + activePayloadBytes +
                         LightWeaveFrame::kCrcBytes;
  const int slots = LightWeaveParallel::slotCount(frameBytes);
  Serial.print("Three-lane LWF1 transmission: ");
  Serial.print(frameBytes);
  Serial.print(" frame bytes / ");
  Serial.print(slots);
  Serial.println(" parallel byte slots");
  Serial.flush();

  unsigned long nextBitBoundary = micros() + bitDurationUs;
  setAllLanes(1);
  waitUntil(nextBitBoundary);

  for (int slot = 0; slot < slots; ++slot) {
    uint8_t laneValues[LightWeaveParallel::kLaneCount] = {0, 0, 0};
    for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
      const int wireIndex = slot * LightWeaveParallel::kLaneCount + lane;
      if (wireIndex < frameBytes) {
        laneValues[lane] = wireByteAt(wireIndex, header, crc);
      }
    }
    sendByteSlot(laneValues, nextBitBoundary);
  }

  setAllLanes(0);
  nextBitBoundary += bitDurationUs;
  waitUntil(nextBitBoundary);
  setAllLanes(0);
  transmissionInProgress = false;
  Serial.print("Three-lane transmission complete; CRC 0x");
  Serial.println(crc, HEX);
  return true;
}

void setup() {
  Serial.begin(9600);
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    pinMode(laserPins[lane], OUTPUT);
  }
  setAllLanes(0);
  Bridge.begin();
  Bridge.provide("prepare_transmission", prepareTransmission);
  Bridge.provide("store_image_byte", storeImageByte);
  Bridge.provide("is_image_buffer_complete", isImageBufferComplete);
  Bridge.provide("transmit_payload", transmitPayload);
  Bridge.provide("transmit_image", transmitPayload);
  Bridge.provide("get_loaded_byte_count", getLoadedByteCount);
  Bridge.provide("get_lane_count", getLaneCount);
  Bridge.provide("set_lane_test_mask", setLaneTestMask);
  Serial.println("LightWeave three-lane LWF1 transmitter ready");
  Serial.println("D5/D7/D9 / 25 ms per bit / MSB first");
}

void loop() {
}
