#ifndef LIGHTWEAVE_OPTICAL_FRAME_H
#define LIGHTWEAVE_OPTICAL_FRAME_H

#include <Arduino.h>

namespace LightWeaveFrame {

constexpr uint8_t kMagic0 = 0x4c;
constexpr uint8_t kMagic1 = 0x57;
constexpr uint8_t kVersion = 0x01;
constexpr int kHeaderBytes = 10;
constexpr int kCrcBytes = 2;
constexpr int kFrameOverheadBytes = 12;
constexpr int kMaximumPayloadBytes = 2048;

inline uint16_t updateCrc(uint16_t crc, uint8_t value) {
  crc ^= static_cast<uint16_t>(value) << 8;
  for (int bit = 0; bit < 8; ++bit) {
    crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                         : static_cast<uint16_t>(crc << 1);
  }
  return crc;
}

inline bool validateFields(uint8_t profileId, uint16_t payloadBytes,
                           uint32_t mediaParameter) {
  if (payloadBytes == 0) return false;
  if (profileId == 0x01) return payloadBytes <= 128 && mediaParameter == 0;
  if (profileId == 0x02) return payloadBytes <= 768 && mediaParameter == 0;
  if (profileId == 0x03) return payloadBytes <= 2048 && mediaParameter == 0;
  if (profileId == 0x20) return payloadBytes <= 100 && mediaParameter == 0;
  if (profileId != 0x10 || payloadBytes > 940 || payloadBytes % 188 != 0) {
    return false;
  }
  uint32_t chunks = payloadBytes / 188;
  uint32_t minimum = (chunks - 1) * 24000UL + 1;
  uint32_t maximum = chunks * 24000UL;
  return mediaParameter >= minimum && mediaParameter <= maximum &&
         mediaParameter <= 120000UL;
}

inline void writeHeader(uint8_t *header, uint8_t profileId,
                        uint16_t payloadBytes, uint32_t mediaParameter) {
  header[0] = kMagic0;
  header[1] = kMagic1;
  header[2] = kVersion;
  header[3] = profileId;
  header[4] = static_cast<uint8_t>(payloadBytes & 0xff);
  header[5] = static_cast<uint8_t>((payloadBytes >> 8) & 0xff);
  header[6] = static_cast<uint8_t>(mediaParameter & 0xff);
  header[7] = static_cast<uint8_t>((mediaParameter >> 8) & 0xff);
  header[8] = static_cast<uint8_t>((mediaParameter >> 16) & 0xff);
  header[9] = static_cast<uint8_t>((mediaParameter >> 24) & 0xff);
}

inline uint16_t readPayloadBytes(const uint8_t *header) {
  return static_cast<uint16_t>(header[4]) |
         (static_cast<uint16_t>(header[5]) << 8);
}

inline uint32_t readMediaParameter(const uint8_t *header) {
  return static_cast<uint32_t>(header[6]) |
         (static_cast<uint32_t>(header[7]) << 8) |
         (static_cast<uint32_t>(header[8]) << 16) |
         (static_cast<uint32_t>(header[9]) << 24);
}

}  // namespace LightWeaveFrame

#endif
