#include "lightweave/ncnn_decoder.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <string>

#include <gpu.h>
#include <layer.h>
#include <net.h>

namespace lightweave {

ReconstructionResult reconstruct_ncnn_vulkan(
    const std::vector<float>& latent, std::size_t latent_size,
    std::size_t output_size, const std::filesystem::path& param_path,
    const std::filesystem::path& bin_path) {
  if (ncnn::get_gpu_count() <= 0) {
    throw std::runtime_error("ncnn did not discover a Vulkan GPU.");
  }
  const auto* device = ncnn::get_gpu_device(0);
  if (device == nullptr || !device->is_valid()) {
    throw std::runtime_error("ncnn Vulkan device 0 is invalid.");
  }
  const std::string device_name = device->info.device_name();
  if (device_name.find("Adreno") == std::string::npos ||
      device_name.find("llvmpipe") != std::string::npos) {
    throw std::runtime_error(
        "Strict UNO Q reconstruction requires the Qualcomm Adreno GPU; "
        "ncnn selected " +
        device_name + ".");
  }

  ncnn::Net net;
  net.set_vulkan_device(device);
  net.opt.use_vulkan_compute = true;
  net.opt.use_fp16_packed = true;
  net.opt.use_fp16_storage = true;
  // Turnip on the exercised Adreno 702 intermittently faults during repeated
  // 256px runs with fp16 arithmetic. Keep compact fp16 storage/packing but use
  // fp32 arithmetic for stable strict-Vulkan execution.
  net.opt.use_fp16_arithmetic = false;
  net.opt.num_threads = 1;
  if (net.load_param(param_path.string().c_str()) != 0 ||
      net.load_model(bin_path.string().c_str()) != 0) {
    throw std::runtime_error("Could not load the ncnn decoder artifacts.");
  }

  std::size_t compute_layers = 0;
  for (const auto* layer : net.layers()) {
    if (layer == nullptr) {
      throw std::runtime_error("ncnn graph contains a null layer.");
    }
    if (layer->type == "Input" || layer->type == "Split" ||
        layer->type == "Noop") {
      continue;
    }
    ++compute_layers;
    if (!layer->support_vulkan) {
      throw std::runtime_error("ncnn layer " + layer->name + " (" +
                               layer->type +
                               ") does not support Vulkan; CPU fallback is "
                               "forbidden.");
    }
  }
  if (compute_layers == 0) {
    throw std::runtime_error("ncnn graph contains no compute layers.");
  }

  const auto expected_latent = 192U * latent_size * latent_size;
  if (latent.size() != expected_latent) {
    throw std::runtime_error("Latent tensor has the wrong element count.");
  }
  ncnn::Mat input(static_cast<int>(latent_size),
                  static_cast<int>(latent_size), 192,
                  const_cast<float*>(latent.data()));
  auto extractor = net.create_extractor();
  if (extractor.input("in0", input) != 0) {
    throw std::runtime_error("ncnn rejected the latent input tensor.");
  }

  const auto started = std::chrono::steady_clock::now();
  ncnn::Mat output;
  if (extractor.extract("out0", output) != 0) {
    throw std::runtime_error("ncnn failed to reconstruct the image.");
  }
  const auto elapsed = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - started);

  if (output.dims != 3 || output.c != 3 ||
      output.w != static_cast<int>(output_size) ||
      output.h != static_cast<int>(output_size)) {
    throw std::runtime_error("ncnn returned an unexpected image shape.");
  }
  ReconstructionResult result;
  result.image.reserve(3U * output_size * output_size);
  for (int channel = 0; channel < 3; ++channel) {
    const ncnn::Mat channel_view = output.channel(channel);
    const auto* values = reinterpret_cast<const float*>(channel_view.data);
    for (std::size_t index = 0; index < output_size * output_size; ++index) {
      const auto value = values[index];
      if (!std::isfinite(value)) {
        throw std::runtime_error("ncnn returned a non-finite image value.");
      }
      result.image.push_back(value);
    }
  }
  result.evidence.backend = "ncnn-vulkan";
  result.evidence.device = device_name;
  result.evidence.layer_count = compute_layers;
  result.evidence.inference_seconds = elapsed.count();
  return result;
}

void write_ppm_rgb(const std::filesystem::path& path,
                   const std::vector<float>& nchw, std::size_t size) {
  if (nchw.size() != 3U * size * size) {
    throw std::runtime_error("Image tensor has the wrong element count.");
  }
  std::ofstream output(path, std::ios::binary | std::ios::trunc);
  if (!output) {
    throw std::runtime_error("Could not create reconstructed image.");
  }
  output << "P6\n" << size << " " << size << "\n255\n";
  for (std::size_t pixel = 0; pixel < size * size; ++pixel) {
    for (std::size_t channel = 0; channel < 3; ++channel) {
      const auto value = std::clamp(nchw[channel * size * size + pixel],
                                    0.0F, 1.0F);
      const auto byte = static_cast<unsigned char>(std::lround(value * 255.0F));
      output.put(static_cast<char>(byte));
    }
  }
  if (!output) {
    throw std::runtime_error("Failed while writing reconstructed image.");
  }
}

}  // namespace lightweave
