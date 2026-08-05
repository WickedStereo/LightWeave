# LightWeave

LightWeave is an offline-first software interface for sending AI-compressed media through an extremely low-bandwidth, air-gapped byte channel. The current milestone focuses on images: a transmitter converts an image into a compact `.lwv` byte stream, and a Snapdragon receiver reconstructs it with a neural decoder intended to run entirely on the Hexagon NPU through QNN HTP.

The physical optical link is deliberately outside the current milestone. File and stream loopback stand in for the future Arduino/laser transport while the media format, compression, validation, NPU execution, metrics, CLI, and local dashboard are built and verified.

Implementation has been authorized and environment bring-up is in progress. No NPU or performance claim is considered verified until strict no-fallback execution and profiling evidence are recorded.

The living project record is [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). Qualcomm tools, workflows, friction, and improvement notes are tracked in [docs/QUALCOMM_DEVELOPER_EXPERIENCE.md](docs/QUALCOMM_DEVELOPER_EXPERIENCE.md).

Licensed under the [MIT License](LICENSE).
