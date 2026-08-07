# Qualcomm Developer Experience Log

This public engineering log records how Qualcomm hardware, tools, runtimes,
documentation, and samples help or hinder LightWeave. Documentation claims and
direct observations are separated. Failures are useful evidence. Credentials,
private endpoints, and confidential material must never appear here.

## Entry template

| Field | Required content |
| --- | --- |
| Date and ID | Stable observation ID and date |
| Objective | LightWeave task attempted |
| Environment | Device, OS, architecture, and exact relevant versions |
| Tool/source | Product, package, SDK, sample, or documentation |
| Intended workflow | Expected developer path |
| Actual result and evidence | Observed result and verification |
| Usefulness | Concrete project value |
| Friction and owner | Problem plus Qualcomm/documentation/third-party classification |
| Workaround | Safe tested path |
| Suggested improvement | Actionable developer-experience feedback |

## Resource register

| Resource | Classification | LightWeave use | Current status |
| --- | --- | --- | --- |
| [Qualcomm Developer](https://www.qualcomm.com/developer) | Active gateway | SDK, Windows on Snapdragon, and sample discovery | Available |
| [Windows on Snapdragon AI development](https://docs.qualcomm.com/bundle/publicresource/topics/80-62010-1/ai-app-development.html?product=1601111740057789) | Active documentation | Native ARM64 environment/runtime guidance | Available; JavaScript-heavy |
| Supplied external QUAD client 0.2.0 | Active tooling | Hardware detection, diagnostics, and server workflow guidance | Local detect/doctor exercised; server not exercised |
| [Qualcomm AI Hub](https://aihub.qualcomm.com/get-started) | Setup-time tooling | Hosted conversion, validation, and profiling | Not exercised; no project account/token in scope |
| [QAIRT Visualizer](https://docs.qualcomm.com/bundle/publicresource/topics/80-87189-1/overview.html?product=1601111740009302) | Setup-time tooling | Graph partition, quantization, memory, and profile inspection | Unavailable locally; SDK not installed |
| [ONNX Runtime QNN plugin](https://github.com/onnxruntime/onnxruntime-qnn) | Active runtime | Native ARM64 strict HTP inference | Exercised successfully at 2.4.0 with ORT 1.24.4 |
| [ONNX Runtime QNN EP docs](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html) | Active reference | QDQ configuration and no-fallback session contract | Used for both media graphs |
| [Whisper + AI Hub sample](https://github.com/thatrandomfrenchdude/simple-whisper-transcription) | Implementation reference | Model assets and Windows QNN flow | Reference only; provider examples require current API review |
| [HRNet pose sample](https://github.com/quic/Pose-Detection-with-HRPoseNet) | Implementation reference | Model manifests and device setup | Reference only |
| [Local Agent](https://github.com/thatrandomfrenchdude/local-agent) | Later reference | Modular local agent patterns | Not a runtime dependency |
| [AnythingLLM NPU chatbot](https://github.com/thatrandomfrenchdude/simple-npu-chatbot) | Later reference | Local NPU demo structure | Not a runtime dependency |
| Scaler Chatbot | Unavailable reference | Potential local chatbot sample | No unambiguous public link supplied |
| [Awesome Qualcomm Developer](https://qualcomm.github.io/awesome-qualcomm-developer/) | Discovery reference | Comparable projects and samples | Available |
| [Arduino UNO Q documentation](https://docs.arduino.cc/hardware/uno-q) | Active hardware documentation | QRB2210 receiver, Debian/App Lab deployment, and direct USB phone interface | Direct S25 optical text receive passes through the boot-managed Router monitor; PNG/WAV/reconnect remain |
| [ncnn](https://github.com/Tencent/ncnn) Vulkan runtime | Active third-party tooling | Complete image synthesis and EnCodec suffix execution on UNO Q Adreno 702 | All image graphs and the selected 39-layer audio suffix exercised with strict no-fallback |
| [Meta EnCodec](https://github.com/facebookresearch/encodec) | Model/preparation dependency | 24 kHz raw audio codebooks and decoder conversion | Native UNO Q conversion validated; upstream Python runtime is not installed on board |
| [Android USB host documentation](https://developer.android.com/develop/connectivity/usb/host) | Platform documentation | Galaxy S25 USB enumeration, permission, and endpoint workflow | Real UNO Q enumeration, interface match, and CDC open exercised successfully |
| [usb-serial-for-android](https://github.com/mik3y/usb-serial-for-android) 3.10.0 | Third-party Android library | CDC/ACM transport for decoded UNO Q results | Real S25 opened UNO Q CDC and wrote controls; board response blocked downstream |
| Provided `qualcomm/edge-ai-labs-arduino` RPC path | Later hardware reference | Future UNO Q byte adapter | Stale/404 |
| [Arduino MessagePack RPC router](https://github.com/arduino/arduino-router) | Later hardware reference | Maintained UNO Q RPC alternative | Available; hardware phase deferred |

## Observation log

### DX-001 - QUAD provides useful local Snapdragon discovery

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; detect and diagnose the LightWeave development laptop |
| Environment | Windows 11 Pro ARM64; QUAD client 0.2.0; Python 3.11.9 ARM64 |
| Tool/source | Supplied external QUAD checkout; `quad-client detect --local-only` and `quad-client doctor` |
| Intended workflow | Establish authoritative hardware/runtime facts before model integration |
| Actual result and evidence | Detected Snapdragon X Elite X1E80100, 12 ARM64 CPU cores, Adreno X1-85, Hexagon v73 at 45 TOPS, 31.6 GB RAM, and CPU/NPU runtimes. Doctor confirmed ARM64 Python and warned that no QAIRT SDK environment is configured. |
| Usefulness | Replaced assumptions with a reproducible device inventory and identified missing optional SDK tooling early |
| Friction and owner | The supplied QUAD venv initially depended on a removed base interpreter; standard Windows venv portability issue. Doctor also found plain `onnxruntime` and `onnxruntime-qnn` installed together in that environment; environment provisioning issue. |
| Workaround | Restore a supported ARM64 Python for QUAD; keep LightWeave's QNN worker in a separate clean ARM64 environment |
| Suggested improvement | Make QUAD's installer/doctor detect a missing venv base interpreter and conflicting ORT packages before normal commands run, then print a one-command repair path |

### DX-002 - QUAD is a client/orchestrator, not the local inference runtime

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; determine where QUAD belongs in LightWeave |
| Environment | QUAD client checkout and bundled documentation; local commands only |
| Tool/source | QUAD SDK and skill documentation |
| Intended workflow | `hardware_detect -> convert_model -> profile_workload -> orchestrate_workload -> generate_code`, with AI Hub selection as another server-backed route |
| Actual result and evidence | Local detect/doctor are self-contained. Conversion, profiling, orchestration, and code generation are MCP server workflows and are not required by the LightWeave runtime. No unverified configured server was contacted. |
| Usefulness | Gives a clear optional preparation workflow while keeping the air-gapped runtime independent |
| Friction and owner | The term "orchestration" can be confused with LightWeave's media/device orchestration; documentation naming issue |
| Workaround | Name QUAD server orchestration, LightWeave application orchestration, and optical transport as separate layers |
| Suggested improvement | Generate a capability report that separately marks local client, configured server, hosted service, and target-device facts as detected, documented, or unverified |

### DX-003 - Current QNN plugin can prove full image-decoder NPU assignment

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; run complete CompressAI `g_s` on Hexagon without CPU fallback |
| Environment | Snapdragon X Elite; Windows ARM64 Python 3.11.9; ONNX Runtime 1.24.4; `onnxruntime-qnn` 2.4.0 |
| Tool/source | ONNX Runtime QNN plugin and QNN HTP backend |
| Intended workflow | Register the plugin library, enumerate EP devices, select only the NPU, compile a static QDQ graph, and reject fallback |
| Actual result and evidence | Complete `[1,192,16,16] -> [1,3,256,256]` graph ran with `session.disable_cpu_ep_fallback=1`. Profile events list only `QNNExecutionProvider` and zero CPU nodes. NPU/image-reference parity was at least 56.99 dB over the acceptance set. A fresh installed-CLI run and the rendered localhost dashboard reproduced the same strict device/provider evidence. |
| Usefulness | Provides defensible on-device AI evidence rather than inferring NPU use from a successful call |
| Friction and owner | Many older provider-list examples do not show plugin registration or concrete NPU-device selection; documentation/sample versioning issue |
| Workaround | Centralize current plugin registration, exact NPU selection, fallback disabling, and profile validation in the ARM64 worker |
| Suggested improvement | Publish a migration table and a minimal "strict NPU or fail" sample alongside every older provider-list example |

### DX-004 - Generative decoders need graph-specific precision choices

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; quantize the CompressAI image synthesis graph without violating fidelity |
| Environment | x64 ONNX Runtime 1.24.4 quantizer; native QNN HTP execution |
| Tool/source | `qnn_preprocess_model`, `get_qnn_qdq_config`, and QDQ quantization |
| Intended workflow | Apply the documented unsigned 16-bit activation / unsigned 8-bit weight recipe |
| Actual result and evidence | The common recipe reached only 30.32 dB minimum parity. Unsigned 16-bit activations and weights reached 65.09 dB minimum CPU QDQ parity and passed strict HTP assignment. |
| Usefulness | Demonstrates that QNN supports a high-fidelity full generative image decoder when precision is tuned |
| Friction and owner | Classification-centric defaults are easy to overgeneralize to reconstruction models; tooling guidance issue |
| Workaround | Calibrate on representative latent tensors and gate each precision choice with CPU and NPU reconstruction parity |
| Suggested improvement | Add generative-codec examples and an automated mixed-precision search report to the QNN quantization workflow |

### DX-005 - Windows on Snapdragon benefits from an explicit two-architecture workflow

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; combine PyTorch/CompressAI preparation with native QNN inference |
| Environment | Python 3.11.9 x64 and ARM64 on the same Snapdragon Windows PC |
| Tool/source | Windows Python, PyTorch 2.13.0, CompressAI 1.2.8, ORT/QNN plugin |
| Intended workflow | Use one reproducible environment for codec and NPU work |
| Actual result and evidence | CompressAI built from source in x64 with Visual Studio C++ tools; native ARM64 QNN inference worked in a separate environment. A neutral `.npy` handoff preserved the tensor contract. During final validation, registered Python components remained while both base interpreter executables were absent; repairing each Core Interpreter MSI restored the existing environments, after which unit, strict-QNN, and offline smoke checks passed again. |
| Usefulness | Keeps the heavy synthesis/reconstruction subgraphs native on Hexagon while retaining mature x64 model tooling |
| Friction and owner | No dependable matching native Windows ARM64 PyTorch/CompressAI path for this stack; third-party packaging limitation. Managing two environments is extra Windows on Snapdragon friction. |
| Workaround | Pin both environments, never mix plain/QNN ORT in ARM64, verify architecture and interpreter launchability explicitly, provide one setup script, and document MSI repair as recovery rather than rebuilding model environments |
| Suggested improvement | Publish a tested Windows on Snapdragon package matrix and native ARM64 wheels for common model-preparation dependencies |

### DX-006 - Full HTP assignment does not by itself prove audio semantics

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; accelerate the EnCodec convolutional reconstruction tail |
| Environment | Same QNN versions and Snapdragon device as DX-003; EnCodec 0.1.1 |
| Tool/source | QNN HTP with fixed 1-second ONNX/QDQ graphs |
| Intended workflow | Run decoder layers 2-15 after CPU codebook/initial-convolution/LSTM stages |
| Actual result and evidence | Native 1D operators were rejected. Semantics-preserving height/width-1 2D rewrites passed PyTorch and CPU ONNX/QDQ parity and were fully assigned to HTP, yet HTP output was uncorrelated with CPU output (about 8-10 dB parity). Narrowing the NPU graph to regular-convolution layers 13-15 produced 48.80 dB NPU parity with zero CPU profile nodes. |
| Usefulness | Establishes a truthful passing hybrid and shows why provider assignment must be paired with numerical validation |
| Friction and owner | Layout/operator validation accepted larger graphs whose runtime semantics were unusable; Qualcomm/Microsoft runtime issue or undocumented restriction |
| Workaround | Keep upsampling/larger tail on CPU, use a QDQ final regular-convolution block on HTP, and retain the failure evidence |
| Suggested improvement | Add post-compilation numerical validation to QAIRT/QNN tooling and flag height/width-1 transpose-convolution patterns with known accuracy risk |

### DX-007 - Audio-tail quantization exposed useful bias-range feedback

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; quantize the supported final EnCodec block |
| Environment | x64 ORT QNN quantizer; native HTP execution |
| Tool/source | QNN QDQ utilities |
| Intended workflow | Preserve the final audio block at high precision |
| Actual result and evidence | Unsigned 16-bit weights triggered explicit int32 bias-range warnings and failed fidelity. Unsigned 16-bit activations with unsigned 8-bit weights reached 47.92 dB minimum CPU QDQ parity and 48.80 dB NPU parity. |
| Usefulness | The warning identified the correct direction for precision tuning and produced a passing graph |
| Friction and owner | Warning messages name affected nodes but do not propose a precision override or estimate resulting output error; tooling UX issue |
| Workaround | Make weight precision configurable, test both supported types, and require numerical gates |
| Suggested improvement | Have the quantizer recommend per-node or global precision changes when bias quantization exceeds int32 range |

### DX-008 - Meta EnCodec audio I/O packaging is the Windows blocker, not the neural model

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; install EnCodec without destabilizing the image stack |
| Environment | Windows x64 Python 3.11; PyTorch 2.13.0; EnCodec 0.1.1 |
| Tool/source | Meta EnCodec and PyTorch audio packages |
| Intended workflow | Install EnCodec plus its declared `torchaudio` dependency |
| Actual result and evidence | No torchaudio 2.13 release was available. EnCodec imports torchaudio for optional file utilities, while its neural model runs with PyTorch alone. LightWeave's PCM WAV I/O plus a narrow import shim produced valid 24 kHz, two-codebook payloads. |
| Usefulness | Preserves the official EnCodec model and avoids downgrading/rebuilding the proven image environment |
| Friction and owner | Third-party package dependency is broader than the model core and does not match the current PyTorch release cadence on Windows |
| Workaround | Install EnCodec without dependencies, install `einops`, and use tested local PCM WAV I/O only |
| Suggested improvement | Make EnCodec file I/O an optional extra and avoid importing torchaudio at model-module import time |

### DX-009 - AI Hub and QAIRT Visualizer must remain explicitly unverified

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; evaluate hosted and SDK-based Qualcomm model workflows |
| Environment | QUAD doctor and public documentation; no local QAIRT SDK configuration |
| Tool/source | Qualcomm AI Hub and QAIRT Visualizer |
| Intended workflow | Hosted conversion/profile plus local graph/partition inspection |
| Actual result and evidence | QUAD reports no QAIRT/QNN SDK root or tools. No AI Hub account/token was placed in project scope. Neither workflow was exercised, and no claim depends on them. |
| Usefulness | Direct QNN plugin integration still produced strict device and profile evidence; hosted/Visualizer paths remain valuable comparisons later |
| Friction and owner | Resource lists describe the products but do not provide a credential-free local readiness check or offline sample artifact; access/onboarding issue |
| Workaround | Keep setup/runtime independent, use only non-confidential calibration data if access is later granted, and document the unverified state |
| Suggested improvement | Provide a no-login compatibility preflight and a downloadable sample profile that developers can open in Visualizer before SDK/account setup |

### DX-010 - The provided Arduino RPC link is stale

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; classify the supplied later-phase Arduino communication resource |
| Environment | Public link validation |
| Tool/source | Supplied `qualcomm/edge-ai-labs-arduino` path and Arduino router repository |
| Intended workflow | Reuse an RPC example for the future UNO Q byte transport |
| Actual result and evidence | The supplied path returns 404. Arduino's maintained router documents a MessagePack RPC bridge. |
| Usefulness | A later-phase alternative exists without blocking software payload work |
| Friction and owner | Published hackathon resource is stale; resource-list maintenance issue |
| Workaround | Defer hardware and revalidate the maintained router when that milestone begins |
| Suggested improvement | Run automated link checks and retain redirects or archived references for renamed samples |

### DX-011 - A second static CompressAI shape reuses the strict QNN workflow cleanly

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; reduce an image to a hard 128-byte raw payload while retaining a complete Hexagon reconstruction graph |
| Environment | Snapdragon X Elite X1E80100; Windows 11 ARM64; x64 Python 3.11 model preparation; native ARM64 Python 3.11 worker |
| Tool/source | PyTorch 2.13.0, CompressAI 1.2.8, ONNX 1.19.0, ONNX Runtime 1.24.4, `onnxruntime-qnn` 2.4.0, QNN HTP |
| Intended workflow | Export a fixed `[1,192,4,4] -> [1,3,64,64]` `g_s`, calibrate every raw effective-detail level, quantize to QDQ, select the concrete QNN NPU device, disable CPU fallback, and prove numerical parity plus provider assignment |
| Actual result and evidence | PyTorch/CPU ONNX export parity passed with maximum absolute error `7.15e-7`. Unsigned 16-bit activation/weight QDQ reached 71.75 dB minimum CPU parity. Four deterministic raw image cases measured 76-124 bytes; every strict NPU profile listed only `QNNExecutionProvider`, zero CPU nodes, finite 64 by 64 output, and at least 59.92 dB NPU/CPU parity. The rendered transmitter/receiver workflow reproduced the device/profile evidence without browser console errors, and the raw image/audio workers passed again with non-loopback networking blocked. |
| Usefulness | The same strict worker contract supports both the 256-pixel `.lwv` decoder and a much smaller raw preset without weakening the NPU claim |
| Friction and owner | Static shapes require separate generated graphs/manifests, and QNN session preparation remains much longer than the single-digit-millisecond inference; integration and runtime startup cost rather than an assignment failure |
| Workaround | Track both artifact contracts, keep generated files ignored, validate source/model hashes locally, and consider QNN context caching after functional milestones |
| Suggested improvement | Provide a documented multi-shape artifact/context-cache workflow and distinguish graph preparation latency from inference latency in default profiling output |

### DX-012 - UNO Q documents the pieces for an offline phone gateway, but not the complete workflow

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; evaluate how a future LightWeave receiver could expose output from UNO Q to a Galaxy S25 Ultra |
| Environment | Documentation-only evaluation; Arduino UNO Q with Qualcomm Dragonwing QRB2210/Debian and STM32U585/Zephyr; Android phone target; exact board image, Android build, and application versions unverified |
| Tool/source | Official Arduino UNO Q hardware page and datasheet; official Samsung Galaxy S25 Ultra specifications |
| Intended workflow | Receive framed bytes on the MCU, pass complete frames to Debian through Arduino Bridge/RPC, and expose status/output to the phone over an offline local connection |
| Actual result and evidence | Arduino documents Bridge/RPC, dual-band Wi-Fi 5, Bluetooth 5.1, USB-C role switching, and a Debian Linux MPU. Samsung documents Wi-Fi, Bluetooth 5.4, and USB-C/USB 3.2 Gen 1. No board, cable, network, decoder, or phone browser behavior was exercised. |
| Usefulness | The documented USB role switching and Android USB-host API support the owner-selected prototype topology: S25 as host, UNO Q as device, and an Android app reading an enumerated USB interface |
| Friction and owner | The official hardware material does not provide an end-to-end UNO Q-to-Android receiver-display example, name a supported general-purpose UNO Q USB gadget interface for an Android app, settle power behavior for this pairing, or establish that the existing LightWeave decoder runs on QRB2210/Android; documentation and unperformed integration work |
| Workaround | Validate enumeration with a data-capable C-to-C cable, define and test the UNO Q gadget interface before application integration, use a standards-compliant powered hub/PD arrangement if the phone cannot power the board reliably, and treat media decoding as a separate gate |
| Suggested improvement | Publish an Android USB-host companion example covering a supported UNO Q gadget interface, USB-C role/power expectations, reconnect handling, and MCU-to-Linux streaming through Bridge |

### DX-013 - UNO Q exposes USB serial and ADB on the development PC

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; establish the UNO Q's current USB interfaces before connecting it to the Galaxy S25 Ultra |
| Environment | Direct observation; Arduino UNO Q attached to the Windows 11 ARM64 Snapdragon development PC by USB-C; board image/version not yet queried |
| Tool/source | Windows present-device enumeration |
| Intended workflow | Determine whether the existing UNO Q image already exposes an Android-consumable serial interface or requires a new Linux USB gadget configuration |
| Actual result and evidence | Windows enumerated Arduino USB composite `VID 2341`, `PID 0078`, including an ADB interface and a standard `USB Serial Device` COM port. The `adb` CLI was not available on the PC `PATH`. No identifying device serial was retained. |
| Usefulness | Removes the immediate need to invent a gadget mode for the first phone test; an Android CDC/USB-serial terminal can be used to validate C-to-C enumeration before building the LightWeave app |
| Friction and owner | The device exposes the interfaces, but the phone-side driver match, power stability, serial data source, board image version, and reconnect behavior remain untested; integration work rather than a demonstrated platform defect |
| Workaround | Test enumeration and permission on the S25 with a CDC-capable terminal, then send a known heartbeat before introducing LightWeave framing |
| Suggested improvement | Document the UNO Q's default USB composite descriptors and provide an Android CDC enumeration/loopback test alongside the PC ADB workflow |

### DX-014 - Android receiver software is buildable before UNO Q/S25 hardware validation

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; implement the phone presentation layer for decoded UNO Q text and images |
| Environment | Windows 11 ARM64 Snapdragon development PC; Microsoft JDK 17.0.18; Android SDK/target 36; build tools 36.1.0; Android Gradle Plugin 9.0.0; Gradle 9.1.0; no phone attached |
| Tool/source | Native Android USB-host APIs, `usb-serial-for-android` 3.10.0, Android Gradle toolchain |
| Intended workflow | Match UNO Q `2341:0078`, obtain Android USB permission, read CDC chunks, reconstruct framed UTF-8/PNG/JPEG results, and render them without network access or AI decoding on the phone |
| Actual result and evidence | The debug APK builds, 9 unit tests pass, lint reports zero errors, and a post-setup offline build succeeds. Fragmentation, multiple frames, CRC rejection/resynchronization, malformed UTF-8, identity matching, and counters are tested. Local text and generated-PNG demos use the production parser. The packaged app declares USB host and no Internet permission. No S25, cable, UNO Q CDC interface, power, throughput, or board decoder was exercised. |
| Usefulness | Android UI/protocol work can progress without occupying scarce receiver hardware, and the decoder/phone boundary is explicit: UNO Q produces standard content while Android presents it |
| Friction and owner | Initial offline Gradle attempts failed because AGP transitive AAPT2/lint/Kotlin artifacts and the pinned JitPack library were not cached; Gradle configuration-cache serialization errors obscured the missing-artifact cause. A stale Android Studio Start-menu shortcut exists although the Gradle SDK/toolchain is usable. This is setup/tooling friction, not Qualcomm runtime evidence. |
| Workaround | Resolve pinned dependencies once with network access, use the checked-in wrapper and checksum thereafter, build from PowerShell until Android Studio is installed/repaired, and use wireless ADB later because the phone USB-C port will be occupied by UNO Q |
| Suggested improvement | Publish a maintained UNO Q-to-Android sample that states the default composite descriptors, phone power expectations, supported baud/throughput, and a decoded binary-file framing example |

### DX-015 - Fixed-shape QNN decoders scale predictably across image budgets

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; add a practical 128 by 128 raw image option between the existing tiny and 256-pixel decoders |
| Environment | Snapdragon X Elite X1E80100; Windows 11 ARM64; x64 Python 3.11 preparation; native ARM64 Python 3.11 worker |
| Tool/source | PyTorch 2.13.0, CompressAI 1.2.8, ONNX Runtime 1.24.4, `onnxruntime-qnn` 2.4.0, QNN HTP |
| Intended workflow | Export `[1,192,8,8] -> [1,3,128,128]`, calibrate all balanced effective-detail levels, use unsigned 16-bit QDQ, disable fallback, and compare CPU and NPU output across the acceptance set |
| Actual result and evidence | Export parity passed with `5.96e-7` maximum absolute error. The QDQ graph reached 66.74 dB minimum CPU parity. The QNN probe and four real payloads selected the Qualcomm NPU, listed only `QNNExecutionProvider`, recorded zero CPU nodes, returned finite 128 by 128 output, and measured at least 51.29 dB NPU/CPU parity. Inference was about 6-7 ms after roughly 2.1-2.5 seconds of per-session graph setup. |
| Usefulness | A middle static shape materially improves the demo: measured payloads were 216-664 bytes instead of forcing every image through the 128-byte/64-pixel path, while preserving the complete-NPU claim |
| Friction and owner | Each resolution still needs a separately exported, calibrated, hashed, and deployed artifact; repeated graph preparation dominates interactive latency. This is an integration and QNN startup-cost issue. |
| Workaround | Keep explicit preset-to-artifact mapping, validate each graph independently, default the UI to the balanced profile, and reuse the existing 256 graph for the quality raw profile |
| Suggested improvement | Make multi-shape export plus QNN context-cache generation a first-class workflow, with a single manifest and separate graph-setup/inference timing in standard output |

### DX-016 - Galaxy S25 and UNO Q require different Qualcomm acceleration claims

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; determine whether LightWeave compression/reconstruction can move from Snapdragon Windows to Galaxy S25 and UNO Q Qualcomm silicon |
| Environment | Research only; Galaxy S25 with Snapdragon 8 Elite for Galaxy and UNO Q with QRB2210/Debian ARM64; no inference session, profile, or numerical result was produced on either target |
| Tool/source | Samsung Galaxy S25 specification; ONNX Runtime QNN Android/build/Java documentation; Qualcomm QRB2210 product page and product brief; Arduino UNO Q/App Lab documentation; CompressAI and EnCodec upstream repositories |
| Intended workflow | Reuse the fixed-shape QDQ image graphs and raw payload contract, while assigning neural work to the strongest supported accelerator on each device and leaving entropy/media operations on CPU |
| Actual result and evidence | Android QNN documentation exposes an HTP NPU path and Java integration but requires a custom Android ARM64 build. Qualcomm documents QRB2210 AI inference on CPU/GPU and a Hexagon DSP for lightweight AI/sensor/audio work. Arduino's current ARM64 AI Hub runner container installs `libqnn1` and `qcom-fastrpc1`, and its App Lab repository publishes a QNN inference container. No physical-device assignment evidence exists for the LightWeave graph. |
| Usefulness | The S25 is a credible strict-NPU image reconstruction/encoding target. UNO Q is a credible self-contained Debian codec/receiver with CPU and possible QNN acceleration, but the exact backend and NPU/DSP claim must be withheld until runtime discovery and profiling prove it. |
| Friction and owner | Runtime packaging and SDK/device-version matching differ across Windows, Android, and Debian ARM64. CompressAI entropy code must be made native/portable, and EnCodec does not officially support Android/mobile ARM. These are Qualcomm, Arduino, and third-party integration/documentation concerns. |
| Workaround | Maintain one repository with shared manifests, payload contracts, test vectors, and target-specific bootstrap layers. Gate S25 with one stored latent on HTP; gate UNO Q with CPU parity/latency first, then inspect and test any supported GPU/QNN path. |
| Suggested improvement | Publish a current cross-device QAIRT compatibility matrix and maintained examples showing strict accelerator assignment, packaging, profiling, and model reuse across Snapdragon Windows, Android flagship, and QRB2210 Debian targets. |

### DX-017 - UNO Q acceleration is available through Adreno Vulkan, not QNN on the exercised image

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; prove complete LightWeave image reconstruction on a Qualcomm accelerator in UNO Q |
| Environment | Arduino UNO Q; Qualcomm QRB2210; Debian 13.1 ARM64; Linux 6.16.7; 3.6 GiB RAM; Mesa 25.2.6 Turnip Vulkan; Adreno 702; Arduino App CLI 0.12.1 |
| Tool/source | Read-only board doctor, native CompressAI-compatible rANS, pnnx 20260526 model conversion, source-built ncnn Vulkan reporting build version 20260805 |
| Intended workflow | Prefer strict QNN Hexagon, then QNN Adreno, then strict ncnn Vulkan; require one backend to execute every complete `g_s` graph with no neural CPU fallback |
| Actual result and evidence | The base image exposed no QNN/FastRPC libraries, firmware, or device nodes. Vulkan identified Turnip Adreno 702 plus llvmpipe. Native entropy decoding matched CompressAI latents exactly for all presets. The runner audited all 16 compute layers for Vulkan support, rejected non-Adreno devices, and ran the 64, 128, and 256 graphs completely on Adreno. Final accelerator/CPU parity measured 36.34, 41.77, and 44.38 dB; five-run median/p95 inference was 0.173/0.176, 0.521/0.562, and 1.978/2.160 seconds. |
| Usefulness | Establishes a defensible Qualcomm-accelerated UNO Q receiver without making an unsupported Hexagon claim and preserves the existing raw payload contract |
| Friction and owner | The available base image differs from Arduino's published QNN-oriented runner material, and current documentation does not clearly map UNO Q image versions to QNN/FastRPC availability; Qualcomm/Arduino runtime and documentation gap. ncnn conversion/build is third-party integration work. |
| Workaround | Discover the installed runtime before selecting a backend, fail closed on unsupported/non-Vulkan layers, require Adreno by name, and pair assignment evidence with numerical CPU parity |
| Suggested improvement | Publish an image-versioned UNO Q accelerator matrix with QNN/FastRPC packages, firmware/device-node prerequisites, supported accelerator targets, and a strict full-graph profiling sample |

### DX-018 - Native Debian delivery works, but App Lab's generic container omits Vulkan user space

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; deliver the same strict receiver as a native command and board-hosted App Lab WebUI without changing the base OS |
| Environment | Same UNO Q as DX-017; Arduino App CLI 0.12.1; Docker 26.1.5 used by the platform and as a temporary build tool; Python 3.11 standard-library service |
| Tool/source | Native ARM64 runner, Arduino App Lab generic Python application container, board-local Vulkan loader/Turnip driver/ICD |
| Intended workflow | Run `lightweave-uno` directly on Debian and expose the same decoder through an offline App Lab receive page |
| Actual result and evidence | The native host CLI ran without Docker. App Lab mounted GPU device nodes and groups but its generic container omitted `libvulkan`, the Turnip driver, and the Freedreno ICD descriptor. Copying those three files from the target board into only the installed LightWeave app and setting loader/ICD environment variables made the strict Adreno status probe and a real 216-byte/128-pixel reconstruction succeed. The installer performs this target-local copy; no vendor binary is committed or redistributed. |
| Usefulness | Preserves a native existing-OS tool while still integrating with App Lab's user-facing application model; the same CLI, validation, and evidence serve both entry points |
| Friction and owner | App Lab's generic image exposes GPU devices without the matching Vulkan user-space stack, so a nominally available accelerator is unusable until manually bridged; Arduino container packaging/documentation issue |
| Workaround | Keep Docker out of the delivered CLI, use it only for reproducible source builds, copy only the target's matching Vulkan files into the one app, hash all LightWeave artifacts, and leave the base OS and other apps untouched |
| Suggested improvement | Provide an official UNO Q App Lab base image/Brick with the board-matched Vulkan loader and Turnip ICD, plus a GPU doctor and redistributable-boundary guidance |

### DX-019 - Resource-limited native builds need realistic time and clock guidance

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; compile a Vulkan-enabled ncnn runner reproducibly on the attached UNO Q |
| Environment | Same UNO Q; two compile jobs; first dependency build on board storage; subsequent cache retained |
| Tool/source | ncnn source build and official ncnn build guide |
| Intended workflow | Prepare one statically linked native runner, then deploy it without compilers or a runtime container |
| Actual result and evidence | The first ncnn build took about 27 minutes; a cached LightWeave-runner rebuild took about 20 seconds. The board clock was about nine hours behind the setup host, causing current signed package metadata to appear future-dated inside the temporary builder. A scoped build-only clock shim and temporary host network proxy allowed dependency setup without modifying the board clock. |
| Usefulness | Sets accurate developer expectations: the expensive operation is a one-time dependency build, not every LightWeave iteration or runtime launch |
| Friction and owner | The board image lacks a native compiler/CMake toolchain and its clock can invalidate package metadata; base-image/setup friction. The long first ncnn compile is expected third-party/resource-limited build cost. |
| Workaround | Use two jobs as the ncnn guide recommends for constrained machines, retain the build cache during development, scope any clock workaround to the disposable builder, and deploy only the native binary and hashed assets |
| Suggested improvement | Add UNO Q App Lab documentation for native extension builds, expected compile times, clock synchronization diagnostics, disk preflight, and reusable build caches |

### DX-020 - Assignment evidence must be paired with repeated GPU stability tests

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; measure cold/median/p95 behavior and repeated execution for every UNO Q image profile |
| Environment | Same UNO Q/Turnip stack as DX-017; native ncnn runner invoked from both Debian host and App Lab |
| Tool/source | ncnn Vulkan, Mesa Turnip/MSM DRM kernel driver, LightWeave benchmark and shared accelerator lock |
| Intended workflow | Repeat all three strict full-graph reconstructions five times, measure latency/RSS/disk, and keep the board-hosted service available |
| Actual result and evidence | An initial FP16-arithmetic sequence reached the quality graph and produced `vkWaitForFences -4`; kernel DRM logs recorded an MSM GPU hang, recovery, and translation faults in the LightWeave quality runner. A process-local delay alone and explicit ncnn teardown did not immediately clear the affected driver state. The final runner retains FP16 storage/packing but uses FP32 arithmetic, explicitly tears down the Vulkan instance, and serializes host/App Lab calls through a shared file lock with a one-second cooldown. A subsequent five-run sequence of all profiles passed; peak observed child RSS was about 60.6 MiB, installed bundle about 35.6 MiB, and 17.6 GB disk remained free. A deliberately concurrent native quality decode and App Lab balanced request both completed strictly, proving cross-container lock arbitration. |
| Usefulness | Prevented a one-shot accelerator demo from being mislabeled production-stable and produced an explicit concurrency/runtime contract for the receiver |
| Friction and owner | The graph was fully Vulkan-supported and numerically valid, yet a repeated workload still triggered a low-level GPU fault; likely ncnn/Turnip/MSM interaction requiring upstream isolation rather than an application semantic error |
| Workaround | Use the validated mixed-storage/FP32-arithmetic configuration, coordinate all LightWeave accelerator clients with one shared lock and cooldown, retain kernel-log evidence, and keep CPU fallback forbidden |
| Suggested improvement | Add a maintained UNO Q GPU-inference stress sample, automatic device-loss diagnostics/reset guidance, and App Lab-wide accelerator arbitration for host plus container clients |

### DX-021 - EnCodec audio requires a truthful CPU/Adreno partition on UNO Q

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; add receiver-only raw EnCodec reconstruction to the existing native UNO Q image receiver |
| Environment | Arduino UNO Q; Qualcomm QRB2210 CPU plus Turnip Adreno 702; Debian 13.1 ARM64; App Lab 0.12.1; EnCodec 0.1.1 preparation under Windows x64 Python 3.11.9; board Python 3.13.14 |
| Tool/source | Meta EnCodec 24 kHz checkpoint `d7cc33bc`; PyTorch 2.13.0 CPU; pnnx 20260526; ncnn board runtime 20260805; native C++ 10-bit unpacking/codebook summation |
| Intended workflow | Preserve `A1-E15-S<n>` exactly, run recurrent work on CPU, select the earliest split in 2/5/8/11/13 whose complete suffix is Vulkan-supported and numerically stable, and expose the result through the native CLI plus App Lab |
| Actual result and evidence | Split 2 was fully Vulkan-supported but returned non-finite Adreno output and was rejected. Split 5 was the earliest pass: code indices matched Python exactly, native codebook error was 0.0, CPU layers 0-4 preserved recurrence across the complete clip, and all 39 suffix compute layers 5-15 ran on Adreno. One- and five-second board output measured 52.11/52.07 dB against PyTorch with exact 24,000/120,000 samples and zero conditioned boundary jump. Five-run one-second median/p95 was 1.306/1.317 s for the Adreno suffix and 2.716/2.745 s total; five-second results were 6.248/6.249 s and 8.483/8.487 s. Peak child RSS was about 109.1 MiB. |
| Usefulness | Extends the same 188-byte-per-second transport contract to a small Qualcomm edge board without installing PyTorch/EnCodec or making a false full-GPU/NPU claim |
| Friction and owner | Upstream EnCodec does not provide an onboard ARM runtime; its LSTM is outside ncnn Vulkan, pnnx produces many duration-specific static shape files, and a graph can report Vulkan support yet still fail numerically. This is primarily third-party model/runtime friction, with Qualcomm/Arduino documentation lacking an end-to-end neural audio partition example. |
| Workaround | Export two codebooks plus one content-addressed shared prefix weight file, generate static 1-5 second prefix params, audit every suffix layer, pair assignment with finite/parity tests, reject split 2, cap the first release at five seconds, and retain the shared accelerator lock/cooldown. Docker is used only for the reproducible board build; the installed tool runs natively on Debian/App Lab. |
| Suggested improvement | Publish a maintained QRB2210 audio-inference sample covering recurrent CPU/GPU partitioning, Vulkan numerical validation, shared accelerator arbitration, duration/memory tradeoffs, and packaging into App Lab without a Python ML runtime. |

### DX-022 - Existing App Lab optical app has a reusable byte boundary but no host API

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; inspect the owner's connected transmitting UNO Q and determine whether `image_transmitter_bkp` can carry LightWeave raw payloads |
| Environment | Arduino UNO Q/QRB2210; Linux 6.16.7 ARM64; Arduino App CLI and daemon 0.12.1; Arduino Zephyr core 0.90.0; Arduino RouterBridge 0.4.3; Python Apps base image 0.11.0; Pillow declared without a pinned version |
| Tool/source | Read-only ADB device/app discovery, `arduino-app-cli app list` and historical logs, and direct inspection of the installed Python/App Lab manifest/STM32 sketch; the stopped app was not started, flashed, or modified |
| Intended workflow | Find a binary-safe boundary between the Windows LightWeave `RawByteSink` and the existing laser transmitter without changing the raw codec bytes |
| Actual result and evidence | The app has no ports or Bricks and autonomously converts bundled `images.jpg` into a thresholded 128-by-128 one-bit bitmap. Python makes 2,048 per-byte RouterBridge calls into a fixed STM32 buffer. The sketch accepts every byte value 0-255, then drives pin 9 with one high start bit, 16,384 MSB-first data bits, and one low stop bit at 25 ms/bit. Historical logs show all 2,048 bytes loaded and transmission requested. There is no length, checksum, retry, line coding, or variable-size input. The resulting rate is 40 bit/s and one frame takes about 409.65 seconds. Installed MessagePack 0.4.2 supports binary `std::vector<unsigned char>`, but RouterBridge's default RPC message buffer is 256 bytes, so payload loading can be chunked but cannot be one 2,048-byte call. |
| Usefulness | The RouterBridge byte store, STM32 buffer, absolute bit schedule, and laser loop can be retained; LightWeave needs only a host-facing binary input plus variable-length transmission and a matching receive-length contract |
| Friction and owner | App Lab makes MPU-to-MCU function calls straightforward, but the sample performs one RPC per byte and exposes no external application port. The app is tightly coupled to fixed image dimensions rather than a transport payload, and its Pillow dependency is unpinned. These are application-design issues; bulk binary RPC capability and App Lab host/API guidance are Arduino tooling/documentation questions. |
| Workaround | Expose a local `application/octet-stream` endpoint or watched inbox, validate a maximum of 2,048 bytes, pass an explicit payload length to the sketch, preserve the byte array exactly, and configure the receiver length out of band unless a separate physical-frame change is approved. Measure a conservative binary chunk size below the 256-byte RPC limit instead of retaining 2,048 per-byte calls. |
| Suggested improvement | Provide an App Lab binary-transfer example with chunked RouterBridge byte arrays, host-facing local upload/API patterns, backpressure, variable-length buffers, and explicit timing/throughput measurements. |

### DX-023 - App Lab clone and USB inbox provide a safe dashboard transmitter path

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; connect LightWeave's Windows image/audio dashboard to the owner's UNO Q laser transmitter while preserving the backup and waveform |
| Environment | Windows 11 x64 host; Arduino UNO Q/Qualcomm QRB2210; Debian 13.1 ARM64 with Linux 6.16.7; Arduino App CLI/daemon 0.12.1; App Lab Python 3.13.14; Arduino Zephyr core 0.90.0; RouterBridge 0.4.3; RPClite 0.3.0; MessagePack 0.4.2 |
| Tool/source | Arduino App Lab clone/build/start workflow, ADB over USB, RouterBridge MPU-to-STM32 RPC, tracked `uno_q/transmitter_app` source, and the Windows `RawByteSink` dashboard boundary |
| Intended workflow | Clone `image_transmitter_bkp` without touching it, accept exact header-free `payload.bin` files from the Windows dashboard, buffer the declared variable length on the STM32, and retain pin 9, 25 ms timing, MSB-first bits, and start/stop signaling |
| Actual result and evidence | Important backup hashes were identical before and after installation. App Lab compiled/flashed the clone in about 93 seconds; the sketch used 86,468 bytes of flash and 35,070 bytes of global RAM. A 124-byte image and a 188-byte one-second audio payload were acknowledged byte-for-byte, launched with 994/1,506 optical bits, and produced serial start/completion plus laser-off evidence at 24.85/37.65-second estimates. An immediate second request was rejected busy. The browser then generated and sent a 104-byte image through the same dashboard API, displayed the 20.85-second launch evidence, and produced no console errors. The owner later independently observed the physical laser blinking during a dashboard send; reception correctness remains unproven. The original app remained stopped and unmodified. |
| Usefulness | App Lab provides a practical way to keep the Linux inbox/orchestration and real-time STM32 waveform in one project. ADB supplies an offline USB control path, while the shared repository now contains the App Lab source, installer, validation contract, and setup instructions instead of relying on board-only state. |
| Friction and owner | App Lab permits one active application, so starting the transmitter required an explicit reversible stop of another app. Two ADB devices were attached, requiring capability-based UNO Q selection. App CLI JSON includes Unicode output that Windows' default console codec could not decode reliably. A missing result file can also surface command stderr before it is ready, and the sketch exposes no physical-completion callback. Per-byte RouterBridge loading is slow but was explicitly retained for this milestone. These are a mix of App Lab lifecycle/API documentation gaps and host-integration/application concerns. |
| Workaround | Make stopping another app opt-in, detect the UNO Q by a successful App CLI probe, decode subprocess output as UTF-8, test result-file existence before reading it, publish inbox files atomically with SHA-256/length validation, maintain an estimated busy window, and report only buffer/launch acceptance. |
| Suggested improvement | Add an official App Lab host-to-app USB inbox/upload recipe, stable machine-readable status without decorative Unicode, explicit multi-device selection guidance, a lifecycle API that explains the one-active-app rule, bulk binary RouterBridge examples, and an MCU-to-MPU completion/progress callback pattern. |

### DX-024 - Two-board USB discovery requires an independently enumerated data connection

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; discover the newly connected receiver UNO Q without disturbing the running transmitter |
| Environment | Windows 11 build 26100 x64; Android Debug Bridge 1.0.41/platform-tools 36.0.2; transmitting UNO Q `123900964`/`UNOQ-1` on COM3 with App CLI 0.12.1 |
| Tool/source | Read-only ADB device/app discovery plus Windows PnP and serial-port enumeration |
| Intended workflow | Enumerate two independent UNO Q serials, preserve the running transmitter, and map the second board before inspecting its receiver application |
| Actual result and evidence | The initial scan exposed only one Arduino `2341:0078` composite device, one ADB interface, and COM3. After the receiver cable/port was reconnected, both boards enumerated independently: transmitter `123900964`/`UNOQ-1`/COM3 and receiver `371371094`/`unoq2`/COM4. `lightweave_transmitter` remained running; no receiver app was stopped, started, flashed, or modified. |
| Usefulness | Capability-based discovery prevented the connected transmitter from being mistaken for an unverified receiver and avoided changing the wrong board. |
| Friction and owner | The second board did not enumerate on the first attempt, making a cable/port/power issue look like device-selection failure; this was a physical USB setup issue rather than an App Lab or LightWeave software failure. |
| Workaround | Verify receiver power and a known data-capable cable/direct host port, then require a distinct composite/ADB/serial identity before any receiver action. Capability plus explicit serial selection keeps the boards deterministic. |
| Suggested improvement | Provide a concise official two-UNO-Q host setup guide covering unique USB identities, expected composite interfaces, power/cable requirements, and deterministic App CLI device selection. |

### DX-025 - Existing optical receiver matches timing but not the raw payload contract

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; inspect receiver App Lab projects read-only and find the safest base for LightWeave optical-byte verification |
| Environment | Receiver UNO Q `371371094`/`unoq2`/COM4; Arduino App CLI 0.12.1; stopped `image_receiver`, `laser_receiver_ui`, and LightWeave accelerated receiver apps |
| Tool/source | Read-only ADB source listing, SHA-256 capture, and inspection of App Lab Python/STM32 sketches |
| Intended workflow | Reuse an existing optical receiver only if its waveform matches the running LightWeave transmitter and it can preserve arbitrary variable-length binary payloads |
| Actual result and evidence | `image_receiver` samples analog A0 at threshold 800 and matches one leading bit, 25 ms/bit, MSB-first data, and a low stop bit. It is hard-coded to 16,384 data bits/2,048 bytes and converts them into a 128-by-128 monochrome PNG. `laser_receiver_ui` instead uses 100 ms/bit, one leading bit per ASCII character, and a text string, so it is incompatible. The accelerated `LightWeave UNO Q Receiver` is installed but stopped and currently accepts uploaded files rather than optical bytes. |
| Usefulness | Most timing-sensitive receiver logic can be retained from `image_receiver`; the already validated LightWeave decoder can remain a separate raw-byte consumer. |
| Friction and owner | App Lab examples couple optical framing, fixed image dimensions, transport buffering, and media rendering. There is no variable-length binary handoff between the timing-sensitive STM32 receiver and the Linux inference app. This is application architecture friction, with room for a stronger Arduino binary-transport sample. |
| Workaround | Clone rather than edit `image_receiver`; pass an explicit trusted payload length, stop after that many bytes, retrieve binary-safe chunks below RouterBridge limits, validate exact bytes first, then hand the unchanged payload and preset to the existing decoder. |
| Suggested improvement | Publish an App Lab optical/serial receiver example with explicit length, arbitrary binary data, chunked MPU/MCU transfer, byte-integrity evidence, and a clean adapter boundary independent of image dimensions. |

### DX-026 - Separate App Lab byte receiver proves the two-board optical path

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; build a minimal receiver that proves exact optical bytes before connecting Qualcomm-accelerated reconstruction |
| Environment | Transmitter `123900964`/COM3 and receiver `371371094`/COM4; UNO Q QRB2210 plus STM32U585; App CLI 0.12.1; Python 3.13.14; Arduino Zephyr core 0.90.0; RouterBridge 0.4.3; RPClite 0.3.0; MessagePack 0.4.2 |
| Tool/source | Tracked `lightweave_byte_receiver` App Lab clone, ADB atomic arm/result inbox, A0 analog receiver at threshold 800, 25-ms STM32 sampling, and Windows byte-verification script |
| Intended workflow | Preserve every existing receiver app, arm a trusted expected length out of band, capture arbitrary raw binary, retrieve it in RouterBridge-safe chunks, and compare the exact sent/received bytes before invoking AI |
| Actual result and evidence | The hash-checking installer preserved both source apps, stopped only the receiver's unrelated default `Copy of connect to phone`, and compiled/flashed the new app in about 95 seconds. The sketch used 87,756 bytes of flash and 33,678 bytes of global RAM. A physical 34-bit transmission carried four data bytes `00 FF AA 55`; the receiver returned the identical four bytes, matching SHA-256 `df7d75aad696b49ea81cbddff8c30a794ce0243bf9895db26e8127e0485f4de5`, and a valid low stop bit. The transmitter app continued running on the other board. |
| Usefulness | Separates optical reliability from CompressAI/EnCodec/ncnn behavior and gives a reproducible exact-byte gate using the same two-board hardware and waveform as future media transfers. |
| Friction and owner | App Lab rejected a textual `[RX]` icon because the manifest requires one emoji, and the receiver's default app could start between discovery and installation. A first build/flash still takes about 95 seconds. RouterBridge response sizing makes chunked retrieval preferable to one large return value. These are App Lab schema/lifecycle/documentation and application-integration issues. |
| Workaround | Use a valid single-emoji icon, recheck running apps immediately before start, require explicit device serials, make stopping another app opt-in, preserve original hashes, retrieve 32 bytes per RPC, and keep the expected length in the local ADB/UI control plane. |
| Suggested improvement | Validate App Lab manifests before deployment with clear field constraints, expose deterministic default-app lifecycle controls, document safe RPC payload sizes, and publish a two-board binary optical loopback example with exact-byte evidence. |

### DX-027 - App Lab composes optical capture with strict Adreno reconstruction

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; turn the verified byte path into a production LightWeave image receiver without rebuilding the native AI runtime |
| Environment | Receiver UNO Q `371371094`/`unoq2`; Qualcomm QRB2210 CPU plus Turnip Adreno 702; Debian 13.1 ARM64; App CLI 0.12.1; Python 3.13.14; Arduino Zephyr 0.90.0; RouterBridge 0.4.3; ncnn Vulkan runtime and LightWeave bundle 0.2.0 installed previously |
| Tool/source | Arduino App Lab clone/build/start workflow; reused `image_receiver` A0 threshold-800/25-ms sampling; tracked `lightweave_optical_receiver`; existing native rANS plus 16-layer ncnn Vulkan image decoder; ADB acceptance harness; live App Lab WebUI |
| Intended workflow | Arm a trusted preset and exact length, receive only the raw CompressAI entropy bytes through the laser, retrieve them from the STM32 in bounded chunks, and reconstruct through the existing complete Adreno graph with CPU fallback disabled |
| Actual result and evidence | The expensive native preparation was reused rather than repeated. App Lab built/flashed the integration in 92.4 seconds, using 87,764 bytes flash and 33,678 bytes RAM. Two physical 80-byte `I64-Q1-B128` transfers matched sender SHA-256 `17493ea32aee4d0e615cf7f49ef678c78198de716f5cf31247e2b7d89a30033f` and had valid stop bits. The automated run reconstructed exactly 64 by 64 through `ncnn-vulkan` on `Turnip Adreno (TM) 702`, reported 16 compute layers, `strict_no_fallback: true`, about 0.15 ms entropy time, about 214 ms accelerator time, and about 1.97 seconds serialized runner time. A browser-armed repeat rendered the PNG/download and reported about 175 ms Adreno time with zero console errors. Decoder, `image_receiver`, and diagnostic source remained separate and unchanged. |
| Usefulness | Demonstrates a complete Qualcomm edge workflow: Windows generates compact AI codec bytes, two UNO Q boards carry them over visible light, and the receiving QRB2210 reconstructs the image on Adreno without reinstalling PyTorch or rebuilding ncnn |
| Friction and owner | App Lab allows one active app, so the diagnostic had to stop before the production receiver started. The first start failed before compilation because a minimal `sketch.yaml` lacked `default_profile`; App Lab's error was accurate but the manifest requirement was not obvious. The first idempotent update also exposed that App CLI JSON reports the human-readable manifest name rather than the directory ID, so target recognition must model both identities. App Lab duplicates the prepared receiver app to preserve its target-local Vulkan/runtime files, and preset/length still travel out of band. These are App Lab schema/lifecycle documentation plus deliberate application-protocol tradeoffs. |
| Workaround | Preserve a known-good `sketch.yaml`, distinguish the display name from the app directory ID, make stopping another app explicit, verify installed decoder hashes against the repository, clone target-local artifacts instead of redistributing vendor files, keep diagnostic and production apps separate, and fail closed on preset budget, stop bit, device, layer count, and fallback evidence. The corrected idempotent reinstall stopped only its own app, preserved source hashes, and restarted successfully. |
| Suggested improvement | Add App Lab schema validation before deployment, document `default_profile` with a minimal sketch example, support shared immutable model/runtime assets across apps, and publish an optical binary-to-accelerator sample with explicit preset/length control and per-stage evidence. |

### DX-028 - Self-describing media framing exposes open-loop clock drift safely

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; remove manual receiver settings and route image/audio frames automatically into the existing UNO Q accelerated decoders |
| Environment | Two Arduino UNO Q boards with Qualcomm QRB2210 plus STM32U585; Debian 13.1 ARM64; App CLI/daemon 0.12.1; Python 3.13.14; Arduino Zephyr 0.90.0; RouterBridge 0.4.3; Turnip Adreno 702 and the installed ncnn Vulkan receiver |
| Tool/source | Tracked App Lab transmitter/receiver applications, shared Python/C++ `LWF1` contract, ADB acceptance harnesses, browser-tested App Lab WebUI, CRC-16/CCITT-FALSE, native rANS image decoder, and native CPU/Adreno EnCodec decoder |
| Intended workflow | Press Listen once, transmit an unchanged `payload.bin` inside a 12-byte optical wrapper, validate media/profile/length/sample count/CRC/stop bit on the STM32 and Linux sides, then automatically invoke the correct strict accelerator path |
| Actual result and evidence | Canonical image/audio vectors matched in Python and C++. The first 80-byte image passed, while an initial 216-byte frame failed CRC repeatably. Preserved rejected bytes showed equality through byte 154 followed by a one-bit stream displacement around optical bit 1,389, isolating cumulative free-running-clock phase error rather than codec corruption. Retaining the 25,000-us transmitter bit and sampling the receiver at 24,991 us passed 80-, 216-, and 716-byte image payloads plus a 188-byte one-second audio payload. Images reconstructed to 64/128/256 through all 16 Adreno layers with strict fallback disabled. Audio restored exactly 24,000 mono samples through CPU layers 0-4 and the strict 39-layer Adreno suffix, with a zero conditioned boundary jump. CRC-invalid frames never reached inference. Explicit `raw-v0` still carried `00 FF AA 55` exactly after the upgrade. The live WebUI's one-shot Listen/Cancel controls returned correctly to idle with no browser console errors. The owner elected to skip further long optical transfers, so the five-second wire case was not run. |
| Usefulness | The production receiver no longer relies on users copying presets or lengths, one protocol serves both Qualcomm-accelerated media paths, and CRC evidence turned an otherwise silent image failure into an actionable timing diagnosis before inference |
| Friction and owner | App Lab rebuild/flash still takes roughly 90 seconds for a small sketch change, only one App Lab app can run per board, two connected boards need role-aware selection, and fixed-delay optical sampling lacks transition-based clock recovery. The first three are Arduino/App Lab workflow issues; oscillator drift is a limitation of the deliberately simple application waveform. |
| Workaround | Share the frame contract between Python and C++, reject request-schema mismatches, select the single board running the tracked transmitter marker, preserve the raw diagnostic, store rejected-frame evidence atomically, keep the measured 24,991-us receiver calibration explicit, and avoid claiming general optical reliability from this board pair |
| Suggested improvement | Publish a two-board App Lab binary-link sample with machine-readable lifecycle/device roles, incremental build progress, CRC/error telemetry, and transition-based clock recovery or a synchronization pattern robust to oscillator drift. |

### DX-029 - App Lab WebUI health and mobile LAN discovery are separate gates

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; diagnose intermittent access to the UNO Q optical receiver WebUI from a mobile browser |
| Environment | Arduino UNO Q/Qualcomm QRB2210 receiver; Debian 13.1 ARM64; App CLI 0.12.1; App Lab WebUI Brick; Wi-Fi DHCP; Android mobile browser path not instrumented directly |
| Tool/source | Read-only ADB inspection, NetworkManager status/logs, socket inspection, loopback HTTP, and a Windows LAN HTTP probe |
| Intended workflow | Reach the board-hosted receiver consistently from a phone on the same trusted local network |
| Actual result and evidence | The LightWeave receiver app was running, the WebUI listener was bound to IPv4/IPv6 on port 7000, local HTTP returned 200, the board had an active DHCP IPv4 route with 100-percent reported signal, and Windows reached that direct IPv4 address with HTTP 200. The `.local` hostname did not resolve from Windows. No post-association Wi-Fi disconnect appeared in the inspected interval. This isolates the observed intermittency from the App Lab process itself; phone subnet/routing, multicast name discovery, DHCP address changes, VPN/cellular fallback, or access-point client policy remain candidate causes. |
| Usefulness | Separates inference/UI process health from LAN discovery and gives the demo a deterministic direct-IP test before changing application code |
| Friction and owner | The WebUI Brick is reachable on the board but does not provide a stable user-facing discovery URL or authentication; `.local` support and guest-network client reachability vary by host/network. This is primarily local-network/discovery friction around the App Lab experience, not a Qualcomm accelerator issue. |
| Workaround | Use `http://<current-board-ip>:7000` on the same IPv4 subnet, confirm plain HTTP, disable phone VPN/cellular fallback during testing, and reserve the DHCP address or use a controlled demo router/hotspot. Keep the page on a trusted LAN because it has no authentication. |
| Suggested improvement | App Lab should display the active LAN URL, connection/interface state, and WebUI reachability in a device status panel, with clear guidance for mDNS, guest-network isolation, and secure remote access. |

### DX-030 - The original App Lab text demo is useful logic, not a production protocol

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; inspect the original text transmitter/receiver and integrate its useful behavior into LightWeave |
| Environment | Two stopped Arduino UNO Q App Lab projects; Arduino Zephyr/RouterBridge path; Python WebUI backends and browser assets inspected read-only over ADB |
| Tool/source | `laser_transmitter_ui`, `laser_receiver_ui`, Arduino App Lab WebUI Brick, RouterBridge, and STM32 sketches |
| Intended workflow | Preserve simple text-over-light behavior without introducing an AI codec, while fitting the production image/audio application and repository |
| Actual result and evidence | The transmitter validates 1-100 printable ASCII characters and emits a 100-ms high leading bit plus eight MSB-first bits per character after one low interval. The receiver detects the first rising edge on digital pin 2, majority-votes three center samples, and ends when the next leading-bit slot is low. Both apps were stopped and left unchanged. There is no length/version/CRC, the frontend and backend duration formulas disagree, browser HTML loads a remote Socket.IO CDN despite bundled local assets, metadata/docs remain from an LED example, and received text is volatile. |
| Usefulness | Confirms that text requires only deterministic ASCII byte handling and provides a legacy waveform reference for interoperability demonstrations |
| Friction and owner | App Lab makes the WebUI-to-RouterBridge path approachable, but copied examples can retain stale documentation/assets and silently diverge between frontend timing and MCU behavior. This is sample/application hygiene friction rather than Qualcomm inference friction. |
| Workaround | Preserve the originals, record the legacy protocol, encode printable ASCII directly, and route production text as profile `0x20` through the existing offline `LWF1` frame and paired LightWeave applications. No AI or accelerator claim is made for text. |
| Suggested improvement | App Lab templates should keep metadata/docs synchronized with generated code, default to local WebUI assets, expose protocol timing from one shared definition, and include framed text/binary examples with length and integrity checks. |

### DX-031 - One App Lab pair can route no-AI text and accelerated media honestly

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; deploy the matched production transmitter/receiver pair and prove text over the same optical link without implying AI usage |
| Environment | Two Arduino UNO Q boards with QRB2210 Linux hosts and STM32U585 MCUs; Debian ARM64; Arduino App CLI 0.12.1; Arduino Zephyr 0.90.0; RouterBridge 0.4.3; USB/ADB from Windows 11 ARM64 |
| Tool/source | Arduino App Lab lifecycle/build, WebUI Brick, RouterBridge/RPClite, tracked `lightweave_transmitter` and `lightweave_receiver` sources |
| Intended workflow | Generate exact ASCII in the Windows dashboard, buffer it over USB, frame it dynamically on the transmitter MCU, auto-detect it on the receiver MCU, and persist/render it without a codec model |
| Actual result and evidence | Both apps built and started in about 92-95 seconds. The transmitter sketch used 88,252 bytes flash/35,766 bytes global RAM; the receiver used 93,044/35,146. A 16-byte `Hello LightWeave` payload crossed as LWF1 profile `0x20` in 5.65 seconds and matched exactly. Both boards agreed on header `4c570120100000000000`, CRC `0xa62b`, payload SHA-256, and valid stop bit. The receiver atomically stored TXT/BIN/JSON, labeled the path `printable-ascii`, and reported that no accelerator was required. Both local WebUIs loaded without remote assets or browser console errors. Legacy and rollback source hashes were unchanged. |
| Usefulness | Reuses one offline application pair, control plane, dynamic frame, CRC, persistence layer, and UI for text/image/audio while keeping AI claims scoped only to media reconstruction |
| Friction and owner | App Lab identifies applications by display name in status output while deployment paths use app IDs, so production naming changes must be updated consistently across app YAML, ADB discovery, installers, and verifiers. The first build still recompiles/flashes even for a lightweight protocol/UI extension. This is Arduino App Lab lifecycle/tooling friction, not a Qualcomm inference limitation. |
| Workaround | Keep stable lowercase app IDs and paired title-case display names, track both in manifests, fail closed when the expected running display name/marker is absent, and preserve original apps with before/after source hashes. Use one shared profile table in Python and C++ tests. |
| Suggested improvement | App CLI should expose stable app ID and display name as separate first-class fields in every lifecycle response, support source-only incremental updates, and provide an official binary-framing/RouterBridge sample that demonstrates dynamic length, CRC, local assets, and persisted output. |

### DX-032 - Presentation telemetry needs precise scope, not headline FLOP claims

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; expose useful hardware evidence for each LightWeave transfer and reconstruction without overstating what the runtimes measure |
| Environment | Snapdragon X Elite/Windows 11 ARM64 with x64 Python orchestration and native ARM64 ONNX Runtime QNN; two UNO Q boards with QRB2210 Linux, Adreno 702, and STM32U585; App CLI 0.12.1 |
| Tool/source | Python process clocks and peak working set, ONNX Runtime profiling JSON, QNN execution-provider device metadata, ncnn runner evidence, App Lab/RouterBridge acknowledgements, and the shared LWF1 frame contract |
| Intended workflow | Give judges a per-operation view of which CPU/GPU/NPU/MCU stages ran, how long they took, and what exact work can be counted |
| Actual result and evidence | Windows operations now report wall/process CPU time, peak process RSS, media counters, selected QNN device, provider event counts, and zero-CPU-node evidence. The UNO Q transmitter reports per-byte bridge calls, buffer size, CRC input, framed bytes, and laser GPIO bits. The receiver reports STM32 decoded bits/CRC bytes, CPU entropy or recurrent-prefix time, strict Adreno image/suffix time, audited layer counts, and child peak RSS. After reinstalling both production apps, a physical 12-byte `Telemetry OK` text fixture crossed in a 194-bit frame with 15 bridge calls, 22 CRC input bytes, valid CRC/stop bit, and CPU/MCU-only labeling. Windows UI validation showed Qualcomm CPU identity and measured 80.1 MiB peak process memory. No current interface supplies trustworthy energy, NPU utilization percentage, or model FLOP execution counts. |
| Usefulness | Creates an auditable Qualcomm heterogeneous-compute story: Windows image synthesis uses Hexagon HTP, Windows audio is CPU/HTP hybrid, UNO Q images use complete Adreno Vulkan, UNO Q audio is CPU/Adreno hybrid, and optical timing/framing belongs to the STM32 MCU |
| Friction and owner | ONNX Runtime profile entries are execution-provider events rather than FLOPs; ncnn exposes the validated graph/layer path but not unified power counters; dashboard process RSS excludes native worker peak memory; and App Lab has no physical-completion callback. These are a mix of runtime observability gaps and deliberate application boundaries. |
| Workaround | Label every counter by scope, retain raw JSON evidence, separate CPU and accelerator stages, use strict no-fallback gates, disclose estimated physical completion, and avoid converting layer/event counts into unsupported FLOP or energy claims. |
| Suggested improvement | Qualcomm tooling should expose one portable telemetry schema across QNN/QAIRT and Adreno paths with device identity, graph assignment, per-stage time, peak memory, power/energy when available, and clear event semantics suitable for application dashboards. |

### DX-033 - UNO Q USB gadget access is capable but hidden behind App Lab container policy

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-06; replace the network-dependent receiver page with a final no-laptop Galaxy S25 Ultra + UNO Q USB receiver/display |
| Environment | Receiver UNO Q `371371094`/`unoq2`; Qualcomm QRB2210; Debian GNU/Linux 13 ARM64; kernel 6.16.7-g0dd6551ae96b; Python 3.13.14; App CLI 0.12.1; Docker 26.1.5+dfsg1; Compose 2.26.1-4; STM32U585 with Arduino Zephyr 0.90.0; Windows 11 ARM64 Android build host with JDK 17, SDK/target 36, AGP 9.0.0, and Gradle 9.1.0 |
| Tool/source | UNO Q composite USB gadget `2341:0078`, Linux `/dev/ttyGS0`, App Lab generated Compose service, `usb-serial-for-android` 3.10.0, fresh LightWeave Mobile app, and the existing strict Adreno receiver |
| Intended workflow | Let the S25 act as USB host, send one-shot Listen/Cancel/Status controls, keep all reconstruction on QRB2210/Adreno, and return decoded text/PNG/WAV plus frame and hardware evidence without a laptop or network at runtime |
| Actual result and evidence | The board exposes ACM plus ADB and `/dev/ttyGS0` works in both directions. The generated App Lab container could see the node and had the `dialout` group but its device cgroup rejected major 505. A narrow Compose `devices` override fixed only that endpoint. The receiver installer rebuilt successfully in 101.6 seconds, preserved all reusable-source hashes, and verified container read/write access. A blocking worker was required because polling a gadget descriptor could miss host sessions opened later. Physical host-side tests then passed exact `LWCT/1` Status, Listen, and Cancel; Listen produced `source: phone-usb` and Cancel returned idle. The board returned valid `LWRX/2` status and a real strict-Adreno reconstructed PNG: 4,469 PNG bytes with the correct signature plus 1,909 bytes of recorded optical/CPU/Adreno/STM32 evidence in a 6,398-byte frame. The fresh Android project builds, lints, and passes all seven unit tests, including a canonical Python-to-Java frame vector. Direct S25 enumeration, power, screen rendering, playback, and reconnect are not yet claimed. |
| Usefulness | Confirms that the QRB2210 can remain the complete reconstruction host while the Galaxy is a clean offline control/presentation surface, eliminating unstable LAN discovery and any receiver-side laptop from the final display |
| Friction and owner | Arduino documents UNO Q USB-C role switching and App Lab containers separately, but App Lab does not expose a first-class per-app gadget-device declaration or explain generated device cgroups. The node appeared mounted and group-readable while open still failed with `EPERM`, which is misleading. App CLI also does not automatically apply an adjacent Compose override. These are Arduino/App Lab packaging and documentation issues, not a Qualcomm CPU/GPU limitation. Direct phone power remains a hardware integration question. |
| Workaround | Keep the decoder and base OS unchanged; track a minimal Compose override containing only `/dev/ttyGS0`; have the hash-checking installer apply it after App Lab restart and fail unless the service can read/write the node; use a blocking reader thread for host sessions; persist decoded results until delivery; use a compliant OTG/PD powered hub if the S25 cannot sustain board power |
| Suggested improvement | App Lab should support a reviewed `devices` declaration in `app.yaml`, show effective cgroup/device permissions in Doctor output, preserve that declaration across lifecycle commands, and publish an official UNO Q-to-Android bidirectional CDC sample with power-role guidance and offline binary framing. Qualcomm/Arduino samples would also benefit from carrying per-stage heterogeneous-compute evidence through the mobile presentation layer. |

### DX-034 - The standalone receiver installs cleanly on the real Galaxy S25 Ultra

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-07; build the canonical Android Studio project, install it on the project S25 Ultra, and verify real-device startup/UI behavior before moving the phone cable to UNO Q |
| Environment | Snapdragon Windows 11 ARM64 build host; Android Studio with JDK 17; SDK/target 36; AGP 9.0.0; Gradle 9.1.0; Samsung Galaxy S25 Ultra `SM-S938U1`, Android 15/API 35, ARM64 |
| Tool/source | Repository `android/` project, Android Studio/Gradle, ADB, Android USB-host framework, and `usb-serial-for-android` 3.10.0 |
| Intended workflow | Rebuild and test the single-source Android project, install its APK, cold-start it on the real phone, and confirm that the offline receiver surface is ready for a matching UNO Q USB device |
| Actual result and evidence | `clean lintDebug testDebugUnitTest assembleDebug` passed with seven unit tests, zero lint errors, and nine non-blocking style/typography warnings. Debug APK version 1.0.0/code 2 installed successfully. The first cold launch completed in 228 ms. The app was the top resumed activity, rendered the complete monochrome receiver screen in both light and dark modes, showed the correct unattached-board state and disabled transport controls, exposed no Internet permission in its manifest, and produced no crash-buffer entry. Android reported `android.hardware.usb.host`. Direct UNO Q enumeration, permission, power, CDC data, media playback, and reconnect are not claimed yet. |
| Usefulness | Removes Android build, packaging, install, launch, layout, theme, and basic device-compatibility uncertainty before the cable is moved; the remaining risk is isolated to the physical UNO Q-to-phone connection and downstream protocol exercise |
| Friction and owner | Wired ADB occupies the phone's only USB-C port, while this phone had no active Wi-Fi address for wireless ADB. Automated observation therefore cannot continue when the cable is moved unless wireless debugging is prepared or a powered OTG/PD topology exposes a separate debug path. This is a mobile hardware/debug topology constraint rather than a Qualcomm compute limitation. |
| Workaround | Use Android Studio/ADB for one-time installation and UI checks, then test UNO Q directly with on-screen evidence; when available, enable trusted-network wireless debugging before moving the cable. Use a standards-compliant powered OTG/PD hub if UNO Q power is unstable. |
| Suggested improvement | Publish a maintained UNO Q-to-Android sample and test checklist covering USB roles, permission filters, CDC endpoint selection, phone power budgets, powered-hub topology, wireless-debug handoff, reconnect, and offline binary result delivery. |

### DX-035 - App Lab default state identifies the boot app but not full device readiness

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-07; determine whether the production receiver will start after power-on without a development PC |
| Environment | Receiver UNO Q `371371094`; Qualcomm QRB2210/Debian ARM64; Arduino App CLI 0.12.1; production `lightweave_receiver` App Lab application |
| Tool/source | Live `arduino-app-cli` state, systemd service configuration, container inspection, and the official Arduino UNO Q user manual's startup-app section |
| Intended workflow | Persist LightWeave Receiver as the board's boot application so the final display contains only the powered receiver UNO Q and Galaxy phone |
| Actual result and evidence | `arduino-app-cli properties get default` returned **LightWeave Receiver** at `/home/arduino/ArduinoApps/lightweave_receiver`; the app list marked it `running` and `default: true`. `arduino-app-cli.service` is enabled for `multi-user.target` with `Restart=always`. The application container itself has Docker restart policy `no`, so App Lab's persisted default/boot daemon—not Docker—is the correct startup owner. Arduino's manual states that the DEFAULT app runs automatically on boot. No reboot was needed for this read-only verification. |
| Usefulness | Confirms which Linux application App Lab launches after power-on; DX-036 exposed the failed direct-device grant and DX-037 resolves it through the boot-managed Router monitor |
| Friction and owner | Docker restart policy alone gives the misleading impression that the app will not return after boot, while DEFAULT/running state gives the opposite misleading impression that all required devices are usable. State is split across App Lab's default property, its systemd daemon, and generated container policy. This is an Arduino App Lab observability/documentation concern. |
| Workaround | Check `arduino-app-cli properties get default` for boot identity, then separately verify every required device with an actual open from the live container. After a reimage or manual app change, set `user:lightweave_receiver` as default once and verify the application list. |
| Suggested improvement | App CLI Doctor/status should print one explicit line combining default-app identity, boot-service health, current runtime state, and whether the app will launch after the next power cycle. |

### DX-036 - Default-app boot drops the custom CDC device grant

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-07; diagnose why the installed S25 app detected UNO Q and sent controls but displayed no receiver output |
| Environment | Galaxy S25 Ultra `SM-S938U1`, Android 15/API 35; `usb-serial-for-android` 3.10.0; receiver UNO Q `371371094`/`unoq2`, QRB2210 Debian ARM64, App CLI 0.12.1, Docker 26.1.5+dfsg1; Anker USB-C host hub |
| Tool/source | Android USB manager/logcat and retained LightWeave UI event log; live App CLI/container state; Docker inspect; direct `/dev/ttyGS0` open probe |
| Intended workflow | Power the default receiver independently, let S25 enumerate its composite gadget, send `LWCT/1` controls over CDC, and receive `LWRX/2` status/media without a laptop |
| Actual result and evidence | Android enumerated `UNO Q - unoq2` as `2341:0078` with ADB, CDC control, and CDC data interfaces. LightWeave reported `USB connected / receiver ready` and multiple exact 12-byte controls, including Listen. The serial reader remained open until physical detach. On UNO Q, LightWeave Receiver was running/default, but Docker inspect showed an empty device allow-list. The node was visible via the base `/dev` mount, yet `dd if=/dev/ttyGS0 ... count=0` failed `Operation not permitted`. The adjacent `usb-compose.override.yaml` correctly declares `/dev/ttyGS0`, but App Lab's default boot did not apply it. No controls reached the receiver worker and no phone outbox response was created. |
| Usefulness | Proves the Android USB identity, host role, CDC probing, permission, serial open, and control-write path are functional, and isolates the failure to reproducible UNO Q container lifecycle policy rather than the phone app or optical decoder |
| Friction and owner | App Lab can persist an application as DEFAULT but does not persist or automatically merge its adjacent Compose override. The UI reports the app running even though a required device is cgroup-blocked. This is Arduino App Lab lifecycle/observability friction. |
| Workaround | Superseded by DX-037: do not recreate the service with an adjacent Compose override. Use the already boot-managed system serial service through Router `mon/read`/`mon/write`, so the App Lab container needs no direct gadget-device grant. |
| Suggested improvement | App Lab should support reviewed per-app device declarations in `app.yaml`, persist them through default boot/restart, and fail application health when a declared device exists but cannot be opened. |

### DX-037 - Arduino Router provides the boot-safe UNO Q phone transport

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-07; replace the failed direct gadget-node mapping with a supported boot-safe path from Galaxy controls to the QRB2210 receiver and decoded results back to the phone |
| Environment | Receiver UNO Q `371371094`/`unoq2`; Qualcomm QRB2210; Debian GNU/Linux 13 ARM64; Arduino App CLI 0.12.1; Python 3.13.14; Docker 26.1.5+dfsg1; Compose 2.26.1-4; RouterBridge 0.4.3; Windows USB CDC host used for the first physical round trip |
| Tool/source | Official open-source `arduino-app-cli` and `arduino-router` code; enabled `arduino-router.service` and `arduino-router-serial.service`; existing App Lab Router socket; MessagePack RPC `mon/connected`, `mon/read`, and `mon/write`; LightWeave `LWCT/1` and `LWRX/2` |
| Intended workflow | Keep App Lab's supported default-app lifecycle, avoid privileged container changes, consume phone controls nonblockingly, and return exact binary frames while leaving the optical receiver, decoder, STM32, and transmitter unchanged |
| Actual result and evidence | Official App CLI source confirms that its regenerated `.cache/app-compose-overrides.yaml` supports predefined Brick device classes and that startup regenerates it; the adjacent LightWeave override was outside that lifecycle. Official Router source registers `mon/connected`, nonblocking `mon/read`, and binary `mon/write`. Direct board inspection found the enabled system serial unit running root-owned `socat file:/dev/ttyGS0 ... tcp:127.0.0.1:7500`, while the App Lab container already had the Router socket. The running receiver returned `True` from `mon/connected` and `bytes` from `mon/read`. After migration, its Docker device list remained empty by design, yet a physical exact 12-byte Status control was logged and produced a valid 192-byte `LWRX/2` idle response with CRC32 `8a1a53d2`. Fifteen focused protocol/transport/outbox tests passed. With receiver UNO Q connected directly through the powered hub, the S25 then displayed idle, passed Listen and Cancel state changes, and rendered the exact optical text `S25 PROOF`. The transmitter sent 9 payload bytes in a 21-byte `LWF1` frame (170 bits / 4.25 seconds); sender and receiver agreed on CRC `f8f8` and SHA-256 `a0972d2c422917f06b6a7d9045535cc0356f2111cb088da489d984b7f76ec1d4`, and the phone showed valid CRC/stop-bit plus QRB2210/STM32 hardware evidence. No receiver-side laptop was present. |
| Usefulness | Reuses the board's maintained boot service as the narrow USB data plane, removes the unsupported Compose grant and cgroup dependency, and preserves the no-laptop receiver architecture without changing Qualcomm inference or optical behavior |
| Friction and owner | The useful monitor API is discoverable in Router source but not presented as an App Lab phone/CDC integration pattern. `mon/connected` describes the system serial client, not necessarily that the Android application is actively consuming bytes. The first installer health probe also exposed ADB shell quote stripping, requiring a base64/stdin probe. These are Arduino documentation/API semantics and host-tooling friction, not Qualcomm compute limitations. |
| Workaround | Inject a shared Router monitor transport into the receiver control reader and durable outbox, poll `mon/read`, require exact byte counts from `mon/write`, fail closed on unavailable/malformed RPC results, delete the obsolete Compose override, and verify the enabled services plus live monitor connection during installation. Preserve `LWRX/2` CRC and outbox behavior above this transport. |
| Suggested improvement | Document the Router monitor API as the supported UNO Q gadget-serial path for App Lab, expose host-open/DTR state separately from the system `socat` connection, provide an official binary Android USB sample, and add an App CLI Doctor check that correlates gadget, serial service, Router monitor, and application readiness. |

### DX-038 - Three-lane optical sketches need observable per-lane calibration

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-07; preserve the proven LightWeave software stack while reducing optical elapsed time with three independent STM32 lanes |
| Environment | Transmitter UNO Q `123900964`/UNOQ-1 and receiver UNO Q `371371094`/unoq2; Qualcomm QRB2210 Debian ARM64 hosts plus STM32U585 MCUs; Arduino App CLI 0.12.1; Arduino Zephyr 0.90.0; RouterBridge 0.4.3; Windows 11 x64 host over USB/ADB |
| Tool/source | Separate App Lab clones, `arduino-app-cli`, OpenOCD, RouterBridge RPC, live STM32 ADC diagnostics, and unchanged LightWeave `LWF1` framing |
| Intended workflow | Change only the cloned STM32 sketches: buffer the complete payload, stripe consecutive `LWF1` frame bytes over D5/D7/D9, reassemble from A0/A2/A5, and expose the standard Bridge contract so Python, codecs, reconstruction, UI, and phone transport remain unchanged |
| Actual result and evidence | Both clones compiled and flashed. The final diagnostic transmitter used 90,440 bytes flash and 36,698 bytes RAM; the receiver used 96,288 bytes flash and 36,334 bytes RAM. Initial reception produced zero bytes because A0 was below threshold and then showed optical crosstalk from D7/D9. New sketch-only test methods exposed raw lane ADC values and laser masks. After physical isolation, D5/D7/D9 produced exact high masks 1/2/4, all three produced mask 7, and a 60-second D5/A0 hold recorded 60/60 values above threshold 800 (minimum 1,015, maximum 1,023, mean 1,022.7). A real six-byte text payload `3-LANE` was reconstructed exactly as hex `332D4C414E45`; receiver/computed CRC values both equaled 50,021, the stop bit was valid, and no error was reported. Its 18-byte frame used six parallel byte slots and 1.25 seconds versus 3.65 seconds for the same frame on one lane. Installer hash gates confirmed the standard single-lane applications were unchanged. |
| Usefulness | App Lab and RouterBridge make it practical to keep Qualcomm Linux orchestration and reconstruction untouched while iterating independently on the STM32 physical layer. Live per-lane ADC and mask evidence turned an apparent protocol failure into a measurable alignment/isolation issue. QRB2210, GPU, and NPU do not perform the wire timing; the STM32 owns framing, GPIO, sampling, and reassembly. |
| Friction and owner | App Lab allows one running app per board, each sketch restart recompiles/provisions for about 97 seconds, and the default tools expose no per-lane ADC health. A compile-time threshold alone obscures whether failure is weak alignment, crosstalk, lane swapping, or protocol corruption. These are Arduino App Lab/embedded observability and physical-demo setup concerns, not Qualcomm inference limitations. |
| Workaround | Keep the production single-lane apps installed, use separate parallel clones, provide explicit laser-mask and sensor-reading Bridge diagnostics, require isolated masks 1/2/4 before transmission, retain threshold 800 and CRC rejection, and run a short exact text frame before attempting media. |
| Suggested improvement | App Lab should provide a low-latency pin/ADC diagnostics panel, retain compile caches across sketch-only clone updates, display the active/default app clearly, and offer a standard multi-channel timing/capture example with synchronized GPIO output and ADC threshold visualization. |

### DX-039 - The unchanged Galaxy presentation path accepts the parallel clone

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-07; verify that changing only the two STM32 optical sketches still delivers decoded data to the standalone Galaxy S25 application |
| Environment | Transmitter UNO Q `123900964` over Windows USB/ADB; receiver UNO Q `371371094` powered directly by the Galaxy S25 Ultra host path; Qualcomm QRB2210 Debian ARM64 plus STM32U585; LightWeave Mobile 1.0.0/code 2 on Android 15; boot-managed Arduino Router monitor |
| Tool/source | `arduino-app-cli properties set default`, parallel App Lab receiver clone, unchanged receiver Python/Router `mon/read`/`mon/write` transport, unchanged `LWCT/1`/`LWRX/2`, and owner-observed LightWeave Mobile UI |
| Intended workflow | Power-cycle the receiver during the laptop-to-phone cable move, let the parallel clone boot automatically, arm it from the existing phone Listen control, reconstruct/route text through the existing Linux service, and display the result without Android or codec changes |
| Actual result and evidence | The receiver default was changed reversibly from `/home/arduino/ArduinoApps/lightweave_receiver` to `/home/arduino/ArduinoApps/lightweave_parallel_receiver`; App CLI reported the parallel clone running and `default: true`. With the receiver connected directly to the S25, the phone reported listening. The transmitter buffered and launched exact ASCII `PHONE 3-LANE`: 12 payload bytes, 24 total LWF1 bytes, eight parallel byte slots, and 1.65 seconds. The owner then confirmed the exact text appeared in LightWeave Mobile. This builds on direct Bridge evidence for matching CRC and stop-bit behavior from the immediately preceding `3-LANE`/`HELLO` tests; no Android, Python, model, GPU, or NPU source changed for the phone test. |
| Usefulness | Confirms the Qualcomm Linux host and boot-safe Router transport remain stable abstractions above a different STM32 physical implementation. The QRB2210 continues orchestration/persistence while the phone remains presentation-only; the optical speedup does not require a second mobile build. |
| Friction and owner | App Lab's one-active-app rule and separate default-app property mean a running parallel clone can silently revert to the standard clone after a cable-induced reboot unless default identity is checked explicitly. This is Arduino lifecycle observability friction rather than a Qualcomm compute limitation. |
| Workaround | Set and verify the intended clone as default before moving the receiver cable, keep the standard app installed, and restore it with `arduino-app-cli properties set default /home/arduino/ArduinoApps/lightweave_receiver` when returning to the single-lane setup. |
| Suggested improvement | App Lab should show RUNNING and BOOT DEFAULT as distinct persistent badges, offer an atomic “start and make default” action with rollback, and surface the active sketch pin contract so multi-app hardware configurations are harder to confuse. |

### DX-040 - One Windows executable can select the active App Lab transmitter clone

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-07; run the three-lane transmitter from the same Windows dashboard executable used by the standard app |
| Environment | Snapdragon X Elite Windows 11 x64 host; LightWeave x64 Python environment; ADB platform-tools; transmitter UNO Q `123900964` with **LightWeave Parallel Transmitter** running |
| Tool/source | Existing `lightweave.exe dashboard`, `UnoQAdbSink`, Arduino App CLI JSON status, tracked standard/parallel manifest markers, and live USB/ADB probe |
| Intended workflow | Avoid a second Windows product while safely targeting either installed transmitter clone by name/path/manifest |
| Actual result and evidence | A constrained `LIGHTWEAVE_UNO_Q_TRANSMITTER_APP` selector accepts only `standard` or `parallel` and maps the parallel value to `/home/arduino/ArduinoApps/lightweave_parallel_transmitter`, display name **LightWeave Parallel Transmitter**, and its dedicated manifest. With serial `123900964`, the real dashboard status API returned HTTP 200, connected/ready, app status running, and `app_variant: parallel`. The owner then selected parallel as the laptop default; `standard` is the explicit rollback. Focused dashboard/transmitter tests passed. The App Lab Python worker remains unchanged, so its reported busy duration is intentionally conservative. |
| Usefulness | Preserves one Windows installation and dashboard for text/image/audio generation while keeping clone selection explicit and preventing arbitrary remote paths. This is host orchestration only; it does not change QNN, models, payloads, or STM32 framing. |
| Friction and owner | App Lab app identity is split among filesystem path, display name, manifest, running state, and default state. A hard-coded host adapter works for one clone but becomes invisible when an equally valid parallel clone is active. This is Arduino lifecycle/discovery friction. |
| Workaround | Map a small allow-list of known tracked app identities, verify its manifest plus running display name through App CLI, retain serial override for multiple boards, and expose the selected variant in status evidence. |
| Suggested improvement | App CLI should expose a stable machine-readable application capability/role identifier independent of display name and path, allowing host tools to discover “LightWeave transmitter” implementations without duplicating identity rules. |

## Change log

| Date | Change |
| --- | --- |
| 2026-08-05 | Created the resource register and initial planning observations. |
| 2026-08-05 | Replaced planning assumptions with exercised QUAD 0.2.0, ORT/QNN 1.24.4/2.4.0, full image HTP, precision tuning, dual-architecture setup, EnCodec hybrid, failure evidence, unavailable AI Hub/QAIRT paths, and actionable improvement notes. |
| 2026-08-05 | Recorded the automation boundary: portable lint/unit checks run in CI, while QNN assignment and profiling remain native Snapdragon acceptance gates. |
| 2026-08-05 | Added the final dual-Python recovery observation and the successful post-repair QNN/offline validation evidence. |
| 2026-08-05 | Revalidated strict QNN image/audio paths through the installed CLI and rendered dashboard, with zero CPU profile nodes and no browser console errors. |
| 2026-08-05 | Published the complete public engineering log alongside a green hardware-independent repository CI run; native Snapdragon QNN evidence remains an explicit local gate. |
| 2026-08-05 | Evaluated the documented UNO Q/S25 connectivity pieces for a future receiver display path, recommended an offline browser gateway, and recorded that no device integration or decoder compatibility has been exercised. |
| 2026-08-05 | Updated the future phone gateway evaluation for the owner's direct USB-C selection: S25 host, UNO Q device, Android USB API, with gadget enumeration, power, and decoder support still unverified. |
| 2026-08-05 | Directly observed the UNO Q's default Windows USB composite, ADB, and serial interfaces; selected Android CDC enumeration as the next incremental test. |
| 2026-08-05 | Added the raw 64 by 64 CompressAI decoder evidence: 71.75 dB minimum CPU QDQ parity, 59.92 dB minimum NPU/CPU parity, complete HTP assignment, zero CPU nodes, and the separate-static-artifact/session-startup tradeoff. |
| 2026-08-05 | Published the raw transmitter/receiver milestone and confirmed its hardware-independent Windows CI run passed; strict Snapdragon QNN evidence remains a reproducible local gate. |
| 2026-08-05 | Built the hardware-independent Android text/image receiver with pinned CDC, framed CRC-checked payloads, no network permission, local demos, 9 passing tests, and zero lint errors; recorded that UNO Q decoding and S25 hardware behavior remain unverified. |
| 2026-08-05 | Added and profiled the 128 by 128 raw decoder: 66.74 dB minimum CPU QDQ parity, at least 51.29 dB NPU/CPU parity, complete QNN HTP assignment, zero CPU nodes, and explicit multi-shape artifact/startup guidance. |
| 2026-08-05 | Published the multi-size dashboard and confirmed GitHub Actions run `31057418505` passed its portable Windows lint/unit gate; Snapdragon QNN proof remains the separately reproduced native-device gate recorded in DX-015. |
| 2026-08-05 | Evaluated Galaxy S25 HTP and UNO Q QRB2210 inference options, found Arduino's QNN/FastRPC App Lab container path while keeping UNO Q accelerator assignment unproven, and recorded the single-repository/multiple-installer approach. |
| 2026-08-05 | Replaced UNO Q inference assumptions with direct evidence: no QNN/FastRPC on the exercised image, exact native rANS parity, strict full-graph Adreno Vulkan execution for all presets, and accelerator/CPU parity above 35 dB. |
| 2026-08-05 | Recorded native Debian delivery, the App Lab generic container's missing Vulkan user-space stack and target-local workaround, plus the 27-minute first build, cached rebuild behavior, and board-clock setup friction. |
| 2026-08-05 | Browser-tested the live App Lab receiver: a 216-byte payload reconstructed to 128 by 128 with about 524 ms accelerator time, exposed 16-layer/no-fallback evidence and PNG download, and showed the preset-budget error without browser console failures. |
| 2026-08-05 | Added repeated-run evidence: diagnosed an FP16-arithmetic quality-run MSM GPU hang, introduced explicit teardown and cross-process serialization with FP32 arithmetic/FP16 storage, and passed five runs of every profile while recording p95, RSS, and disk measurements. |
| 2026-08-05 | Packaged the final runner with an SPDX SBOM and third-party notice, rebuilt the portable entropy reference with exact latent equality, and reinstalled the hash-verified 24-file App Lab bundle with healthy strict-Adreno status. |
| 2026-08-05 | Implemented and exercised the UNO Q EnCodec receiver: split 2 failed numerically, split 5 passed strict 39-layer Adreno execution and 52.07 dB or better parity, native indices/codebooks matched exactly, the limit became five seconds, and App Lab playback/download/error plus offline-network tests passed. |
| 2026-08-06 | Inspected the stopped `image_transmitter_bkp` App Lab application on the connected UNO Q, documented its fixed monochrome producer, binary-safe per-byte RouterBridge/STM32 boundary, unframed 40-bit/s laser loop, and the host API/variable-length changes needed to reuse it for LightWeave. |
| 2026-08-06 | Cloned and exercised the tracked `lightweave_transmitter` App Lab app, recorded its USB/ADB atomic inbox and exact variable-length image/audio transfers, preserved backup hashes and waveform timing, and documented App Lab lifecycle, Unicode output, multi-device, polling, and completion-evidence friction. |
| 2026-08-06 | Published the dashboard-to-App-Lab transmitter source, installer, tests, setup guidance, and board evidence to `origin/main` as commit `028f9d9`. |
| 2026-08-06 | Added the owner's direct visual observation of laser activity from a dashboard send while keeping optical byte correctness and reception explicitly unverified. |
| 2026-08-06 | Recorded that the first two-board discovery attempt exposed only transmitter `123900964`/COM3, leaving receiver inspection blocked on USB data enumeration while preserving the running app. |
| 2026-08-06 | Resolved independent enumeration of both UNO Q boards and documented that `image_receiver` matches the transmitter waveform but requires a variable-length binary clone, while the installed text receiver is protocol-incompatible. |
| 2026-08-06 | Installed a separate variable-length App Lab byte receiver and proved the physical two-board link with exact `00 FF AA 55`, matching SHA-256, valid stop bit, preserved source hashes, and explicit App Lab build/lifecycle friction. |
| 2026-08-06 | Composed the proven optical receiver with the installed strict-Adreno decoder, reused the prior native runtime, and passed automated plus browser-armed 80-byte physical image reconstruction with exact hashes, valid stop bits, 16 Vulkan layers, disabled fallback, PNG download, and zero browser errors. |
| 2026-08-06 | Published the complete production optical image receiver and its reproducible App Lab installer/acceptance workflow as commit `506eee9` on `origin/main`. |
| 2026-08-06 | Implemented and exercised common `LWF1` image/audio framing, diagnosed long-frame clock drift through preserved CRC evidence, calibrated the receiver board pair, passed all image profiles plus one-second hybrid audio, retained exact `raw-v0`, and recorded the owner's choice to skip further long transfers. |
| 2026-08-06 | Published the complete dynamic optical media milestone, including tracked App Lab source and reproducible setup, as commit `c8600c7` on `origin/main`. |
| 2026-08-06 | Separated a healthy App Lab port-7000 receiver from intermittent mobile LAN discovery and documented direct-IP, same-subnet, DHCP, and trusted-network guidance. |
| 2026-08-06 | Inspected the stopped legacy text apps, retained their protocol as compatibility reference, and selected a no-AI ASCII profile plus matched production App Lab identities. |
| 2026-08-06 | Built and installed the paired production App Lab apps, preserved original/rollback hashes, and proved exact 16-byte no-AI text reception with automatic LWF1 routing, valid CRC/stop bit, persisted TXT output, and browser-clean local UIs. |
| 2026-08-06 | Published the unified text/image/audio App Lab integration as commit `62c540d`; GitHub Actions run `31147024146` passed the portable Windows lint/unit gate while board evidence remains recorded separately. |
| 2026-08-06 | Added scoped heterogeneous-compute telemetry across Windows QNN, UNO Q Adreno/CPU, RouterBridge, and STM32 optical work while explicitly rejecting unsupported FLOP/power claims. |
| 2026-08-06 | Recorded publication of the presentation-telemetry milestone as commit `98481a8` after live Windows/UNO Q UI checks, physical text evidence, and 124 passing portable tests. |
| 2026-08-06 | Replaced the old Android prototype with the no-laptop LightWeave Mobile text/image/audio receiver, exposed the UNO Q gadget endpoint narrowly through App Lab, passed 137 Python tests plus Android build/lint/7 tests, and recorded exact duplex control/status plus reconstructed-PNG USB evidence while keeping direct S25 behavior as the final gate. |
| 2026-08-06 | Published the standalone Galaxy receiver source, board bridge, tests, setup guidance, and evidence as commit `81c8888`, with the pre-rebuild receiver baseline preserved by a pushed annotated tag. |
| 2026-08-07 | Rebuilt and installed the canonical app on a real S25 Ultra, verified cold startup, light/dark rendering, USB-host capability, disconnected control state, manifest network boundary, and a clean crash buffer; retained direct UNO Q cable exchange as the remaining hardware gate. |
| 2026-08-07 | Verified that the live production receiver is the persisted App Lab DEFAULT app and that the boot daemon is enabled; documented the one-time verification/recovery command and clarified that Docker restart policy is not the startup authority. |
| 2026-08-07 | Directly proved S25 USB-host enumeration and LightWeave CDC/control writes, then isolated the missing response to App Lab default boot dropping the custom `/dev/ttyGS0` device grant; recorded the exact empty allow-list and `EPERM` evidence. |
| 2026-08-07 | Replaced direct container gadget access with the boot-managed Arduino Router monitor, removed the unsupported Compose override, passed direct S25 Status/Listen/Cancel, and rendered an exact nine-byte optical text result with matching CRC/hash/stop-bit evidence and no receiver laptop. |
| 2026-08-07 | Exercised separate three-lane STM32 sketch clones, used live per-lane ADC/mask diagnostics to resolve alignment and crosstalk, passed a 60-second threshold hold plus isolated masks 1/2/4/7, and received exact `3-LANE` LWF1 bytes with matching CRC and valid stop bit in 1.25 seconds while preserving standard app hashes. |
| 2026-08-07 | Published the three-lane App Lab sketches, hash-preserving clone installers, exact-text verifier, tests, setup instructions, and evidence as commit `2e50e0a`. |
| 2026-08-07 | Made the parallel receiver the reversible boot default, moved it to the direct S25 host path, and confirmed owner-observed `PHONE 3-LANE` display through the unchanged Android/Router service after a 1.65-second optical send. |
| 2026-08-07 | Added and live-tested the existing Windows executable's constrained standard/parallel App Lab selector; the real dashboard status API identified the running parallel transmitter as ready without changing its Python worker or media pipeline. |
| 2026-08-07 | Changed the dashboard's default App Lab transmitter identity to the three-lane parallel clone, restarted its existing default App Lab service, and verified ready/running status without an environment selector while preserving the original through explicit `standard`. |
