# LightWeave Parallel Receiver

This is a separate App Lab application. It does not replace or edit
`lightweave_receiver`.

The application reuses the standard receiver's Python service, WebUI, phone USB
transport, image decoder, and audio decoder unchanged. Only the STM32 sketch is
different. It samples three optical lanes in parallel and reconstructs the
original `LWF1` byte sequence before exposing it through the same RouterBridge
interface:

- lane 0: A0, frame bytes `0, 3, 6, ...`;
- lane 1: A2, frame bytes `1, 4, 7, ...`;
- lane 2: A5, frame bytes `2, 5, 8, ...`.

All three lanes must carry the common high start bit and common low stop bit.
Each sensor uses threshold 800. The complete reassembled frame must
pass the unchanged profile, size, media-parameter, text/audio, stop-bit, and
CRC-16 validations before reconstruction starts.

Sketch-only diagnostics expose each raw sensor reading, the fixed threshold,
and the combined high-lane mask through RouterBridge. Before a transfer, D5,
D7, and D9 alone should produce masks 1, 2, and 4 respectively. These methods
do not alter the receiver's framing or reconstruction interface.

Install only after the standard receiver is available:

```powershell
.\scripts\install_uno_q_parallel_receiver.ps1 -DeviceSerial <RX_SERIAL> -DryRun
.\scripts\install_uno_q_parallel_receiver.ps1 `
  -DeviceSerial <RX_SERIAL> -StopRunningApp
```

App Lab permits one running application. The standard receiver remains
installed and can be restored by stopping this app and restarting
`lightweave_receiver`.
