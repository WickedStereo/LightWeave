# LightWeave UNO Q transmitter

This App Lab project is derived from the owner's `image_transmitter_bkp`
application. The backup remains untouched. The tracked clone accepts binary
requests placed in `data/inbox`, loads the exact bytes into the STM32 through
RouterBridge, and launches the existing pin-9 laser waveform.

The optical behavior remains intentionally simple: one high start bit, every
payload bit MSB first, one low stop bit, and 25 milliseconds per bit. Only the
active payload length is variable. The application does not add headers,
hashes, padding, checksums, or preset data to the optical bytes.

Use `scripts/install_uno_q_transmitter.ps1` from the repository root. The
Windows LightWeave dashboard communicates with the running app through an
atomic ADB inbox; the board exposes no network port.
