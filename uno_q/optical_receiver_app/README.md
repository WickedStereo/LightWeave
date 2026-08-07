# LightWeave optical image receiver

This App Lab project joins the proven variable-length optical receiver with the
existing native LightWeave image decoder on Arduino UNO Q.

It is intentionally separate from `lightweave_byte_receiver`, which remains a
transport-only diagnostic. The production flow is:

1. Select the raw image preset and enter the exact payload byte count.
2. Arm the receiver before starting the transmitter.
3. Capture one high start bit, the raw payload MSB first, and one low stop bit.
4. Reconstruct the received entropy string through the complete ncnn Vulkan
   graph on Adreno 702.
5. Display and download the reconstructed PNG.

The raw optical bytes contain no header, hash, preset, or length. Preset and
length are trusted out-of-band settings. The SHA-256 shown after reception is
measurement evidence only.

The tracked project contains no model files or vendor libraries. Installation
reuses the hash-verified runtime already installed by `scripts/install_uno_q.ps1`.

