#include "lightweave/audio_decoder.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <stdexcept>

#include <gpu.h>
#include <layer.h>
#include <net.h>

namespace lightweave {
namespace {

constexpr std::array<char, 4> kCodebookMagic{'L', 'W', 'C', 'B'};
constexpr std::uint16_t kCodebookVersion = 1;
constexpr std::size_t kCodebookCount = 2;
constexpr std::size_t kCodebookEntries = 1024;
constexpr std::size_t kCodebookDimension = 128;
constexpr std::size_t kBitsPerCode = 10;

template <typename T>
T read_little(std::istream& input) {
  std::array<unsigned char, sizeof(T)> bytes{};
  if (!input.read(reinterpret_cast<char*>(bytes.data()), bytes.size())) {
    throw std::runtime_error("Truncated LightWeave audio artifact.");
  }
  T result{};
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    result = static_cast<T>(result | static_cast<T>(bytes[index])
                                      << (8U * index));
  }
  return result;
}

float read_f32(std::istream& input) {
  const auto bits = read_little<std::uint32_t>(input);
  float value = 0.0F;
  static_assert(sizeof(value) == sizeof(bits));
  std::memcpy(&value, &bits, sizeof(value));
  if (!std::isfinite(value)) {
    throw std::runtime_error("Audio codebook contains a non-finite value.");
  }
  return value;
}

std::vector<std::uint16_t> unpack_codes(
    const std::vector<std::uint8_t>& payload) {
  if (payload.empty() || payload.size() % kAudioChunkBytes != 0 ||
      payload.size() > kAudioChunkBytes * kAudioMaximumChunks) {
    throw std::runtime_error(
        "Raw audio payload must contain 1-5 complete 188-byte chunks.");
  }
  std::vector<std::uint16_t> codes;
  const auto chunks = payload.size() / kAudioChunkBytes;
  codes.reserve(chunks * kAudioFramesPerChunk * kCodebookCount);
  for (std::size_t chunk_index = 0; chunk_index < chunks; ++chunk_index) {
    const auto start = chunk_index * kAudioChunkBytes;
    if ((payload[start + kAudioChunkBytes - 1] & 0xF0U) != 0U) {
      throw std::runtime_error("Raw audio chunk has non-zero padding bits.");
    }
    std::uint64_t buffer = 0;
    std::size_t buffered_bits = 0;
    std::size_t position = start;
    for (std::size_t value = 0;
         value < kAudioFramesPerChunk * kCodebookCount; ++value) {
      while (buffered_bits < kBitsPerCode) {
        if (position >= start + kAudioChunkBytes) {
          throw std::runtime_error("Raw audio bitstream is truncated.");
        }
        buffer |= static_cast<std::uint64_t>(payload[position++])
                  << buffered_bits;
        buffered_bits += 8;
      }
      codes.push_back(static_cast<std::uint16_t>(buffer & 0x3FFU));
      buffer >>= kBitsPerCode;
      buffered_bits -= kBitsPerCode;
    }
    if (buffer != 0 || buffered_bits != 4 ||
        position != start + kAudioChunkBytes) {
      throw std::runtime_error("Raw audio chunk violates its padding contract.");
    }
  }
  return codes;
}

std::size_t audited_compute_layers(const ncnn::Net& net, bool require_vulkan) {
  std::size_t count = 0;
  for (const auto* layer : net.layers()) {
    if (layer == nullptr) {
      throw std::runtime_error("ncnn audio graph contains a null layer.");
    }
    if (layer->type == "Input" || layer->type == "Split" ||
        layer->type == "Noop") {
      continue;
    }
    ++count;
    if (require_vulkan && !layer->support_vulkan) {
      throw std::runtime_error("Audio suffix layer " + layer->name + " (" +
                               layer->type +
                               ") cannot run on Vulkan; fallback is forbidden.");
    }
  }
  if (count == 0) {
    throw std::runtime_error("ncnn audio graph contains no compute layers.");
  }
  return count;
}

double maximum_boundary_jump(const std::vector<float>& values) {
  double maximum = 0.0;
  for (std::size_t boundary = kAudioSamplesPerChunk;
       boundary < values.size(); boundary += kAudioSamplesPerChunk) {
    maximum = std::max(
        maximum,
        static_cast<double>(std::abs(values[boundary] - values[boundary - 1])));
  }
  return maximum;
}

void condition_boundaries(std::vector<float>& values) {
  constexpr std::size_t correction_samples = 480;
  for (std::size_t boundary = kAudioSamplesPerChunk;
       boundary < values.size(); boundary += kAudioSamplesPerChunk) {
    const auto length =
        std::min(correction_samples, values.size() - boundary);
    const auto difference = values[boundary] - values[boundary - 1];
    for (std::size_t index = 0; index < length; ++index) {
      const auto fade = length == 1
                            ? 1.0F
                            : 1.0F - static_cast<float>(index) /
                                         static_cast<float>(length - 1);
      values[boundary + index] -= difference * fade;
    }
  }
}

void write_u16(std::ostream& output, std::uint16_t value) {
  output.put(static_cast<char>(value & 0xFFU));
  output.put(static_cast<char>((value >> 8U) & 0xFFU));
}

void write_u32(std::ostream& output, std::uint32_t value) {
  for (std::size_t index = 0; index < 4; ++index) {
    output.put(static_cast<char>((value >> (index * 8U)) & 0xFFU));
  }
}

}  // namespace

AudioCodebooks load_audio_codebooks(const std::filesystem::path& path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error("Could not open audio codebook artifact.");
  }
  std::array<char, 4> magic{};
  if (!input.read(magic.data(), magic.size()) || magic != kCodebookMagic) {
    throw std::runtime_error("Invalid LightWeave audio codebook magic.");
  }
  const auto version = read_little<std::uint16_t>(input);
  const auto codebooks = read_little<std::uint16_t>(input);
  const auto entries = read_little<std::uint16_t>(input);
  const auto dimension = read_little<std::uint16_t>(input);
  if (version != kCodebookVersion || codebooks != kCodebookCount ||
      entries != kCodebookEntries || dimension != kCodebookDimension) {
    throw std::runtime_error("Unsupported LightWeave audio codebook contract.");
  }
  AudioCodebooks result;
  if (!input.read(reinterpret_cast<char*>(result.model_sha256.data()),
                  result.model_sha256.size())) {
    throw std::runtime_error("Truncated LightWeave audio model fingerprint.");
  }
  result.values.reserve(kCodebookCount * kCodebookEntries * kCodebookDimension);
  for (std::size_t index = 0;
       index < kCodebookCount * kCodebookEntries * kCodebookDimension;
       ++index) {
    result.values.push_back(read_f32(input));
  }
  if (input.peek() != std::char_traits<char>::eof()) {
    throw std::runtime_error("Audio codebook artifact contains trailing bytes.");
  }
  return result;
}

AudioEmbedding decode_audio_embedding(
    const std::vector<std::uint8_t>& payload,
    const AudioCodebooks& codebooks) {
  AudioEmbedding result;
  result.codes = unpack_codes(payload);
  result.frame_count = payload.size() / kAudioChunkBytes * kAudioFramesPerChunk;
  result.values.assign(kCodebookDimension * result.frame_count, 0.0F);
  for (std::size_t frame = 0; frame < result.frame_count; ++frame) {
    for (std::size_t book = 0; book < kCodebookCount; ++book) {
      const auto code = result.codes[frame * kCodebookCount + book];
      const auto source =
          (book * kCodebookEntries + code) * kCodebookDimension;
      for (std::size_t channel = 0; channel < kCodebookDimension; ++channel) {
        result.values[channel * result.frame_count + frame] +=
            codebooks.values[source + channel];
      }
    }
  }
  return result;
}

void write_audio_codes_u16(const std::filesystem::path& path,
                           const std::vector<std::uint16_t>& codes) {
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) {
    throw std::runtime_error("Could not create native audio code output.");
  }
  for (const auto code : codes) {
    write_u16(output, code);
  }
  if (!output) {
    throw std::runtime_error("Failed while writing native audio codes.");
  }
}

AudioDecodeResult reconstruct_audio_ncnn_hybrid(
    const std::vector<std::uint8_t>& payload, std::size_t original_samples,
    std::size_t split, std::size_t tail_channels,
    std::size_t tail_frames_per_chunk, const AudioCodebooks& codebooks,
    const std::filesystem::path& prefix_param,
    const std::filesystem::path& prefix_bin,
    const std::filesystem::path& tail_param,
    const std::filesystem::path& tail_bin) {
  const auto chunk_count = payload.size() / kAudioChunkBytes;
  const auto minimum_samples = (chunk_count - 1) * kAudioSamplesPerChunk + 1;
  const auto maximum_samples = chunk_count * kAudioSamplesPerChunk;
  if (chunk_count == 0 || chunk_count > kAudioMaximumChunks ||
      original_samples < minimum_samples || original_samples > maximum_samples) {
    throw std::runtime_error(
        "Audio sample count is impossible for the supplied raw chunks.");
  }
  if (tail_channels == 0 || tail_frames_per_chunk == 0 ||
      split < 2 || split > 13) {
    throw std::runtime_error("Invalid generated audio decoder configuration.");
  }

  AudioDecodeResult result;
  result.backend = "ncnn-hybrid-cpu-vulkan";
  result.split = split;
  const auto codebook_started = std::chrono::steady_clock::now();
  auto embedding = decode_audio_embedding(payload, codebooks);
  const auto frame_count = embedding.frame_count;
  result.codebook_seconds = std::chrono::duration<double>(
                                std::chrono::steady_clock::now() -
                                codebook_started)
                                .count();

  ncnn::Net prefix;
  prefix.opt.use_vulkan_compute = false;
  prefix.opt.use_fp16_storage = false;
  prefix.opt.use_fp16_packed = false;
  prefix.opt.use_fp16_arithmetic = false;
  prefix.opt.num_threads = 4;
  if (prefix.load_param(prefix_param.string().c_str()) != 0 ||
      prefix.load_model(prefix_bin.string().c_str()) != 0) {
    throw std::runtime_error("Could not load the ncnn audio CPU prefix.");
  }
  result.cpu_compute_layers = audited_compute_layers(prefix, false);
  ncnn::Mat prefix_input(static_cast<int>(frame_count),
                         static_cast<int>(kCodebookDimension),
                         embedding.values.data());
  auto prefix_extractor = prefix.create_extractor();
  if (prefix_extractor.input("in0", prefix_input) != 0) {
    throw std::runtime_error("ncnn rejected the audio embedding tensor.");
  }
  const auto prefix_started = std::chrono::steady_clock::now();
  ncnn::Mat prefix_output;
  if (prefix_extractor.extract("out0", prefix_output) != 0) {
    throw std::runtime_error("ncnn failed to execute the audio CPU prefix.");
  }
  result.cpu_prefix_seconds = std::chrono::duration<double>(
                                  std::chrono::steady_clock::now() -
                                  prefix_started)
                                  .count();
  if (prefix_output.dims != 2 ||
      prefix_output.h != static_cast<int>(tail_channels) ||
      prefix_output.w !=
          static_cast<int>(tail_frames_per_chunk * chunk_count)) {
    throw std::runtime_error("Audio CPU prefix returned an unexpected shape.");
  }

  if (ncnn::get_gpu_count() <= 0) {
    throw std::runtime_error("ncnn did not discover a Vulkan GPU for audio.");
  }
  const auto* device = ncnn::get_gpu_device(0);
  if (device == nullptr || !device->is_valid()) {
    throw std::runtime_error("ncnn Vulkan device 0 is invalid for audio.");
  }
  result.device = device->info.device_name();
  if (result.device.find("Adreno") == std::string::npos ||
      result.device.find("llvmpipe") != std::string::npos) {
    throw std::runtime_error(
        "Strict UNO Q audio reconstruction requires Qualcomm Adreno.");
  }

  ncnn::Net tail;
  tail.set_vulkan_device(device);
  tail.opt.use_vulkan_compute = true;
  tail.opt.use_fp16_packed = true;
  tail.opt.use_fp16_storage = true;
  tail.opt.use_fp16_arithmetic = false;
  tail.opt.num_threads = 1;
  if (tail.load_param(tail_param.string().c_str()) != 0 ||
      tail.load_model(tail_bin.string().c_str()) != 0) {
    throw std::runtime_error("Could not load the ncnn audio Vulkan suffix.");
  }
  result.vulkan_compute_layers = audited_compute_layers(tail, true);
  result.waveform.reserve(maximum_samples);
  const auto accelerator_started = std::chrono::steady_clock::now();
  for (std::size_t chunk = 0; chunk < chunk_count; ++chunk) {
    std::vector<float> tail_values(tail_channels * tail_frames_per_chunk);
    for (std::size_t channel = 0; channel < tail_channels; ++channel) {
      const auto* source = prefix_output.row(channel) +
                           chunk * tail_frames_per_chunk;
      std::copy(source, source + tail_frames_per_chunk,
                tail_values.begin() + channel * tail_frames_per_chunk);
    }
    ncnn::Mat tail_input(1, static_cast<int>(tail_frames_per_chunk),
                         static_cast<int>(tail_channels), tail_values.data());
    auto extractor = tail.create_extractor();
    if (extractor.input("in0", tail_input) != 0) {
      throw std::runtime_error("ncnn rejected an audio suffix input.");
    }
    ncnn::Mat output;
    if (extractor.extract("out0", output) != 0 ||
        output.total() != kAudioSamplesPerChunk) {
      throw std::runtime_error("ncnn audio suffix returned an invalid output.");
    }
    const auto* samples = reinterpret_cast<const float*>(output.data);
    for (std::size_t index = 0; index < kAudioSamplesPerChunk; ++index) {
      if (!std::isfinite(samples[index])) {
        throw std::runtime_error("ncnn audio suffix returned non-finite output.");
      }
      result.waveform.push_back(samples[index]);
    }
  }
  result.accelerator_seconds = std::chrono::duration<double>(
                                   std::chrono::steady_clock::now() -
                                   accelerator_started)
                                   .count();
  const auto postprocess_started = std::chrono::steady_clock::now();
  result.raw_maximum_boundary_jump = maximum_boundary_jump(result.waveform);
  condition_boundaries(result.waveform);
  result.conditioned_maximum_boundary_jump =
      maximum_boundary_jump(result.waveform);
  result.waveform.resize(original_samples);
  result.postprocess_seconds = std::chrono::duration<double>(
                                   std::chrono::steady_clock::now() -
                                   postprocess_started)
                                   .count();
  return result;
}

void write_wav_pcm16(const std::filesystem::path& path,
                     const std::vector<float>& waveform) {
  if (waveform.empty() || waveform.size() >
                              kAudioMaximumChunks * kAudioSamplesPerChunk) {
    throw std::runtime_error("Audio output length is outside the supported range.");
  }
  const auto data_bytes = waveform.size() * sizeof(std::int16_t);
  if (data_bytes > std::numeric_limits<std::uint32_t>::max() - 36U) {
    throw std::runtime_error("Audio WAV output is too large.");
  }
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) {
    throw std::runtime_error("Could not create reconstructed WAV output.");
  }
  output.write("RIFF", 4);
  write_u32(output, static_cast<std::uint32_t>(36U + data_bytes));
  output.write("WAVEfmt ", 8);
  write_u32(output, 16);
  write_u16(output, 1);
  write_u16(output, 1);
  write_u32(output, 24000);
  write_u32(output, 24000 * sizeof(std::int16_t));
  write_u16(output, sizeof(std::int16_t));
  write_u16(output, 16);
  output.write("data", 4);
  write_u32(output, static_cast<std::uint32_t>(data_bytes));
  for (const auto value : waveform) {
    if (!std::isfinite(value)) {
      throw std::runtime_error("Audio output contains a non-finite sample.");
    }
    const auto clipped = std::clamp(value, -0.999F, 0.999F);
    const auto pcm = static_cast<std::int16_t>(std::lround(clipped * 32767.0F));
    write_u16(output, static_cast<std::uint16_t>(pcm));
  }
  if (!output) {
    throw std::runtime_error("Failed while writing reconstructed WAV output.");
  }
}

}  // namespace lightweave
