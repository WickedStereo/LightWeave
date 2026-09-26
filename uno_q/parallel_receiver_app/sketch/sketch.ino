#include <Arduino_RouterBridge.h>
#include "lightweave_optical_frame.h"
#include "lightweave_parallel_optical.h"

const int sensorPins[LightWeaveParallel::kLaneCount] = {A0, A2, A5};
const int sensorThresholds[LightWeaveParallel::kLaneCount] = {800, 800, 800};
const unsigned long bitDurationUs = 25000UL;
// The wire remains 25 ms/bit. This fixed receiver-side sampling calibration
// preserves the proven oscillator compensation used by the single-lane pair.
const unsigned long samplingIntervalUs = 24991UL;
const int maximumPayloadBytes = LightWeaveFrame::kMaximumPayloadBytes;
const int maximumChunkBytes = 32;

uint8_t frameHeader[LightWeaveFrame::kHeaderBytes];
uint8_t receivedPayload[maximumPayloadBytes];
uint8_t laneCurrentBytes[LightWeaveParallel::kLaneCount];
int headerByteCount = 0;
int activePayloadBytes = 0;
int receivedByteCount = 0;
int crcByteCount = 0;
int bitsInCurrentSlot = 0;
int wireByteCount = 0;
int totalFrameBytes = 0;
uint8_t activeProfileId = 0;
uint32_t activeMediaParameter = 0;
uint16_t computedCrc = 0xffff;
uint16_t receivedCrc = 0;
unsigned long nextSampleTimeUs = 0;
bool stopBitValid = false;
String receiverErrorCode = "none";

enum ReceiverState {
  IDLE,
  WAITING_FOR_START,
  RECEIVING_HEADER,
  RECEIVING_PAYLOAD,
  RECEIVING_CRC,
  WAITING_FOR_STOP,
  FRAME_READY,
  FRAME_ERROR
};

ReceiverState receiverState = IDLE;

int readLightBit(int lane) {
  return analogRead(sensorPins[lane]) > sensorThresholds[lane] ? 1 : 0;
}

bool allLanesEqual(int bitValue) {
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    if (readLightBit(lane) != bitValue) return false;
  }
  return true;
}

void appendByteAsHex(String &output, uint8_t value) {
  const char hexadecimal[] = "0123456789ABCDEF";
  output += hexadecimal[(value >> 4) & 0x0F];
  output += hexadecimal[value & 0x0F];
}

void notifyFinished() {
  Bridge.notify("frame_finished");
}

void rejectFrame(const char *code) {
  receiverErrorCode = code;
  receiverState = FRAME_ERROR;
  Serial.print("Three-lane LWF1 frame rejected: ");
  Serial.println(receiverErrorCode);
  notifyFinished();
}

void clearFrame() {
  headerByteCount = 0;
  activePayloadBytes = 0;
  receivedByteCount = 0;
  crcByteCount = 0;
  bitsInCurrentSlot = 0;
  wireByteCount = 0;
  totalFrameBytes = 0;
  activeProfileId = 0;
  activeMediaParameter = 0;
  computedCrc = 0xffff;
  receivedCrc = 0;
  nextSampleTimeUs = 0;
  stopBitValid = false;
  receiverErrorCode = "none";
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    laneCurrentBytes[lane] = 0;
  }
  for (int index = 0; index < LightWeaveFrame::kHeaderBytes; ++index) {
    frameHeader[index] = 0;
  }
}

bool startListen() {
  if (receiverState != IDLE) return false;
  clearFrame();
  receiverState = WAITING_FOR_START;
  Serial.println("LightWeave three-lane LWF1 receiver listening");
  return true;
}

bool cancelReceive() {
  if (receiverState == IDLE) return false;
  clearFrame();
  receiverState = IDLE;
  Serial.println("LightWeave three-lane listen cancelled");
  return true;
}

bool resetReceiver() {
  clearFrame();
  receiverState = IDLE;
  return true;
}

bool validateHeader() {
  if (frameHeader[0] != LightWeaveFrame::kMagic0 ||
      frameHeader[1] != LightWeaveFrame::kMagic1) {
    rejectFrame("bad-magic");
    return false;
  }
  if (frameHeader[2] != LightWeaveFrame::kVersion) {
    rejectFrame("bad-version");
    return false;
  }
  activeProfileId = frameHeader[3];
  activePayloadBytes = LightWeaveFrame::readPayloadBytes(frameHeader);
  activeMediaParameter = LightWeaveFrame::readMediaParameter(frameHeader);
  if (!LightWeaveFrame::validateFields(activeProfileId, activePayloadBytes,
                                        activeMediaParameter)) {
    rejectFrame("invalid-profile-contract");
    return false;
  }
  totalFrameBytes = LightWeaveFrame::kHeaderBytes + activePayloadBytes +
                    LightWeaveFrame::kCrcBytes;
  return true;
}

bool audioPaddingValid() {
  if (activeProfileId != 0x10) return true;
  for (int offset = 0; offset < activePayloadBytes; offset += 188) {
    if (receivedPayload[offset + 187] & 0xf0) return false;
  }
  return true;
}

bool textPayloadValid() {
  if (activeProfileId != 0x20) return true;
  for (int index = 0; index < activePayloadBytes; ++index) {
    if (receivedPayload[index] < 32 || receivedPayload[index] > 126) return false;
  }
  return true;
}

int getReceivedByteCount() {
  return receivedByteCount;
}

int getFrameProfileId() {
  return activeProfileId;
}

int getMediaParameter() {
  return static_cast<int>(activeMediaParameter);
}

int getReceivedCrc() {
  return receivedCrc;
}

int getComputedCrc() {
  return computedCrc;
}

String getReceiverErrorCode() {
  return receiverErrorCode;
}

bool getStopBitValid() {
  return (receiverState == FRAME_READY || receiverState == FRAME_ERROR) &&
         stopBitValid;
}

int getSensorReading(int lane) {
  if (lane < 0 || lane >= LightWeaveParallel::kLaneCount) return -1;
  return analogRead(sensorPins[lane]);
}

int getSensorThreshold(int lane) {
  if (lane < 0 || lane >= LightWeaveParallel::kLaneCount) return -1;
  return sensorThresholds[lane];
}

int getLaneHighMask() {
  int mask = 0;
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    if (readLightBit(lane)) mask |= 1 << lane;
  }
  return mask;
}

String getFrameHeader() {
  if (receiverState != FRAME_READY && receiverState != FRAME_ERROR) return "";
  String output;
  output.reserve(LightWeaveFrame::kHeaderBytes * 2);
  for (int index = 0; index < LightWeaveFrame::kHeaderBytes; ++index) {
    appendByteAsHex(output, frameHeader[index]);
  }
  return output;
}

String getReceivedChunk(int offset, int count) {
  if (receiverState != FRAME_READY && receiverState != FRAME_ERROR) return "";
  if (offset < 0 || count < 1 || count > maximumChunkBytes ||
      offset + count > receivedByteCount) {
    return "";
  }
  String output;
  output.reserve(count * 2);
  for (int index = offset; index < offset + count; ++index) {
    appendByteAsHex(output, receivedPayload[index]);
  }
  return output;
}

void handleWaitingForStart() {
  if (!allLanesEqual(1)) return;
  const unsigned long detectedUs = micros();
  nextSampleTimeUs = detectedUs + bitDurationUs + (bitDurationUs / 2);
  receiverState = RECEIVING_HEADER;
  Serial.println("Parallel optical start detected; reading LWF1 header");
}

void consumeWireByte(uint8_t value) {
  if (receiverState == RECEIVING_HEADER) {
    frameHeader[headerByteCount++] = value;
    computedCrc = LightWeaveFrame::updateCrc(computedCrc, value);
    if (headerByteCount == LightWeaveFrame::kHeaderBytes && validateHeader()) {
      receiverState = RECEIVING_PAYLOAD;
      Serial.print("Three-lane LWF1 header valid; profile 0x");
      Serial.print(activeProfileId, HEX);
      Serial.print("; payload ");
      Serial.print(activePayloadBytes);
      Serial.println(" bytes");
    }
    return;
  }
  if (receiverState == RECEIVING_PAYLOAD) {
    receivedPayload[receivedByteCount++] = value;
    computedCrc = LightWeaveFrame::updateCrc(computedCrc, value);
    if (receivedByteCount == activePayloadBytes) receiverState = RECEIVING_CRC;
    return;
  }
  if (receiverState == RECEIVING_CRC) {
    if (crcByteCount == 0) {
      receivedCrc = value;
    } else {
      receivedCrc |= static_cast<uint16_t>(value) << 8;
    }
    crcByteCount++;
    if (crcByteCount == LightWeaveFrame::kCrcBytes) {
      receiverState = WAITING_FOR_STOP;
    }
  }
}

void handleReceivingBits() {
  const unsigned long nowUs = micros();
  if ((long)(nowUs - nextSampleTimeUs) < 0) return;

  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    laneCurrentBytes[lane] = static_cast<uint8_t>(
        (laneCurrentBytes[lane] << 1) | readLightBit(lane));
  }
  bitsInCurrentSlot++;
  nextSampleTimeUs += samplingIntervalUs;
  if (bitsInCurrentSlot != 8) return;

  bitsInCurrentSlot = 0;
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    const uint8_t value = laneCurrentBytes[lane];
    laneCurrentBytes[lane] = 0;
    if (receiverState == FRAME_ERROR) return;
    if (totalFrameBytes > 0 && wireByteCount >= totalFrameBytes) continue;
    consumeWireByte(value);
    wireByteCount++;
  }
}

void handleWaitingForStop() {
  const unsigned long nowUs = micros();
  if ((long)(nowUs - nextSampleTimeUs) < 0) return;
  stopBitValid = allLanesEqual(0);
  if (receivedCrc != computedCrc) {
    rejectFrame("crc-mismatch");
    return;
  }
  if (!audioPaddingValid()) {
    rejectFrame("audio-padding");
    return;
  }
  if (!textPayloadValid()) {
    rejectFrame("invalid-text-payload");
    return;
  }
  if (!stopBitValid) {
    rejectFrame("invalid-stop-bit");
    return;
  }
  receiverState = FRAME_READY;
  Serial.print("Three-lane LWF1 frame complete: ");
  Serial.print(receivedByteCount);
  Serial.print(" payload bytes; CRC 0x");
  Serial.println(receivedCrc, HEX);
  notifyFinished();
}

void setup() {
  Serial.begin(9600);
  for (int lane = 0; lane < LightWeaveParallel::kLaneCount; ++lane) {
    pinMode(sensorPins[lane], INPUT);
  }
  Bridge.begin();
  Bridge.provide("start_listen", startListen);
  Bridge.provide("cancel_receive", cancelReceive);
  Bridge.provide("reset_receiver", resetReceiver);
  Bridge.provide("get_received_byte_count", getReceivedByteCount);
  Bridge.provide("get_received_chunk", getReceivedChunk);
  Bridge.provide("get_frame_header", getFrameHeader);
  Bridge.provide("get_frame_profile_id", getFrameProfileId);
  Bridge.provide("get_media_parameter", getMediaParameter);
  Bridge.provide("get_received_crc", getReceivedCrc);
  Bridge.provide("get_computed_crc", getComputedCrc);
  Bridge.provide("get_stop_bit_valid", getStopBitValid);
  Bridge.provide("get_receiver_error_code", getReceiverErrorCode);
  Bridge.provide("get_sensor_reading", getSensorReading);
  Bridge.provide("get_sensor_threshold", getSensorThreshold);
  Bridge.provide("get_lane_high_mask", getLaneHighMask);
  Serial.println("LightWeave three-lane LWF1 receiver ready");
  Serial.println("A0/A2/A5 threshold 800 / 25 ms per bit / MSB first");
}

void loop() {
  switch (receiverState) {
    case WAITING_FOR_START:
      handleWaitingForStart();
      break;
    case RECEIVING_HEADER:
    case RECEIVING_PAYLOAD:
    case RECEIVING_CRC:
      handleReceivingBits();
      break;
    case WAITING_FOR_STOP:
      handleWaitingForStop();
      break;
    case IDLE:
    case FRAME_READY:
    case FRAME_ERROR:
      break;
  }
}
