# Native runner third-party notices

The entropy decoder implements the binary contract used by CompressAI 1.2.8.
Its algorithm is derived from `compressai/cpp_exts/rans/rans_interface.cpp`,
Copyright 2021-2024 InterDigital Communications, Inc., under the
BSD-3-Clause-Clear license included with CompressAI.

The underlying 64-bit rANS algorithm is based on `ryg_rans`, Copyright Fabian
Giesen, dedicated to the public domain under CC0 1.0.

The accelerated backend links to ncnn 20260805, Copyright Tencent, under the
BSD-3-Clause license. Model preparation uses pnnx 20260526. Both tools are
acquired during preparation/build and are not vendored in this repository.

The audio artifact preparation workflow uses Meta EnCodec, Copyright Meta
Platforms, Inc. and affiliates, under the MIT license. EnCodec source is not
installed on the UNO Q. The native receiver reads converted codebooks and ncnn
graphs generated from the separately downloaded 24 kHz model checkpoint. The
checkpoint and converted artifacts are not committed; verify the upstream
checkpoint redistribution terms before distributing an offline bundle.

## App Lab transmitter companion

The tracked `uno_q/transmitter_app` source includes
`Arduino_RouterBridge.h`. RouterBridge 0.4.3, RPClite 0.3.0, MessagePack 0.4.2,
and the Arduino Zephyr core 0.90.0 are supplied by the target UNO Q/App Lab
installation; LightWeave does not vendor or redistribute those platform files.
Review the licenses shipped with the installed Arduino platform before
redistributing a complete board image or App Lab runtime.
