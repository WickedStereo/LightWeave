"use strict";

const socket = io(window.location.origin, { path: "/socket.io" });
const connection = document.querySelector("#connection");
const receiverStatus = document.querySelector("#receiver-status");
const form = document.querySelector("#arm-form");
const preset = document.querySelector("#preset-code");
const expectedBytes = document.querySelector("#expected-bytes");
const budget = document.querySelector("#budget");
const result = document.querySelector("#result");
const image = document.querySelector("#image");
const download = document.querySelector("#download");
const metrics = document.querySelector("#metrics");
const error = document.querySelector("#error");
const submit = form.querySelector("button");
const budgets = {
  "I64-Q1-B128": 128,
  "I128-Q1-B768": 768,
  "I256-Q1-B2048": 2048,
};
let imageUrl = null;

function updateBudget() {
  const maximum = budgets[preset.value];
  expectedBytes.max = maximum;
  if (Number(expectedBytes.value) > maximum) expectedBytes.value = maximum;
  budget.textContent = `Enter the exact payload size; ${preset.value} allows 1–${maximum} bytes.`;
}

function showError(message) {
  error.textContent = message;
  error.hidden = false;
}

function renderMetrics(values) {
  const reconstruction = values.reconstruction || {};
  const rows = [
    ["preset", values.preset_code],
    ["optical payload", `${values.received_bytes} bytes`],
    ["payload SHA-256", values.payload_sha256],
    ["stop bit", values.stop_bit_valid ? "valid" : "INVALID"],
    ["entropy decode", `${(reconstruction.entropy_seconds * 1000).toFixed(2)} ms`],
    ["Adreno inference", `${(reconstruction.inference_seconds * 1000).toFixed(2)} ms`],
    ["backend", reconstruction.backend],
    ["device", reconstruction.device],
    ["Vulkan compute layers", reconstruction.compute_layers],
    ["CPU fallback", reconstruction.strict_no_fallback ? "disabled" : "ERROR"],
    ["output", `${reconstruction.output_width} × ${reconstruction.output_height}`],
    ["model SHA-256", reconstruction.model_sha256],
  ];
  metrics.replaceChildren();
  for (const [name, value] of rows) {
    const term = document.createElement("dt");
    const definition = document.createElement("dd");
    term.textContent = name;
    definition.textContent = String(value);
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
  submit.disabled = true;
});

socket.on("receiver_status", (data) => {
  receiverStatus.textContent = data.expected_bytes
    ? `${data.status} / ${data.preset_code} / ${data.expected_bytes} bytes`
    : data.status;
  submit.disabled = ["arming", "armed", "reconstructing"].includes(data.status);
});

socket.on("receiver_error", (data) => {
  showError(data.error);
  submit.disabled = false;
});

socket.on("receiver_result", (data) => {
  if (imageUrl) URL.revokeObjectURL(imageUrl);
  const raw = atob(data.png_base64);
  const bytes = Uint8Array.from(raw, (character) => character.charCodeAt(0));
  imageUrl = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
  image.src = imageUrl;
  download.href = imageUrl;
  renderMetrics(data);
  result.hidden = false;
  error.hidden = true;
  submit.disabled = false;
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  error.hidden = true;
  result.hidden = true;
  submit.disabled = true;
  socket.emit("arm_receiver", {
    preset_code: preset.value,
    expected_bytes: Number(expectedBytes.value),
  });
});

preset.addEventListener("change", updateBudget);
updateBudget();

