package com.lightweave.receiver;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;

import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;

import org.junit.Test;

public final class FramePayloadsTest {
    @Test
    public void decodesValidUtf8() throws Exception {
        assertEquals(
                "LightWeave - hello",
                FramePayloads.decodeUtf8(
                        "LightWeave - hello".getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    public void rejectsMalformedUtf8() {
        assertThrows(
                CharacterCodingException.class,
                () -> FramePayloads.decodeUtf8(new byte[] {(byte) 0xC3, 0x28}));
    }
}
