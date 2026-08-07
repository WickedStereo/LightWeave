#include <Arduino_RouterBridge.h>

const int sensorPin = A0;
const int sensorThreshold = 800;
const unsigned long bitDurationUs = 25000UL;
const int maximumPayloadBytes = 2048;
const int maximumChunkBytes = 32;

uint8_t receivedPayload[maximumPayloadBytes];
int activePayloadBytes = 0;
int receivedByteCount = 0;
int totalBitsCollected = 0;
int bitsInCurrentByte = 0;
uint8_t currentByte = 0;
unsigned long nextSampleTimeUs = 0;
bool stopBitValid = false;

enum ReceiverState {
  IDLE,
  WAITING_FOR_START,
  RECEIVING_DATA,
  WAITING_FOR_STOP,
  PAYLOAD_READY
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

bool startReceive(int payloadLength) {
  if (
    receiverState == WAITING_FOR_START ||
    receiverState == RECEIVING_DATA ||
    receiverState == WAITING_FOR_STOP
  ) {
    return false;
  }
  if (payloadLength < 1 || payloadLength > maximumPayloadBytes) {
    return false;
  }

  activePayloadBytes = payloadLength;
  receivedByteCount = 0;
  totalBitsCollected = 0;
  bitsInCurrentByte = 0;
  currentByte = 0;
  nextSampleTimeUs = 0;
  stopBitValid = false;
  for (int index = 0; index < activePayloadBytes; index++) {
    receivedPayload[index] = 0;
  }
  receiverState = WAITING_FOR_START;
  Serial.print("LightWeave image receiver armed for ");
  Serial.print(activePayloadBytes);
  Serial.println(" bytes");
  return true;
}

int getReceivedByteCount() {
  return receivedByteCount;
}

bool getStopBitValid() {
  return receiverState == PAYLOAD_READY && stopBitValid;
}

String getReceivedChunk(int offset, int count) {
  if (receiverState != PAYLOAD_READY) {
    return "";
  }
  if (
    offset < 0 || count < 1 || count > maximumChunkBytes ||
    offset + count > receivedByteCount
  ) {
    return "";
  }
  String output;
  output.reserve(count * 2);
  for (int index = offset; index < offset + count; index++) {
    appendByteAsHex(output, receivedPayload[index]);
  }
  return output;
}

void handleWaitingForStart() {
  if (readLightBit() == 0) {
    return;
  }
  const unsigned long detectedUs = micros();
  nextSampleTimeUs = detectedUs + bitDurationUs + (bitDurationUs / 2);
  receiverState = RECEIVING_DATA;
  Serial.println("Optical start detected");
}

void handleReceivingData() {
  const unsigned long nowUs = micros();
  if ((long)(nowUs - nextSampleTimeUs) < 0) {
    return;
  }

  currentByte = (uint8_t)((currentByte << 1) | readLightBit());
  bitsInCurrentByte++;
  totalBitsCollected++;
  if (bitsInCurrentByte == 8) {
    receivedPayload[receivedByteCount] = currentByte;
    receivedByteCount++;
    currentByte = 0;
    bitsInCurrentByte = 0;
  }
  nextSampleTimeUs += bitDurationUs;
  if (totalBitsCollected == activePayloadBytes * 8) {
    receiverState = WAITING_FOR_STOP;
  }
}

void handleWaitingForStop() {
  const unsigned long nowUs = micros();
  if ((long)(nowUs - nextSampleTimeUs) < 0) {
    return;
  }
  stopBitValid = readLightBit() == 0;
  receiverState = PAYLOAD_READY;
  Serial.print("Optical payload complete: ");
  Serial.print(receivedByteCount);
  Serial.print(" bytes; stop bit ");
  Serial.println(stopBitValid ? "valid" : "invalid");
  Bridge.notify("payload_ready");
}

void setup() {
  Serial.begin(9600);
  pinMode(sensorPin, INPUT);
  Bridge.begin();
  Bridge.provide("start_receive", startReceive);
  Bridge.provide("get_received_byte_count", getReceivedByteCount);
  Bridge.provide("get_received_chunk", getReceivedChunk);
  Bridge.provide("get_stop_bit_valid", getStopBitValid);
  Serial.println("LightWeave optical image receiver ready");
  Serial.println("A0 threshold 800 / 25 ms per bit");
}

void loop() {
  switch (receiverState) {
    case WAITING_FOR_START:
      handleWaitingForStart();
      break;
    case RECEIVING_DATA:
      handleReceivingData();
      break;
    case WAITING_FOR_STOP:
      handleWaitingForStop();
      break;
    case IDLE:
    case PAYLOAD_READY:
      break;
  }
}

