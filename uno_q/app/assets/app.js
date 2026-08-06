"use strict";

const form = document.querySelector("#receive-form");
const preset = document.querySelector("#preset");
const payload = document.querySelector("#payload");
const budget = document.querySelector("#budget");
const result = document.querySelector("#result");
const errorBox = document.querySelector("#error");
const image = document.querySelector("#image");
const download = document.querySelector("#download");
const metrics = document.querySelector("#metrics");
const statusMark = document.querySelector("#status-mark");
const statusText = document.querySelector("#status-text");
const submit = form.querySelector("button");
let presets = [];

function selectedPreset() {
  return presets.find((item) => item.code === preset.value);
}

function updateBudget() {
  const item = selectedPreset();
  budget.textContent = item
    ? `${item.output_size} × ${item.output_size} output / maximum ${item.maximum_bytes} raw bytes`
    : "";
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
  result.hidden = true;
}

function showMetrics(values) {
  metrics.replaceChildren();
  const ordered = [
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
  ];
  for (const [name, value] of ordered) {
    const term = document.createElement("dt");
    const definition = document.createElement("dd");
    term.textContent = name;
    definition.textContent = String(value);
    metrics.append(term, definition);
  }
}

async function initialize() {
  try {
    const [statusResponse, presetResponse] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch("/api/presets", { cache: "no-store" }),
    ]);
    const status = await statusResponse.json();
    const available = await presetResponse.json();
    if (!statusResponse.ok) throw new Error(status.issues?.join("; ") || "Accelerator unavailable.");
    presets = available.presets;
    for (const item of presets) {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = `${item.code} — ${item.output_size}px / ${item.maximum_bytes} B`;
      preset.append(option);
    }
    if (presets.some((item) => item.code === "I128-Q1-B768")) preset.value = "I128-Q1-B768";
    updateBudget();
    statusMark.textContent = "[OK]";
    statusText.textContent = `${status.gpu} / ${status.backend} / CPU fallback disabled`;
  } catch (error) {
    statusMark.textContent = "[!!]";
    statusText.textContent = error.message;
    submit.disabled = true;
  }
}

preset.addEventListener("change", updateBudget);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  const file = payload.files[0];
  const item = selectedPreset();
  if (!file || !item) return showError("Choose a preset and payload.bin.");
  if (file.size === 0 || file.size > item.maximum_bytes) {
    return showError(`Payload must contain 1–${item.maximum_bytes} bytes for ${item.code}.`);
  }
  submit.disabled = true;
  submit.textContent = "Reconstructing...";
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
    download.href = url;
    showMetrics(body.metrics);
    result.hidden = false;
  } catch (error) {
    showError(error.message);
  } finally {
    submit.disabled = false;
    submit.textContent = "Reconstruct image";
  }
});

initialize();
