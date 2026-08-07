package com.lightweave.mobile;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.CRC32;

public final class ResultFrameParser {
    public interface Listener {
        void onFrame(ResultFrame frame);
        void onProtocolError(String message);
    }

    private final Listener listener;
    private byte[] buffer = new byte[0];

    public ResultFrameParser(Listener listener) {
        this.listener = listener;
    }

    public void reset() {
        buffer = new byte[0];
    }

    public void accept(byte[] bytes) {
        if (bytes == null || bytes.length == 0) {
            return;
        }
        byte[] combined = Arrays.copyOf(buffer, buffer.length + bytes.length);
        System.arraycopy(bytes, 0, combined, buffer.length, bytes.length);
        buffer = combined;
        parseAvailable();
    }

    private void parseAvailable() {
        while (true) {
            int magicOffset = findMagic(buffer);
            if (magicOffset < 0) {
                keepMagicTail();
                return;
            }
            if (magicOffset > 0) {
                discard(magicOffset);
            }
            if (buffer.length < ResultProtocol.RESULT_HEADER_BYTES) {
                return;
            }
            ByteBuffer header = ByteBuffer.wrap(buffer, 0, ResultProtocol.RESULT_HEADER_BYTES)
                    .order(ByteOrder.LITTLE_ENDIAN);
            header.position(4);
            int version = Byte.toUnsignedInt(header.get());
            int type = Byte.toUnsignedInt(header.get());
            int flags = Short.toUnsignedInt(header.getShort());
            long metadataLength = Integer.toUnsignedLong(header.getInt());
            long payloadLength = Integer.toUnsignedLong(header.getInt());
            long expectedCrc = Integer.toUnsignedLong(header.getInt());

            if (version != ResultProtocol.RESULT_VERSION
                    || type < ResultFrame.TYPE_TEXT
                    || type > ResultFrame.TYPE_STATUS
                    || flags != 0
                    || metadataLength < 1
                    || metadataLength > ResultProtocol.MAX_METADATA_BYTES
                    || payloadLength < 1
                    || payloadLength > ResultProtocol.MAX_MEDIA_BYTES) {
                listener.onProtocolError("Rejected an invalid LWRX/2 header.");
                discard(1);
                continue;
            }
            long totalLong = ResultProtocol.RESULT_HEADER_BYTES
                    + metadataLength
                    + payloadLength;
            if (totalLong > Integer.MAX_VALUE) {
                listener.onProtocolError("Rejected an oversized LWRX/2 frame.");
                discard(1);
                continue;
            }
            int total = (int) totalLong;
            if (buffer.length < total) {
                return;
            }

            CRC32 crc = new CRC32();
            crc.update(buffer, 0, 16);
            crc.update(buffer, ResultProtocol.RESULT_HEADER_BYTES,
                    (int) (metadataLength + payloadLength));
            if (crc.getValue() != expectedCrc) {
                listener.onProtocolError("Rejected an LWRX/2 frame with a CRC-32 mismatch.");
                discard(total);
                continue;
            }

            int metadataStart = ResultProtocol.RESULT_HEADER_BYTES;
            int payloadStart = metadataStart + (int) metadataLength;
            String metadataJson;
            try {
                metadataJson = StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(buffer, metadataStart, (int) metadataLength))
                        .toString();
            } catch (CharacterCodingException error) {
                listener.onProtocolError("Rejected non-UTF-8 LWRX/2 metadata.");
                discard(total);
                continue;
            }
            byte[] payload = Arrays.copyOfRange(buffer, payloadStart, total);
            listener.onFrame(new ResultFrame(type, metadataJson, payload, expectedCrc));
            discard(total);
        }
    }

    private static int findMagic(byte[] value) {
        for (int offset = 0; offset <= value.length - 4; offset++) {
            if (value[offset] == 'L'
                    && value[offset + 1] == 'W'
                    && value[offset + 2] == 'R'
                    && value[offset + 3] == 'X') {
                return offset;
            }
        }
        return -1;
    }

    private void keepMagicTail() {
        int keep = Math.min(3, buffer.length);
        buffer = Arrays.copyOfRange(buffer, buffer.length - keep, buffer.length);
    }

    private void discard(int count) {
        buffer = Arrays.copyOfRange(buffer, count, buffer.length);
    }
}
