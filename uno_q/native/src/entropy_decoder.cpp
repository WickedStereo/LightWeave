/*
 * The entropy contract in this file is derived from CompressAI 1.2.8's
 * rans_interface.cpp (BSD-3-Clause-Clear) and ryg_rans (CC0). The implementation
 * was rewritten to use bounds-checked little-endian reads instead of unchecked
 * pointer casts. See ../THIRD_PARTY_NOTICES.md.
 */

#include "lightweave/entropy_decoder.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <functional>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace lightweave {
namespace {

constexpr std::array<std::uint8_t, 4> kTableMagic{'L', 'W', 'E', 'T'};
constexpr std::uint16_t kTableVersion = 1;
constexpr std::uint16_t kExpectedChannels = 192;
constexpr std::uint16_t kExpectedPrecision = 16;
constexpr std::uint32_t kCdfTotal = 1U << kExpectedPrecision;
constexpr std::uint64_t kRansLowerBound = 1ULL << 31U;
constexpr std::uint32_t kBypassPrecision = 4;
constexpr std::uint32_t kMaximumBypassValue =
    (1U << kBypassPrecision) - 1U;

class ByteReader {
 public:
  explicit ByteReader(std::vector<std::uint8_t> bytes)
      : bytes_(std::move(bytes)) {}

  std::uint16_t read_u16() {
    require(2);
    const auto value = static_cast<std::uint16_t>(
        static_cast<std::uint16_t>(bytes_[position_]) |
        static_cast<std::uint16_t>(bytes_[position_ + 1] << 8U));
    position_ += 2;
    return value;
  }

  std::uint32_t read_u32() {
    require(4);
    const auto value = static_cast<std::uint32_t>(bytes_[position_]) |
                       static_cast<std::uint32_t>(bytes_[position_ + 1]) << 8U |
                       static_cast<std::uint32_t>(bytes_[position_ + 2]) << 16U |
                       static_cast<std::uint32_t>(bytes_[position_ + 3]) << 24U;
    position_ += 4;
    return value;
  }

  std::int32_t read_i32() { return static_cast<std::int32_t>(read_u32()); }

  float read_f32() {
    const auto bits = read_u32();
    float value = 0.0F;
    static_assert(sizeof(value) == sizeof(bits));
    std::memcpy(&value, &bits, sizeof(value));
    return value;
  }

  std::vector<std::uint8_t> read_bytes(std::size_t count) {
    require(count);
    std::vector<std::uint8_t> value(bytes_.begin() + position_,
                                    bytes_.begin() + position_ + count);
    position_ += count;
    return value;
  }

  bool finished() const { return position_ == bytes_.size(); }

 private:
  void require(std::size_t count) const {
    if (count > bytes_.size() - position_) {
      throw std::runtime_error("Truncated LightWeave entropy-table artifact.");
    }
  }

  std::vector<std::uint8_t> bytes_;
  std::size_t position_ = 0;
};

class RansDecoder {
 public:
  explicit RansDecoder(const std::vector<std::uint8_t>& bytes) {
    if (bytes.size() < 8 || bytes.size() % 4 != 0) {
      throw std::runtime_error(
          "CompressAI rANS payload must contain at least two 32-bit words.");
    }
    words_.reserve(bytes.size() / 4);
    for (std::size_t index = 0; index < bytes.size(); index += 4) {
      words_.push_back(static_cast<std::uint32_t>(bytes[index]) |
                       static_cast<std::uint32_t>(bytes[index + 1]) << 8U |
                       static_cast<std::uint32_t>(bytes[index + 2]) << 16U |
                       static_cast<std::uint32_t>(bytes[index + 3]) << 24U);
    }
    state_ = static_cast<std::uint64_t>(words_[0]) |
             static_cast<std::uint64_t>(words_[1]) << 32U;
    position_ = 2;
    if (state_ < kRansLowerBound) {
      throw std::runtime_error("Invalid initial rANS state.");
    }
  }

  std::int32_t decode(const EntropyChannel& channel) {
    const auto cumulative = static_cast<std::uint32_t>(state_) & 0xFFFFU;
    const auto upper = std::upper_bound(channel.cdf.begin(), channel.cdf.end(),
                                        cumulative);
    if (upper == channel.cdf.begin() || upper == channel.cdf.end()) {
      throw std::runtime_error("Entropy CDF did not contain the rANS state.");
    }
    const auto symbol = static_cast<std::uint32_t>(
        std::distance(channel.cdf.begin(), upper) - 1);
    const auto start = channel.cdf[symbol];
    const auto frequency = channel.cdf[symbol + 1] - start;
    advance(start, frequency, kExpectedPrecision);

    const auto maximum_value =
        static_cast<std::int32_t>(channel.cdf.size() - 2);
    std::int32_t value = static_cast<std::int32_t>(symbol);
    if (value == maximum_value) {
      auto part = get_bits(kBypassPrecision);
      std::uint32_t bypass_count = part;
      while (part == kMaximumBypassValue) {
        part = get_bits(kBypassPrecision);
        if (bypass_count > 8U - part) {
          throw std::runtime_error("rANS bypass value exceeds 32-bit range.");
        }
        bypass_count += part;
      }
      if (bypass_count > 8) {
        throw std::runtime_error("rANS bypass value exceeds 32-bit range.");
      }

      std::uint32_t raw = 0;
      for (std::uint32_t index = 0; index < bypass_count; ++index) {
        raw |= get_bits(kBypassPrecision) << (index * kBypassPrecision);
      }
      value = static_cast<std::int32_t>(raw >> 1U);
      if ((raw & 1U) != 0U) {
        value = -value - 1;
      } else {
        value += maximum_value;
      }
    }

    const auto decoded = static_cast<std::int64_t>(value) + channel.offset;
    if (decoded < std::numeric_limits<std::int32_t>::min() ||
        decoded > std::numeric_limits<std::int32_t>::max()) {
      throw std::runtime_error("Decoded entropy symbol exceeds int32 range.");
    }
    return static_cast<std::int32_t>(decoded);
  }

  std::size_t words_consumed() const { return position_; }
  std::size_t words_total() const { return words_.size(); }

 private:
  std::uint32_t get_bits(std::uint32_t bits) {
    const auto value =
        static_cast<std::uint32_t>(state_) & ((1U << bits) - 1U);
    state_ >>= bits;
    renormalize();
    return value;
  }

  void advance(std::uint32_t start, std::uint32_t frequency,
               std::uint32_t scale_bits) {
    if (frequency == 0) {
      throw std::runtime_error("Entropy CDF contains a zero-frequency symbol.");
    }
    const auto mask = (1ULL << scale_bits) - 1ULL;
    state_ = frequency * (state_ >> scale_bits) + (state_ & mask) - start;
    renormalize();
  }

  void renormalize() {
    if (state_ < kRansLowerBound) {
      if (position_ >= words_.size()) {
        throw std::runtime_error("Truncated rANS payload during renormalization.");
      }
      state_ = (state_ << 32U) | words_[position_++];
      if (state_ < kRansLowerBound) {
        throw std::runtime_error("Invalid rANS state after renormalization.");
      }
    }
  }

  std::vector<std::uint32_t> words_;
  std::uint64_t state_ = 0;
  std::size_t position_ = 0;
};

void validate_channel(const EntropyChannel& channel) {
  if (channel.cdf.size() < 3 || channel.cdf.size() > 4096) {
    throw std::runtime_error("Entropy CDF length is outside safe bounds.");
  }
  if (channel.cdf.front() != 0 || channel.cdf.back() != kCdfTotal) {
    throw std::runtime_error("Entropy CDF endpoints are invalid.");
  }
  if (!std::is_sorted(channel.cdf.begin(), channel.cdf.end()) ||
      std::adjacent_find(channel.cdf.begin(), channel.cdf.end(),
                         std::greater_equal<>()) != channel.cdf.end()) {
    throw std::runtime_error("Entropy CDF must be strictly increasing.");
  }
  if (!std::isfinite(channel.median)) {
    throw std::runtime_error("Entropy median must be finite.");
  }
}

}  // namespace

std::vector<std::uint8_t> read_binary_file(const std::filesystem::path& path,
                                           std::size_t maximum_bytes) {
  std::ifstream input(path, std::ios::binary | std::ios::ate);
  if (!input) {
    throw std::runtime_error("Could not open " + path.string() + ".");
  }
  const auto length = input.tellg();
  if (length < 0) {
    throw std::runtime_error("Could not determine file length.");
  }
  const auto size = static_cast<std::size_t>(length);
  if (maximum_bytes != 0 && size > maximum_bytes) {
    throw std::runtime_error("Input exceeds its configured byte budget.");
  }
  std::vector<std::uint8_t> bytes(size);
  input.seekg(0);
  if (size != 0 &&
      !input.read(reinterpret_cast<char*>(bytes.data()),
                  static_cast<std::streamsize>(size))) {
    throw std::runtime_error("Could not read complete input file.");
  }
  return bytes;
}

EntropyTables load_entropy_tables(const std::filesystem::path& path) {
  ByteReader reader(read_binary_file(path, 1024U * 1024U));
  const auto magic = reader.read_bytes(kTableMagic.size());
  if (!std::equal(magic.begin(), magic.end(), kTableMagic.begin())) {
    throw std::runtime_error("Invalid LightWeave entropy-table magic.");
  }

  EntropyTables tables;
  tables.version = reader.read_u16();
  const auto channel_count = reader.read_u16();
  tables.precision = reader.read_u16();
  const auto reserved = reader.read_u16();
  if (tables.version != kTableVersion || channel_count != kExpectedChannels ||
      tables.precision != kExpectedPrecision || reserved != 0) {
    throw std::runtime_error("Unsupported LightWeave entropy-table contract.");
  }
  const auto digest = reader.read_bytes(tables.model_sha256.size());
  std::copy(digest.begin(), digest.end(), tables.model_sha256.begin());

  tables.channels.reserve(channel_count);
  for (std::uint16_t index = 0; index < channel_count; ++index) {
    EntropyChannel channel;
    channel.offset = reader.read_i32();
    const auto cdf_length = reader.read_u32();
    channel.median = reader.read_f32();
    if (cdf_length < 3 || cdf_length > 4096) {
      throw std::runtime_error("Entropy CDF length is outside safe bounds.");
    }
    channel.cdf.reserve(cdf_length);
    for (std::uint32_t item = 0; item < cdf_length; ++item) {
      channel.cdf.push_back(reader.read_u32());
    }
    validate_channel(channel);
    tables.channels.push_back(std::move(channel));
  }
  if (!reader.finished()) {
    throw std::runtime_error("Entropy-table artifact contains trailing bytes.");
  }
  return tables;
}

DecodeResult decode_entropy_payload(const std::vector<std::uint8_t>& payload,
                                    const EntropyTables& tables,
                                    std::size_t latent_size) {
  if (latent_size != 4 && latent_size != 8 && latent_size != 16) {
    throw std::runtime_error("Latent size must be 4, 8, or 16.");
  }
  if (tables.channels.size() != kExpectedChannels) {
    throw std::runtime_error("Entropy tables must contain 192 channels.");
  }

  const auto values_per_channel = latent_size * latent_size;
  DecodeResult result;
  result.latent.reserve(tables.channels.size() * values_per_channel);
  RansDecoder decoder(payload);
  for (const auto& channel : tables.channels) {
    for (std::size_t index = 0; index < values_per_channel; ++index) {
      const auto symbol = decoder.decode(channel);
      result.latent.push_back(static_cast<float>(symbol) + channel.median);
    }
  }
  result.words_consumed = decoder.words_consumed();
  result.words_total = decoder.words_total();
  if (result.words_consumed != result.words_total) {
    throw std::runtime_error("rANS payload contains trailing words.");
  }
  return result;
}

void write_npy_f32(const std::filesystem::path& path,
                   const std::vector<float>& values,
                   const std::array<std::size_t, 4>& shape) {
  const auto expected = shape[0] * shape[1] * shape[2] * shape[3];
  if (values.size() != expected) {
    throw std::runtime_error("NPY value count does not match its shape.");
  }
  std::ostringstream descriptor;
  descriptor << "{'descr': '<f4', 'fortran_order': False, 'shape': ("
             << shape[0] << ", " << shape[1] << ", " << shape[2] << ", "
             << shape[3] << "), }";
  auto header = descriptor.str();
  const std::size_t prefix_size = 10;
  const auto padding = (16 - ((prefix_size + header.size() + 1) % 16)) % 16;
  header.append(padding, ' ');
  header.push_back('\n');
  if (header.size() > std::numeric_limits<std::uint16_t>::max()) {
    throw std::runtime_error("NPY header is too large.");
  }

  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) {
    throw std::runtime_error("Could not create " + path.string() + ".");
  }
  const std::array<char, 8> magic{static_cast<char>(0x93), 'N', 'U', 'M',
                                  'P', 'Y', 1, 0};
  output.write(magic.data(), static_cast<std::streamsize>(magic.size()));
  const auto length = static_cast<std::uint16_t>(header.size());
  const std::array<char, 2> length_bytes{
      static_cast<char>(length & 0xFFU), static_cast<char>(length >> 8U)};
  output.write(length_bytes.data(), 2);
  output.write(header.data(), static_cast<std::streamsize>(header.size()));
  output.write(reinterpret_cast<const char*>(values.data()),
               static_cast<std::streamsize>(values.size() * sizeof(float)));
  if (!output) {
    throw std::runtime_error("Failed while writing NPY output.");
  }
}

std::string hex_sha256(const std::array<std::uint8_t, 32>& digest) {
  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (const auto byte : digest) {
    output << std::setw(2) << static_cast<unsigned int>(byte);
  }
  return output.str();
}

}  // namespace lightweave
