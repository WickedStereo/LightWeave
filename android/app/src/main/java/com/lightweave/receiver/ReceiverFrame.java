package com.lightweave.receiver;

import java.util.Arrays;

public final class ReceiverFrame {
    public static final int TYPE_TEXT = 1;
    public static final int TYPE_IMAGE = 2;

    private final int type;
    private final byte[] payload;

    public ReceiverFrame(int type, byte[] payload) {
        if (type != TYPE_TEXT && type != TYPE_IMAGE) {
            throw new IllegalArgumentException("Unsupported receiver frame type: " + type);
        }
        this.type = type;
        this.payload = Arrays.copyOf(payload, payload.length);
    }

    public int type() {
        return type;
    }

    public byte[] payload() {
        return Arrays.copyOf(payload, payload.length);
    }

    public int payloadLength() {
        return payload.length;
    }
}
