const state = { image: null, audio: null };
const formatSeconds = (value) => `${Number(value).toFixed(3)} s`;

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
      ["Transfer / 1 kbps", formatSeconds(body.at_1_kbps_seconds)],
      ["Transfer / 2 kbps", formatSeconds(body.at_2_kbps_seconds)],
      ["Encode", formatSeconds(body.encode_seconds)],
    ]);
    document.querySelector("#image-verification").hidden = true;
    document.querySelector("#image-reference-caption").textContent = `${body.output_size} x ${body.output_size} encoded target`;
    result.hidden = false;
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
      ["Transfer / 1 kbps", formatSeconds(body.at_1_kbps_seconds)],
      ["Transfer / 2 kbps", formatSeconds(body.at_2_kbps_seconds)],
      ["Encode", formatSeconds(body.encode_seconds)],
    ]);
    document.querySelector("#audio-verification").hidden = true;
    result.hidden = false;
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    activity.hidden = true;
    form.querySelector("button[type=submit]").disabled = false;
  }
});

document.querySelector("#audio-copy").addEventListener("click", () => navigator.clipboard.writeText(state.audio.preset_code));
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

const presetNotes = {
  "I64-Q1-B128": "Worst case: 1.024 s at 1 kbps or 0.512 s at 2 kbps.",
  "I128-Q1-B768": "Worst case: 6.144 s at 1 kbps or 3.072 s at 2 kbps.",
  "I256-Q1-B2048": "Worst case: 16.384 s at 1 kbps or 8.192 s at 2 kbps.",
};
document.querySelector("#image-preset").addEventListener("change", (event) => {
  document.querySelector("#image-preset-note").textContent = presetNotes[event.target.value];
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
