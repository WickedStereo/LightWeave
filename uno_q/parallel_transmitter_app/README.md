# LightWeave Parallel Transmitter

This is a separate App Lab application. It does not replace or edit
`lightweave_transmitter`.

The application keeps the same ADB inbox, payload validation, per-byte
RouterBridge buffering, `LWF1` header, CRC-16, profile IDs, 25 ms timing, and
MSB-first ordering. It changes only the physical transmission stage:

- lane 0: D5, frame bytes `0, 3, 6, ...`;
- lane 1: D7, frame bytes `1, 4, 7, ...`;
- lane 2: D9, frame bytes `2, 5, 8, ...`.

All lanes emit the start bit together, send one byte per lane in each slot,
and emit the stop bit together. A partially occupied final slot is padded low;
padding is not part of the reconstructed frame or CRC.

The sketch-only `set_lane_test_mask` Bridge method accepts masks 0 through 7
for optical alignment. Use it only while idle and always return the mask to 0.
It is diagnostic control-plane behavior and does not change transmitted frames.

Install only after the standard transmitter is available:

```powershell
.\scripts\install_uno_q_parallel_transmitter.ps1 -DeviceSerial <TX_SERIAL> -DryRun
.\scripts\install_uno_q_parallel_transmitter.ps1 `
  -DeviceSerial <TX_SERIAL> -StopRunningApp
```

App Lab permits one running application. The standard transmitter remains
installed and can be restored by stopping this app and restarting
`lightweave_transmitter`.
