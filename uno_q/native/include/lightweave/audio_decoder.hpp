#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace lightweave {

constexpr std::size_t kAudioChunkBytes = 188;
constexpr std::size_t kAudioFramesPerChunk = 75;
constexpr std::size_t kAudioSamplesPerChunk = 24000;
constexpr std::size_t kAudioMaximumChunks = 5;

struct AudioCodebooks {
  std::array<std::uint8_t, 32> model_sha256{};
  std::vector<float> values;
};

struct AudioEmbedding {
  std::vector<std::uint16_t> codes;
  std::vector<float> values;
  std::size_t frame_count = 0;
};

struct AudioDecodeResult {
  std::vector<float> waveform;
  std::string backend;
  std::string device;
  std::size_t split = 0;
  std::size_t cpu_compute_layers = 0;
  std::size_t vulkan_compute_layers = 0;
  double codebook_seconds = 0.0;
  double cpu_prefix_seconds = 0.0;
  double accelerator_seconds = 0.0;
  double postprocess_seconds = 0.0;
  double raw_maximum_boundary_jump = 0.0;
  double conditioned_maximum_boundary_jump = 0.0;
};

AudioCodebooks load_audio_codebooks(const std::filesystem::path& path);

AudioEmbedding decode_audio_embedding(
    const std::vector<std::uint8_t>& payload,
    const AudioCodebooks& codebooks);

void write_audio_codes_u16(const std::filesystem::path& path,
                           const std::vector<std::uint16_t>& codes);

AudioDecodeResult reconstruct_audio_ncnn_hybrid(
    const std::vector<std::uint8_t>& payload, std::size_t original_samples,
    std::size_t split, std::size_t tail_channels,
    std::size_t tail_frames_per_chunk, const AudioCodebooks& codebooks,
    const std::filesystem::path& prefix_param,
    const std::filesystem::path& prefix_bin,
    const std::filesystem::path& tail_param,
    const std::filesystem::path& tail_bin);

void write_wav_pcm16(const std::filesystem::path& path,
                     const std::vector<float>& waveform);

}  // namespace lightweave
