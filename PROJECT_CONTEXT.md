# LightWeave Project Context

> Living source of truth for project intent, decisions, architecture, progress,
> evidence, risks, and open questions.

| Field | Current value |
| --- | --- |
| Project | LightWeave |
| Phase | Standalone S25 + UNO Q optical text receive passes; publication and optional direct image/audio proof remain |
| Primary milestone | Publish the boot-safe Router transport and direct S25 optical acceptance evidence |
| Secondary milestone | Submission hardening and presentation evidence |
| Last updated | 2026-08-07 |
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
- A header-free raw codec-file mode that preserves `.lwv`; `LWF1` framing is
  generated only for the production laser wire.
- Three raw image profiles: 64 by 64 at 128 bytes, 128 by 128 at 768 bytes,
  and 256 by 256 at 2,048 bytes, with the balanced profile as the UI default.
- Raw `A1-E15-S<n>` audio with exact 188-byte independently packed chunks and
  an out-of-band exact sample count.
- Separate `/transmit`, `/receive`, and `/loopback` dashboard pages plus
  `RawByteSink`/`RawByteSource` adapter contracts for future hardware.
- A fresh native **LightWeave Mobile** Android receiver for direct UNO Q USB
  control plus decoded text, PNG, WAV, and hardware-evidence display, with no
  Internet permission and no laptop required at runtime.
- A native UNO Q receiver for all three raw image presets plus up to five
  seconds of header-free EnCodec audio. Images run fully on Adreno; audio uses
  a measured CPU/Adreno split with no fallback inside its Vulkan suffix.
- A USB/ADB `RawByteSink` that hands generated image and audio payloads to a
  tracked `lightweave_transmitter` App Lab application, which buffers the exact
  variable byte count on the STM32 and launches the existing laser waveform.
- A 12-byte `LWF1` optical wrapper that carries version, media/profile, payload
  length, exact audio sample count, and CRC-16 without changing `payload.bin`.
- Plain printable-ASCII text as `T1-ASCII-B100`: no AI model, at most 100 raw
  bytes, automatically routed through the same `LWF1` Send/Listen workflow.
- A separate `lightweave_byte_receiver` diagnostic that accepts an out-of-band
  expected length, captures the matching raw optical bytes, and reports binary,
  SHA-256, length, and stop-bit evidence without invoking media reconstruction.
- The production `lightweave_receiver` App Lab application with
  one-shot Listen/Cancel controls. It validates `LWF1`, automatically routes all
  three image presets, one- to five-second audio, and exact ASCII text, then
  reconstructs through the installed strict image-Adreno or truthful
  CPU/Adreno audio path. The former `lightweave_optical_receiver` is retained
  stopped as rollback.
- Persistent system-aware light/dark controls across the Windows dashboard and
  production UNO Q receiver WebUI.
- Per-operation presentation evidence: Windows process CPU time/RSS and QNN
  provider events; UNO Q CPU/Adreno stage timings and audited layers; and STM32
  framing, CRC, payload, optical-bit, GPIO-write, and RouterBridge counts.

The following remain out of scope:

- Analog/photodiode redesign, clock recovery, serial framing, retransmission,
  faster modulation, and changes to the existing laser waveform/timing.
- Galaxy-hosted neural inference, WebSockets, and Cloud AI in the runtime path.
- UNO Q media encoding and MCU performance optimization beyond the approved
  variable-length framed receive/transmit loop.
- Medical, regulatory, safety, or absolute-security claims.
- A packaged EXE/MSIX.

### UNO Q-to-Android receiver extension

The owner selected a final receiver/display topology with no laptop: Galaxy
S25 Ultra as USB host and presentation/control surface, plus receiver UNO Q as
USB device, optical endpoint, validator, and reconstruction host. The phone
does not run an AI model. It sends Listen/Cancel/Status controls and displays
decoded text, exact PNG, playable WAV, and the same frame/hardware evidence as
the receiver WebUI.

The old Android prototype was explicitly retired and replaced from scratch by
the `com.lightweave.mobile` **LightWeave Mobile** project. It matches observed
UNO Q USB identity `2341:0078`, requests USB-host permission, uses
`usb-serial-for-android` 3.10.0 for bidirectional CDC/ACM, and has no Internet
or broad-storage permission. Phone-to-board `LWCT/1` uses fixed 12-byte
CRC32-protected Listen, Cancel, and Status commands. Board-to-phone `LWRX/2`
uses a 20-byte header, canonical JSON evidence, decoded TXT/PNG/WAV or status,
and CRC32 over the prefix plus metadata and media. This downstream framing
never travels over the laser and does not alter `payload.bin` or `LWF1`.

The receiver App Lab service receives controls and persists every decoded
result in `data/phone-outbox` until USB delivery succeeds. An initial direct
`/dev/ttyGS0` implementation required a custom Compose device grant, but App
Lab's default-app boot path discarded that unsupported adjacent override. The
production implementation now reuses UNO Q's enabled, boot-managed
`arduino-router-serial.service`: its root-owned `socat` process owns the gadget
node, while the receiver uses the existing Router socket and official
`mon/read`/`mon/write` methods. The App Lab container requires no gadget-device
permission and its effective Docker device list can remain empty. The checked
installer removes the obsolete override and verifies both system services plus
the live Router monitor connection. The base OS, receiver decode path, STM32
sketch, and transmitter remain unchanged. Direct board inspection reports
**LightWeave Receiver** as both `running` and the persisted App Lab `default`.
A receiver-side PC is not part of the intended final runtime; adequate power
and the phone USB data link are still required.

The UNO Q reconstruction boundary is now verified independently of the phone.
Its native ARM64 rANS decoder produces the same latent tensor as CompressAI for
all three raw image presets, and the complete `g_s` graph runs through ncnn
Vulkan on the Adreno 702 with unsupported layers and CPU fallback rejected.
The board-local CLI and App Lab WebUI both reconstruct real payloads. Direct
board evidence now also proves exact host-to-board `LWCT/1` Status and
Listen/Cancel, an `LWRX/2` status response, and delivery of an existing strict-
Adreno reconstructed 4,469-byte PNG with its 1,909-byte evidence metadata and
correct PNG signature. The fresh APK was then built, installed, and cold-started
on the real S25 Ultra. Its complete receiver UI rendered in both light and dark
modes with no crash, and Android reported USB-host capability. The remaining
S25 host logs subsequently proved direct enumeration of `UNO Q - unoq2` as
`2341:0078`, exposed its expected ADB plus CDC/ACM interfaces, and showed the
LightWeave app opening serial and sending exact 12-byte control frames. After
the Router migration, the physical USB interface accepted an exact 12-byte
Status control, the App Lab log recorded it, and the board returned a valid
192-byte `LWRX/2` idle response with a correct CRC. That round trip was measured
with Windows as the USB host. Direct board-to-S25 status/media presentation,
reconnect, sustained power, and media-specific rendering remained to be
exercised at that point. The follow-up direct run passed Status, Listen, Cancel,
and result display. The laptop-connected transmitter sent `S25 PROOF` as nine
raw text bytes in a 21-byte `LWF1` optical frame (170 bits / 4.25 seconds); UNO Q
validated CRC `f8f8`, the low stop bit, and payload SHA-256, then delivered the
decoded text and full hardware evidence to LightWeave Mobile. The receiver side
contained only the S25 and UNO Q. Direct PNG/WAV display, reconnect, and longer
sustained power remain optional physical gates.

Documentation claims: Arduino specifies that UNO Q has a Qualcomm Dragonwing
QRB2210 MPU running Debian, an STM32U585 MCU, Bridge/RPC, Wi-Fi, Bluetooth, and
USB-C role switching. Samsung specifies USB-C/USB 3.2 Gen 1 for the Galaxy S25
Ultra. Direct local PC observation: UNO Q enumerated as Arduino USB composite
`2341:0078` with ADB and a standard USB serial interface. Direct S25 evidence:
Samsung `SM-S938U1`, Android 15/API 35, ARM64, successful APK installation and
rendering, and `android.hardware.usb.host`. The S25 then enumerated the real
receiver through an Anker USB-C host hub, matched its CDC interfaces, opened the
serial link, sent controls, received state, and rendered a decoded optical text
result. Direct PNG/WAV display, longer sustained power, throughput, and
reconnect remain unverified.

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
on-board encoding and Galaxy S25 HTP remain deferred. Image and audio optical
receive integration are now complete.

The repository should be the single source of source code, pinned manifests,
payload contracts, validation vectors, and setup orchestration for all targets.
It should not pretend that one binary or environment installs everywhere:
Windows x64/ARM64, Android ARM64, and UNO Q Debian ARM64 need separate thin
installers that consume shared versioned model/codec definitions. Generated
models, SDK redistributables, and credentials remain outside Git; manifests and
download/verification scripts are tracked.

### Deferred next milestones

The direct Windows-to-UNO-Q optical workflow and standalone Android receiver
software are implemented. The APK is installed and its complete disconnected
state is rendered on the S25 Ultra. The next gate is physically validating
direct USB enumeration/power, Listen/Cancel, text/image/audio presentation,
reconnect, and an end-to-end optical transfer with no receiver-side laptop.
Faster modulation, transition-based clock recovery, retries, and sustained
adverse-light testing remain later transport work.

### Existing App Lab transmitter discovery

Direct read-only inspection on 2026-08-06 confirmed that the connected
transmitting UNO Q contains a stopped App Lab app named
`image_transmitter_bkp`. No app or sketch was started, stopped, flashed, or
modified during discovery.

The app is an autonomous fixed-image transmitter, not currently a user-facing
upload service:

- `app.yaml` exposes no ports or Bricks. Its Python process reads the bundled
  `python/images.jpg`; Windows cannot submit a payload to it as written.
- Python uses Pillow to convert the bundled image to grayscale, resize it to
  128 by 128 with Lanczos, threshold at 128, and pack monochrome pixels MSB
  first into exactly 2,048 bytes.
- Python calls RouterBridge `prepare_image_buffer`, then calls
  `store_image_byte(index, value)` once for each byte, and finally notifies
  `transmit_image`. Historical logs confirm all 2,048 bytes were loaded and the
  transmit command was issued in an earlier run.
- The STM32 sketch holds a fixed 2,048-byte buffer, drives the laser on pin 9,
  and emits one high start bit, 16,384 raw data bits MSB first, and one low stop
  bit. Each bit lasts 25 ms. There is no length, checksum, retry, Manchester
  coding, or other framing.
- The current optical rate is 40 bit/s (5 payload bytes/s), so one fixed frame
  takes 409.65 seconds, about 6 minutes 50 seconds. This is substantially below
  LightWeave's earlier 1-2 kbps transfer assumption.

The internal Bridge and STM32 storage boundary is already binary-safe for byte
values 0-255, so the laser/timing portion is reusable. The implemented
integration replaces the bundled-image producer in a clone with an atomic
binary inbox, retains the 2,048-byte maximum and per-byte RouterBridge loading,
and changes only the active payload length used by buffer-completeness checks
and the transmit loop. The receiver must learn that exact length out of band or
from a separately approved transport frame; the raw codec payload itself
remains unchanged.

### Dashboard-to-UNO Q transmitter

The repository tracks the complete App Lab source under
`uno_q/transmitter_app/` and a hash-checking installer. Installation clones
`image_transmitter_bkp` into `lightweave_transmitter`, then replaces source only
inside the clone. The backup's important source hashes were identical before
and after installation. The installer refuses unrelated targets, supports
dry-run/no-start operation, and stops another running App Lab app only through
the explicit `-StopRunningApp` option because App Lab permits one active app.

The Windows `UnoQAdbSink` discovers ADB, automatically selects the single UNO Q
running the tracked transmitter when two boards are attached, and uses an atomic
USB inbox: payload and metadata are pushed to partial paths, renamed, and the
request descriptor is published last. SHA-256, request ID, media type, preset,
and byte length protect only this USB control-plane handoff. The default laser
mode wraps the exact raw `payload.bin` in `LWF1`; explicit `raw-v0` remains only
for the byte diagnostic. The App Lab worker
validates the image/audio contracts, acknowledges every byte stored on the
STM32, then launches transmission. Since the existing sketch has no completion
callback, the dashboard reports launch acceptance and an estimated busy window,
not physical completion.

Board acceptance on 2026-08-06 used App CLI 0.12.1, Python 3.13.14, Arduino
Zephyr core 0.90.0, and RouterBridge 0.4.3. The App Lab build/flash took about
93 seconds and used 86,468 bytes of flash plus 35,070 bytes of global RAM. A
124-byte image and 188-byte one-second audio payload were buffered exactly and
completed the unchanged 25 ms/bit laser loop in 24.85 and 37.65 seconds. A
second request was rejected during the active window. A browser-generated
104-byte image then passed the inline two-step confirmation, USB handoff, exact
104-byte buffer acknowledgement, and 20.85-second launch estimate with no
browser console errors. The owner subsequently initiated a dashboard send and
visually observed the physical laser blinking. This proves the commanded laser
activity reached the hardware; it does not yet prove optical byte correctness
or receiver reconstruction.

The first receiver-connection attempt exposed only the transmitter, but a
subsequent cable/port reconnect resolved enumeration. Two boards are now mapped
without stopping either app: transmitter `123900964`/`UNOQ-1`/COM3 and receiver
`371371094`/`unoq2`/COM4. The transmitter now runs
`lightweave_transmitter`/**LightWeave Transmitter**; the receiver now runs
`lightweave_receiver`/**LightWeave Receiver**. The former
`lightweave_optical_receiver` is stopped and retained as rollback.

Read-only inspection found that `image_receiver` is the closest optical
receiver base. Its STM32 sketch already matches the transmitter's 25 ms/bit,
single leading bit, raw MSB-first data, and low stop bit. It samples analog A0
with threshold 800. However, it is fixed to 128-by-128 monochrome data—exactly
2,048 bytes—and its Python app converts the result into a one-bit PNG. It cannot
finish a typical variable-length LightWeave payload or feed raw bytes into the
existing accelerated decoder. `laser_receiver_ui` is not a suitable base
because it uses 100 ms/bit, per-character leading bits, and ASCII strings. All
inspected receiver source remained unchanged; important `image_receiver`
source hashes were recorded before any future clone.

### Legacy App Lab text-pair discovery

Read-only inspection on 2026-08-06 found stopped `laser_transmitter_ui` and
`laser_receiver_ui` projects. Neither was started, flashed, or modified. The
prototype accepts 1-100 printable ASCII characters. The transmitter drives pin
9 at 100 ms per bit, emits one initial low interval, then for each character one
high leading bit followed by eight MSB-first ASCII bits. It leaves the laser low
after the final character. The receiver uses digital pin 2 with `INPUT_PULLUP`,
detects the first low-to-high transition, takes three majority-vote samples
around each bit center, and treats a low next-leading-bit sample as end of text.

The logic proves the no-model text use case, but the pair is not a production
protocol: it has no magic, length, CRC, or version; the backend and browser use
different duration formulas; the browser downloads Socket.IO from a CDN; the
README/App metadata still describe an LED example; and received text is only
kept in memory. Production integration therefore retains this exact framing as
a documented compatibility reference while using `T1-ASCII-B100` (`0x20`) in
the common offline `LWF1` frame. The saved payload is the exact ASCII bytes.
The current A0/25-ms production hardware path stays unchanged. The complete
production integration was installed and exercised on 2026-08-06. A 16-byte
`Hello LightWeave` message arrived byte-for-byte in 5.65 seconds inside a
28-byte LWF1 frame. Both ends reported header
`4c570120100000000000`, CRC `0xa62b` (wire `2ba6`), profile ID `0x20`,
valid stop bit, and matching payload SHA-256. The receiver stored the result as
`.bin`, `.txt`, and `.json`; its evidence explicitly reports printable ASCII
with `accelerator_required: false`.

Final App Lab identities are deliberately paired:

- `lightweave_transmitter`, displayed as **LightWeave Transmitter**.
- `lightweave_receiver`, displayed as **LightWeave Receiver**.

The existing `lightweave_optical_receiver` remains stopped as rollback during
migration, and both original `laser_*` apps remain untouched.

### Basic optical byte receiver

The repository now tracks `uno_q/byte_receiver_app/`, installed only on receiver
`371371094` as `lightweave_byte_receiver`. Existing `image_receiver`,
`laser_receiver_ui`, and accelerated LightWeave receiver apps remain unchanged.
The new STM32 sketch retains the proven A0 threshold 800, one high start bit,
25 ms/bit, MSB-first data, and one low stop bit, but accepts an explicit
1-2,048-byte length. After timing-sensitive reception finishes, Python retrieves
the buffer in 32-byte hexadecimal RPC chunks and atomically saves the exact
binary plus SHA-256 evidence. A local App Lab page can arm a manual length and
download the result; an ADB verifier can arm, transmit, retrieve, and compare
automatically.

Installation on 2026-08-06 stopped only the receiver board's unrelated default
`Copy of connect to phone` app. The transmitter remained running on the other
board. App Lab built/flashed the receiver in about 95 seconds; its sketch used
87,756 bytes of flash and 33,678 bytes of global RAM. The first physical test
sent `00 FF AA 55` in 0.85 seconds. The receiver returned the exact same four
bytes, matching SHA-256
`df7d75aad696b49ea81cbddff8c30a794ce0243bf9895db26e8127e0485f4de5`,
and a valid stop bit. This proves byte correctness for that diagnostic pattern,
not general reliability under adverse optical conditions. The same diagnostic
passed a second time before production integration began.

### Production optical text/image/audio receiver

The repository tracks `uno_q/optical_receiver_app/`, installed on receiver
`371371094` as `lightweave_receiver` and displayed as **LightWeave Receiver**.
It remains separate from the byte diagnostic and all original apps. The former
`lightweave_optical_receiver` is preserved stopped as rollback. Its installer
clones the installed
`lightweave-uno` runtime/models, verifies decoder source, reuses the board-local
WebUI/Vulkan files, and deploys the A0/threshold-800, MSB-first framing sketch.
The expensive native runtime preparation is not repeated. The text-integrated
receiver sketch uses 93,044 bytes of flash and 35,146 bytes of global RAM with
Arduino Zephyr 0.90.0 and RouterBridge 0.4.3.

The production receiver accepts a self-describing text/image/audio frame. The
downloaded/generated `payload.bin` remains the unchanged raw codec output; only
the laser wire wraps it:

```text
start bit
magic "LW"             2 bytes
frame version           1 byte
codec/profile ID        1 byte
payload length          2 bytes, little-endian
media parameter         4 bytes, little-endian
raw payload             N bytes
CRC-16/CCITT-FALSE      2 bytes, little-endian
stop bit
```

Text uses `0x20`, a zero media parameter, and 1-100 printable ASCII bytes.
Images use profile IDs `0x01` through `0x03` and a zero media parameter. Audio
uses `0x10` and places the exact 24 kHz sample count in the media parameter. The
CRC covers the ten-byte header plus raw payload. The common wrapper adds 12
bytes/2.4 seconds at 25 ms per bit. The one-shot WebUI exposes **Listen for
transfer** and **Cancel**, derives decoder settings automatically, and does not
reconstruct invalid magic, version, profile, length, media parameter, audio
padding, CRC, or stop bit.

Physical `LWF1` acceptance passed for 80-byte/64-pixel, 216-byte/128-pixel, and
716-byte/256-pixel image payloads. Every image reconstructed at the exact size
through all 16 compute layers on Turnip Adreno 702 with strict fallback
disabled. One 188-byte `A1-E15-S24000` frame produced an exact 24,000-sample,
24 kHz mono PCM16 WAV through CPU codebooks/layers 0-4 and the strict 39-layer
Adreno suffix; the conditioned boundary jump was zero. The five-second optical
case was deliberately not run after the owner chose to skip further long
transfers; five-second codec/board reconstruction remains validated separately.
The 16-byte text fixture also passed exact optical reception, CRC, stop-bit,
automatic profile routing, atomic TXT persistence, and no-AI evidence. The
Windows text panel and board receiver page were browser-tested with local-only
assets and zero console errors.

An initial 216-byte frame consistently slipped one bit around optical bit 1,389
because the two STM32 free-running clocks accumulated phase error. A receiver
sample interval of 24,991 microseconds, while retaining the transmitter's
25,000-microsecond wire timing, passed all three image sizes plus audio. This is
a measured board-pair calibration, not general clock recovery. CRC rejection
preserved failed-frame evidence and prevented reconstruction. Explicit
`raw-v0` also passed the `00 FF AA 55` exact-byte diagnostic after the upgrade.

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

### Raw payload and optical wire modes

Generated `payload.bin` files remain header-free codec bytes and can be decoded
with an out-of-band preset on Windows or UNO Q. The production optical wire mode
is `LWF1`, which supplies the minimum routing and integrity fields required by
automatic reception but no model fingerprint or cryptographic hash. Explicit
`raw-v0` sends no header and is retained only for the exact-byte diagnostic.
`.lwv` remains the safer format for archival, diagnosis, SHA-256 integrity, and
model negotiation.

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
- Text preset `T1-ASCII-B100` is the exact 1-100 printable-ASCII byte string.
  It uses no compression, model, entropy coder, or accelerator. LWF1 profile
  `0x20` provides media type, length, and CRC only on the optical wire.

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
| Fresh debug APK | Clean build succeeds; package `com.lightweave.mobile`, version `1.0.0`/code 2; installed successfully on the S25 Ultra |
| Unit tests | 7 passing tests for exact control vectors, Python/Android canonical parity, all four result types, single-byte fragmentation, CRC/resync, invalid headers, and USB identity |
| Android lint | Pass, 0 errors and 9 non-blocking style/typography warnings |
| USB host declaration | Present; exact UNO Q filter `2341:0078` |
| App network permission | None |
| Supported result types | Status, UTF-8 text, PNG image, and playable PCM WAV audio |
| Controls | Bidirectional Listen, Cancel, and Status through `LWCT/1` |
| UNO Q USB service | Boot-managed `arduino-router-serial.service`; App Lab uses `mon/read`/`mon/write` and needs no direct gadget-node permission |
| Physical USB protocol | Direct S25 Status returned idle; Listen changed board state to `phone-usb`/`listening`; Cancel returned it to idle |
| Real decoded result delivery | Existing strict-Adreno 64 by 64 PNG delivered as a valid 6,398-byte `LWRX/2` frame; 4,469 PNG bytes and 1,909 metadata bytes |
| S25 install and screen | Pass on `SM-S938U1`, Android 15/API 35, ARM64; cold launch in 228 ms, light/dark receiver UI rendered, app resumed, and no crash entries |
| S25 USB-host capability | Present as `android.hardware.usb.host`; disconnected controls correctly remain disabled until a matching board is attached |
| Direct S25 UNO Q enumeration | Pass through the exercised USB-C host hub: `UNO Q - unoq2`, `2341:0078`, ADB plus CDC/ACM interfaces |
| Android CDC open/control transmit | Pass: app reported receiver ready and sent exact 12-byte Status/Listen/Cancel controls |
| UNO Q boot-started CDC service | Pass: Router and serial services are active/enabled, live `mon/connected` succeeds, and direct S25 control/results work with an empty container device list |
| Direct decoded-media delivery/power/reconnect | Text pass: `S25 PROOF`, 9 payload bytes, 21 frame bytes, CRC `f8f8`, valid stop bit, 4.25 seconds, rendered with evidence; PNG/WAV, reconnect, and longer power remain pending |

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
| Android standalone receiver | Fresh APK, text/image/audio/status, Listen/Cancel, save/playback, evidence UI, tests/lint, S25 install/render, direct enumeration, CDC open, and control writes pass; board response blocked by boot container permissions |
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
| Android standalone receiver | Direct standalone text receive passes | Router transport, S25 Status/Listen/Cancel, 9-byte optical text result, CRC/stop-bit/hash evidence, and decoded display pass; direct PNG/WAV and reconnect remain |
| UNO Q accelerator feasibility | Complete | ncnn Vulkan executes all three complete graphs on Adreno 702; QNN/FastRPC is absent on the exercised image |
| UNO Q native receiver | Complete locally | Native rANS, strict runner, CLI, rendered API/WebUI, manifest, SPDX SBOM, offline bundle, dry-run/idempotent installer, and 60-test repository suite pass |
| UNO Q receiver publication | Complete | Source/evidence commit `8074645` and Android-preservation commit `fa19c64` published to `origin/main` |
| UNO Q audio receiver | Complete and published | Commit `03b0bd7`; native unpack/codebook parity, earliest valid split 5, strict 39-layer Adreno suffix, 1/5-second parity, CLI/API/WebUI, offline bundle, installer, and offline smoke pass |
| Android receiver UI and hardware path | Installed; direct optical text accepted | Commit `81c8888`; boot-safe Router update adds S25 Status/Listen/Cancel and exact optical text display with no receiver laptop; publish focused update next |
| Windows-to-UNO Q transmitter flow | Complete and published | Commit `028f9d9`; dashboard image/audio Send actions, USB/ADB sink, atomic App Lab inbox, variable-length STM32 loop, tracked clone source, installer, and real 104/124/188-byte board acceptance pass |
| UNO Q optical byte diagnostic | Complete and published | Commit `80ba103`; exact `00 FF AA 55` received twice with matching SHA-256 and valid stop bit |
| UNO Q optical image receiver | Complete and published | Commit `506eee9`; two 80-byte physical image transfers passed exact-byte, stop-bit, 64-by-64 PNG, 16-layer Adreno, strict-no-fallback, App Lab UI, and zero-console-error gates |
| Self-describing optical image/audio framing | Complete and published | Commit `c8600c7`; `LWF1` carries profile, length, audio sample count, and CRC; all image routes plus one-second audio passed physical reconstruction |
| Integrated text transport | Complete and published | Commit `62c540d`; exact 16-byte optical transfer passed profile `0x20`, CRC/stop-bit, TXT persistence, no-AI evidence, paired App Lab names, local browser UI, and protected legacy-source hashes |
| Offline runtime | Complete locally | Process guard and dual-media smoke script implemented |
| QUAD local workflow | Complete | Detect and doctor exercised |
| GitHub Actions unit CI | Complete | Windows run `31147024146` passed on text-integration head `62c540d`; accelerator/hardware gates stay local |
| Second Snapdragon PC | Pending external device | Transfer the same `.lwv` plus generated artifacts and verify |
| AI Hub/QAIRT Visualizer | Pending access/install | Compare only when account/SDK are available |
| Arduino/optical adapter | Image/audio implementation complete | Default `LWF1`, explicit `raw-v0` diagnostic, automatic routing, strict image Adreno and truthful audio hybrid verified physically |
| GitHub push | Complete | Standalone Galaxy receiver commit `81c8888` and pre-rebuild tag `lightweave-pre-android-rebuild` were pushed without force |

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
| USB stream loses boundaries or reconnects mid-result | `LWRX/2` bounds plus CRC32 reject corruption and resynchronize on magic; completed media remains in a durable UNO Q outbox until delivery succeeds |
| Phone receives an unsafe allocation | Reject metadata above 256 KiB, decoded media above 16 MiB, and decoded images above 16 megapixels before rendering |
| App Lab container cannot access gadget CDC by default | Resolved without device access: the boot-managed system serial service owns `/dev/ttyGS0`, and the app uses Arduino Router `mon/read`/`mon/write` through its existing socket |
| Phone may not sustain UNO Q power | Direct S25 behavior remains a hardware gate; use a standards-compliant USB-C OTG/PD powered hub while preserving S25 host and UNO Q device roles if needed |
| App Lab default boot omits adjacent Compose overrides | Resolved by deleting the unsupported override dependency; the supported Router serial service is enabled independently and the default-started app needs no Docker device allow-list |
| Multiple ADB devices are connected | Automatically select the only UNO Q running the tracked transmitter marker; fail on ambiguity and retain the serial override |
| App Lab allows only one active application | Installer does not stop anything by default; the explicit `-StopRunningApp` option performs the reversible stop before starting `lightweave_transmitter` |
| USB inbox is interrupted or stale | Publish payload/metadata atomically, publish the descriptor last, verify SHA-256/length/request ID, ignore partial files, and return per-request result files |
| Transmitter has no physical completion callback | Report only exact buffering plus launch acceptance; enforce an estimated busy window and never claim optical completion from the dashboard |
| Fixed analog threshold and open-loop timing may be environment-sensitive | CRC caught a repeatable long-frame bit slip; a 24,991-us receiver interval passes this board pair while the transmitter stays at 25 ms, but true clock recovery and broader alignment/light testing remain necessary |
| `LWF1` is not cryptographically self-describing | It supplies routing, bounds, sample count, and CRC but no model hash; pinned artifacts remain required and `.lwv` is used where model negotiation/SHA-256 matter |
| Five-second optical audio is slow | Codec/board decode is validated to five seconds, but the owner elected not to spend 190.45 seconds on the optical stress transfer; one-second optical audio is the physical acceptance evidence |
| Legacy and production text waveforms differ | The stopped `laser_*` apps remain unchanged and their 100-ms character framing is documented. Production uses `T1-ASCII-B100` in the common 25-ms LWF1 frame; do not present the two as wire-compatible. |
| Mobile access to the App Lab WebUI is intermittent | Direct board IPv4 port 7000 currently returns HTTP 200 and Wi-Fi signal is strong, while `.local` discovery did not resolve from Windows. Use the current DHCP IPv4 address on the same trusted subnet; avoid `localhost`, HTTPS, VPN/cellular fallback, and client-isolated Wi-Fi. Reserve the address or use a dedicated demo router/hotspot for stability. |

## Open questions

- Will the same generated artifacts and `.lwv` payloads pass on the second
  Snapdragon PC?
- Can QAIRT Visualizer provide per-layer evidence that explains the rejected
  larger audio-tail semantics?
- Can AI Hub or a newer QNN release run more of EnCodec accurately without the
  narrowed split?
- Should future work add QNN context caching to reduce the audio tail's session
  preparation time?
- Will direct S25 PNG and WAV rendering match the passing text path and prior
  Android parser/UNO Q decoder evidence?
- Can the exercised powered USB-C hub sustain longer image/audio receive and
  reconnect cycles without resetting the S25 host or UNO Q?
- What sustained USB throughput and reconnect behavior does the S25 show for
  the largest decoded PNG and five-second PCM WAV result?
- Can a custom Android ONNX Runtime/QNN AAR run the existing fixed-shape QDQ
  image decoder on Galaxy S25 HTP with no fallback, zero CPU graph nodes, and
  at least 35 dB parity against the Windows CPU reference?
- Can the pinned CompressAI rANS decoder and tables be ported to Android NDK
  while decoding existing raw `payload.bin` files byte-identically?
- Would a future, explicitly approved UNO Q encoding phase justify the extra
  `g_a` model, native rANS encoder, storage, and accelerator-validation cost?
- What sustained frame-error rate does `LWF1` achieve under varied alignment and
  ambient light, beyond the passing current-board image/audio fixtures?
- Would transition-based clock recovery remove the board-pair-specific 24,991-us
  receiver calibration while preserving the simple 25-ms waveform?
- Is the existing 25 ms bit duration intentional for the optical hardware, and
  what faster rate passes sustained end-to-end tests?

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
| D-037 | 2026-08-05 | Make the Android receiver UI and direct Windows-to-UNO Q flow the next two milestones, with work paused for now. | Owner-defined follow-on order after completing the UNO Q image/audio receiver. |
| D-038 | 2026-08-06 | Resume with transmitter-side integration discovery and inspect `image_transmitter_bkp` without modifying or starting it. | Owner connected the transmitting UNO Q and requested an explanation and bridge assessment before implementation. |
| D-039 | 2026-08-06 | Use USB/ADB plus an atomic watched inbox as the Windows-dashboard-to-App-Lab transport. | Works offline, preserves the existing `RawByteSink` boundary, handles multiple attached ADB devices safely, and does not alter optical bytes. |
| D-040 | 2026-08-06 | Clone the backup as `lightweave_transmitter`, retain per-byte RouterBridge loading and the existing waveform, and change only the active payload length on the STM32. | Owner explicitly prohibited backup edits and approved variable-length transmission without hardware/timing changes. |
| D-041 | 2026-08-06 | Keep SHA-256 and request metadata in the local USB control plane and report launch acceptance rather than physical completion. | `payload.bin` and explicit `raw-v0` stay header-free; D-045 later adds only a wire-time routing/CRC wrapper. The MCU still exposes no completion callback. |
| D-042 | 2026-08-06 | Add a separate variable-length optical byte diagnostic before connecting the accelerated media receiver. | Preserves all existing receiver apps, proves the transport independently, and keeps expected length as out-of-band control data. |
| D-043 | 2026-08-06 | Keep the byte diagnostic separate and add `lightweave_optical_receiver` by composing the proven `image_receiver` sampling logic with the installed strict-Adreno decoder. | Preserves original apps, avoids repeating the long runtime build, and makes optical transport evidence distinct from reconstruction evidence. |
| D-044 | 2026-08-06 | Add an eight-byte image-only self-describing optical wrapper. | Superseded by D-045 before implementation so image and audio share one format. |
| D-045 | 2026-08-06 | Use the common 12-byte `LWF1` image/audio wrapper and keep `payload.bin` unchanged. | Carries profile, payload length, exact audio sample count, and CRC-16 while preserving raw codec compatibility. |
| D-046 | 2026-08-06 | Calibrate this receiver to a 24,991-us sample interval while retaining 25-ms transmitter bits. | Removed a measured long-frame phase slip; this is board-pair evidence, not general clock recovery. |
| D-047 | 2026-08-06 | Stop additional long optical acceptance transfers. | Owner accepted existing evidence; the five-second audio wire test is intentionally skipped while the supported decoder limit remains five seconds. |
| D-048 | 2026-08-06 | Integrate text as `T1-ASCII-B100` / profile `0x20` in `LWF1`, with no AI stage. | Reuses automatic routing, length, CRC, storage, and one-shot reception while preserving exact printable-ASCII payload bytes. |
| D-049 | 2026-08-06 | Name the production App Lab pair `lightweave_transmitter` / **LightWeave Transmitter** and `lightweave_receiver` / **LightWeave Receiver**. | Clear matched identities; original `laser_*` and stopped `lightweave_optical_receiver` remain rollback/reference apps. |
| D-050 | 2026-08-06 | Present measured process time/memory, accelerator profile events, audited graph layers, bridge calls, and optical-bit counts instead of estimating FLOPs, power, or energy. | These quantities are available and defensible from the current runtimes; layer/event counts are explicitly not operation or energy estimates. |
| D-051 | 2026-08-06 | Add persistent light/dark modes while preserving the plain monochrome visual system. | Uses local assets, browser preference on first visit, and local storage thereafter; runtime remains offline. |
| D-052 | 2026-08-06 | Track an evidence-based submission checklist and classify the repository as ready for open-source distribution, not commercially certified. | Reproducible source installation, verified hardware behavior, tests, and licenses satisfy the open-source-platform path; no signed/store package, authentication, or production clock recovery is claimed. Team roster and form completion remain owner actions. |
| D-053 | 2026-08-06 | Replace the old Android prototype from scratch and make Galaxy S25 Ultra + receiver UNO Q the final no-laptop receiver/display. | Owner explicitly retired the prior Android work and clarified that the phone must replace the receiver WebUI, including Listen/Cancel plus text, image, audio, and evidence. |
| D-054 | 2026-08-06 | Preserve all reconstruction on UNO Q and add only a durable bidirectional USB presentation/control channel. | `LWCT/1` and `LWRX/2` sit after the unchanged optical/decode path; the phone runs no AI, the transmitter is untouched, and decoded results survive temporary phone disconnects. |
| D-055 | 2026-08-07 | Use the existing fresh `android/` Android Studio project as the canonical mobile project and install that build on the S25 Ultra. | The earlier prototype was already replaced; creating a second project would duplicate the supported app and break the repository's single-source installation model. |
| D-056 | 2026-08-07 | Route phone CDC bytes through UNO Q's boot-managed Arduino Router monitor instead of opening `/dev/ttyGS0` in the App Lab container. | Official `mon/read`/`mon/write` reuse the enabled system serial bridge, eliminate the unsupported Compose override and cgroup failure, preserve default-app startup, and pass direct S25 Status/Listen/Cancel plus decoded optical text delivery. |

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
| 2026-08-05 | Recorded publication of the UNO Q audio receiver and selected Android receiver UI plus direct Windows-to-UNO Q transfer as the next deferred milestones; identified the existing App Lab text transmitter as a reusable transport candidate pending a binary-safety and interface audit. |
| 2026-08-06 | Inspected the connected transmitter and recorded that `image_transmitter_bkp` is a stopped, autonomous 128-by-128 monochrome app with a fixed 2,048-byte STM32 buffer, per-byte RouterBridge loading, and an unframed 40-bit/s laser stream; identified its binary-safe buffer/laser loop and Python input boundary as the reuse points. |
| 2026-08-06 | Implemented the tracked `lightweave_transmitter` App Lab clone, variable-length STM32 transmit loop, atomic USB/ADB sink, dashboard status/Send flow, hash-preserving installer, and setup documentation; verified exact real image/audio byte counts, busy rejection, unchanged 25 ms waveform completion, and browser acceptance without modifying the backup. |
| 2026-08-06 | Published the complete Windows-dashboard-to-UNO Q transmitter milestone as commit `028f9d9` on `origin/main` without force-pushing. |
| 2026-08-06 | Recorded the owner's independent visual observation that a dashboard-initiated request made the physical laser blink; optical byte correctness and reception remain the next gate. |
| 2026-08-06 | Attempted read-only two-board discovery after the receiver was connected; only transmitter `123900964`/COM3 enumerated, so receiver inspection remains pending a second USB data connection. |
| 2026-08-06 | Resolved two-board discovery and mapped transmitter `123900964`/COM3 versus receiver `371371094`/COM4; read-only inspection found `image_receiver` waveform-compatible but fixed at 2,048 monochrome bytes, while `laser_receiver_ui` uses an incompatible text protocol. |
| 2026-08-06 | Added and installed the separate variable-length byte receiver plus automated verifier; the first physical two-board test received `00 FF AA 55` exactly with matching SHA-256 and a valid stop bit while preserving all original receiver apps. |
| 2026-08-06 | Published the byte diagnostic as commit `80ba103`, then installed and exercised the separate production optical image receiver: two exact 80-byte transfers reconstructed to 64 by 64 through all 16 Adreno layers with strict fallback disabled, including a live App Lab UI run with PNG download and no browser errors. |
| 2026-08-06 | Published the production optical image receiver, installer, acceptance harness, tests, setup instructions, and evidence as commit `506eee9` on `origin/main` without force-pushing. |
| 2026-08-06 | Approved self-describing optical image framing as the next implementation: eight transport bytes provide magic/version/preset/length/CRC while the generated raw payload remains unchanged; current manual receiver testing comes first. |
| 2026-08-06 | Replaced the image-only proposal with common 12-byte `LWF1` framing for images/audio, automatic two-board transmitter selection, one-shot Listen/Cancel reception, CRC-gated routing, and preserved explicit `raw-v0` diagnostics. |
| 2026-08-06 | Diagnosed a repeatable long-frame free-running-clock slip, calibrated this receiver to 24,991 us against the unchanged 25-ms transmitter, and physically passed 80/216/716-byte images plus 188-byte one-second audio with strict Adreno evidence. |
| 2026-08-06 | Honored the owner's request to skip further long transfers, omitted the five-second optical audio run, revalidated exact `00 FF AA 55` in `raw-v0`, and left the production optical receiver running. |
| 2026-08-06 | Published the dynamic `LWF1` image/audio transmitter/receiver implementation, App Lab sources, installers, tests, setup guidance, SBOM/notices, and physical evidence as commit `c8600c7` on `origin/main`. |
| 2026-08-06 | Recorded publication in commit `db6cf62`; GitHub Actions run `31140365004` passed the Windows lint/unit gate on that head. |
| 2026-08-06 | Diagnosed intermittent phone access: the receiver app and `0.0.0.0:7000` listener were healthy and direct IPv4 returned HTTP 200, isolating the remaining instability to DHCP/name discovery, phone routing, or Wi-Fi client policy. |
| 2026-08-06 | Inspected the stopped legacy text pair, documented its 100-ms printable-ASCII leading-bit protocol and prototype gaps, selected `T1-ASCII-B100` in `LWF1`, and chose matched production transmitter/receiver App Lab names. |
| 2026-08-06 | Integrated no-AI text into the Windows dashboard and production App Lab pair, installed **LightWeave Transmitter**/**LightWeave Receiver**, preserved all legacy/rollback source hashes, and physically received `Hello LightWeave` exactly with valid LWF1 CRC/stop bit and atomic TXT output. |
| 2026-08-06 | Published the integrated text implementation as commit `62c540d`; GitHub Actions run `31147024146` passed the Windows lint/unit gate. |
| 2026-08-06 | Added persistent light/dark UI controls, defensible Windows/UNO Q/STM32 hardware evidence, QNN provider-event counts, and an explicit hackathon submission audit with owner-only gaps; reinstalled both production apps and physically verified `Telemetry OK` with 194 optical bits, 15 bridge calls, valid CRC/stop bit, and correct CPU-only text labeling. |
| 2026-08-06 | Committed the theme, hardware telemetry, board evidence, tests, and submission-readiness audit as `98481a8`; 124 portable tests and repository lint passed before publication. |
| 2026-08-06 | Retired the previous Android prototype, selected a final no-laptop Galaxy S25 Ultra + receiver UNO Q topology, and created the `lightweave-pre-android-rebuild` backup tag at the last published working receiver head. |
| 2026-08-06 | Rebuilt LightWeave Mobile for bidirectional USB Listen/Cancel/Status and decoded text/PNG/WAV/evidence, added the receiver's durable `LWRX/2` outbox and narrow `/dev/ttyGS0` App Lab mapping, passed 137 Python tests plus Android build/lint/7 tests, and physically verified status, listen/cancel, and real reconstructed-PNG delivery through the UNO Q USB gadget. Direct S25 validation remains pending. |
| 2026-08-06 | Published the standalone Galaxy receiver implementation as commit `81c8888` and pushed the annotated `lightweave-pre-android-rebuild` backup tag; transmitter source and logic remained unchanged. |
| 2026-08-07 | Rebuilt the canonical Android Studio project, passed lint and all seven unit tests, installed version 1.0.0/code 2 on the real S25 Ultra, and verified its light/dark disconnected UI, USB-host feature, resumed activity, and crash-free startup; direct UNO Q cable exchange remains the final gate. |
| 2026-08-07 | Verified from the live UNO Q that LightWeave Receiver is running and stored as the App Lab default startup application; confirmed the enabled App CLI boot service and documented that the final receiver needs power plus the phone cable, not a PC. |
| 2026-08-07 | Exercised the direct S25 host path: Android enumerated the real receiver and LightWeave opened CDC and sent controls, but no response arrived because App Lab default boot omitted the Compose device allow-list; reproduced `/dev/ttyGS0` `EPERM` in the live container and marked standalone boot blocked pending a persistent mapping. |
| 2026-08-07 | Replaced direct gadget-node access with the boot-managed Arduino Router monitor, removed the unsupported Compose override, deployed the default-started receiver, passed 15 focused tests, direct S25 Status/Listen/Cancel, and a complete 9-byte optical text transfer rendered with matching CRC/hash/stop-bit evidence. |
