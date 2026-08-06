package com.lightweave.receiver;

public final class ReceiverStats {
    private long wireBytes;
    private long frames;
    private long errors;

    public void recordWireBytes(int byteCount) {
        if (byteCount < 0) {
            throw new IllegalArgumentException("byteCount must be non-negative");
        }
        wireBytes += byteCount;
    }

    public void recordFrame() {
        frames += 1;
    }

    public void recordError() {
        errors += 1;
    }

    public long wireBytes() {
        return wireBytes;
    }

    public long frames() {
        return frames;
    }

    public long errors() {
        return errors;
    }

    public void reset() {
        wireBytes = 0;
        frames = 0;
        errors = 0;
    }
}
