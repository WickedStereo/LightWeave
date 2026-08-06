package com.lightweave.receiver;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.Test;

public final class ReceiverFrameParserTest {
    @Test
    public void parsesAFrameSplitAcrossArbitraryUsbReads() {
        Capture capture = new Capture();
        ReceiverFrameParser parser = new ReceiverFrameParser(capture);
        byte[] payload = "hello from UNO Q".getBytes(StandardCharsets.UTF_8);
        byte[] encoded = FrameProtocol.encode(ReceiverFrame.TYPE_TEXT, payload);

        parser.accept(Arrays.copyOfRange(encoded, 0, 3));
        parser.accept(Arrays.copyOfRange(encoded, 3, 11));
        parser.accept(Arrays.copyOfRange(encoded, 11, encoded.length));

        assertEquals(1, capture.frames.size());
        assertEquals(ReceiverFrame.TYPE_TEXT, capture.frames.get(0).type());
        assertArrayEquals(payload, capture.frames.get(0).payload());
        assertEquals(0, capture.errors.size());
    }

    @Test
    public void parsesBackToBackTextAndImageFrames() {
        Capture capture = new Capture();
        ReceiverFrameParser parser = new ReceiverFrameParser(capture);
        byte[] text = FrameProtocol.encode(
                ReceiverFrame.TYPE_TEXT, "ok".getBytes(StandardCharsets.UTF_8));
        byte[] imagePayload = new byte[] {(byte) 0x89, 'P', 'N', 'G'};
        byte[] image = FrameProtocol.encode(ReceiverFrame.TYPE_IMAGE, imagePayload);
        byte[] combined = new byte[text.length + image.length];
        System.arraycopy(text, 0, combined, 0, text.length);
        System.arraycopy(image, 0, combined, text.length, image.length);

        parser.accept(combined);

        assertEquals(2, capture.frames.size());
        assertEquals(ReceiverFrame.TYPE_TEXT, capture.frames.get(0).type());
        assertEquals(ReceiverFrame.TYPE_IMAGE, capture.frames.get(1).type());
        assertArrayEquals(imagePayload, capture.frames.get(1).payload());
    }

    @Test
    public void rejectsCorruptPayloadAndResynchronizes() {
        Capture capture = new Capture();
        ReceiverFrameParser parser = new ReceiverFrameParser(capture);
        byte[] corrupt = FrameProtocol.encode(
                ReceiverFrame.TYPE_TEXT, "bad".getBytes(StandardCharsets.UTF_8));
        corrupt[corrupt.length - 1] ^= 0x01;
        byte[] valid = FrameProtocol.encode(
                ReceiverFrame.TYPE_TEXT, "good".getBytes(StandardCharsets.UTF_8));
        byte[] combined = new byte[corrupt.length + valid.length];
        System.arraycopy(corrupt, 0, combined, 0, corrupt.length);
        System.arraycopy(valid, 0, combined, corrupt.length, valid.length);

        parser.accept(combined);

        assertEquals(1, capture.frames.size());
        assertArrayEquals(
                "good".getBytes(StandardCharsets.UTF_8), capture.frames.get(0).payload());
        assertTrue(capture.errors.stream().anyMatch(value -> value.contains("CRC32")));
    }

    @Test
    public void reportsAndSkipsGarbageBeforeMagic() {
        Capture capture = new Capture();
        ReceiverFrameParser parser = new ReceiverFrameParser(capture);
        parser.accept(new byte[] {1, 2, 3});
        parser.accept(FrameProtocol.encode(
                ReceiverFrame.TYPE_TEXT, "ok".getBytes(StandardCharsets.UTF_8)));

        assertEquals(1, capture.frames.size());
        assertTrue(capture.errors.stream().anyMatch(value -> value.contains("Discarded")));
    }

    private static final class Capture implements ReceiverFrameParser.Listener {
        private final List<ReceiverFrame> frames = new ArrayList<>();
        private final List<String> errors = new ArrayList<>();

        @Override
        public void onFrame(ReceiverFrame frame) {
            frames.add(frame);
        }

        @Override
        public void onProtocolError(String message) {
            errors.add(message);
        }
    }
}
