#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace lightweave {

struct EntropyChannel {
  std::int32_t offset = 0;
  float median = 0.0F;
  std::vector<std::uint32_t> cdf;
};

struct EntropyTables {
  std::uint16_t version = 0;
  std::uint16_t precision = 0;
  std::array<std::uint8_t, 32> model_sha256{};
  std::vector<EntropyChannel> channels;
};

struct DecodeResult {
  std::vector<float> latent;
  std::size_t words_consumed = 0;
  std::size_t words_total = 0;
};

EntropyTables load_entropy_tables(const std::filesystem::path& path);

DecodeResult decode_entropy_payload(const std::vector<std::uint8_t>& payload,
                                    const EntropyTables& tables,
                                    std::size_t latent_size);

std::vector<std::uint8_t> read_binary_file(const std::filesystem::path& path,
                                           std::size_t maximum_bytes = 0);

void write_npy_f32(const std::filesystem::path& path,
                   const std::vector<float>& values,
                   const std::array<std::size_t, 4>& shape);

std::string hex_sha256(const std::array<std::uint8_t, 32>& digest);

}  // namespace lightweave
