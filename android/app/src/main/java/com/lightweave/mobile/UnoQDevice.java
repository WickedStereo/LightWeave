package com.lightweave.mobile;

import android.hardware.usb.UsbDevice;

public final class UnoQDevice {
    public static final int VENDOR_ID = 0x2341;
    public static final int PRODUCT_ID = 0x0078;

    private UnoQDevice() {}

    public static boolean matches(int vendorId, int productId) {
        return vendorId == VENDOR_ID && productId == PRODUCT_ID;
    }

    public static boolean matches(UsbDevice device) {
        return device != null && matches(device.getVendorId(), device.getProductId());
    }

    public static String describe(UsbDevice device) {
        if (device == null) {
            return "Device: not attached";
        }
        return String.format(
                "Device: UNO Q %04x:%04x / %s",
                device.getVendorId(),
                device.getProductId(),
                device.getDeviceName());
    }
}
