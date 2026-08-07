#include <Arduino_RouterBridge.h>
#include "lightweave_optical_frame.h"

const int sensorPin = A0;
const int sensorThreshold = 800;
const unsigned long bitDurationUs = 25000UL;
// The wire remains 25 ms/bit. This fixed receiver-side sampling calibration
// compensates the measured oscillator offset between the two current boards.
const unsigned long samplingIntervalUs = 24991UL;
const int maximumPayloadBytes = LightWeaveFrame::kMaximumPayloadBytes;
const int maximumChunkBytes = 32;

uint8_t frameHeader[LightWeaveFrame::kHeaderBytes];
uint8_t receivedPayload[maximumPayloadBytes];
int headerByteCount = 0;
int activePayloadBytes = 0;
int receivedByteCount = 0;
int crcByteCount = 0;
int bitsInCurrentByte = 0;
uint8_t currentByte = 0;
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

int readLightBit() {
  return analogRead(sensorPin) > sensorThreshold ? 1 : 0;
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
  Serial.print("LWF1 frame rejected: ");
  Serial.println(receiverErrorCode);
  notifyFinished();
}

void clearFrame() {
  headerByteCount = 0;
  activePayloadBytes = 0;
  receivedByteCount = 0;
  crcByteCount = 0;
  bitsInCurrentByte = 0;
  currentByte = 0;
  activeProfileId = 0;
  activeMediaParameter = 0;
  computedCrc = 0xffff;
  receivedCrc = 0;
  nextSampleTimeUs = 0;
  stopBitValid = false;
  receiverErrorCode = "none";
  for (int index = 0; index < LightWeaveFrame::kHeaderBytes; ++index) {
    frameHeader[index] = 0;
  }
}

bool startListen() {
  if (receiverState != IDLE) return false;
  clearFrame();
  receiverState = WAITING_FOR_START;
  Serial.println("LightWeave LWF1 receiver listening");
  return true;
}

bool cancelReceive() {
  if (receiverState == IDLE) return false;
  clearFrame();
  receiverState = IDLE;
  Serial.println("LightWeave LWF1 listen cancelled");
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
  if (readLightBit() == 0) return;
  const unsigned long detectedUs = micros();
  nextSampleTimeUs = detectedUs + bitDurationUs + (bitDurationUs / 2);
  receiverState = RECEIVING_HEADER;
  Serial.println("Optical start detected; reading LWF1 header");
}

void consumeCompletedByte(uint8_t value) {
  if (receiverState == RECEIVING_HEADER) {
    frameHeader[headerByteCount++] = value;
    computedCrc = LightWeaveFrame::updateCrc(computedCrc, value);
    if (headerByteCount == LightWeaveFrame::kHeaderBytes && validateHeader()) {
      receiverState = RECEIVING_PAYLOAD;
      Serial.print("LWF1 header valid; profile 0x");
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
  currentByte = static_cast<uint8_t>((currentByte << 1) | readLightBit());
  bitsInCurrentByte++;
  nextSampleTimeUs += samplingIntervalUs;
  if (bitsInCurrentByte == 8) {
    uint8_t value = currentByte;
    currentByte = 0;
    bitsInCurrentByte = 0;
    consumeCompletedByte(value);
  }
}

void handleWaitingForStop() {
  const unsigned long nowUs = micros();
  if ((long)(nowUs - nextSampleTimeUs) < 0) return;
  stopBitValid = readLightBit() == 0;
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
  Serial.print("LWF1 frame complete: ");
  Serial.print(receivedByteCount);
  Serial.print(" payload bytes; CRC 0x");
  Serial.println(receivedCrc, HEX);
  notifyFinished();
}

void setup() {
  Serial.begin(9600);
  pinMode(sensorPin, INPUT);
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
  Serial.println("LightWeave one-shot LWF1 image/audio receiver ready");
  Serial.println("A0 threshold 800 / 25 ms per bit / MSB first");
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
