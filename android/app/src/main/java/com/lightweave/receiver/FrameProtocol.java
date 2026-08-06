package com.lightweave.receiver;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.zip.CRC32;

public final class FrameProtocol {
    public static final byte[] MAGIC = new byte[] {'L', 'W', 'R', 'X'};
    public static final int VERSION = 1;
    public static final int HEADER_BYTES = 16;
    public static final int MAX_PAYLOAD_BYTES = 8 * 1024 * 1024;

    private FrameProtocol() {}

    public static byte[] encode(int type, byte[] payload) {
        if (type != ReceiverFrame.TYPE_TEXT && type != ReceiverFrame.TYPE_IMAGE) {
            throw new IllegalArgumentException("Unsupported receiver frame type: " + type);
        }
        if (payload.length > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException("Receiver frame payload exceeds 8 MiB.");
        }
        CRC32 crc = new CRC32();
        crc.update(payload);
        ByteBuffer output = ByteBuffer
                .allocate(HEADER_BYTES + payload.length)
                .order(ByteOrder.LITTLE_ENDIAN);
        output.put(MAGIC);
        output.put((byte) VERSION);
        output.put((byte) type);
        output.putShort((short) 0);
        output.putInt(payload.length);
        output.putInt((int) crc.getValue());
        output.put(payload);
        return output.array();
    }
}
