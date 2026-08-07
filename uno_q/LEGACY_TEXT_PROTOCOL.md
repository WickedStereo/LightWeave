# Legacy App Lab text protocol

The workshop boards retain the owner's original, stopped App Lab projects:
`laser_transmitter_ui` and `laser_receiver_ui`. LightWeave does not overwrite,
start, or vendor those projects. This document preserves their observed wire
contract so the prototype remains understandable.

## Observed `laser_*` contract

- Printable ASCII only (`0x20` through `0x7e`), with a sender limit of 100
  characters.
- Laser output on pin 9 and receiver input on pin 2.
- 100 milliseconds per bit, MSB first.
- Each character consists of one high leading bit followed by eight ASCII
  data bits.
- A low leading-bit slot terminates the message. There is no length, version,
  checksum, profile, or retry mechanism.
- The receiver samples each bit three times around its center and uses a
  majority vote.

For example, `A` (`0x41`) is emitted as the leading bit and byte
`1 01000001`, followed by the low terminator slot.

The prototype's browser estimate counted nine bits per character, while its
backend estimate counted eleven. Neither represents a self-describing frame.
These discrepancies are retained here as historical evidence, not copied into
the production implementation.

## Production LightWeave text contract

Production text uses preset `T1-ASCII-B100`, LWF1 profile ID `0x20`. The raw
`payload.bin` is still the exact printable-ASCII message, with no AI model or
compression. On the optical wire it uses the same 25-ms LWF1 framing as image
and audio, gaining automatic media detection, payload length, and CRC-16.

The production pair is:

- App ID `lightweave_transmitter`, display name **LightWeave Transmitter**.
- App ID `lightweave_receiver`, display name **LightWeave Receiver**.

The legacy waveform is a compatibility reference only. It is not the default
mode of either production app.
