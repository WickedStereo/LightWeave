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
    box.textContent = ready ? "Receiver ready · offline" : "Setup incomplete · inspect status";
    box.classList.toggle("ready", ready);
    box.title = JSON.stringify(status, null, 2);
  } catch {
    box.textContent = "Local runtime unavailable";
  }
}

document.querySelector("#image-receive-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const activity = document.querySelector("#image-activity");
  const error = document.querySelector("#image-error");
  const result = document.querySelector("#image-result");
  activity.hidden = false;
  error.hidden = true;
  result.hidden = true;
  form.querySelector("button").disabled = true;
  try {
    const data = new FormData(form);
    data.append("backend", "qnn");
    const body = await responseBody(await fetch("/api/receive/image", { method: "POST", body: data }));
    document.querySelector("#image-output").src = body.reconstructed_image;
    document.querySelector("#image-save").href = body.reconstructed_image;
    renderMetrics(document.querySelector("#image-metrics"), [
      ["Raw payload", `${body.raw_bytes} bytes`],
      ["Output", `${body.output_width}×${body.output_height}`],
      ["Entropy decode", formatSeconds(body.entropy_decode_seconds)],
      ["NPU reconstruction", formatSeconds(body.reconstruction_seconds)],
    ]);
    document.querySelector("#image-evidence").textContent = JSON.stringify(body.npu_evidence, null, 2);
    result.hidden = false;
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    activity.hidden = true;
    form.querySelector("button").disabled = false;
  }
});

document.querySelector("#audio-receive-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const activity = document.querySelector("#audio-activity");
  const error = document.querySelector("#audio-error");
  const result = document.querySelector("#audio-result");
  activity.hidden = false;
  error.hidden = true;
  result.hidden = true;
  form.querySelector("button").disabled = true;
  try {
    const data = new FormData(form);
    data.append("backend", "hybrid-qnn");
    const body = await responseBody(await fetch("/api/receive/audio", { method: "POST", body: data }));
    document.querySelector("#audio-output").src = body.reconstructed_audio;
    document.querySelector("#audio-save").href = body.reconstructed_audio;
    renderMetrics(document.querySelector("#audio-metrics"), [
      ["Raw payload", `${body.raw_bytes} bytes`],
      ["Chunks", `${body.chunk_count} × 188 bytes`],
      ["Restored samples", Number(body.restored_samples).toLocaleString()],
      ["Codebook", formatSeconds(body.codebook_decode_seconds)],
      ["CPU prefix", formatSeconds(body.cpu_prefix_seconds)],
      ["NPU tail", formatSeconds(body.reconstruction_seconds)],
    ]);
    document.querySelector("#audio-evidence").textContent = JSON.stringify(body.execution_evidence, null, 2);
    result.hidden = false;
  } catch (caught) {
    error.textContent = caught.message;
    error.hidden = false;
  } finally {
    activity.hidden = true;
    form.querySelector("button").disabled = false;
  }
});

loadStatus();
