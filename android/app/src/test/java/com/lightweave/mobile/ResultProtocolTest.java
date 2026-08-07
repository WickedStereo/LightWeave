package com.lightweave.mobile;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;

import org.junit.Test;

public final class ResultProtocolTest {
    @Test
    public void controlFramesAreFixedAndDeterministic() {
        assertEquals(12, ResultProtocol.controlFrame(ResultProtocol.CONTROL_LISTEN).length);
        assertArrayEquals(
                hex("4c5743540101000069c34300"),
                ResultProtocol.controlFrame(ResultProtocol.CONTROL_LISTEN));
        assertArrayEquals(
                hex("4c57435401020000307d0502"),
                ResultProtocol.controlFrame(ResultProtocol.CONTROL_CANCEL));
        assertArrayEquals(
                hex("4c574354010300000717c703"),
                ResultProtocol.controlFrame(ResultProtocol.CONTROL_STATUS));
    }

    @Test
    public void rejectsUnknownControlCommand() {
        assertThrows(IllegalArgumentException.class, () -> ResultProtocol.controlFrame(4));
    }

    private static byte[] hex(String text) {
        byte[] output = new byte[text.length() / 2];
        for (int index = 0; index < output.length; index++) {
            output[index] = (byte) Integer.parseInt(text.substring(index * 2, index * 2 + 2), 16);
        }
        return output;
    }
}
