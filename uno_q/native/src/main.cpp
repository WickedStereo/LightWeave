#include "lightweave/entropy_decoder.hpp"

#include <array>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

#ifdef LIGHTWEAVE_WITH_NCNN
#include <gpu.h>

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

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 2) {
      throw std::runtime_error(
          "Usage: lightweave-uno-runner entropy-decode|decode [options]");
    }
    const std::string command = argv[1];
    const auto arguments = parse_arguments(argc, argv, 2);
    const auto preset_code = require(arguments, "preset");
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
