# LightWeave Project Context

> Living source of truth for project intent, decisions, architecture, progress, risks, and open questions.

| Field | Current value |
| --- | --- |
| Project | LightWeave |
| Phase | Implementation authorized; environment and image feasibility gate |
| Primary milestone | Air-gapped optical image-network software path |
| Secondary milestone | EnCodec audio extension after the image gate passes |
| Last updated | 2026-08-05 |
| Approval gate | Application implementation explicitly approved on 2026-08-05 |

## Required maintenance

1. Read this document before substantive project work.
2. Update it in the same change whenever work changes scope, architecture, requirements, assumptions, decisions, risks, plan, or progress.
3. Update `Last updated`, append a change-log entry, and add a decision-log entry when a decision is made or reversed.
4. Keep confirmed facts, working assumptions, proposals, and unresolved questions distinct.
5. Update `docs/QUALCOMM_DEVELOPER_EXPERIENCE.md` whenever Qualcomm hardware, SDKs, runtimes, tools, samples, documentation, or workflows are exercised.
6. Never record credentials, personal information, or confidential source material.

Repository enforcement lives in `AGENTS.md`.

## Approved objective

LightWeave is a transport-agnostic, offline-first software system that converts media into compact bytes suitable for a very low-bandwidth optical link and reconstructs that media on a Snapdragon PC.

The current milestone ignores the physical optical implementation. It assumes a reliable, ordered byte pipe and focuses on:

1. Converting an image into a compact, self-validating `.lwv` byte stream.
2. Transferring those bytes through a file, standard stream, or loopback simulation.
3. Validating and entropy-decoding the stream on the receiver.
4. Reconstructing the image with the complete neural synthesis transform on the Snapdragon Hexagon NPU through QNN HTP.
5. Proving the selected execution device and rejecting silent CPU fallback.
6. Presenting payload, transfer, quality, latency, and provider evidence through a CLI and offline local dashboard.

After the image path passes its feasibility and acceptance gates, the same envelope and application surfaces will be extended to neural audio compression.

## Confirmed scope

### In scope now

- Image encode/decode using CompressAI `bmshj2018_factorized`, quality 1.
- EXIF correction, RGB conversion, aspect-preserving resize, and symmetric padding to 256 by 256.
- A compact versioned `.lwv` binary envelope with typed metadata, payload length, model fingerprint, and SHA-256 integrity.
- A 2,048-byte complete-envelope target for the curated image demo set.
- Separate transmitter and receiver commands, initially exercised on one PC.
- Two receiver processes/environments when required: x64 codec/entropy work and native ARM64 QNN inference.
- Fixed-shape `g_s` export, quantization/conversion, QNN HTP execution, profiling, and no-fallback enforcement.
- Offline runtime after dependencies, weights, and generated model artifacts have been prepared.
- A CLI and localhost-only dashboard.
- Reproducible source setup rather than a packaged executable.
- QUAD, Qualcomm AI Hub, QAIRT Visualizer, and direct QNN integration as development workflows.
- EnCodec 24 kHz mono audio as a later extension using an explicitly labeled hybrid CPU/NPU decoder.

### Out of scope for the current milestone

- Laser, LED, photodiode, analog front end, optical modulation, clock recovery, or Arduino firmware.
- Serial packet framing, retransmission, or error correction below the `.lwv` media envelope.
- Galaxy S25 and Cloud AI in the runtime data path.
- WebSockets or any RF-based runtime dependency.
- Medical, safety, regulatory, or absolute-security claims.
- A Windows EXE/MSIX deliverable.

### Assumptions

- The later hardware layer transfers every `.lwv` byte in order without changing the media format.
- Internet access is available during setup/model preparation but not required during encode, decode, loopback, inspection, or dashboard use.
- A second Snapdragon PC will be used for cross-device validation when available; it is not required for initial loopback development.
- Model weights and generated artifacts may be redistributed only if their licenses allow it; otherwise setup will acquire them locally and verify their hashes.

## Approved architecture

### `.lwv` media envelope

The common little-endian header contains:

- Magic `LWV1`.
- Format version, media type, codec profile, and flags.
- Metadata length and payload length.
- SHA-256 of the payload.

Typed metadata includes a SHA-256 model fingerprint. Image profile `0x0101` stores input dimensions, resized content dimensions, padding, latent shape, quality, color space, and one CompressAI entropy string. Audio profile `0x0201` stores sample rate, original sample count, channels, codebook count, bits per code, frame count, chunk size, padding, and packed code indices.

Parsers must reject unsupported versions, unknown profiles, impossible lengths, truncation, trailing bytes, hash failure, and model mismatch before reconstruction.

### Image transmitter

1. Correct EXIF orientation and convert the input to RGB.
2. Preserve aspect ratio, resize the longest edge to 256, and symmetrically black-pad to 256 by 256.
3. Run the official CompressAI `compress()` path for `bmshj2018_factorized`, quality 1.
4. Wrap the entropy string and metadata in `.lwv`.
5. Reject complete envelopes over 2,048 bytes by default; an explicit analysis override may write them.

### Image receiver

1. Verify the envelope, profile, lengths, digest, and model fingerprint.
2. Use the pinned x64 codec environment for CompressAI entropy decompression and recover `y_hat`.
3. Transfer the tensor through a neutral local artifact/interface to the native ARM64 worker.
4. Run the complete fixed-shape synthesis transform `g_s` on QNN HTP with CPU fallback disabled.
5. Remove padding and save the visible reconstructed region.

The expected latent shape for the selected 256 by 256 quality-1 profile is `[1, 192, 16, 16]`; implementation must verify this from the loaded model before treating it as final.

### Runtime environments

- **Codec environment:** Windows x64 Python 3.11 for PyTorch, CompressAI, entropy coding, orchestration, dashboard, and most tests.
- **NPU environment:** native Windows ARM64 Python 3.11 containing ONNX Runtime plus the QNN plugin runtime required for Hexagon NPU inference.
- Never install mutually conflicting plain and QNN ONNX Runtime distributions into the same environment.
- Generated models, weights, QNN contexts, calibration data, profiles, and offline bundles remain outside Git; tracked manifests record versions and hashes.

### Public commands

- `lightweave image encode INPUT --output PAYLOAD`
- `lightweave inspect PAYLOAD`
- `lightweave image decode PAYLOAD --output IMAGE --require-npu`
- `lightweave image roundtrip INPUT --work-dir DIR`
- `lightweave dashboard`

Core media functions operate on binary streams so a future serial/Arduino adapter does not require a new media format.

### Audio extension

- EnCodec 24 kHz mono at 1.5 kbps.
- Two 1,024-entry codebooks packed at 10 bits per code.
- Fixed 75-frame, one-second chunks rather than dynamic QNN sequence dimensions.
- Codebook reconstruction, initial convolution, and stateful LSTM prefix on CPU.
- Fixed-shape convolutional reconstruction tail on QNN HTP with fallback disabled for that tail.
- Carry state and handle chunk boundaries explicitly; report CPU and NPU stages separately.

## Qualcomm development workflow

1. Inspect the actual Snapdragon hardware and development environment.
2. Use the external QUAD checkout for diagnostics and evaluate `hardware_detect -> convert_model -> profile_workload -> orchestrate_workload -> generate_code` where available.
3. Export and numerically validate a fixed-shape ONNX decoder before conversion.
4. Use AI Hub Workbench with non-confidential calibration data to convert, quantize, validate, and profile when credentials and a suitable hosted target are available.
5. Use QAIRT Visualizer to inspect operators, graph assignment, quantization, memory, and performance evidence.
6. Integrate the current QNN plugin API directly and confirm the selected NPU device. Do not infer NPU use merely because inference completed.
7. Compare direct integration with QUAD and AI Hub guidance and record gaps in the developer-experience log.

## Feasibility and acceptance gates

### Image NPU gate

- Export static `g_s` and compare PyTorch with CPU ONNX output.
- Convert/quantize for QNN HTP.
- Disable CPU fallback.
- Require the complete image decoder graph to be accepted by QNN HTP.
- Capture provider/device and profiling evidence.
- If semantic-preserving export changes cannot achieve full assignment, stop and report the evidence before weakening the claim.

### Image acceptance

- Every complete envelope in the curated demo set is at most 2,048 bytes.
- Average reconstruction quality is at least 26 dB PSNR and 0.90 MS-SSIM against the resized visible source region.
- Transfer estimate is no more than 16.384 seconds at 1 kbps and 8.192 seconds at 2 kbps.
- NPU output is at least 35 dB PSNR relative to the unquantized CPU decoder output.
- Runtime encode, inspect, decode, loopback, and dashboard smoke tests pass without network access.

### Audio acceptance

- Exact output sample length and finite samples.
- Code payload approximately matches 1.5 kbps before envelope overhead.
- No obvious chunk-boundary spikes.
- The declared NPU tail has no CPU fallback and is compared against the reference PyTorch tail.

## Current environment facts

- The development host reports native ARM64 and a Qualcomm ARMv8 processor.
- No system Python interpreter is currently available through `python` or the Python launcher.
- The supplied QUAD checkout exists, but its virtual environment currently references a missing Python interpreter and cannot run.
- No local QAIRT/QNN installation has yet been confirmed.
- The repository contains no application source code at the start of implementation.

## Progress tracker

| Work item | Status | Evidence / next action |
| --- | --- | --- |
| Initial proposal and repository review | Complete | Historical draft and constraints were reviewed during planning. |
| Final software scope and architecture | Approved | Project owner explicitly requested implementation of the image-first plan. |
| Repository hygiene and living documents | In progress | Preparing the required documentation-only baseline commit. |
| Host/runtime inventory | In progress | ARM64 host confirmed; Python and QUAD runtime repair required. |
| `.lwv` envelope and image core | Not started | Begins after the baseline commit. |
| Image model export and CPU parity | Not started | Requires codec environment and model weights. |
| Strict QNN image inference | Not started | Requires native ARM64 environment and converted model. |
| CLI and dashboard | Not started | Follows the shared core and NPU worker. |
| Audio extension | Gated | Starts only after the image NPU gate passes. |
| Arduino/optical adapter | Deferred | Outside the current milestone. |

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| CompressAI/PyTorch Windows ARM64 packaging gap | High | Use a pinned x64 codec environment and neutral handoff to native ARM64 inference. |
| QNN rejects part of `g_s` or silently falls back | High | Fixed shapes, QDQ conversion, fallback disabled, provider/device checks, and profile evidence. |
| CompressAI entropy streams are not portable across builds | High | Pin exact versions and weights; use golden payloads and cross-device tests. |
| The 2,048-byte ceiling is missed on complex images | Medium | Curate and report the acceptance set; fail oversize by default rather than hiding it. |
| Quantization reduces reconstruction quality | Medium | Compare PyTorch, CPU ONNX, and NPU outputs and enforce quality gates. |
| AI Hub/QUAD credentials or service access fail | Medium | Keep export, local CPU validation, `.lwv`, CLI, and dashboard independent of hosted services. |
| Two Python architectures make setup fragile | High | Provide explicit setup scripts, manifests, diagnostics, and actionable error messages. |
| EnCodec LSTM cannot use the selected ONNX Runtime QNN path | Medium | Use the approved hybrid split and label it accurately. |
| Third-party model-weight redistribution is unclear | High | Verify licenses before committing or bundling weights. |

## Open questions

- Which exact Python, PyTorch, CompressAI, ONNX Runtime, and QNN plugin versions form a working tested matrix on this machine?
- Can `g_s` be quantized without violating the image quality gates?
- Does AI Hub expose a compatible Snapdragon X target and conversion route for this graph under the available account?
- Can QUAD be repaired and connected without modifying or vendoring its checkout?
- Which redistributable images will form the public calibration and acceptance manifests?
- Is direct QAIRT capable of accelerating more of EnCodec than the selected ONNX Runtime hybrid path, and would that complexity be worthwhile later?

## Decision log

| ID | Date | Decision | Status / rationale |
| --- | --- | --- | --- |
| D-001 | 2026-08-05 | Treat the original multiverse proposal as a draft rather than the final specification. | Confirmed by project owner. |
| D-002 | 2026-08-05 | Maintain this file as the living project source of truth. | Confirmed by project owner. |
| D-003 | 2026-08-05 | Keep confidential material, credentials, local environments, and generated model/profile artifacts out of Git. | Required repository hygiene. |
| D-004 | 2026-08-05 | Ignore the physical optical layer for the current software milestone and assume an ordered byte pipe. | Approved final scope. |
| D-005 | 2026-08-05 | Implement images first and audio second. | Reduces model/runtime risk and preserves a shared architecture. |
| D-006 | 2026-08-05 | Use fixed 256 by 256 quality-1 CompressAI input with aspect-preserving padding. | Approved image profile. |
| D-007 | 2026-08-05 | Require complete `g_s` execution on QNN HTP without CPU fallback. | Provides defensible NPU evidence. |
| D-008 | 2026-08-05 | Enforce a 2,048-byte complete image-envelope target for the curated demo set. | Approved low-bandwidth target. |
| D-009 | 2026-08-05 | Start with one-PC loopback but keep transmitter and receiver independently runnable. | Enables development without blocking two-PC deployment. |
| D-010 | 2026-08-05 | Runtime must be offline; setup may use the network. | Matches the air-gapped demonstration story. |
| D-011 | 2026-08-05 | Retain EnCodec with a clearly labeled CPU/NPU hybrid decoder. | Preserves the audio idea while respecting QNN operator constraints. |
| D-012 | 2026-08-05 | Deliver source and setup instructions; no packaged executable is required. | Confirmed by project owner. |
| D-013 | 2026-08-05 | Use evidence-based gates rather than a fixed implementation window. | Confirmed by project owner. |
| D-014 | 2026-08-05 | Application implementation is authorized. | Explicit approval received in the implementation request. |

## Public references

- Qualcomm Developer: <https://www.qualcomm.com/developer>
- Windows on Snapdragon AI development: <https://docs.qualcomm.com/bundle/publicresource/topics/80-62010-1/ai-app-development.html?product=1601111740057789>
- Qualcomm AI Hub: <https://aihub.qualcomm.com/get-started>
- QAIRT Visualizer: <https://docs.qualcomm.com/bundle/publicresource/topics/80-87189-1/overview.html?product=1601111740009302>
- CompressAI model implementation: <https://interdigitalinc.github.io/CompressAI/_modules/compressai/models/google.html>
- ONNX Runtime QNN Execution Provider: <https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html>
- ONNX Runtime QNN plugin: <https://github.com/microsoft/onnxruntime-qnn>
- Meta EnCodec: <https://github.com/facebookresearch/encodec>
- Arduino MessagePack RPC router: <https://github.com/arduino/arduino-router>

## Change log

| Date | Change |
| --- | --- |
| 2026-08-05 | Created the living context and recorded the original planning gate and draft concept. |
| 2026-08-05 | Replaced the draft architecture with the approved image-first software scope; recorded implementation approval, `.lwv`, strict QNN image gate, offline runtime, two-environment design, later hybrid audio extension, current environment facts, risks, resources, and acceptance criteria. |
