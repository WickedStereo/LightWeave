"use strict";

const socket = io(window.location.origin, { path: "/socket.io" });
const connection = document.querySelector("#connection");
const receiverStatus = document.querySelector("#receiver-status");
const listen = document.querySelector("#listen");
const cancel = document.querySelector("#cancel");
const result = document.querySelector("#result");
const resultTitle = document.querySelector("#result-title");
const textResult = document.querySelector("#text-result");
const textContent = document.querySelector("#text-content");
const textDownload = document.querySelector("#text-download");
const imageResult = document.querySelector("#image-result");
const image = document.querySelector("#image");
const imageDownload = document.querySelector("#image-download");
const audioResult = document.querySelector("#audio-result");
const audio = document.querySelector("#audio");
const audioDownload = document.querySelector("#audio-download");
const metrics = document.querySelector("#metrics");
const error = document.querySelector("#error");
const themeToggle = document.querySelector("#theme-toggle");
let mediaUrl = null;

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  const next = theme === "dark" ? "light" : "dark";
  themeToggle.textContent = `${next} mode`;
  themeToggle.setAttribute("aria-label", `Switch to ${next} mode`);
}

const savedTheme = localStorage.getItem("lightweave-theme");
applyTheme(savedTheme === "light" || savedTheme === "dark"
  ? savedTheme
  : (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
themeToggle.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("lightweave-theme", next);
  applyTheme(next);
});

function showError(message) {
  error.textContent = message;
  error.hidden = false;
}

function makeMediaUrl(encoded, type) {
  const raw = atob(encoded);
  const bytes = Uint8Array.from(raw, (character) => character.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type }));
}

function milliseconds(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 1000).toFixed(2)} ms` : "n/a";
}

function renderMetrics(values) {
  const reconstruction = values.reconstruction || {};
  const hardware = reconstruction.hardware_usage || {};
  const stm32 = hardware.stm32 || {};
  const rows = [
    ["media", values.media_type],
    ["preset", values.preset_code],
    ["profile ID", `0x${Number(values.profile_id).toString(16).padStart(2, "0")}`],
    ["raw payload", `${values.payload_bytes} bytes`],
    ["LWF1 header", values.header_hex],
    ["wire CRC", `${values.wire_crc_hex} / valid`],
    ["stop bit", values.stop_bit_valid ? "valid" : "INVALID"],
    ["payload SHA-256", values.payload_sha256],
  ];
  if (values.media_type === "image") {
    rows.push(
      ["entropy decode", milliseconds(reconstruction.entropy_seconds)],
      ["Adreno inference", milliseconds(reconstruction.inference_seconds)],
      ["backend", reconstruction.backend],
      ["device", reconstruction.device],
      ["Vulkan compute layers", reconstruction.compute_layers],
      ["CPU neural fallback", reconstruction.strict_no_fallback ? "disabled" : "ERROR"],
      ["output", `${reconstruction.output_width} × ${reconstruction.output_height}`],
      ["model SHA-256", reconstruction.model_sha256],
    );
  } else if (values.media_type === "audio") {
    rows.push(
      ["output samples", values.media_parameter],
      ["CPU codebook", milliseconds(reconstruction.cpu_codebook_seconds)],
      ["CPU prefix", milliseconds(reconstruction.cpu_prefix_seconds)],
      ["Adreno suffix", milliseconds(reconstruction.accelerator_seconds)],
      ["selected split", reconstruction.selected_split],
      ["Vulkan suffix layers", reconstruction.vulkan_compute_layers],
      ["device", reconstruction.device],
      ["CPU suffix fallback", reconstruction.strict_suffix_no_fallback ? "disabled" : "ERROR"],
      ["boundary correction", reconstruction.boundary_correction],
      ["model SHA-256", reconstruction.model_sha256],
    );
  } else {
    rows.push(
      ["decoder", reconstruction.decoder],
      ["characters", reconstruction.characters],
      ["AI / accelerator", reconstruction.accelerator_required ? "required" : "not used"],
    );
  }
  rows.push(
    ["optical bits decoded / STM32", stm32.decoded_optical_bits],
    ["CRC bytes checked / STM32", stm32.crc_input_bytes],
    ["peak decoder memory", hardware.peak_child_rss_kib == null ? "n/a" : `${(Number(hardware.peak_child_rss_kib) / 1024).toFixed(1)} MiB`],
    ["hardware count scope", "measured bits/timing + audited layers; not FLOPs"],
  );
  for (const stage of hardware.stages || []) {
    const count = stage.compute_layers == null ? "" : ` / ${stage.compute_layers} layers`;
    const elapsed = stage.measured_seconds == null ? "" : ` / ${milliseconds(stage.measured_seconds)}`;
    rows.push([stage.processor, `${stage.stage}${count}${elapsed}`]);
  }
  metrics.replaceChildren();
  for (const [name, value] of rows) {
    const term = document.createElement("dt");
    const definition = document.createElement("dd");
    term.textContent = name;
    definition.textContent = String(value ?? "n/a");
    metrics.append(term, definition);
  }
}

socket.on("connect", () => {
  connection.textContent = "connected";
  socket.emit("get_initial_state", {});
});

socket.on("disconnect", () => {
  connection.textContent = "disconnected";
  receiverStatus.textContent = "board connection lost";
  listen.disabled = true;
  cancel.disabled = true;
});

socket.on("receiver_status", (data) => {
  receiverStatus.textContent = data.status;
  const active = ["arming", "listening", "cancelling", "reconstructing"].includes(data.status);
  listen.disabled = active;
  cancel.disabled = !["arming", "listening"].includes(data.status);
});

socket.on("receiver_error", (data) => {
  showError(data.error);
  listen.disabled = false;
  cancel.disabled = true;
});

socket.on("receiver_result", (data) => {
  if (mediaUrl) URL.revokeObjectURL(mediaUrl);
  textResult.hidden = true;
  imageResult.hidden = true;
  audioResult.hidden = true;
  if (data.media_type === "text") {
    textContent.textContent = data.text_content;
    mediaUrl = URL.createObjectURL(new Blob([data.text_content], { type: "text/plain;charset=us-ascii" }));
    textDownload.href = mediaUrl;
    textResult.hidden = false;
    resultTitle.textContent = "Received text";
  } else if (data.media_type === "image") {
    mediaUrl = makeMediaUrl(data.png_base64, "image/png");
    image.src = mediaUrl;
    imageDownload.href = mediaUrl;
    imageResult.hidden = false;
    resultTitle.textContent = "Reconstructed image";
  } else {
    mediaUrl = makeMediaUrl(data.wav_base64, "audio/wav");
    audio.src = mediaUrl;
    audioDownload.href = mediaUrl;
    audioResult.hidden = false;
    resultTitle.textContent = "Reconstructed audio";
  }
  renderMetrics(data);
  result.hidden = false;
  error.hidden = true;
});

listen.addEventListener("click", () => {
  error.hidden = true;
  result.hidden = true;
  listen.disabled = true;
  socket.emit("listen_receiver", {});
});

cancel.addEventListener("click", () => {
  cancel.disabled = true;
  socket.emit("cancel_receiver", {});
});
