# LightWeave Project Context

> Living source of truth for project intent, decisions, architecture, progress,
> evidence, risks, and open questions.

| Field | Current value |
| --- | --- |
| Project | LightWeave |
| Phase | UNO Q accelerated image/audio receiver implemented and under final publication validation |
| Primary milestone | Header-free image and audio reconstruction on UNO Q Adreno with fail-closed acceleration evidence |
| Secondary milestone | Galaxy S25 delivery after the UNO Q receiver milestone |
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
the media on Qualcomm-based Windows and Debian edge devices.

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
- A native Android receiver prototype for direct UNO Q USB text/image display,
  with hardware-free framed demos and no Internet permission.
- A native UNO Q receiver for all three raw image presets plus up to five
  seconds of header-free EnCodec audio. Images run fully on Adreno; audio uses
  a measured CPU/Adreno split with no fallback inside its Vulkan suffix.

The following remain out of scope:

- Laser/LED, photodiode, analog circuitry, modulation, clock recovery, Arduino
  firmware, and serial framing.
- Galaxy S25 hardware validation, Android audio playback, WebSockets, and Cloud
  AI in the runtime path.
- UNO Q encoding, optical/serial adapters, and MCU integration.
- Medical, regulatory, safety, or absolute-security claims.
- A packaged EXE/MSIX.

### UNO Q-to-Android receiver extension

The owner selected a direct USB-C-to-USB-C receiver path: Galaxy S25 Ultra as
USB host, UNO Q as USB device, and a native Android application displaying
results already reconstructed by the UNO Q. Text and images are the current
app scope; audio is deferred. The phone application is presentation and USB
transport only, not an AI decoder.

The `android/` Android Studio project implements the hardware-independent side
of that contract. It matches observed UNO Q USB identity `2341:0078`, requests
USB-host permission, uses `usb-serial-for-android` 3.10.0 for CDC/ACM reads,
and parses incremental `LWRX` v1 frames. A 16-byte little-endian header carries
magic, version, media type, flags, payload length, and CRC32. Type 1 is UTF-8
text; type 2 is PNG/JPEG. USB framing is downstream of the optical link and
does not count against the raw optical payload budget.

The UNO Q reconstruction boundary is now verified independently of the phone.
Its native ARM64 rANS decoder produces the same latent tensor as CompressAI for
all three raw image presets, and the complete `g_s` graph runs through ncnn
Vulkan on the Adreno 702 with unsupported layers and CPU fallback rejected.
The board-local CLI and App Lab WebUI both reconstruct real payloads. The
remaining Android uncertainty is the USB transport, phone power, and display
path—not whether the UNO Q can reconstruct the image.

Documentation claims: Arduino specifies that UNO Q has a Qualcomm Dragonwing
QRB2210 MPU running Debian, an STM32U585 MCU, Bridge/RPC, Wi-Fi, Bluetooth, and
USB-C role switching. Samsung specifies USB-C/USB 3.2 Gen 1 for the Galaxy S25
Ultra. Direct local PC observation: UNO Q enumerated as Arduino USB composite
`2341:0078` with ADB and a standard USB serial interface. UNO Q-to-S25
enumeration, sustained power, Android CDC matching, and throughput remain
unexercised.

### Qualcomm edge-device inference targets

For the Galaxy S25, Samsung documents Snapdragon 8 Elite for Galaxy. ONNX
Runtime documents QNN Execution Provider support on Android, HTP as the NPU
backend, and a Java `addQnn` API. Because its prebuilt QNN packages are
Windows-only, LightWeave would need a custom Android ARM64 AAR built against a
pinned Qualcomm AI Engine Direct/QNN SDK and compatible device runtime. The
recommended first gate is a stored latent tensor through one fixed-shape QDQ
`g_s` graph, requiring HTP-only execution, disabled CPU fallback, zero profiled
CPU graph nodes, finite output, and at least 35 dB parity against the Windows
CPU reference. CompressAI rANS entropy decoding would be ported to Android
C++/NDK and remain on CPU; the complete neural synthesis graph would use the
NPU. On-phone image encoding is a second phase using `g_a` on HTP and CPU rANS
encoding. EnCodec audio is later and higher risk because upstream EnCodec does
not support Android/mobile ARM and LightWeave's current audio path is hybrid.

The exercised UNO Q Debian image does not expose QNN/FastRPC libraries,
firmware, or device nodes. It does expose Mesa 25.2.6 Turnip Vulkan on the
Adreno 702. The accepted backend is therefore ncnn Vulkan: one native runner
executes every complete static `g_s` graph, audits Vulkan support for all 16
compute layers, rejects llvmpipe/non-Adreno devices, and never selects a CPU
neural path. CPU work is limited to rANS entropy decoding, PNG packaging, and
application orchestration for images.

UNO Q audio is now a validated, explicitly labeled CPU/Adreno hybrid. Native
code unpacks the two 10-bit codebooks and runs one static CPU prefix across the
complete clip so recurrent state is preserved. Candidate split 2 was rejected
because its Adreno suffix returned non-finite values. Split 5 was the earliest
passing candidate: decoder layers 0-4 run on CPU and all 39 compute layers in
the fixed decoder 5-15 suffix run through ncnn Vulkan on Adreno 702. The same
480-sample disclosed boundary correction is applied before exact trimming and
atomic PCM16 WAV output. The owner reduced the first release from ten seconds
to five: at most 940 bytes and 120,000 samples. UNO Q remains receiver-only;
on-board encoding, optical/MCU integration, and Galaxy S25 HTP remain deferred.

The repository should be the single source of source code, pinned manifests,
payload contracts, validation vectors, and setup orchestration for all targets.
It should not pretend that one binary or environment installs everywhere:
Windows x64/ARM64, Android ARM64, and UNO Q Debian ARM64 need separate thin
installers that consume shared versioned model/codec definitions. Generated
models, SDK redistributables, and credentials remain outside Git; manifests and
download/verification scripts are tracked.

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
  The UNO Q consumes the same bytes/code but limits clips to five seconds and
  uses the separately evidenced CPU/Adreno split described above.

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
- UNO Q Debian 13.1 ARM64: native CompressAI-compatible rANS plus a statically
  linked ncnn Vulkan runner on Mesa Turnip Adreno 702. Docker is not a runtime
  dependency; Arduino App Lab supplies its normal generic application
  container for the optional WebUI.
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
lightweave-uno doctor --json
lightweave-uno image decode PAYLOAD --preset PRESET --output IMAGE --require-accelerator
lightweave-uno benchmark --preset all --json
lightweave-uno serve
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

The hardware-independent repository suite reports 60 passing Python tests.
Generated acceptance and offline-smoke reports remain ignored and reproducible.

### UNO Q image receiver acceptance

| Check | Result |
| --- | --- |
| Board | Arduino UNO Q; Debian 13.1 ARM64; 3.6 GiB RAM |
| Accelerator | Mesa 25.2.6 Turnip Vulkan on Adreno 702 |
| QNN/FastRPC discovery | Not present on the exercised base image |
| Entropy decoder | Exact latent equality with CompressAI for all three presets |
| Neural graph | Complete 16-compute-layer `g_s` on Vulkan for every preset |
| Fallback enforcement | Non-Adreno devices, unsupported Vulkan layers, and neural CPU fallback rejected |
| Static model CPU parity | 43.11 dB tiny, 42.15 dB balanced, 41.17 dB quality |
| Board accelerator/CPU parity | 36.34 dB tiny, 41.77 dB balanced, 44.38 dB quality |
| Exercised payloads | 80 bytes tiny, 216 bytes balanced, 716 bytes quality |
| Five-run median/p95 inference | 0.173/0.176 s tiny, 0.521/0.562 s balanced, 1.978/2.160 s quality |
| Process/disk measurements | Up to about 60.6 MiB observed child RSS; 35.6 MiB installed bundle; 17.6 GB board disk free |
| Repeated-run behavior | Initial FP16-arithmetic stress produced an MSM GPU hang; FP32 arithmetic with FP16 storage/packing and a shared serialized one-second cooldown passed five runs of all profiles |
| Cross-entry-point arbitration | Concurrent native quality decode plus App Lab balanced request both passed strictly; shared file lock serialized the GPU work |
| Board-local API | Status and real 128 by 128 reconstruction passed with strict evidence |
| Runtime Docker dependency | None for the native CLI; App Lab uses the platform's existing container |
| First native dependency build | About 27 minutes at two jobs; cached runner rebuild about 20 seconds |

### UNO Q audio receiver acceptance

| Check | Result |
| --- | --- |
| Raw contract | `A1-E15-S<n>` unchanged; 188 bytes/started second; five-second/940-byte maximum |
| Native unpacking | Exact 150 code-index equality for the one-second fixture |
| Native codebook reconstruction | Maximum absolute tensor error 0.0 against PyTorch |
| Split selection | Split 2 rejected for non-finite Vulkan output; split 5 is earliest passing candidate |
| CPU stage | Codebook summation plus complete-clip decoder layers 0-4; 24 ncnn compute layers |
| Accelerator stage | Decoder layers 5-15; 39 Vulkan compute layers on Turnip Adreno 702 |
| One-second board parity | 52.11 dB against PyTorch; exact 24,000 samples; finite PCM |
| Five-second board parity | 52.07 dB against PyTorch; exact 120,000 samples; finite PCM |
| Boundary correction | 480 samples disclosed; measured conditioned maximum jump 0.0 |
| Five-second single-run latency/RSS | 0.0011 s codebook, 0.955 s CPU prefix, 6.233 s Adreno suffix, 8.474 s wrapper total; about 109.1 MiB peak child RSS |
| Five-run median/p95 | One second: 1.306/1.317 s Adreno and 2.716/2.745 s total. Five seconds: 6.248/6.249 s Adreno and 8.483/8.487 s total |
| Concurrent image/audio API | Balanced image and one-second audio both passed strict evidence; shared lock serialized Adreno use |
| Browser App Lab workflow | WAV reached ready state 4 with exact one-second duration; audio metrics/playback/download link rendered; malformed-size error displayed; no console errors |
| Disconnected runtime | One-second strict decode passed inside an ephemeral `--network none` acceptance container |

### Android receiver acceptance

| Check | Result |
| --- | --- |
| Toolchain | Java 17, Android SDK/target 36, AGP 9.0.0, Gradle 9.1.0 |
| Debug APK | Builds successfully; package `com.lightweave.receiver` |
| Unit tests | 9 passing tests for identity, framing, fragmentation, CRC/resync, UTF-8, and counters |
| Android lint | 0 errors; Gradle-version notice only |
| Offline rebuild after dependency setup | Pass |
| USB host declaration | Present; exact UNO Q filter `2341:0078` |
| App network permission | None |
| Supported result types | UTF-8 text and PNG/JPEG image |
| Hardware-free demos | Text and generated PNG traverse the production frame parser |
| S25/UNO Q cable and power | Not exercised |
| UNO Q decoder deployment | Verified separately on board; UNO Q-to-phone delivery remains unexercised |

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
| Android text/image receiver | Debug APK, framed demos, unit tests, and lint pass; real UNO Q/S25 path pending |
| UNO Q native receiver | All image profiles reconstruct on Adreno Vulkan with strict no-fallback and at least 36.34 dB accelerator/CPU parity |
| UNO Q App Lab WebUI | Rendered browser upload/reconstruction/download and oversize error pass; balanced accelerator time about 524 ms; no console errors |
| UNO Q audio receiver | One- and five-second raw payloads reconstruct through CPU plus a strict 39-layer Adreno suffix at 52.07 dB or better PyTorch parity |
| UNO Q audio App Lab WebUI | Upload, settings-code validation, playback-ready WAV, download action, split timing/evidence, malformed-size error, and no-console-error checks pass |
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
| Multi-size dashboard publication | Complete | Commit `9aee230`; GitHub Actions run `31057418505` passed |
| Android text/image receiver | Complete locally; hardware pending | APK builds; 9 unit tests and lint pass; validate UNO Q CDC, S25 power, and decoded output next |
| UNO Q accelerator feasibility | Complete | ncnn Vulkan executes all three complete graphs on Adreno 702; QNN/FastRPC is absent on the exercised image |
| UNO Q native receiver | Complete locally | Native rANS, strict runner, CLI, rendered API/WebUI, manifest, SPDX SBOM, offline bundle, dry-run/idempotent installer, and 60-test repository suite pass |
| UNO Q receiver publication | Complete | Source/evidence commit `8074645` and Android-preservation commit `fa19c64` published to `origin/main` |
| UNO Q audio receiver | Complete locally; publication pending | Native unpack/codebook parity, earliest valid split 5, strict 39-layer Adreno suffix, 1/5-second parity, CLI/API/WebUI, offline bundle, installer, and offline smoke pass |
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
| UNO Q App Lab image lacks Vulkan user-space files | Installer copies the target board's own loader, Turnip driver, and ICD into only the LightWeave app; no vendor binary is committed or redistributed |
| UNO Q QNN/Hexagon availability | QNN/FastRPC was absent, so the accepted claim is Adreno Vulkan only; do not imply Hexagon execution |
| UNO Q source build time and disk use | Use two compile jobs and preserve cache for iteration; native runtime does not require Docker or a compiler |
| Repeated UNO Q quality runs can stress Turnip/MSM | FP16 arithmetic produced a kernel-reported GPU hang; final runner uses FP16 storage/packing with FP32 arithmetic, explicit Vulkan teardown, cross-process serialization, and a one-second cooldown; five runs of all profiles pass |
| EnCodec recurrent decoder cannot run in the Vulkan suffix | Keep codebooks and complete-clip recurrent layers 0-4 on CPU; label the result CPU/Adreno hybrid and never imply full-GPU/NPU audio |
| Earlier UNO Q audio split returned invalid output | Split 2 is permanently rejected; select the earliest later candidate only after finite-output, parity, support, and stability gates; split 5 passed |
| UNO Q audio memory/latency grows with duration | First release is capped at five seconds/940 bytes; static 1-5 second prefixes share one weight file and all requests use the accelerator lock/cooldown |
| USB stream loses boundaries or reconnects mid-result | `LWRX` length plus CRC32 framing rejects corruption and resynchronizes on magic |
| Phone receives an unsafe image allocation | Reject payloads above 8 MiB and decoded dimensions above 16 megapixels |

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
- Will Android match the observed UNO Q composite device as CDC/ACM through
  `usb-serial-for-android`, or will a custom probe/device interface be needed?
- Can the S25 reliably power the UNO Q during sustained receive, or is a
  standards-compliant powered USB-C hub/PD arrangement required?
- What sustained USB throughput is reliable for decoded PNG/JPEG results,
  before the later audio transport is designed?
- Can a custom Android ONNX Runtime/QNN AAR run the existing fixed-shape QDQ
  image decoder on Galaxy S25 HTP with no fallback, zero CPU graph nodes, and
  at least 35 dB parity against the Windows CPU reference?
- Can the pinned CompressAI rANS decoder and tables be ported to Android NDK
  while decoding existing raw `payload.bin` files byte-identically?
- Would a future, explicitly approved UNO Q encoding phase justify the extra
  `g_a` model, native rANS encoder, storage, and accelerator-validation cost?

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
| D-026 | 2026-08-05 | Use a direct USB-C-to-USB-C link from UNO Q to Galaxy S25 Ultra. | Explicit owner preference; S25 is host and real device behavior remains unverified. |
| D-027 | 2026-08-05 | Keep reconstruction on UNO Q and start the Android app with decoded UTF-8 text and PNG/JPEG images. | Owner-defined boundary; UNO Q reconstruction now passes independently, while Android uses `LWRX` framing and presentation only. |
| D-028 | 2026-08-05 | Expand raw images to explicit 128-, 768-, and 2,048-byte profiles and default the dashboard to 128 by 128 / 768 bytes. | Supersedes D-024 as the only UI choice; preserves its tiny profile and legacy decode alias while providing practical quality options. |
| D-029 | 2026-08-05 | Use a plain monochrome, text-first dashboard visual system. | Owner requested clarity over decorative styling; controls and evidence remain the focus. |
| D-030 | 2026-08-05 | Accept ncnn Vulkan on Adreno 702 as the UNO Q accelerator backend. | QNN/FastRPC is absent on the exercised image; strict full-graph Vulkan passed every preset and the owner allowed any proven Qualcomm accelerator. |
| D-031 | 2026-08-05 | Keep the UNO Q CLI native on the existing Debian OS. | Docker is limited to reproducible build preparation; the delivered CLI has no Docker runtime dependency. |
| D-032 | 2026-08-05 | Copy Vulkan runtime files only from the target board into the installed App Lab app. | Arduino's generic App container omits the Vulkan loader/driver; target-local copying enables the WebUI without redistributing vendor binaries or modifying the base OS. |
| D-033 | 2026-08-05 | Use FP16 storage/packing with FP32 arithmetic and serialize UNO Q accelerator calls across host and App Lab. | Repeated FP16-arithmetic quality runs triggered an MSM GPU hang; the stable configuration plus explicit teardown and one-second shared cooldown passed five runs of every profile. |
| D-034 | 2026-08-05 | Keep UNO Q receiver-only while adding raw EnCodec audio reconstruction. | Owner explicitly limited the board to reconstruction; encoding, mobile, optical firmware, and MCU integration remain deferred. |
| D-035 | 2026-08-05 | Select EnCodec decoder split 5 as the earliest valid UNO Q CPU/Adreno partition. | Split 2 produced non-finite Adreno output; split 5 passed 39-layer Vulkan support, strict no-fallback, finite output, and greater-than-35-dB parity gates. |
| D-036 | 2026-08-05 | Cap the first UNO Q audio receiver at five seconds/940 bytes. | Owner approved the reduction; it halves worst-case work/memory and removes unneeded 6-10 second prefix variants. |

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
| 2026-08-05 | Recorded the proposed UNO Q-to-Galaxy S25 Ultra receiver display extension as future, unimplemented scope; recommended an offline LAN browser prototype and separated documentation claims from unverified device behavior. |
| 2026-08-05 | Replaced the preliminary Wi-Fi recommendation with the owner's selected direct USB-C path; recorded S25-host/UNO-Q-device topology and the unresolved gadget, power, and Android-decoder gates. |
| 2026-08-05 | Observed the connected UNO Q enumerate on the development PC as USB composite `2341:0078` with both ADB and standard USB serial interfaces; phone enumeration remains the next hardware gate. |
| 2026-08-05 | Implemented and locally validated the header-free raw image/audio contracts, 64 by 64 strict-QNN decoder, raw CLI, future adapter interfaces, and `/transmit`/`/receive`/`/loopback` dashboard; preserved `.lwv` and recorded the intentionally missing wire protections. |
| 2026-08-05 | Published raw-mode commit `140f9ae` to `origin/main` and confirmed hardware-independent GitHub Actions run `31047777514` passed. |
| 2026-08-05 | Implemented the Android Studio text/image receiver prototype with USB-host permission, pinned CDC library, `LWRX` length/CRC framing, type-aware rendering, local demos, 9 passing tests, successful lint, and a debug APK; recorded UNO Q decoding and S25 cable behavior as unverified. |
| 2026-08-05 | Added explicit tiny/balanced/quality raw image profiles, a strict 128 by 128 QNN graph, local sample patterns, and a monochrome responsive dashboard; validated all profile budgets and strict NPU assignment and made balanced the UI default. |
| 2026-08-05 | Published multi-size dashboard commit `9aee230` to `origin/main` and confirmed Windows GitHub Actions run `31057418505` passed lint and all hardware-independent tests. |
| 2026-08-05 | Researched Galaxy S25 and UNO Q Qualcomm inference paths and a one-repository/multiple-target-installer architecture; S25 HTP is a credible strict-NPU target, while the Arduino App Lab QNN/FastRPC container makes QRB2210 acceleration credible but still unprofiled, and neither mobile/board path has been implemented. |
| 2026-08-05 | Exercised the UNO Q directly: identified Debian 13.1 ARM64 and Turnip Adreno 702, found no QNN/FastRPC runtime, proved exact native rANS latent parity, ran all three complete `g_s` graphs strictly through ncnn Vulkan, and measured at least 36.34 dB board accelerator/CPU parity. |
| 2026-08-05 | Added the native UNO Q CLI, strict runner, App Lab receive WebUI/API, target-local Vulkan integration, hash-verified offline bundle, dry-run/idempotent installer, model manifest records, and portable tests; Docker remains build-only rather than a delivered runtime dependency. |
| 2026-08-05 | Browser-tested the live board WebUI with a real 216-byte balanced payload and its 128-byte oversize error, observed strict Adreno evidence and PNG download with no console errors, and completed a clean-Ruff validation plus installer dry run. |
| 2026-08-05 | Stress testing exposed a recoverable MSM GPU hang during repeated FP16-arithmetic quality runs; stabilized the runner with FP32 arithmetic plus FP16 storage/packing, explicit teardown, and a shared serialized cooldown, then passed five runs of all profiles with p95 and memory/disk evidence. |
| 2026-08-05 | Proved the shared accelerator lock across the Debian host CLI and App Lab container by launching a quality decode alongside a balanced API request; both completed on Adreno with fallback disabled. |
| 2026-08-05 | Added a tracked SPDX SBOM and bundle notice, completed 51 Python tests, rebuilt the portable native entropy runner with exact latent equality, reinstalled the 24-file offline bundle, and confirmed the final board status and runner hash. |
| 2026-08-05 | Committed the accelerated UNO Q receiver, source-build path, installer, WebUI, tests, manifest, and evidence as `8074645`; the separately preserved Android prototype is commit `fa19c64`. |
| 2026-08-05 | Pushed the Android-preservation, UNO Q receiver, and milestone documentation commits directly to `origin/main` without force-pushing. |
| 2026-08-05 | Added the receiver-only UNO Q EnCodec path, rejected split 2, selected the earliest passing split 5, proved exact native indices/zero-error codebook reconstruction and 52.07 dB or better board parity, reduced the limit to five seconds, and integrated the CLI/API/App Lab audio surface plus offline package. |
