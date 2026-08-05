# LightWeave Project Context

> Living source of truth for project intent, decisions, architecture, progress,
> evidence, risks, and open questions.

| Field | Current value |
| --- | --- |
| Project | LightWeave |
| Phase | Multi-size raw image dashboard complete and validated locally |
| Primary milestone | Header-free image/audio payload generation and receiver dashboard |
| Secondary milestone | EnCodec audio extension with an honest CPU/NPU split |
| Last updated | 2026-08-05 |
| Approval gate | Application implementation explicitly approved on 2026-08-05 |

## Required maintenance

1. Read this document before substantive project work.
2. Update it whenever work changes scope, requirements, architecture, evidence,
   decisions, risks, plan, progress, hardware facts, or open questions.
3. Update `Last updated`, append a change-log entry, and add a decision entry
   when a decision is made or reversed.
4. Keep confirmed facts, assumptions, proposals, and unresolved questions
   distinct.
5. Update `docs/QUALCOMM_DEVELOPER_EXPERIENCE.md` whenever Qualcomm hardware,
   tools, runtimes, SDKs, samples, or documentation are exercised.
6. Never record credentials, personal information, or confidential content.

Repository enforcement lives in `AGENTS.md`.

## Objective and scope

LightWeave is an offline-first, transport-agnostic software system that turns
media into compact bytes for a very low-bandwidth optical link and reconstructs
the media on a Snapdragon PC.

The implemented milestone assumes a reliable ordered byte pipe and includes:

- Image encode/decode with CompressAI `bmshj2018_factorized`, quality 1.
- EXIF correction, RGB conversion, aspect-preserving resize, and symmetric
  padding to 256 by 256.
- A versioned `.lwv` binary envelope with typed metadata, model fingerprint,
  payload length, and SHA-256 integrity.
- A strict 2,048-byte complete image-envelope ceiling by default.
- EnCodec 24 kHz mono audio with two 1,024-entry codebooks packed at exactly
  10 bits per code.
- Separate transmitter, inspect, receiver, and round-trip CLI commands.
- Strict native ARM64 QNN workers with explicit NPU device selection, CPU
  fallback disabled, and profile evidence.
- A localhost-only offline dashboard for images and playable audio.
- An optional runtime guard that blocks DNS and non-loopback networking.
- A header-free raw mode that preserves `.lwv` while sending only codec bytes.
- Three raw image profiles: 64 by 64 at 128 bytes, 128 by 128 at 768 bytes,
  and 256 by 256 at 2,048 bytes, with the balanced profile as the UI default.
- Raw `A1-E15-S<n>` audio with exact 188-byte independently packed chunks and
  an out-of-band exact sample count.
- Separate `/transmit`, `/receive`, and `/loopback` dashboard pages plus
  `RawByteSink`/`RawByteSource` adapter contracts for future hardware.

The following remain out of scope:

- Laser/LED, photodiode, analog circuitry, modulation, clock recovery, Arduino
  firmware, and serial framing.
- Galaxy S25, WebSockets, and Cloud AI in the runtime path.
- Medical, regulatory, safety, or absolute-security claims.
- A packaged EXE/MSIX.

## Confirmed architecture

### `.lwv` envelope

The common little-endian header contains magic `LWV1`, format version, media
type, codec profile, flags, metadata length, payload length, and SHA-256 of the
payload. Typed metadata includes the exact model-weight SHA-256.

- Image profile `0x0101`: original/content dimensions, padding, latent shape,
  quality, color space, and one raw CompressAI entropy string.
- Audio profile `0x0201`: sample rate, original samples, padding, frame count,
  channels, codebooks, bits/code, chunk frames, and packed EnCodec indices.

Parsers reject unsupported versions/profiles/flags, invalid dimensions,
impossible metadata, truncation, trailing bytes, hash failure, payload-length
mismatch, and model mismatch before reconstruction.

### Raw optical mode

Raw mode assumes the byte pipe supplies reliable ordered delivery and exact
message boundaries, and that both hosts have the same pinned model artifacts.
The transmitted bytes contain no magic, version, media type, length, hash, or
model fingerprint. The short settings code is trusted out-of-band
configuration and is not counted toward payload size. `.lwv` remains the safer
format for archival, diagnosis, integrity checking, and model negotiation.

- Raw image presets are `I64-Q1-B128`, `I128-Q1-B768`, and
  `I256-Q1-B2048`. They reconstruct to fixed 64, 128, and 256 pixel square
  outputs with hard entropy-string ceilings of 128, 768, and 2,048 bytes.
  Each profile tries a descending effective-detail schedule, then deterministic
  mean-color and black fallbacks. The legacy `I64-Q1` code remains a decode
  alias for `I64-Q1-B128`; new encodes print the explicit budgeted code. The
  dashboard defaults to balanced `I128-Q1-B768`. Static synthesis graphs use
  latent shapes `[1,192,4,4]`, `[1,192,8,8]`, or `[1,192,16,16]` and run
  completely on strict QNN HTP.
- Audio preset `A1-E15-S<n>` resamples to 24 kHz mono and discloses the exact
  pre-padding sample count as `n`. Each 75-frame, two-codebook second contains
  1,500 valid bits plus four zero pad bits, exactly 188 bytes. The receiver
  rejects non-multiples of 188, nonzero pad bits, and impossible sample counts,
  then uses the established truthful CPU/QNN hybrid and trims to `n`.

### Image path

1. Correct EXIF orientation, convert to RGB, resize the longest edge to 256,
   and black-pad symmetrically.
2. Run the official CompressAI `compress()` API and wrap its entropy string in
   `.lwv`.
3. Validate the envelope and entropy-decode `[1,192,16,16]` on x64 CPU.
4. Send the latent through a neutral `.npy` handoff to native ARM64 Python.
5. Run the complete QDQ `g_s` graph on QNN HTP. The worker selects only the
   QNN NPU device and sets `session.disable_cpu_ep_fallback=1`.
6. Crop recorded padding and save atomically.

Image QDQ uses unsigned 16-bit activations and weights. The common 16-bit
activation/8-bit-weight recipe missed the image fidelity gate; 16-bit weights
passed and are supported by this graph/device combination.

### Audio path

1. Read uncompressed PCM WAV, mix to mono, resample to 24 kHz when needed, and
   zero-pad to complete seconds.
2. Run EnCodec 24 kHz at 1.5 kbps. Pack `[batch,2,frames]` indices frame-major
   at 10 bits each, producing exactly 1,500 code bits/sec.
3. On receive, unpack indices and run codebook reconstruction plus EnCodec
   decoder layers 0-12 on CPU.
4. Split the resulting `[1,32,time]` tensor into static
   `[1,32,24000]` one-second inputs.
5. Run decoder layers 13-15 (final residual and output block) on a mixed-precision
   QDQ QNN HTP graph with fallback disabled.
6. Apply a labeled 480-sample CPU de-click correction at independent NPU chunk
   boundaries, trim padding, and save exact-length PCM WAV atomically.

The originally proposed larger NPU tail (layers 2-15) was not retained. Its 1D
operators were rejected, and semantics-preserving 2D rewrites were fully
assigned to HTP but produced uncorrelated output despite strong CPU ONNX/QDQ
parity. Narrowing the NPU block to regular convolutions produced 48.80 dB NPU
parity and is the truthful supported hybrid.

### Runtime environments

- Windows x64 Python 3.11: PyTorch, CompressAI, EnCodec, entropy/codebook work,
  model preparation, orchestration, dashboard, and tests.
- Native Windows ARM64 Python 3.11: ONNX Runtime 1.24.4 and QNN plugin 2.4.0.
- Plain and QNN ONNX Runtime distributions are kept out of the same ARM64
  environment.
- Weights, ONNX/QDQ graphs, calibration data, QNN profiles, reports, and caches
  are ignored. `models/manifest.json` tracks sources, licenses, hashes, shapes,
  tool versions, conversion intent, and expected artifact paths.

## Public interfaces

```text
lightweave image encode INPUT --output PAYLOAD
lightweave image decode PAYLOAD --output IMAGE --require-npu
lightweave image roundtrip INPUT --work-dir DIR
lightweave audio encode INPUT.wav --output PAYLOAD
lightweave audio decode PAYLOAD --output OUTPUT.wav
lightweave audio roundtrip INPUT.wav --work-dir DIR
lightweave raw image encode INPUT --preset I128-Q1-B768 --output payload.bin
lightweave raw image decode payload.bin --preset I128-Q1-B768 --output IMAGE --require-npu
lightweave raw audio encode INPUT.wav --output payload.bin
lightweave raw audio decode payload.bin --preset A1-E15-S48000 --output AUDIO.wav
lightweave inspect PAYLOAD
lightweave dashboard
```

Core encode/decode functions operate on bytes and files. The raw path exposes
`RawByteSink.send(payload) -> SendReceipt` and `RawByteSource.receive() ->
bytes`; the current browser implementation downloads/uploads `payload.bin`,
and a later serial adapter can implement the same contract.

## Verified evidence

### Image acceptance

| Check | Result |
| --- | --- |
| Public acceptance images | 3 |
| Maximum complete envelope | 1,444 bytes |
| Mean PSNR | 27.67 dB |
| Mean MS-SSIM | 0.973 |
| Transfer limits at 1/2 kbps | Pass |
| Strict full-decoder QNN profile | `QNNExecutionProvider` only; 0 CPU nodes |
| CPU/NPU parity | Minimum 56.99 dB |
| Oversize stress case | 2,148 bytes; rejected by default |

### Audio acceptance

| Check | Result |
| --- | --- |
| Input/output duration | 2 seconds / exact 48,000 samples |
| Code payload | 375 bytes / exactly 1,500 bits/sec |
| Complete envelope | 478 bytes |
| Finite output | Pass |
| Conditioned boundary jump | 0.0 in the deterministic sample |
| Strict QNN tail profile | `QNNExecutionProvider` only; 0 CPU nodes |
| NPU-tail parity | 48.80 dB |
| Full CPU to hybrid output parity | 44.95 dB |

### Raw-mode acceptance

| Check | Result |
| --- | --- |
| Image corpus | 4/4 deterministic payloads within every selected profile budget |
| Tiny measured payloads | 76-124 bytes; exactly 64 by 64 output |
| Balanced measured payloads | 216-664 bytes; exactly 128 by 128 output |
| Quality measured payloads | 716-2,044 bytes; exactly 256 by 256 output |
| Balanced CPU QDQ parity | 66.74 dB minimum |
| Raw image strict QNN profile | All three static graphs list `QNNExecutionProvider` only and 0 CPU nodes |
| Raw image NPU/CPU parity | At least 51.29 dB balanced, 56.51 dB quality, and 59.92 dB tiny |
| Image quality | Balanced 17.64-31.16 dB PSNR / 0.890-0.978 MS-SSIM; quality 23.43-35.02 dB / 0.970-0.988; informational |
| Audio payload | 188 bytes/started second; two-second sample is 376 bytes / 1,504 bps including byte padding |
| Audio reconstruction | Exact 48,000 samples; finite output; conditioned boundary jump 0.0 |
| Audio strict QNN tail | `QNNExecutionProvider` only; 0 CPU nodes |

Focused unit tests currently report 44 passing tests. Generated acceptance and
offline-smoke reports remain ignored and reproducible.

### Product surface and packaging

| Check | Result |
| --- | --- |
| Installed CLI image round trip and inspect | Pass with strict QNN evidence |
| Installed CLI audio round trip and inspect | Pass with strict hybrid-QNN evidence |
| Rendered localhost dashboard image workflow | Pass; images, metrics, and QNN evidence displayed |
| Rendered localhost dashboard audio workflow | Pass; playback result metrics and hybrid evidence displayed |
| Raw `/transmit` image/audio workflows | Pass; codes, exact bytes, download links, metrics, and local verification displayed |
| Raw `/receive` workflow | Pass; strict image reconstruction, save link, and oversize error state displayed |
| Monochrome dashboard refresh | Pass; text-first square layout, no gradients/shadows, responsive at 390 px without horizontal overflow |
| Multi-size browser workflow | Pass; balanced sample transmit/verify and separate receiver upload both reconstructed 128 by 128 with 0 CPU profile nodes |
| Raw disconnected-runtime smoke | Pass for balanced strict image QNN and audio hybrid; 216/376 raw bytes and exact outputs |
| Dashboard browser console | No errors |
| Built wheel contents | Pass; CLI modules and all local HTML/CSS/JavaScript assets included |

## Qualcomm workflow evidence

- QUAD client 0.2.0 runs under native ARM64 Python 3.11.9.
- QUAD local detection identifies Snapdragon X Elite X1E80100, 12 ARM64 CPU
  cores, Adreno X1-85, Hexagon v73 (45 TOPS), 31.6 GB RAM, and Windows 11 Pro.
- QUAD doctor confirms ARM64 architecture but reports no QAIRT/QNN SDK
  environment and detects conflicting plain/QNN ONNX Runtime packages inside
  the supplied QUAD venv.
- Direct LightWeave QNN plugin integration succeeds without a local QAIRT SDK.
- QAIRT Visualizer is not installed and has not been exercised.
- AI Hub hosted conversion/profiling is not exercised because no project
  account/token was placed in scope. Runtime does not depend on it.
- Server-backed QUAD conversion/profile/code-generation remains a setup-time
  workflow; local detection and doctor were exercised without disclosing local
  artifacts to an unverified endpoint.

## Progress tracker

| Work item | Status | Evidence / next action |
| --- | --- | --- |
| Planning/repository baseline | Published with corrected attribution | Commit `2d8c2e6`; original repository root preserved |
| Software MVP repository handoff | Published with corrected attribution | Implementation commit `5dc4e8b`; file trees and timestamps preserved |
| `.lwv` envelope and image core | Complete | Unit and real-model acceptance tests pass |
| Image export/QDQ/strict QNN | Complete | Full graph, no fallback, 0 CPU profile nodes |
| CLI and offline dashboard | Complete | Image and audio APIs implemented; localhost assets only |
| Audio extension | Complete locally | Truthful narrowed hybrid passes acceptance |
| Raw optical mode | Complete locally | Three image budgets plus `A1-E15-S<n>` audio, CLI, adapters, and three-page dashboard pass local acceptance |
| Raw 64 by 64 strict QNN decoder | Complete locally | QUInt16 QDQ, no fallback, 0 CPU nodes, 59.92 dB minimum NPU/CPU parity |
| Raw 128 by 128 strict QNN decoder | Complete locally | QUInt16 QDQ, 66.74 dB minimum CPU parity, no fallback, 0 CPU nodes, 51.29 dB minimum NPU/CPU parity |
| Raw milestone publication | Complete | Commit `140f9ae`; GitHub Actions run `31047777514` passed |
| Offline runtime | Complete locally | Process guard and dual-media smoke script implemented |
| QUAD local workflow | Complete | Detect and doctor exercised |
| GitHub Actions unit CI | Complete | Corrected-history Windows Python 3.11 run `31034723025` passed; QNN gates stay local |
| Second Snapdragon PC | Pending external device | Transfer the same `.lwv` plus generated artifacts and verify |
| AI Hub/QAIRT Visualizer | Pending access/install | Compare only when account/SDK are available |
| Arduino/optical adapter | Deferred | Must not change `.lwv` media format |
| GitHub push | Complete | Corrected history replaced `origin/main` with an exact force-with-lease and verified owner attribution |

## Risks and mitigations

| Risk | Status / mitigation |
| --- | --- |
| Two Python architectures | Mitigated with pinned requirements, setup script, neutral handoff, and diagnostics |
| Silent CPU fallback | Mitigated with explicit NPU device selection, disabled fallback, and profile checks |
| Weight/artifact mismatch | Mitigated with tracked hashes and runtime fingerprints |
| Generated manifests move to a second PC | Runtime trusts recorded graph hashes rather than setup-machine absolute paths |
| Complex images exceed 2,048 bytes | Fail closed; documented stress image proves rejection |
| EnCodec/torchaudio package mismatch | LightWeave uses tested PCM WAV I/O; EnCodec neural model remains upstream |
| Larger EnCodec NPU tail has incorrect HTP semantics | Do not claim it; supported split ends at layers 13-15 and records failed experiments |
| Audio chunk clicks | Labeled CPU de-click correction; raw and conditioned jumps reported |
| Model-weight redistribution terms | Weights remain ignored; verify upstream terms before distribution |
| AI Hub/QAIRT unavailable | Direct QNN path and reproducible local evidence do not depend on them |
| GitHub credentials/permission | Resolved with Git Credential Manager; never store tokens in source, remotes, or documentation |
| Git commit attribution | Corrected commits use the verified repository-owner GitHub no-reply identity; original root is unchanged |
| Raw payload has no integrity/model negotiation | Intentional tradeoff; UI warns, preset validation fails early where possible, and `.lwv` remains available |
| Image quality and transfer time trade off sharply | UI exposes explicit 128/768/2,048-byte profiles, output resolution, measured bytes, and 1/2 kbps estimates; no original-resolution claim |

## Open questions

- Will the same generated artifacts and `.lwv` payloads pass on the second
  Snapdragon PC?
- Can QAIRT Visualizer provide per-layer evidence that explains the rejected
  larger audio-tail semantics?
- Can AI Hub or a newer QNN release run more of EnCodec accurately without the
  narrowed split?
- Should future work add QNN context caching to reduce the audio tail's session
  preparation time?
- Which serial reliability/framing adapter will carry `.lwv` over the physical
  optical link without altering the media format?

## Decision log

| ID | Date | Decision | Status / rationale |
| --- | --- | --- | --- |
| D-001 | 2026-08-05 | Treat the original multiverse proposal as a draft. | Confirmed by owner. |
| D-002 | 2026-08-05 | Maintain this living source of truth. | Confirmed by owner. |
| D-003 | 2026-08-05 | Keep credentials, local environments, weights, and generated artifacts out of Git. | Required hygiene. |
| D-004 | 2026-08-05 | Assume an ordered byte pipe and defer physical optics. | Approved scope. |
| D-005 | 2026-08-05 | Implement images before audio. | Reduced model/runtime risk. |
| D-006 | 2026-08-05 | Use fixed padded 256 by 256 quality-1 images. | Approved profile. |
| D-007 | 2026-08-05 | Require complete image `g_s` on QNN HTP without fallback. | Defensible NPU claim. |
| D-008 | 2026-08-05 | Enforce a 2,048-byte complete image-envelope ceiling. | Approved target. |
| D-009 | 2026-08-05 | Start with one-PC loopback and independent commands. | Preserves two-PC compatibility. |
| D-010 | 2026-08-05 | Allow network during setup; require offline runtime. | Air-gapped story. |
| D-011 | 2026-08-05 | Use an honestly labeled audio hybrid. | Respects recurrent/operator constraints. |
| D-012 | 2026-08-05 | Deliver source and setup instructions, not a packaged executable. | Confirmed by owner. |
| D-013 | 2026-08-05 | Use evidence gates rather than a fixed schedule. | Confirmed by owner. |
| D-014 | 2026-08-05 | Application implementation is authorized. | Explicit owner approval. |
| D-015 | 2026-08-05 | Use `QUInt16` image activations and weights. | `QUInt8` weights missed fidelity; 16-bit passed full HTP. |
| D-016 | 2026-08-05 | Install separate x64 codec and ARM64 QNN environments. | Tested solution to Windows package/runtime constraints. |
| D-017 | 2026-08-05 | Narrow the audio NPU block to decoder layers 13-15. | Larger tails were fully assigned but semantically incorrect on HTP. |
| D-018 | 2026-08-05 | Use `QUInt16` audio activations and `QUInt8` weights. | Passed CPU and NPU fidelity; 16-bit weights overflowed bias ranges. |
| D-019 | 2026-08-05 | Apply and disclose a 480-sample CPU boundary de-click. | Removes independent fixed-chunk DC steps without changing length. |
| D-020 | 2026-08-05 | Use LightWeave PCM WAV I/O instead of torchaudio. | Avoids an unavailable PyTorch 2.13 companion wheel on Windows. |
| D-021 | 2026-08-05 | Rewrite only the assistant-created commits to the verified repository-owner identity. | Corrects attribution while preserving the original root commit, file trees, messages, and timestamps. |
| D-022 | 2026-08-05 | Preserve `.lwv` and add a separate raw optical mode containing only codec bytes. | Meets the minimum-wire-payload goal without weakening archival/debug workflows. |
| D-023 | 2026-08-05 | Treat preset codes as trusted out-of-band configuration. | Keeps hashes, headers, lengths, and fingerprints out of the optical payload. |
| D-024 | 2026-08-05 | Fix raw image output at 64 by 64 and enforce 128 bytes with adaptive detail and deterministic fallbacks. | The hard byte budget is the gate; quality remains informational. |
| D-025 | 2026-08-05 | Pack raw audio as independent 188-byte one-second chunks and disclose exact sample count in `A1-E15-S<n>`. | Preserves exact length while keeping the wire bytes header-free. |
| D-028 | 2026-08-05 | Expand raw images to explicit 128-, 768-, and 2,048-byte profiles and default the dashboard to 128 by 128 / 768 bytes. | Supersedes D-024 as the only UI choice; preserves its tiny profile and legacy decode alias while providing practical quality options. |
| D-029 | 2026-08-05 | Use a plain monochrome, text-first dashboard visual system. | Owner requested clarity over decorative styling; controls and evidence remain the focus. |

## Public references

- Qualcomm Developer: <https://www.qualcomm.com/developer>
- Windows on Snapdragon AI development: <https://docs.qualcomm.com/bundle/publicresource/topics/80-62010-1/ai-app-development.html?product=1601111740057789>
- Qualcomm AI Hub: <https://aihub.qualcomm.com/get-started>
- QAIRT Visualizer: <https://docs.qualcomm.com/bundle/publicresource/topics/80-87189-1/overview.html?product=1601111740009302>
- ONNX Runtime QNN EP: <https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html>
- ONNX Runtime QNN plugin: <https://github.com/onnxruntime/onnxruntime-qnn>
- CompressAI: <https://github.com/InterDigitalInc/CompressAI>
- Meta EnCodec: <https://github.com/facebookresearch/encodec>
- Arduino MessagePack RPC router: <https://github.com/arduino/arduino-router>

## Change log

| Date | Change |
| --- | --- |
| 2026-08-05 | Created the living context and recorded the draft proposal and planning gate. |
| 2026-08-05 | Replaced the draft with the approved image-first architecture, `.lwv`, strict QNN gate, offline runtime, and later audio extension. |
| 2026-08-05 | Recorded the completed image path, QDQ/full-HTP evidence, CLI, dashboard, acceptance set, and corrected Windows environment facts. |
| 2026-08-05 | Recorded the implemented EnCodec payload, failed larger NPU-tail experiments, narrowed passing hybrid, boundary conditioning, audio acceptance, QUAD evidence, remaining external validations, and GitHub permission blocker. |
| 2026-08-05 | Added Windows unit CI while keeping model conversion and QNN hardware acceptance as explicit local gates. |
| 2026-08-05 | Recorded local implementation commit `61bc8fb`, final validation reruns, repaired Python base interpreters, and the repeated GitHub 403 permission blocker. |
| 2026-08-05 | Re-ran full image/audio QNN acceptance, verified the installed CLI and rendered dashboard, audited wheel contents, and corrected the tracked audio/quantization manifest contract. |
| 2026-08-05 | Published the implementation to `origin/main` and split CI dependencies from the heavyweight codec/model-preparation environment after observing redundant installation work. |
| 2026-08-05 | Confirmed optimized GitHub Actions run `30996830347` passed and replaced the obsolete push blocker with the published repository state. |
| 2026-08-05 | Corrected author and committer attribution for the six assistant-created commits, preserved the original repository root and content, configured repository-local identity, and removed the stale GitHub credential. |
| 2026-08-05 | Published the corrected history, verified every GitHub commit maps to the repository owner, and confirmed corrected-head CI run `31034723025` passed. |
| 2026-08-05 | Implemented and locally validated the header-free raw image/audio contracts, 64 by 64 strict-QNN decoder, raw CLI, future adapter interfaces, and `/transmit`/`/receive`/`/loopback` dashboard; preserved `.lwv` and recorded the intentionally missing wire protections. |
| 2026-08-05 | Published raw-mode commit `140f9ae` to `origin/main` and confirmed hardware-independent GitHub Actions run `31047777514` passed. |
| 2026-08-05 | Added explicit tiny/balanced/quality raw image profiles, a strict 128 by 128 QNN graph, local sample patterns, and a monochrome responsive dashboard; validated all profile budgets and strict NPU assignment and made balanced the UI default. |
