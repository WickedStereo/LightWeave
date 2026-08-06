package com.lightweave.receiver;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;
import java.util.zip.CRC32;

public final class ReceiverFrameParser {
    public interface Listener {
        void onFrame(ReceiverFrame frame);
        void onProtocolError(String message);
    }

    private static final int INITIAL_BUFFER_BYTES = 8192;

    private final Listener listener;
    private byte[] buffer = new byte[INITIAL_BUFFER_BYTES];
    private int size;

    public ReceiverFrameParser(Listener listener) {
        this.listener = listener;
    }

    public void accept(byte[] bytes) {
        if (bytes.length == 0) {
            return;
        }
        ensureCapacity(size + bytes.length);
        System.arraycopy(bytes, 0, buffer, size, bytes.length);
        size += bytes.length;
        parseAvailable();
    }

    public void reset() {
        size = 0;
    }

    private void parseAvailable() {
        while (true) {
            int magicIndex = findMagic();
            if (magicIndex < 0) {
                int previousSize = size;
                int retained = retainPossibleMagicPrefix();
                int discarded = previousSize - retained;
                if (discarded > 0) {
                    listener.onProtocolError(
                            "Discarded " + discarded + " byte(s) before an LWRX frame.");
                }
                return;
            }
            if (magicIndex > 0) {
                discard(magicIndex);
                listener.onProtocolError(
                        "Skipped " + magicIndex + " byte(s) before the LWRX magic.");
            }
            if (size < FrameProtocol.HEADER_BYTES) {
                return;
            }

            ByteBuffer header = ByteBuffer
                    .wrap(buffer, 0, FrameProtocol.HEADER_BYTES)
                    .order(ByteOrder.LITTLE_ENDIAN);
            header.position(4);
            int version = header.get() & 0xFF;
            int type = header.get() & 0xFF;
            int flags = header.getShort() & 0xFFFF;
            long payloadLength = Integer.toUnsignedLong(header.getInt());
            long expectedCrc = Integer.toUnsignedLong(header.getInt());

            if (version != FrameProtocol.VERSION) {
                rejectHeader("Unsupported LWRX version " + version + ".");
                continue;
            }
            if (type != ReceiverFrame.TYPE_TEXT && type != ReceiverFrame.TYPE_IMAGE) {
                rejectHeader("Unsupported LWRX media type " + type + ".");
                continue;
            }
            if (flags != 0) {
                rejectHeader("Unsupported LWRX flags " + flags + ".");
                continue;
            }
            if (payloadLength > FrameProtocol.MAX_PAYLOAD_BYTES) {
                rejectHeader("LWRX payload exceeds the 8 MiB app limit.");
                continue;
            }

            int frameLength = FrameProtocol.HEADER_BYTES + (int) payloadLength;
            if (size < frameLength) {
                return;
            }
            byte[] payload = Arrays.copyOfRange(
                    buffer, FrameProtocol.HEADER_BYTES, frameLength);
            CRC32 crc = new CRC32();
            crc.update(payload);
            discard(frameLength);
            if (crc.getValue() != expectedCrc) {
                listener.onProtocolError("LWRX payload CRC32 mismatch.");
                continue;
            }
            listener.onFrame(new ReceiverFrame(type, payload));
        }
    }

    private void rejectHeader(String message) {
        discard(1);
        listener.onProtocolError(message);
    }

    private int findMagic() {
        int limit = size - FrameProtocol.MAGIC.length;
        for (int offset = 0; offset <= limit; offset++) {
            boolean matches = true;
            for (int index = 0; index < FrameProtocol.MAGIC.length; index++) {
                if (buffer[offset + index] != FrameProtocol.MAGIC[index]) {
                    matches = false;
                    break;
                }
            }
            if (matches) {
                return offset;
            }
        }
        return -1;
    }

    private int retainPossibleMagicPrefix() {
        int maximum = Math.min(size, FrameProtocol.MAGIC.length - 1);
        for (int count = maximum; count > 0; count--) {
            boolean matches = true;
            for (int index = 0; index < count; index++) {
                if (buffer[size - count + index] != FrameProtocol.MAGIC[index]) {
                    matches = false;
                    break;
                }
            }
            if (matches) {
                System.arraycopy(buffer, size - count, buffer, 0, count);
                size = count;
                return count;
            }
        }
        size = 0;
        return 0;
    }

    private void discard(int count) {
        int remaining = size - count;
        if (remaining > 0) {
            System.arraycopy(buffer, count, buffer, 0, remaining);
        }
        size = remaining;
    }

    private void ensureCapacity(int required) {
        if (required <= buffer.length) {
            return;
        }
        int next = buffer.length;
        while (next < required) {
            next = Math.max(next * 2, required);
        }
        buffer = Arrays.copyOf(buffer, next);
    }
}
