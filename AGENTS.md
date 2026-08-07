# LightWeave Repository Working Rules

## Living context is mandatory

- Read `PROJECT_CONTEXT.md` before substantive work.
- Update `PROJECT_CONTEXT.md` in the same change whenever work changes project understanding, requirements, scope, assumptions, decisions, architecture, risks, plan, progress, hardware facts, QUAD usage, or open questions.
- Update its `Last updated` field and append a dated change-log entry. Add a decision-log entry when a decision is made or reversed.
- Preserve the distinction between confirmed facts, proposals, assumptions, and unresolved questions.
- Never place credentials, personal data, or confidential source content in the living context.

## Qualcomm developer-experience notes are mandatory

- Update `docs/QUALCOMM_DEVELOPER_EXPERIENCE.md` whenever work exercises or materially evaluates Qualcomm hardware, SDKs, runtimes, AI Hub, QAIRT, QNN, QUAD, compilers, profilers, samples, or documentation.
- Record versions, device/OS/architecture, intended workflow, actual evidence, usefulness, friction, workaround, and a concrete improvement suggestion.
- Distinguish direct observations from documentation claims and third-party limitations.
- Do not record API keys, tokens, internal endpoints, or confidential content.

## Implementation authorization and scope

- The project owner explicitly authorized implementation of the approved image-first software plan on 2026-08-05.
- The project owner explicitly authorized the raw transmitter/receiver dashboard milestone on 2026-08-05. Preserve `.lwv` while adding the header-free `I64-Q1` and `A1-E15-S<n>` workflows.
- Application source code, tests, portable setup scripts, and development configuration may be created within that plan.
- The owner authorized the two-UNO-Q optical transmitter/receiver integration and the common `LWF1` dynamic image/audio frame on 2026-08-06. Analog redesign, faster modulation, retransmission, transition-based clock recovery, Galaxy S25 runtime work, and Cloud AI remain deferred.
- The complete image synthesis transform must not silently fall back to CPU. If strict QNN HTP execution cannot be proven, preserve the failure evidence and stop before weakening the claim.
- The image feasibility gate passed locally on 2026-08-05; the audio extension is authorized and implemented.
- The owner authorized the UNO Q receiver-only image/audio milestone on 2026-08-05. UNO Q encoding and Galaxy S25 delivery remain deferred; the later approved STM32 work is limited to the tracked transmitter/receiver framing and variable-length loops.
- Describe each audio target accurately: Windows runs layers 0-12 on CPU and 13-15 on QNN HTP; UNO Q runs codebooks/layers 0-4 on CPU and a strict layers 5-15 suffix on Adreno Vulkan. Both apply the labeled CPU boundary de-click. Do not imply full-NPU/full-GPU audio or restore a failed partition without new numerical evidence.
- The UNO Q audio limit is five seconds/940 raw bytes. Preserve exact `A1-E15-S<n>` compatibility and fail closed on any unexpected CPU layer inside its selected Vulkan suffix.
- A successful QNN assignment is not enough by itself. Preserve CPU/ONNX/NPU numerical parity gates and profile evidence for every generated graph.
- Raw `payload.bin` must remain the unchanged header-free codec output. Production optical sends may wrap it in `LWF1` with version, profile, length, media parameter, and CRC-16; those 12 wire bytes are never written into `payload.bin`. Explicit `raw-v0` remains only for the byte diagnostic. Neither raw files nor `LWF1` contain model negotiation or a cryptographic payload hash.
- Do not spend time on additional long physical transfers unless the owner asks. The five-second/940-byte audio contract remains supported, but current optical acceptance stops at the passing one-second fixture.

## Repository hygiene

- Keep the internal hackathon presentation, credentials, secrets, local environments, build products, logs, captures, caches, calibration data, downloaded weights, and generated model/profile artifacts out of Git.
- Do not vendor the external QUAD-Client checkout into this repository.
- Prefer portable setup documentation and environment-variable references over machine-specific paths or literal credentials.
- Keep the public README accurate to verified capabilities; label unverified NPU or performance claims clearly.
- Stage and commit only task-related files. Never force-push.
