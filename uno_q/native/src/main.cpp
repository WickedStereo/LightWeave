#include "lightweave/entropy_decoder.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

#ifdef LIGHTWEAVE_WITH_NCNN
#include <gpu.h>

#include "lightweave/audio_decoder.hpp"
#include "lightweave/ncnn_decoder.hpp"
#endif

namespace {

struct Preset {
  std::size_t latent_size;
  std::size_t output_size;
  std::size_t maximum_bytes;
};

const std::map<std::string, Preset> kPresets{
    {"I64-Q1-B128", {4, 64, 128}},
    {"I128-Q1-B768", {8, 128, 768}},
    {"I256-Q1-B2048", {16, 256, 2048}},
};

std::string json_escape(const std::string& value) {
  std::string escaped;
  for (const auto character : value) {
    switch (character) {
      case '\\':
        escaped += "\\\\";
        break;
      case '"':
        escaped += "\\\"";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        escaped += character;
    }
  }
  return escaped;
}

std::map<std::string, std::string> parse_arguments(int argc, char** argv,
                                                   int first) {
  std::map<std::string, std::string> values;
  for (int index = first; index < argc; index += 2) {
    if (index + 1 >= argc || std::string(argv[index]).rfind("--", 0) != 0) {
      throw std::runtime_error("Expected --name value arguments.");
    }
    values.emplace(std::string(argv[index]).substr(2), argv[index + 1]);
  }
  return values;
}

std::string require(const std::map<std::string, std::string>& values,
                    const std::string& name) {
  const auto found = values.find(name);
  if (found == values.end() || found->second.empty()) {
    throw std::runtime_error("Missing required --" + name + " argument.");
  }
  return found->second;
}

const Preset& preset_for(const std::string& code) {
  const auto found = kPresets.find(code);
  if (found == kPresets.end()) {
    throw std::runtime_error("Unsupported raw image preset: " + code + ".");
  }
  return found->second;
}

std::size_t parse_size(const std::map<std::string, std::string>& values,
                       const std::string& name, std::size_t minimum,
                       std::size_t maximum) {
  const auto text = require(values, name);
  if (text.empty() ||
      !std::all_of(text.begin(), text.end(), [](unsigned char character) {
        return std::isdigit(character) != 0;
      })) {
    throw std::runtime_error("--" + name + " must be a decimal integer.");
  }
  std::size_t value = 0;
  try {
    value = static_cast<std::size_t>(std::stoull(text));
  } catch (const std::exception&) {
    throw std::runtime_error("--" + name + " is outside the supported range.");
  }
  if (value < minimum || value > maximum) {
    throw std::runtime_error("--" + name + " is outside the supported range.");
  }
  return value;
}

std::size_t audio_samples_for(const std::string& code) {
  constexpr auto prefix = "A1-E15-S";
  if (code.rfind(prefix, 0) != 0 ||
      code.size() <= std::char_traits<char>::length(prefix)) {
    throw std::runtime_error(
        "Malformed raw audio preset; expected A1-E15-S<n>.");
  }
  const auto samples = code.substr(std::char_traits<char>::length(prefix));
  if (samples.front() == '0' ||
      !std::all_of(samples.begin(), samples.end(), [](unsigned char character) {
        return std::isdigit(character) != 0;
      })) {
    throw std::runtime_error(
        "Malformed raw audio preset; expected A1-E15-S<n>.");
  }
  std::size_t result = 0;
  try {
    result = static_cast<std::size_t>(std::stoull(samples));
  } catch (const std::exception&) {
    throw std::runtime_error("Raw audio sample count is outside the supported range.");
  }
  if (result == 0 || result > 5U * 24000U) {
    throw std::runtime_error("Raw audio preset exceeds the 5-second limit.");
  }
  return result;
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 2) {
      throw std::runtime_error(
          "Usage: lightweave-uno-runner entropy-decode|decode|audio-decode "
          "[options]");
    }
    const std::string command = argv[1];
    const auto arguments = parse_arguments(argc, argv, 2);
    const auto preset_code = require(arguments, "preset");

    if (command == "audio-decode" || command == "audio-unpack") {
#ifdef LIGHTWEAVE_WITH_NCNN
      const auto original_samples = audio_samples_for(preset_code);
      const auto payload_path =
          std::filesystem::path(require(arguments, "payload"));
      const auto payload = lightweave::read_binary_file(
          payload_path, lightweave::kAudioChunkBytes *
                            lightweave::kAudioMaximumChunks);
      const auto codebooks = lightweave::load_audio_codebooks(
          std::filesystem::path(require(arguments, "codebooks")));
      if (command == "audio-unpack") {
        const auto embedding =
            lightweave::decode_audio_embedding(payload, codebooks);
        lightweave::write_npy_f32(
            std::filesystem::path(require(arguments, "output")),
            embedding.values, {1, 128, 1, embedding.frame_count});
        lightweave::write_audio_codes_u16(
            std::filesystem::path(require(arguments, "codes-output")),
            embedding.codes);
        std::cout << "{\"status\":\"ok\",\"preset\":\""
                  << json_escape(preset_code) << "\",\"model_sha256\":\""
                  << lightweave::hex_sha256(codebooks.model_sha256)
                  << "\",\"payload_bytes\":" << payload.size()
                  << ",\"frame_count\":" << embedding.frame_count
                  << ",\"code_count\":" << embedding.codes.size()
                  << "}\n";
        return 0;
      }
      const auto split = parse_size(arguments, "split", 2, 13);
      const auto tail_channels =
          parse_size(arguments, "tail-channels", 1, 512);
      const auto tail_frames =
          parse_size(arguments, "tail-frames", 1, 24000);
      ncnn::create_gpu_instance();
      lightweave::AudioDecodeResult reconstructed;
      try {
        reconstructed = lightweave::reconstruct_audio_ncnn_hybrid(
            payload, original_samples, split, tail_channels, tail_frames,
            codebooks,
            std::filesystem::path(require(arguments, "prefix-param")),
            std::filesystem::path(require(arguments, "prefix-bin")),
            std::filesystem::path(require(arguments, "tail-param")),
            std::filesystem::path(require(arguments, "tail-bin")));
      } catch (...) {
        ncnn::destroy_gpu_instance();
        throw;
      }
      ncnn::destroy_gpu_instance();
      const auto output = std::filesystem::path(require(arguments, "output"));
      lightweave::write_wav_pcm16(output, reconstructed.waveform);
      std::cout
          << "{\"status\":\"ok\",\"preset\":\""
          << json_escape(preset_code) << "\",\"backend\":\""
          << json_escape(reconstructed.backend) << "\",\"device\":\""
          << json_escape(reconstructed.device)
          << "\",\"strict_suffix_no_fallback\":true,\"selected_split\":"
          << reconstructed.split << ",\"cpu_compute_layers\":"
          << reconstructed.cpu_compute_layers
          << ",\"vulkan_compute_layers\":"
          << reconstructed.vulkan_compute_layers
          << ",\"model_sha256\":\""
          << lightweave::hex_sha256(codebooks.model_sha256)
          << "\",\"payload_bytes\":" << payload.size()
          << ",\"chunk_count\":"
          << payload.size() / lightweave::kAudioChunkBytes
          << ",\"output_samples\":" << reconstructed.waveform.size()
          << ",\"cpu_codebook_seconds\":" << reconstructed.codebook_seconds
          << ",\"cpu_prefix_seconds\":"
          << reconstructed.cpu_prefix_seconds
          << ",\"accelerator_seconds\":"
          << reconstructed.accelerator_seconds
          << ",\"postprocess_seconds\":"
          << reconstructed.postprocess_seconds
          << ",\"raw_maximum_boundary_jump\":"
          << reconstructed.raw_maximum_boundary_jump
          << ",\"conditioned_maximum_boundary_jump\":"
          << reconstructed.conditioned_maximum_boundary_jump << "}\n";
      return 0;
#else
      throw std::runtime_error(
          "This runner was built without the ncnn hybrid audio backend.");
#endif
    }

    const auto& preset = preset_for(preset_code);
    const auto payload_path = std::filesystem::path(require(arguments, "payload"));
    const auto tables_path = std::filesystem::path(require(arguments, "tables"));
    const auto payload =
        lightweave::read_binary_file(payload_path, preset.maximum_bytes);
    if (payload.empty()) {
      throw std::runtime_error("Raw image payload is empty.");
    }
    const auto tables = lightweave::load_entropy_tables(tables_path);
    const auto entropy_started = std::chrono::steady_clock::now();
    const auto decoded = lightweave::decode_entropy_payload(
        payload, tables, preset.latent_size);
    const auto entropy_seconds = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - entropy_started).count();

    if (command == "entropy-decode") {
      const auto output = std::filesystem::path(require(arguments, "output"));
      lightweave::write_npy_f32(
          output, decoded.latent,
          {1, 192, preset.latent_size, preset.latent_size});
      std::cout << "{\"status\":\"ok\",\"preset\":\""
                << json_escape(preset_code) << "\",\"model_sha256\":\""
                << lightweave::hex_sha256(tables.model_sha256)
                << "\",\"latent_size\":" << preset.latent_size
                << ",\"symbols\":" << decoded.latent.size()
                << ",\"payload_bytes\":" << payload.size()
                << ",\"entropy_seconds\":" << entropy_seconds
                << ",\"words_consumed\":" << decoded.words_consumed << "}\n";
      return 0;
    }

    if (command == "decode") {
#ifdef LIGHTWEAVE_WITH_NCNN
      const auto param = std::filesystem::path(require(arguments, "model-param"));
      const auto bin = std::filesystem::path(require(arguments, "model-bin"));
      const auto output = std::filesystem::path(require(arguments, "output"));
      ncnn::create_gpu_instance();
      lightweave::ReconstructionResult reconstructed;
      try {
        reconstructed = lightweave::reconstruct_ncnn_vulkan(
            decoded.latent, preset.latent_size, preset.output_size, param, bin);
      } catch (...) {
        ncnn::destroy_gpu_instance();
        throw;
      }
      ncnn::destroy_gpu_instance();
      lightweave::write_ppm_rgb(output, reconstructed.image, preset.output_size);
      std::cout << "{\"status\":\"ok\",\"preset\":\""
                << json_escape(preset_code) << "\",\"backend\":\""
                << json_escape(reconstructed.evidence.backend)
                << "\",\"device\":\""
                << json_escape(reconstructed.evidence.device)
                << "\",\"strict_no_fallback\":true,\"compute_layers\":"
                << reconstructed.evidence.layer_count
                << ",\"model_sha256\":\""
                << lightweave::hex_sha256(tables.model_sha256) << "\""
                << ",\"payload_bytes\":" << payload.size()
                << ",\"entropy_seconds\":" << entropy_seconds
                << ",\"inference_seconds\":"
                << reconstructed.evidence.inference_seconds << "}\n";
      return 0;
#else
      throw std::runtime_error(
          "This runner was built without the strict ncnn Vulkan backend.");
#endif
    }

    throw std::runtime_error("Unsupported runner command: " + command + ".");
  } catch (const std::exception& error) {
    std::cerr << "{\"status\":\"error\",\"message\":\""
              << json_escape(error.what()) << "\"}\n";
    return 2;
  }
}
