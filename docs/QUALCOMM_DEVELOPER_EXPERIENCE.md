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
| [Arduino UNO Q documentation](https://docs.arduino.cc/hardware/uno-q) | Active hardware documentation | QRB2210 receiver, Debian/App Lab deployment, and direct USB phone interface | Board receiver exercised; phone path pending |
| [ncnn](https://github.com/Tencent/ncnn) Vulkan runtime | Active third-party tooling | Complete image synthesis and EnCodec suffix execution on UNO Q Adreno 702 | All image graphs and the selected 39-layer audio suffix exercised with strict no-fallback |
| [Meta EnCodec](https://github.com/facebookresearch/encodec) | Model/preparation dependency | 24 kHz raw audio codebooks and decoder conversion | Native UNO Q conversion validated; upstream Python runtime is not installed on board |
| [Android USB host documentation](https://developer.android.com/develop/connectivity/usb/host) | Platform documentation | Galaxy S25 USB enumeration, permission, and endpoint workflow | Used for Android receiver design; phone path not exercised |
| [usb-serial-for-android](https://github.com/mik3y/usb-serial-for-android) 3.10.0 | Third-party Android library | CDC/ACM transport for decoded UNO Q results | Integrated and built; real UNO Q/S25 match not exercised |
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
