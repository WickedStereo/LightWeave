package com.lightweave.receiver;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class UnoQIdentityTest {
    @Test
    public void matchesOnlyObservedUnoQUsbIdentity() {
        assertTrue(UnoQIdentity.matches(0x2341, 0x0078));
        assertFalse(UnoQIdentity.matches(0x2341, 0x0079));
        assertFalse(UnoQIdentity.matches(0x1234, 0x0078));
    }
}
