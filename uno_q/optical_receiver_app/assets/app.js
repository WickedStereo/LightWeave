"use strict";

const socket = io(window.location.origin, { path: "/socket.io" });
const connection = document.querySelector("#connection");
const receiverStatus = document.querySelector("#receiver-status");
const listen = document.querySelector("#listen");
const cancel = document.querySelector("#cancel");
const result = document.querySelector("#result");
const resultTitle = document.querySelector("#result-title");
const imageResult = document.querySelector("#image-result");
const image = document.querySelector("#image");
const imageDownload = document.querySelector("#image-download");
const audioResult = document.querySelector("#audio-result");
const audio = document.querySelector("#audio");
const audioDownload = document.querySelector("#audio-download");
const metrics = document.querySelector("#metrics");
const error = document.querySelector("#error");
let mediaUrl = null;

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
  } else {
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
  imageResult.hidden = true;
  audioResult.hidden = true;
  if (data.media_type === "image") {
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
