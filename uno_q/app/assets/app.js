"use strict";

const imageForm = document.querySelector("#image-form");
const imagePreset = document.querySelector("#image-preset");
const imagePayload = document.querySelector("#image-payload");
const imageBudget = document.querySelector("#image-budget");
const imageResult = document.querySelector("#image-result");
const audioForm = document.querySelector("#audio-form");
const audioPreset = document.querySelector("#audio-preset");
const audioPayload = document.querySelector("#audio-payload");
const audioResult = document.querySelector("#audio-result");
const errorBox = document.querySelector("#error");
const image = document.querySelector("#image");
const imageDownload = document.querySelector("#image-download");
const imageMetrics = document.querySelector("#image-metrics");
const audio = document.querySelector("#audio");
const audioDownload = document.querySelector("#audio-download");
const audioMetrics = document.querySelector("#audio-metrics");
const statusMark = document.querySelector("#status-mark");
const statusText = document.querySelector("#status-text");
const imageSubmit = imageForm.querySelector("button");
const audioSubmit = audioForm.querySelector("button");
let imagePresets = [];
let audioContract = null;

function selectedImagePreset() {
  return imagePresets.find((item) => item.code === imagePreset.value);
}

function updateImageBudget() {
  const item = selectedImagePreset();
  imageBudget.textContent = item
    ? `${item.output_size} x ${item.output_size} output / maximum ${item.maximum_bytes} raw bytes`
    : "";
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function renderMetrics(target, ordered) {
  target.replaceChildren();
  for (const [name, value] of ordered) {
    const term = document.createElement("dt");
    const definition = document.createElement("dd");
    term.textContent = name;
    definition.textContent = String(value);
    target.append(term, definition);
  }
}

function showImageMetrics(values) {
  renderMetrics(imageMetrics, [
    ["preset", values.preset_code],
    ["payload", `${values.raw_bytes} bytes`],
    ["entropy", `${(values.entropy_seconds * 1000).toFixed(2)} ms`],
    ["accelerator", `${(values.inference_seconds * 1000).toFixed(2)} ms`],
    ["total runner", `${(values.total_seconds * 1000).toFixed(2)} ms`],
    ["backend", values.backend],
    ["device", values.device],
    ["Vulkan compute layers", values.compute_layers],
    ["CPU fallback", values.strict_no_fallback ? "disabled" : "ERROR"],
    ["model SHA-256", values.model_sha256],
  ]);
}

function showAudioMetrics(values) {
  renderMetrics(audioMetrics, [
    ["preset", values.preset_code],
    ["payload", `${values.raw_bytes} bytes / ${values.chunk_count} chunks`],
    ["samples", `${values.output_samples} at 24 kHz mono`],
    ["CPU codebook", `${(values.cpu_codebook_seconds * 1000).toFixed(2)} ms`],
    ["CPU recurrent prefix", `${(values.cpu_prefix_seconds * 1000).toFixed(2)} ms`],
    ["Adreno suffix", `${(values.accelerator_seconds * 1000).toFixed(2)} ms`],
    ["total runner", `${(values.total_seconds * 1000).toFixed(2)} ms`],
    ["split", `${values.selected_split} / layers ${values.selected_split}-15 on Adreno`],
    ["Vulkan compute layers", values.vulkan_compute_layers],
    ["suffix CPU fallback", values.strict_suffix_no_fallback ? "disabled" : "ERROR"],
    ["device", values.device],
    ["boundary correction", values.boundary_correction],
    ["model SHA-256", values.model_sha256],
  ]);
}

async function initialize() {
  try {
    const [statusResponse, presetResponse] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch("/api/presets", { cache: "no-store" }),
    ]);
    const status = await statusResponse.json();
    const available = await presetResponse.json();
    if (!statusResponse.ok) {
      throw new Error(status.issues?.join("; ") || "Accelerator unavailable.");
    }
    imagePresets = available.image_presets || available.presets;
    audioContract = available.audio;
    for (const item of imagePresets) {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = `${item.code} - ${item.output_size}px / ${item.maximum_bytes} B`;
      imagePreset.append(option);
    }
    if (imagePresets.some((item) => item.code === "I128-Q1-B768")) {
      imagePreset.value = "I128-Q1-B768";
    }
    updateImageBudget();
    statusMark.textContent = "[OK]";
    statusText.textContent = `${status.gpu} / images: Adreno / audio: CPU + Adreno split ${status.audio_selected_split}`;
  } catch (error) {
    statusMark.textContent = "[!!]";
    statusText.textContent = error.message;
    imageSubmit.disabled = true;
    audioSubmit.disabled = true;
  }
}

imagePreset.addEventListener("change", updateImageBudget);

imageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  const file = imagePayload.files[0];
  const item = selectedImagePreset();
  if (!file || !item) return showError("Choose a preset and payload.bin.");
  if (file.size === 0 || file.size > item.maximum_bytes) {
    return showError(`Payload must contain 1-${item.maximum_bytes} bytes for ${item.code}.`);
  }
  imageSubmit.disabled = true;
  imageSubmit.textContent = "Reconstructing...";
  try {
    const response = await fetch(`/api/receive/image?preset=${encodeURIComponent(item.code)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.message || "Reconstruction failed.");
    const url = `data:image/png;base64,${body.png_base64}`;
    image.src = url;
    imageDownload.href = url;
    showImageMetrics(body.metrics);
    imageResult.hidden = false;
  } catch (error) {
    showError(error.message);
  } finally {
    imageSubmit.disabled = false;
    imageSubmit.textContent = "Reconstruct image";
  }
});

audioForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  const file = audioPayload.files[0];
  const code = audioPreset.value.trim();
  const match = /^A1-E15-S([1-9][0-9]*)$/.exec(code);
  if (!file || !match || !audioContract) {
    return showError("Choose payload.bin and enter a valid A1-E15-S<n> settings code.");
  }
  if (file.size === 0 || file.size > audioContract.maximum_bytes || file.size % 188 !== 0) {
    return showError(`Audio payload must contain 1-${audioContract.maximum_bytes} bytes in complete 188-byte chunks.`);
  }
  const chunks = file.size / 188;
  const samples = Number(match[1]);
  if (samples <= (chunks - 1) * 24000 || samples > chunks * 24000) {
    return showError(`Settings code sample count is impossible for ${chunks} chunks.`);
  }
  audioSubmit.disabled = true;
  audioSubmit.textContent = "Reconstructing...";
  try {
    const response = await fetch(`/api/receive/audio?preset=${encodeURIComponent(code)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.message || "Audio reconstruction failed.");
    const url = `data:audio/wav;base64,${body.wav_base64}`;
    audio.src = url;
    audioDownload.href = url;
    showAudioMetrics(body.metrics);
    audioResult.hidden = false;
  } catch (error) {
    showError(error.message);
  } finally {
    audioSubmit.disabled = false;
    audioSubmit.textContent = "Reconstruct audio";
  }
});

initialize();
