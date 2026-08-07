"use strict";

const socket = io(window.location.origin, { path: "/socket.io" });
const connection = document.querySelector("#connection");
const status = document.querySelector("#receiver-status");
const form = document.querySelector("#arm-form");
const expectedBytes = document.querySelector("#expected-bytes");
const result = document.querySelector("#result");
const error = document.querySelector("#error");
const download = document.querySelector("#download");
let downloadUrl = null;

function showError(message) {
  error.textContent = message;
  error.hidden = false;
}

socket.on("connect", () => {
  connection.textContent = "connected";
  socket.emit("get_initial_state", {});
});

socket.on("disconnect", () => {
  connection.textContent = "disconnected";
  status.textContent = "board connection lost";
});

socket.on("receiver_status", (data) => {
  status.textContent = data.expected_bytes
    ? `${data.status} / waiting for ${data.expected_bytes} bytes`
    : data.status;
  form.querySelector("button").disabled = data.status === "armed";
});

socket.on("receiver_error", (data) => showError(data.error));

socket.on("receiver_result", (data) => {
  document.querySelector("#result-bytes").textContent = data.received_bytes;
  document.querySelector("#result-sha").textContent = data.payload_sha256;
  document.querySelector("#result-stop").textContent = data.stop_bit_valid ? "valid" : "INVALID";
  document.querySelector("#result-hex").textContent = data.hex_preview;
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  const raw = atob(data.payload_base64);
  const bytes = Uint8Array.from(raw, (character) => character.charCodeAt(0));
  downloadUrl = URL.createObjectURL(new Blob([bytes], {type: "application/octet-stream"}));
  download.href = downloadUrl;
  result.hidden = false;
  error.hidden = true;
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  error.hidden = true;
  result.hidden = true;
  socket.emit("arm_receiver", {expected_bytes: Number(expectedBytes.value)});
});
