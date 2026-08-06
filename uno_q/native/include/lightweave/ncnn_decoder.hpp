#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

namespace lightweave {

struct AcceleratorEvidence {
  std::string backend;
  std::string device;
  std::size_t layer_count = 0;
  double inference_seconds = 0.0;
};

struct ReconstructionResult {
  std::vector<float> image;
  AcceleratorEvidence evidence;
};

ReconstructionResult reconstruct_ncnn_vulkan(
    const std::vector<float>& latent, std::size_t latent_size,
    std::size_t output_size, const std::filesystem::path& param_path,
    const std::filesystem::path& bin_path);

void write_ppm_rgb(const std::filesystem::path& path,
                   const std::vector<float>& nchw, std::size_t size);

}  // namespace lightweave
