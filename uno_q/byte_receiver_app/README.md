# LightWeave UNO Q byte receiver

This App Lab project is a transport diagnostic, not the final LightWeave media
receiver. It arms the STM32 with an explicit expected byte count, samples the
existing A0 photodiode circuit at 25 milliseconds per bit, and saves the exact
raw bytes received between the existing high start bit and low stop bit.

The project is installed as `lightweave_byte_receiver`. The existing
`image_receiver`, `laser_receiver_ui`, and accelerated
`LightWeave UNO Q Receiver` projects remain untouched. The expected byte count
is trusted out-of-band control data and is not added to the optical stream.

Use `scripts/install_uno_q_byte_receiver.ps1` from the repository root. For an
automated short byte-integrity check, use
`scripts/verify_uno_q_optical_link.py` after installation.
