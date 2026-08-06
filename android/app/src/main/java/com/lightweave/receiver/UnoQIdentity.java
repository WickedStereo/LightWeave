package com.lightweave.receiver;

import android.hardware.usb.UsbDevice;

import java.util.Locale;

public final class UnoQIdentity {
    public static final int VENDOR_ID = 0x2341;
    public static final int PRODUCT_ID = 0x0078;

    private UnoQIdentity() {}

    public static boolean matches(int vendorId, int productId) {
        return vendorId == VENDOR_ID && productId == PRODUCT_ID;
    }

    public static boolean matches(UsbDevice device) {
        return device != null && matches(device.getVendorId(), device.getProductId());
    }

    public static String displayName(UsbDevice device) {
        if (device == null) {
            return "UNO Q 2341:0078 not attached";
        }
        return String.format(
                Locale.ROOT,
                "Arduino UNO Q · %04X:%04X · %d interface%s",
                device.getVendorId(),
                device.getProductId(),
                device.getInterfaceCount(),
                device.getInterfaceCount() == 1 ? "" : "s");
    }
}
