package com.lightweave.mobile;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;

import org.junit.Test;

import java.util.ArrayList;
import java.util.List;

public final class ResultFrameParserTest {
    @Test
    public void parsesEveryMediaTypeAcrossSingleByteReads() {
        for (int type = ResultFrame.TYPE_TEXT; type <= ResultFrame.TYPE_STATUS; type++) {
            Collector collector = new Collector();
            ResultFrameParser parser = new ResultFrameParser(collector);
            byte[] payload = new byte[] {(byte) type, 0, (byte) 0xff, 0x55};
            byte[] frame = ResultProtocol.resultFrameForTest(type, "{\"test\":true}", payload);
            for (byte value : frame) {
                parser.accept(new byte[] {value});
            }
            assertEquals(1, collector.frames.size());
            assertEquals(0, collector.errors.size());
            assertEquals(type, collector.frames.get(0).type());
            assertEquals("{\"test\":true}", collector.frames.get(0).metadataJson());
            assertArrayEquals(payload, collector.frames.get(0).payload());
        }
    }

    @Test
    public void rejectsBadCrcAndResynchronizesToNextFrame() {
        Collector collector = new Collector();
        ResultFrameParser parser = new ResultFrameParser(collector);
        byte[] bad = ResultProtocol.resultFrameForTest(
                ResultFrame.TYPE_TEXT, "{\"id\":1}", "bad".getBytes());
        bad[bad.length - 1] ^= 1;
        byte[] good = ResultProtocol.resultFrameForTest(
                ResultFrame.TYPE_AUDIO, "{\"id\":2}", new byte[] {'R', 'I', 'F', 'F'});
        byte[] stream = new byte[] {9, 8, 7};
        stream = concatenate(stream, bad, good);
        parser.accept(stream);
        assertEquals(1, collector.errors.size());
        assertEquals(1, collector.frames.size());
        assertEquals(ResultFrame.TYPE_AUDIO, collector.frames.get(0).type());
    }

    @Test
    public void rejectsInvalidHeaderWithoutAllocatingDeclaredPayload() {
        Collector collector = new Collector();
        ResultFrameParser parser = new ResultFrameParser(collector);
        byte[] invalid = ResultProtocol.resultFrameForTest(
                ResultFrame.TYPE_IMAGE, "{\"id\":1}", new byte[] {1});
        invalid[4] = 99;
        parser.accept(invalid);
        assertEquals(1, collector.errors.size());
        assertEquals(0, collector.frames.size());
    }

    @Test
    public void parsesCanonicalPythonTextVector() {
        Collector collector = new Collector();
        ResultFrameParser parser = new ResultFrameParser(collector);
        parser.accept(hex(
                "4c575258020100001f000000020000000f47257a"
                        + "7b227072657365745f636f6465223a2254312d41534349492d42313030227d4f4b"));
        assertEquals(1, collector.frames.size());
        assertEquals(ResultFrame.TYPE_TEXT, collector.frames.get(0).type());
        assertEquals("{\"preset_code\":\"T1-ASCII-B100\"}",
                collector.frames.get(0).metadataJson());
        assertArrayEquals(new byte[] {'O', 'K'}, collector.frames.get(0).payload());
    }

    private static byte[] concatenate(byte[]... values) {
        int size = 0;
        for (byte[] value : values) size += value.length;
        byte[] output = new byte[size];
        int offset = 0;
        for (byte[] value : values) {
            System.arraycopy(value, 0, output, offset, value.length);
            offset += value.length;
        }
        return output;
    }

    private static byte[] hex(String text) {
        byte[] output = new byte[text.length() / 2];
        for (int index = 0; index < output.length; index++) {
            output[index] = (byte) Integer.parseInt(
                    text.substring(index * 2, index * 2 + 2), 16);
        }
        return output;
    }

    private static final class Collector implements ResultFrameParser.Listener {
        final List<ResultFrame> frames = new ArrayList<>();
        final List<String> errors = new ArrayList<>();

        @Override
        public void onFrame(ResultFrame frame) {
            frames.add(frame);
        }

        @Override
        public void onProtocolError(String message) {
            errors.add(message);
        }
    }
}
