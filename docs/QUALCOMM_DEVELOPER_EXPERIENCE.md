# Qualcomm Developer Experience Log

This public engineering log records how Qualcomm hardware, developer tools, runtimes, documentation, samples, and workflows help or hinder LightWeave. It is evidence-oriented: documentation claims and direct observations are kept separate, failures are recorded as useful results, and credentials or confidential material are never included.

## Entry template

| Field | Required content |
| --- | --- |
| Date and ID | Stable observation ID and date |
| Objective | What LightWeave work was attempted |
| Environment | Device, OS, process architecture, and relevant versions |
| Tool/source | Product, package, SDK, sample, or documentation |
| Intended workflow | What the resource was expected to enable |
| Actual result and evidence | What happened and how it was verified |
| Usefulness | Concrete value to the project |
| Friction | Missing, confusing, broken, or inefficient behavior |
| Workaround | Safe path used or proposed |
| Suggested improvement | Actionable Qualcomm developer-experience feedback |
| Classification | Qualcomm-controlled, third-party, mixed, or unverified |

## Resource register

| Resource | Classification | LightWeave use | Current status |
| --- | --- | --- | --- |
| [Qualcomm Developer](https://www.qualcomm.com/developer) | Active tooling gateway | Discover current SDKs, Windows on Snapdragon guidance, samples, and support | Available |
| [Windows on Snapdragon AI development](https://docs.qualcomm.com/bundle/publicresource/topics/80-62010-1/ai-app-development.html?product=1601111740057789) | Active documentation | Native ARM64 setup and Snapdragon application guidance | Available; JavaScript-heavy |
| Supplied external QUAD client | Active development infrastructure | Hardware detection, conversion, profiling, orchestration, and generated integration guidance | Checkout available; local virtual environment currently broken |
| [Qualcomm AI Hub](https://aihub.qualcomm.com/get-started) | Active model workflow | Conversion, quantization, hosted-device validation, profiling, and artifact preparation | Account/token required; runtime must not depend on it |
| [QAIRT Visualizer](https://docs.qualcomm.com/bundle/publicresource/topics/80-87189-1/overview.html?product=1601111740009302) | Active analysis tool | Inspect converted graph, operators, partitioning, quantization, memory, and performance | Not yet installed or exercised locally |
| [ONNX Runtime QNN plugin](https://github.com/microsoft/onnxruntime-qnn) | Active runtime | Strict Hexagon NPU inference from native ARM64 Python | Environment not yet installed |
| [Whisper + AI Hub sample](https://github.com/thatrandomfrenchdude/simple-whisper-transcription) | Implementation reference | Model asset layout, offline/standalone split, QNN session patterns, and Windows build lessons | Reviewed; older provider API must be updated before reuse |
| [HRNet pose sample](https://github.com/quic/Pose-Detection-with-HRPoseNet) | Implementation reference | Model manifests, Windows on Snapdragon setup, CPU/NPU selection, tests | Reviewed |
| [Local Agent](https://github.com/thatrandomfrenchdude/local-agent) | Reference only | Modular CLI/config/test conventions | Not a runtime dependency |
| [AnythingLLM NPU chatbot](https://github.com/thatrandomfrenchdude/simple-npu-chatbot) | Reference only | ARM64-vs-x64 troubleshooting and local-NPU demo patterns | Not a runtime dependency |
| Scaler Chatbot | Unavailable reference | Potential additional local-chat sample | No unambiguous public link was supplied |
| [Awesome Qualcomm Developer](https://qualcomm.github.io/awesome-qualcomm-developer/) | Discovery reference | Find comparable open-source Qualcomm projects and submission conventions | Available; listed projects require independent review |
| Provided `qualcomm/edge-ai-labs-arduino` RPC link | Later hardware reference | Future PC/UNO transport adapter | Link currently returns 404 |
| [Arduino MessagePack RPC router](https://github.com/arduino/arduino-router) | Later hardware reference | Maintained UNO Q Linux/MCU RPC alternative | Available; deferred with the hardware layer |

## Observation log

### DX-001 — QUAD maps the intended Qualcomm workflow clearly

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; understand where QUAD fits in LightWeave |
| Environment | Supplied local QUAD checkout; runtime not invoked |
| Intended workflow | `hardware_detect -> convert_model -> profile_workload -> orchestrate_workload -> generate_code`, with AI Hub model selection as an additional path |
| Actual result and evidence | The checkout documentation and client source expose these operations and distinguish hosted conversion/profiling from local application work |
| Usefulness | Gives LightWeave a repeatable sequence for proving hardware, preparing the decoder, comparing backends, and generating reviewed starter integration code |
| Friction | “Orchestration” can be confused with multi-device application orchestration; hosted SDK capability can also be mistaken for local runtime readiness |
| Workaround | Keep QUAD, application orchestration, and the optical transport as separately named layers in project documentation |
| Suggested improvement | Surface a short generated report that separates server capabilities, client capabilities, and verified target-device capabilities |
| Classification | Qualcomm-controlled workflow; direct documentation inspection |

### DX-002 — The supplied QUAD environment is not portable after its base Python disappears

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; run QUAD diagnostics on the supplied Snapdragon PC |
| Environment | Native ARM64 Windows host; supplied checkout contains `.venv`, but no system Python is discoverable |
| Intended workflow | Invoke the existing virtual environment and run QUAD diagnostics without reinstalling the client |
| Actual result and evidence | The virtual-environment launcher references a Python interpreter that is no longer present, so both interpreter and `pip` invocation fail before QUAD starts |
| Usefulness | Confirms that environment repair must precede QUAD, QNN, or model work |
| Friction | A copied or retained virtual environment looks complete but is unusable because Windows venvs depend on the original base interpreter path |
| Workaround | Reinstall a supported interpreter and recreate the environment from the checkout’s declared dependencies; do not copy the checkout into LightWeave |
| Suggested improvement | Have the installer and `doctor` wrapper detect a missing base interpreter before invoking the venv and print a one-command repair path |
| Classification | Mixed Qualcomm workflow and standard Python venv behavior; directly observed |

### DX-003 — Current QNN plugin usage differs from common sample code

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; design a defensible no-fallback NPU session |
| Environment | Documentation review; runtime installation pending |
| Intended workflow | Load a QNN model on the Hexagon NPU and prove that the requested device executed it |
| Actual result and evidence | Current plugin documentation describes registering the provider library, enumerating EP devices, and selecting the NPU device; several older samples instantiate `QNNExecutionProvider` through a provider-name list |
| Usefulness | The current API exposes concrete device selection required for LightWeave evidence |
| Friction | Older samples can appear successful while using a different integration contract or allowing fallback |
| Workaround | Centralize session construction, disable CPU fallback, require an NPU device, and capture profiling/provider evidence |
| Suggested improvement | Add a prominent migration table to all Qualcomm sample READMEs and fail loudly when old provider-list examples are used with the plugin distribution |
| Classification | Qualcomm/Microsoft runtime integration; documentation and sample comparison |

### DX-004 — Windows on Snapdragon currently needs two Python architectures for this codec

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; reconcile CompressAI/PyTorch with native QNN execution |
| Environment | Snapdragon Windows ARM64; package availability research |
| Intended workflow | Encode, entropy-decode, and reconstruct in one native ARM64 Python environment |
| Actual result and evidence | QNN NPU execution requires native ARM64 Python, while the required PyTorch/CompressAI Windows workflow does not have a dependable matching native ARM64 wheel path |
| Usefulness | Native ARM64 QNN remains available for the compute-heavy synthesis transform |
| Friction | Developers must manage an emulated x64 codec environment and a native ARM64 inference environment on one machine |
| Workaround | Use a neutral tensor handoff and provide setup scripts plus explicit architecture diagnostics |
| Suggested improvement | Publish a supported end-to-end Python matrix and native Windows ARM64 wheels for common model-preparation dependencies |
| Classification | Mixed Qualcomm platform and third-party packaging limitation |

### DX-005 — QNN constraints improve the model contract but require early feasibility proof

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; assess CompressAI and EnCodec decoder feasibility |
| Environment | ONNX Runtime QNN and model-architecture documentation review |
| Intended workflow | Export one decoder graph per media type and run it entirely on HTP |
| Actual result and evidence | The selected QNN path requires fixed shapes and quantized deployment for HTP; the image synthesis graph is convolutional, while EnCodec includes recurrent layers not exposed by the selected ONNX Runtime QNN operator path |
| Usefulness | Forces stable profiles and makes image `g_s` the lower-risk first milestone |
| Friction | Dynamic-axis examples and whole-decoder audio claims are incompatible with this route |
| Workaround | Use fixed image and one-second audio profiles; require full image NPU assignment and use the approved hybrid audio split |
| Suggested improvement | Provide an operator-compatibility preflight that accepts ONNX and reports supported partitions before developers invest in application integration |
| Classification | Qualcomm/Microsoft runtime constraint plus third-party model architecture |

### DX-006 — AI Hub is valuable during preparation but must not leak into the offline runtime

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; place AI Hub in an air-gapped project workflow |
| Environment | AI Hub public documentation review; account use pending |
| Intended workflow | Convert, quantize, validate, and profile a custom decoder on hosted Qualcomm devices |
| Actual result and evidence | AI Hub Workbench supports custom-model conversion, quantization, inference, and profiling, but requires an account and API token |
| Usefulness | Reduces local SDK burden and can provide target-device evidence before deployment |
| Friction | Authentication and hosted processing can be mistaken for a runtime dependency or violate data-handling expectations if inputs are not chosen carefully |
| Workaround | Use only public/non-confidential calibration inputs; cache verified artifacts for offline use; keep credentials outside Git |
| Suggested improvement | Generate a downloadable offline-runtime manifest containing tool versions, target, hashes, quantization settings, and minimal integration code |
| Classification | Qualcomm-controlled service; documentation review |

### DX-007 — The provided Arduino RPC resource is stale

| Field | Observation |
| --- | --- |
| Date and objective | 2026-08-05; classify the supplied later-phase Arduino communication resource |
| Environment | Public link validation |
| Intended workflow | Reuse a Qualcomm/Arduino RPC example when connecting the future byte stream to UNO Q |
| Actual result and evidence | The provided repository/path returns 404; Arduino’s maintained router documents a MessagePack RPC bridge with serial routing |
| Usefulness | A maintained later-phase alternative exists |
| Friction | Hackathon resource lists can become stale without a redirect or archive |
| Workaround | Defer hardware work and revalidate the maintained Arduino router when that milestone begins |
| Suggested improvement | Run automated link checks against published resource lists and retain redirects for renamed sample repositories |
| Classification | Qualcomm resource-list maintenance; directly observed |

## Change log

| Date | Change |
| --- | --- |
| 2026-08-05 | Created the public resource register and seeded evidence-based observations for QUAD, QNN, Windows ARM64 Python, model constraints, AI Hub, and Arduino RPC resources. |
