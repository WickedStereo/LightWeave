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
- Application source code, tests, portable setup scripts, and development configuration may be created within that plan.
- The current milestone assumes a reliable ordered byte pipe and excludes optical hardware, Arduino firmware, modulation, analog circuitry, Galaxy S25 runtime work, and Cloud AI runtime work.
- The complete image synthesis transform must not silently fall back to CPU. If strict QNN HTP execution cannot be proven, preserve the failure evidence and stop before weakening the claim.
- The image feasibility gate passed locally on 2026-08-05; the audio extension is authorized and implemented.
- Describe the audio decoder accurately: layers 0-12 run on CPU, fixed layers 13-15 run on QNN HTP, and a labeled CPU boundary de-click follows. Do not restore the failed larger-tail claim without new numerical evidence.
- A successful QNN assignment is not enough by itself. Preserve CPU/ONNX/NPU numerical parity gates and profile evidence for every generated graph.

## Repository hygiene

- Keep the internal hackathon presentation, credentials, secrets, local environments, build products, logs, captures, caches, calibration data, downloaded weights, and generated model/profile artifacts out of Git.
- Do not vendor the external QUAD-Client checkout into this repository.
- Prefer portable setup documentation and environment-variable references over machine-specific paths or literal credentials.
- Keep the public README accurate to verified capabilities; label unverified NPU or performance claims clearly.
- Stage and commit only task-related files. Never force-push.
