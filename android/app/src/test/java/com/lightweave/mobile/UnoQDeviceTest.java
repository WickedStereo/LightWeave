package com.lightweave.mobile;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class UnoQDeviceTest {
    @Test
    public void matchesOnlyObservedUnoQIdentity() {
        assertTrue(UnoQDevice.matches(0x2341, 0x0078));
        assertFalse(UnoQDevice.matches(0x2341, 0x0079));
        assertFalse(UnoQDevice.matches(0x04e8, 0x6860));
    }
}
