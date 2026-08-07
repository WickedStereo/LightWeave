package com.lightweave.mobile;

import java.util.Arrays;

public final class ResultFrame {
    public static final int TYPE_TEXT = 1;
    public static final int TYPE_IMAGE = 2;
    public static final int TYPE_AUDIO = 3;
    public static final int TYPE_STATUS = 4;

    private final int type;
    private final String metadataJson;
    private final byte[] payload;
    private final long crc32;

    ResultFrame(int type, String metadataJson, byte[] payload, long crc32) {
        this.type = type;
        this.metadataJson = metadataJson;
        this.payload = Arrays.copyOf(payload, payload.length);
        this.crc32 = crc32;
    }

    public int type() {
        return type;
    }

    public String metadataJson() {
        return metadataJson;
    }

    public byte[] payload() {
        return Arrays.copyOf(payload, payload.length);
    }

    public int payloadLength() {
        return payload.length;
    }

    public long crc32() {
        return crc32;
    }
}
