# Native runner third-party notices

The entropy decoder implements the binary contract used by CompressAI 1.2.8.
Its algorithm is derived from `compressai/cpp_exts/rans/rans_interface.cpp`,
Copyright 2021-2024 InterDigital Communications, Inc., under the
BSD-3-Clause-Clear license included with CompressAI.

The underlying 64-bit rANS algorithm is based on `ryg_rans`, Copyright Fabian
Giesen, dedicated to the public domain under CC0 1.0.

The optional accelerated backend links to ncnn 20260526, Copyright Tencent,
under the BSD-3-Clause license. ncnn is acquired during the build and is not
vendored in this repository.
