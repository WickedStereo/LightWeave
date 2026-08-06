package com.lightweave.receiver;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;

import org.junit.Test;

public final class ReceiverStatsTest {
    @Test
    public void tracksWireBytesFramesAndErrorsIndependently() {
        ReceiverStats stats = new ReceiverStats();
        stats.recordWireBytes(20);
        stats.recordWireBytes(7);
        stats.recordFrame();
        stats.recordError();
        assertEquals(27, stats.wireBytes());
        assertEquals(1, stats.frames());
        assertEquals(1, stats.errors());

        stats.reset();
        assertEquals(0, stats.wireBytes());
        assertEquals(0, stats.frames());
        assertEquals(0, stats.errors());
    }

    @Test
    public void rejectsNegativeByteCounts() {
        ReceiverStats stats = new ReceiverStats();
        assertThrows(IllegalArgumentException.class, () -> stats.recordWireBytes(-1));
    }
}
