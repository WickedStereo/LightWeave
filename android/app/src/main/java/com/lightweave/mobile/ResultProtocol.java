package com.lightweave.mobile;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;

public final class ResultProtocol {
    public static final byte[] RESULT_MAGIC = {'L', 'W', 'R', 'X'};
    public static final int RESULT_VERSION = 2;
    public static final int RESULT_HEADER_BYTES = 20;
    public static final int MAX_METADATA_BYTES = 256 * 1024;
    public static final int MAX_MEDIA_BYTES = 16 * 1024 * 1024;

    public static final byte[] CONTROL_MAGIC = {'L', 'W', 'C', 'T'};
    public static final int CONTROL_VERSION = 1;
    public static final int CONTROL_LISTEN = 1;
    public static final int CONTROL_CANCEL = 2;
    public static final int CONTROL_STATUS = 3;
    public static final int CONTROL_BYTES = 12;

    private ResultProtocol() {}

    public static byte[] controlFrame(int command) {
        if (command < CONTROL_LISTEN || command > CONTROL_STATUS) {
            throw new IllegalArgumentException("Unsupported LightWeave control command.");
        }
        ByteBuffer prefix = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN);
        prefix.put(CONTROL_MAGIC);
        prefix.put((byte) CONTROL_VERSION);
        prefix.put((byte) command);
        prefix.putShort((short) 0);
        byte[] first = prefix.array();
        CRC32 crc = new CRC32();
        crc.update(first);
        return ByteBuffer.allocate(CONTROL_BYTES)
                .order(ByteOrder.LITTLE_ENDIAN)
                .put(first)
                .putInt((int) crc.getValue())
                .array();
    }

    static byte[] resultFrameForTest(int type, String metadataJson, byte[] payload) {
        if (type < ResultFrame.TYPE_TEXT || type > ResultFrame.TYPE_STATUS) {
            throw new IllegalArgumentException("Unsupported result type.");
        }
        byte[] metadata = metadataJson.getBytes(StandardCharsets.UTF_8);
        ByteBuffer prefix = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN);
        prefix.put(RESULT_MAGIC);
        prefix.put((byte) RESULT_VERSION);
        prefix.put((byte) type);
        prefix.putShort((short) 0);
        prefix.putInt(metadata.length);
        prefix.putInt(payload.length);
        byte[] prefixBytes = prefix.array();
        CRC32 crc = new CRC32();
        crc.update(prefixBytes);
        crc.update(metadata);
        crc.update(payload);
        ByteArrayOutputStream output = new ByteArrayOutputStream(
                RESULT_HEADER_BYTES + metadata.length + payload.length);
        output.write(prefixBytes, 0, prefixBytes.length);
        byte[] checksum = ByteBuffer.allocate(4)
                .order(ByteOrder.LITTLE_ENDIAN)
                .putInt((int) crc.getValue())
                .array();
        output.write(checksum, 0, checksum.length);
        output.write(metadata, 0, metadata.length);
        output.write(payload, 0, payload.length);
        return output.toByteArray();
    }
}
