const form = document.querySelector("#roundtrip-form");
const activity = document.querySelector("#activity");
const errorBox = document.querySelector("#error");
const results = document.querySelector("#results");
const statusBox = document.querySelector("#runtime-status");

const formatSeconds = (value) => `${Number(value).toFixed(3)} s`;
const metric = (label, value) =>
  `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`;

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    const ready = status.weights_ready && status.decoder_ready && status.audio_weights_ready && status.audio_tail_ready && status.arm64_worker_ready;
    statusBox.textContent = ready ? "NPU runtime ready · offline" : "Setup incomplete · inspect status";
    statusBox.classList.toggle("ready", ready);
    statusBox.title = JSON.stringify(status, null, 2);
  } catch {
    statusBox.textContent = "Local runtime unavailable";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  activity.hidden = false;
  errorBox.hidden = true;
  results.hidden = true;
  form.querySelector("button").disabled = true;
  try {
    const response = await fetch("/api/image/roundtrip", {
      method: "POST",
      body: new FormData(form),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    const value = body.result;
    document.querySelector("#input-preview").src = body.input_image;
    document.querySelector("#output-preview").src = body.reconstructed_image;
    document.querySelector("#metrics").innerHTML = [
      metric("Complete payload", `${value.envelope_bytes.toLocaleString()} bytes`),
      metric("Bits / visible pixel", Number(value.bits_per_pixel).toFixed(3)),
      metric("Transfer · 1 kbps", formatSeconds(value.at_1_kbps_seconds)),
      metric("Transfer · 2 kbps", formatSeconds(value.at_2_kbps_seconds)),
      metric("Encode", formatSeconds(value.encode_seconds)),
      metric("Entropy decode", formatSeconds(value.entropy_decode_seconds)),
      metric("NPU reconstruction", formatSeconds(value.reconstruction_seconds)),
      metric("PSNR / MS-SSIM", `${Number(value.psnr_db).toFixed(2)} dB / ${value.ms_ssim === null ? "n/a" : Number(value.ms_ssim).toFixed(3)}`),
    ].join("");
    document.querySelector("#evidence").textContent = JSON.stringify(value.npu_evidence, null, 2);
    results.hidden = false;
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  } finally {
    activity.hidden = true;
    form.querySelector("button").disabled = false;
  }
});

loadStatus();

const audioForm = document.querySelector("#audio-form");
audioForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const audioActivity = document.querySelector("#audio-activity");
  const audioError = document.querySelector("#audio-error");
  const audioResults = document.querySelector("#audio-results");
  const button = audioForm.querySelector("button");
  audioActivity.hidden = false;
  audioError.hidden = true;
  audioResults.hidden = true;
  button.disabled = true;
  try {
    const response = await fetch("/api/audio/roundtrip", {
      method: "POST",
      body: new FormData(audioForm),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    const value = body.result;
    document.querySelector("#audio-output").src = body.reconstructed_audio;
    document.querySelector("#audio-metrics").innerHTML = [
      metric("Complete payload", `${value.envelope_bytes.toLocaleString()} bytes`),
      metric("Code payload rate", `${Number(value.code_payload_bps).toFixed(0)} bps`),
      metric("Duration", `${Number(value.duration_seconds).toFixed(2)} s`),
      metric("Restored samples", value.restored_samples.toLocaleString()),
      metric("Encode", formatSeconds(value.encode_seconds)),
      metric("CPU prefix", formatSeconds(value.cpu_prefix_seconds)),
      metric("NPU tail", formatSeconds(value.reconstruction_seconds)),
      metric("Boundary jump", Number(value.maximum_boundary_jump).toExponential(2)),
    ].join("");
    document.querySelector("#audio-evidence").textContent = JSON.stringify(value.execution_evidence, null, 2);
    audioResults.hidden = false;
  } catch (error) {
    audioError.textContent = error.message;
    audioError.hidden = false;
  } finally {
    audioActivity.hidden = true;
    button.disabled = false;
  }
});
