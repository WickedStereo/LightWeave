const state = {
  text: null,
  image: null,
  audio: null,
  arduino: { ready: false, busy: false, confirming: null, confirmUntil: 0 },
};
const formatSeconds = (value) => `${Number(value).toFixed(3)} s`;
const OPTICAL_FRAME_OVERHEAD_BYTES = 12;
const OPTICAL_BIT_DURATION_SECONDS = 0.025;

function opticalTransferSeconds(payloadBytes, channels) {
  const framedBytes = Number(payloadBytes) + OPTICAL_FRAME_OVERHEAD_BYTES;
  const channelSlots = Math.ceil(framedBytes / channels);
  return (channelSlots * 8 + 2) * OPTICAL_BIT_DURATION_SECONDS;
}

function renderMetrics(target, entries) {
  target.replaceChildren(...entries.map(([label, value]) => {
    const card = document.createElement("div");
    card.className = "metric";
    const caption = document.createElement("span");
    caption.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    card.append(caption, strong);
    return card;
  }));
}

function renderHardware(prefix, usage) {
  if (!usage) return;
  const measurement = usage.process_measurement || {};
  const used = (usage.stages || [])
    .filter((stage) => stage.used !== false && !String(stage.stage).startsWith("not used"))
    .map((stage) => stage.processor)
    .join(" + ");
  renderMetrics(document.querySelector(`#${prefix}-hardware-summary`), [
    ["Processors", used || "CPU"],
    ["Process CPU", formatSeconds(measurement.process_cpu_seconds || 0)],
    ["Process peak memory", measurement.peak_process_rss_mib == null ? "n/a" : `${Number(measurement.peak_process_rss_mib).toFixed(1)} MiB`],
    ["Measured operation", usage.operation || "operation"],
  ]);
  document.querySelector(`#${prefix}-hardware-evidence`).textContent = JSON.stringify(usage, null, 2);
}

function decodeBase64(value) {
  const binary = atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function dataUrlBlob(value) {
  const [header, body] = value.split(",", 2);
  const type = header.match(/^data:([^;]+)/)?.[1] || "application/octet-stream";
  return new Blob([decodeBase64(body)], { type });
}

async function responseBody(response) {
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

async function loadStatus() {
  const box = document.querySelector("#runtime-status");
  try {
    const status = await responseBody(await fetch("/api/status"));
    const ready = status.weights_ready && status.raw_decoder_ready &&
      status.audio_weights_ready && status.audio_tail_ready && status.arm64_worker_ready;
    box.textContent = ready ? "raw runtime ready / offline" : "setup incomplete / inspect status";
    box.classList.toggle("ready", ready);
    box.title = JSON.stringify(status, null, 2);
  } catch {
    box.textContent = "Local runtime unavailable";
  }
}

function setArduinoButtons() {
  document.querySelector("#text-arduino").disabled =
    !state.text || !state.arduino.ready || state.arduino.busy;
  document.querySelector("#image-arduino").disabled =
    !state.image || !state.arduino.ready || state.arduino.busy;
  document.querySelector("#audio-arduino").disabled =
    !state.audio || !state.arduino.ready || state.arduino.busy;
}

function clearArduinoConfirmation() {
  state.arduino.confirming = null;
  state.arduino.confirmUntil = 0;
  document.querySelector("#text-arduino").textContent = "send to Arduino";
  document.querySelector("#image-arduino").textContent = "send to Arduino";
  document.querySelector("#audio-arduino").textContent = "send to Arduino";
}

document.querySelector("#text-input").addEventListener("input", (event) => {
  document.querySelector("#text-count").textContent = new TextEncoder().encode(event.target.value).length;
});

document.querySelector("#text-transmit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const activity = document.querySelector("#text-activity");
  const error = document.querySelector("#text-error");
  const result = document.querySelector("#text-result");
  activity.hidden = false;
  error.hidden = true;
  result.hidden = true;
  form.querySelector("button[type=submit]").disabled = true;
  try {
    const body = await responseBody(await fetch("/api/transmit/text", {
      method: "POST", body: new FormData(form),
    }));
    if (state.text?.payloadUrl) URL.revokeObjectURL(state.text.payloadUrl);
    const payload = decodeBase64(body.payload_base64);
    const payloadUrl = URL.createObjectURL(new Blob([payload], { type: "application/octet-stream" }));
    state.text = { ...body, payload, payloadUrl };
    document.querySelector("#text-download").href = payloadUrl;
    document.querySelector("#text-code").textContent = body.preset_code;
    document.querySelector("#text-preview").textContent = body.text;
    renderMetrics(document.querySelector("#text-metrics"), [
      ["Raw payload", `${body.raw_bytes} / ${body.maximum_bytes} bytes`],
      ["Characters", String(body.characters)],
      ["Encoding", "printable ASCII / no AI"],
      ["Optical / 1 channel", formatSeconds(opticalTransferSeconds(body.raw_bytes, 1))],
      ["Optical / 3 channels", formatSeconds(opticalTransferSeconds(body.raw_bytes, 3))],
    ]);
    renderHardware("text", body.hardware_usage);
    result.hidden = false;
    setArduinoButtons();
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    activity.hidden = true;
    form.querySelector("button[type=submit]").disabled = false;
  }
});

async function loadArduinoStatus() {
  const box = document.querySelector("#arduino-status");
  try {
    const status = await responseBody(await fetch("/api/adapters/uno-q/status"));
    state.arduino.ready = Boolean(status.ready);
    state.arduino.busy = Boolean(status.busy);
    let message = `${status.app_status} / ${status.transport}`;
    if (status.busy) message += " / busy";
    if (status.error) message = status.error;
    box.querySelector("span").textContent = message;
    box.classList.toggle("ready", status.ready && !status.busy);
  } catch (caught) {
    state.arduino.ready = false;
    state.arduino.busy = false;
    box.querySelector("span").textContent = caught.message;
    box.classList.remove("ready");
  }
  setArduinoButtons();
}

async function sendToArduino(mediaType) {
  const current = state[mediaType];
  const button = document.querySelector(`#${mediaType}-arduino`);
  const result = document.querySelector(`#${mediaType}-arduino-result`);
  const error = document.querySelector(`#${mediaType}-error`);
  const singleChannelSeconds = opticalTransferSeconds(current.payload.length, 1);
  const threeChannelSeconds = opticalTransferSeconds(current.payload.length, 3);
  const now = Date.now();
  if (state.arduino.confirming !== mediaType || now > state.arduino.confirmUntil) {
    clearArduinoConfirmation();
    state.arduino.confirming = mediaType;
    state.arduino.confirmUntil = now + 10000;
    button.textContent = `confirm send / ${current.payload.length} B / 1-channel ${singleChannelSeconds.toFixed(2)} s / 3-channel ${threeChannelSeconds.toFixed(2)} s`;
    window.setTimeout(() => {
      if (state.arduino.confirming === mediaType && Date.now() > state.arduino.confirmUntil) {
        clearArduinoConfirmation();
      }
    }, 10100);
    return;
  }
  clearArduinoConfirmation();

  state.arduino.busy = true;
  setArduinoButtons();
  button.textContent = "buffering on Arduino...";
  result.hidden = true;
  error.hidden = true;
  try {
    const form = new FormData();
    form.append("file", new Blob([current.payload]), "payload.bin");
    form.append("media_type", mediaType);
    form.append("preset_code", current.preset_code);
    const body = await responseBody(await fetch("/api/adapters/uno-q/transmit", {
      method: "POST", body: form,
    }));
    result.textContent = [
      `accepted / ${body.adapter}`,
      `${body.buffered_bytes} raw payload bytes buffered unchanged`,
      `${body.wire_mode} / ${body.total_optical_bytes} framed bytes / ${body.optical_bits} optical bits`,
      `header ${body.header_hex} / CRC ${body.wire_crc_hex}`,
      `1-channel optical time ${singleChannelSeconds.toFixed(2)} s`,
      `3-channel optical time ${threeChannelSeconds.toFixed(2)} s`,
      `request ${body.request_id}`,
      "launch accepted; physical completion is not claimed",
      "",
      "HARDWARE EVIDENCE",
      JSON.stringify({ laptop: body.laptop_hardware_usage, uno_q: body.hardware_usage }, null, 2),
    ].join("\n");
    result.hidden = false;
    const delay = Math.max(1000, Number(body.estimated_transmission_seconds) * 1000 + 1000);
    window.setTimeout(loadArduinoStatus, delay);
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
    state.arduino.busy = false;
  } finally {
    button.textContent = "send to Arduino";
    setArduinoButtons();
    loadArduinoStatus();
  }
}

function bindPreview(inputSelector, previewSelector) {
  const input = document.querySelector(inputSelector);
  const preview = document.querySelector(previewSelector);
  input.addEventListener("change", () => {
    if (!input.files.length) return;
    preview.src = URL.createObjectURL(input.files[0]);
    preview.hidden = false;
  });
}

document.querySelector("#image-transmit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const activity = document.querySelector("#image-activity");
  const error = document.querySelector("#image-error");
  const result = document.querySelector("#image-result");
  activity.hidden = false;
  error.hidden = true;
  result.hidden = true;
  form.querySelector("button[type=submit]").disabled = true;
  try {
    const body = await responseBody(await fetch("/api/transmit/image", {
      method: "POST", body: new FormData(form),
    }));
    if (state.image?.payloadUrl) URL.revokeObjectURL(state.image.payloadUrl);
    const payload = decodeBase64(body.payload_base64);
    const payloadUrl = URL.createObjectURL(new Blob([payload], { type: "application/octet-stream" }));
    state.image = { ...body, payload, payloadUrl };
    document.querySelector("#image-download").href = payloadUrl;
    document.querySelector("#image-code").textContent = body.preset_code;
    document.querySelector("#image-reference").src = body.encoded_reference;
    renderMetrics(document.querySelector("#image-metrics"), [
      ["Raw payload", `${body.raw_bytes} / ${body.maximum_bytes} bytes`],
      ["Output", `${body.output_size} x ${body.output_size}`],
      ["Effective detail", body.effective_detail ? `${body.effective_detail} x ${body.effective_detail}` : body.fallback],
      ["Fallback", body.fallback],
      ["Bits / output pixel", Number(body.bits_per_pixel).toFixed(3)],
      ["Optical / 1 channel", formatSeconds(opticalTransferSeconds(body.raw_bytes, 1))],
      ["Optical / 3 channels", formatSeconds(opticalTransferSeconds(body.raw_bytes, 3))],
      ["Encode", formatSeconds(body.encode_seconds)],
    ]);
    renderHardware("image", body.hardware_usage);
    document.querySelector("#image-verification").hidden = true;
    document.querySelector("#image-reference-caption").textContent = `${body.output_size} x ${body.output_size} encoded target`;
    result.hidden = false;
    setArduinoButtons();
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    activity.hidden = true;
    form.querySelector("button[type=submit]").disabled = false;
  }
});

document.querySelector("#image-copy").addEventListener("click", () => navigator.clipboard.writeText(state.image.preset_code));
document.querySelector("#image-verify").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const error = document.querySelector("#image-error");
  button.disabled = true;
  error.hidden = true;
  try {
    const form = new FormData();
    form.append("file", new Blob([state.image.payload]), "payload.bin");
    form.append("preset_code", state.image.preset_code);
    form.append("backend", "qnn");
    form.append("reference", dataUrlBlob(state.image.encoded_reference), "reference.png");
    const body = await responseBody(await fetch("/api/receive/image", { method: "POST", body: form }));
    document.querySelector("#image-reconstructed").src = body.reconstructed_image;
    renderMetrics(document.querySelector("#image-verify-metrics"), [
      ["Output", `${body.output_width} x ${body.output_height}`],
      ["Entropy decode", formatSeconds(body.entropy_decode_seconds)],
      ["NPU reconstruction", formatSeconds(body.reconstruction_seconds)],
      ["PSNR", `${Number(body.psnr_db).toFixed(2)} dB`],
      ["MS-SSIM", body.ms_ssim === null ? "n/a" : Number(body.ms_ssim).toFixed(3)],
    ]);
    document.querySelector("#image-evidence").textContent = JSON.stringify(body.npu_evidence, null, 2);
    renderHardware("image-verify", body.hardware_usage);
    document.querySelector("#image-verification").hidden = false;
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#audio-transmit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const activity = document.querySelector("#audio-activity");
  const error = document.querySelector("#audio-error");
  const result = document.querySelector("#audio-result");
  activity.hidden = false;
  error.hidden = true;
  result.hidden = true;
  form.querySelector("button[type=submit]").disabled = true;
  try {
    const body = await responseBody(await fetch("/api/transmit/audio", {
      method: "POST", body: new FormData(form),
    }));
    if (state.audio?.payloadUrl) URL.revokeObjectURL(state.audio.payloadUrl);
    const payload = decodeBase64(body.payload_base64);
    const payloadUrl = URL.createObjectURL(new Blob([payload], { type: "application/octet-stream" }));
    state.audio = { ...body, payload, payloadUrl };
    document.querySelector("#audio-download").href = payloadUrl;
    document.querySelector("#audio-code").textContent = body.preset_code;
    renderMetrics(document.querySelector("#audio-metrics"), [
      ["Raw payload", `${body.raw_bytes} bytes`],
      ["Chunks", `${body.chunk_count} x 188 bytes`],
      ["Duration", `${Number(body.duration_seconds).toFixed(3)} s`],
      ["Payload rate", `${Number(body.code_payload_bps).toFixed(0)} bps`],
      ["Optical / 1 channel", formatSeconds(opticalTransferSeconds(body.raw_bytes, 1))],
      ["Optical / 3 channels", formatSeconds(opticalTransferSeconds(body.raw_bytes, 3))],
      ["Encode", formatSeconds(body.encode_seconds)],
    ]);
    renderHardware("audio", body.hardware_usage);
    document.querySelector("#audio-verification").hidden = true;
    result.hidden = false;
    setArduinoButtons();
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    activity.hidden = true;
    form.querySelector("button[type=submit]").disabled = false;
  }
});

document.querySelector("#audio-copy").addEventListener("click", () => navigator.clipboard.writeText(state.audio.preset_code));
document.querySelector("#text-copy").addEventListener("click", () => navigator.clipboard.writeText(state.text.preset_code));
document.querySelector("#text-arduino").addEventListener("click", () => sendToArduino("text"));
document.querySelector("#image-arduino").addEventListener("click", () => sendToArduino("image"));
document.querySelector("#audio-arduino").addEventListener("click", () => sendToArduino("audio"));
document.querySelector("#audio-verify").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const error = document.querySelector("#audio-error");
  button.disabled = true;
  error.hidden = true;
  try {
    const form = new FormData();
    form.append("file", new Blob([state.audio.payload]), "payload.bin");
    form.append("preset_code", state.audio.preset_code);
    form.append("backend", "hybrid-qnn");
    const body = await responseBody(await fetch("/api/receive/audio", { method: "POST", body: form }));
    document.querySelector("#audio-reconstructed").src = body.reconstructed_audio;
    renderMetrics(document.querySelector("#audio-verify-metrics"), [
      ["Restored samples", Number(body.restored_samples).toLocaleString()],
      ["Codebook", formatSeconds(body.codebook_decode_seconds)],
      ["CPU prefix", formatSeconds(body.cpu_prefix_seconds)],
      ["NPU tail", formatSeconds(body.reconstruction_seconds)],
    ]);
    document.querySelector("#audio-evidence").textContent = JSON.stringify(body.execution_evidence, null, 2);
    renderHardware("audio-verify", body.hardware_usage);
    document.querySelector("#audio-verification").hidden = false;
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    button.disabled = false;
  }
});

bindPreview("#image-input", "#image-preview");
bindPreview("#audio-input", "#audio-preview");

const presetBudgets = {
  "I64-Q1-B128": 128,
  "I128-Q1-B768": 768,
  "I256-Q1-B2048": 2048,
};
document.querySelector("#image-preset").addEventListener("change", (event) => {
  const budget = presetBudgets[event.target.value];
  document.querySelector("#image-preset-note").textContent =
    `Maximum framed optical time: ${opticalTransferSeconds(budget, 1).toFixed(2)} s / 1 channel; ${opticalTransferSeconds(budget, 3).toFixed(2)} s / 3 channels.`;
});

for (const button of document.querySelectorAll("[data-sample]")) {
  button.addEventListener("click", async () => {
    const error = document.querySelector("#image-error");
    error.hidden = true;
    try {
      const response = await fetch(`/api/samples/image/${button.dataset.sample}`);
      if (!response.ok) throw new Error("Could not load the local test pattern.");
      const blob = await response.blob();
      const file = new File([blob], `${button.dataset.sample}.png`, { type: "image/png" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      const input = document.querySelector("#image-input");
      input.files = transfer.files;
      input.dispatchEvent(new Event("change"));
    } catch (caught) {
      error.textContent = caught.message;
      error.hidden = false;
    }
  });
}
loadStatus();
loadArduinoStatus();
  document.querySelector("#text-arduino").textContent = "send to Arduino";
