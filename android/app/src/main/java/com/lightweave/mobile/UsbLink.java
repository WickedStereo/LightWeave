package com.lightweave.mobile;

import android.content.Context;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
import android.os.Handler;
import android.os.Looper;

import com.hoho.android.usbserial.driver.CdcAcmSerialDriver;
import com.hoho.android.usbserial.driver.ProbeTable;
import com.hoho.android.usbserial.driver.UsbSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialPort;
import com.hoho.android.usbserial.driver.UsbSerialProber;
import com.hoho.android.usbserial.util.SerialInputOutputManager;

import java.io.IOException;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class UsbLink implements AutoCloseable, SerialInputOutputManager.Listener {
    public static final int BAUD_RATE = 115200;

    public interface Listener {
        void onUsbState(String state, boolean connected);
        void onUsbBytes(byte[] bytes);
        void onUsbWrite(int bytes);
        void onUsbError(String message);
    }

    private final UsbManager manager;
    private final Listener listener;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService operations = Executors.newSingleThreadExecutor();
    private final Object lock = new Object();
    private UsbDeviceConnection connection;
    private UsbSerialPort port;
    private SerialInputOutputManager ioManager;
    private boolean opening;

    public UsbLink(Context context, Listener listener) {
        manager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
        this.listener = listener;
    }

    public UsbDevice findUnoQ() {
        for (UsbDevice device : manager.getDeviceList().values()) {
            if (UnoQDevice.matches(device)) {
                return device;
            }
        }
        return null;
    }

    public boolean hasPermission(UsbDevice device) {
        return device != null && manager.hasPermission(device);
    }

    public boolean isConnected() {
        synchronized (lock) {
            return port != null;
        }
    }

    public void connect(UsbDevice device) {
        if (!UnoQDevice.matches(device)) {
            postError("The selected USB device is not UNO Q 2341:0078.");
            return;
        }
        if (!manager.hasPermission(device)) {
            postError("Android USB permission has not been granted.");
            return;
        }
        synchronized (lock) {
            if (opening || port != null) {
                return;
            }
            opening = true;
        }
        postState("Opening UNO Q USB serial...", false);
        operations.execute(() -> open(device));
    }

    private void open(UsbDevice device) {
        UsbSerialDriver driver = findDriver(device);
        if (driver == null || driver.getPorts().isEmpty()) {
            finishOpening();
            postError("UNO Q is attached, but its CDC/ACM interface was not found.");
            return;
        }
        UsbDeviceConnection openedConnection = manager.openDevice(device);
        if (openedConnection == null) {
            finishOpening();
            postError("Android could not open UNO Q. Reconnect it and grant permission.");
            return;
        }
        UsbSerialPort openedPort = driver.getPorts().get(0);
        try {
            openedPort.open(openedConnection);
            openedPort.setParameters(
                    BAUD_RATE,
                    8,
                    UsbSerialPort.STOPBITS_1,
                    UsbSerialPort.PARITY_NONE);
            try {
                openedPort.setDTR(true);
                openedPort.setRTS(true);
            } catch (UnsupportedOperationException ignored) {
                // Control lines are optional for the UNO Q gadget endpoint.
            }
            SerialInputOutputManager reader = new SerialInputOutputManager(openedPort, this);
            synchronized (lock) {
                connection = openedConnection;
                port = openedPort;
                ioManager = reader;
                opening = false;
            }
            reader.start();
            postState("USB connected / receiver ready", true);
        } catch (IOException | RuntimeException error) {
            try {
                openedPort.close();
            } catch (IOException ignored) {
                // Preserve the first failure.
            }
            openedConnection.close();
            finishOpening();
            postError("Could not configure UNO Q USB: " + safeMessage(error));
        }
    }

    private UsbSerialDriver findDriver(UsbDevice device) {
        List<UsbSerialDriver> detected = UsbSerialProber.getDefaultProber()
                .findAllDrivers(manager);
        for (UsbSerialDriver driver : detected) {
            if (driver.getDevice().getDeviceId() == device.getDeviceId()) {
                return driver;
            }
        }
        ProbeTable custom = new ProbeTable();
        custom.addProduct(UnoQDevice.VENDOR_ID, UnoQDevice.PRODUCT_ID,
                CdcAcmSerialDriver.class);
        for (UsbSerialDriver driver : new UsbSerialProber(custom).findAllDrivers(manager)) {
            if (driver.getDevice().getDeviceId() == device.getDeviceId()) {
                return driver;
            }
        }
        return null;
    }

    public void send(byte[] data) {
        byte[] copy = Arrays.copyOf(data, data.length);
        operations.execute(() -> {
            UsbSerialPort openedPort;
            synchronized (lock) {
                openedPort = port;
            }
            if (openedPort == null) {
                postError("Connect UNO Q before sending a command.");
                return;
            }
            try {
                openedPort.write(copy, 3000);
                mainHandler.post(() -> listener.onUsbWrite(copy.length));
            } catch (IOException | RuntimeException error) {
                postError("USB command failed: " + safeMessage(error));
            }
        });
    }

    public void disconnect() {
        SerialInputOutputManager reader;
        UsbSerialPort openedPort;
        UsbDeviceConnection openedConnection;
        synchronized (lock) {
            opening = false;
            reader = ioManager;
            openedPort = port;
            openedConnection = connection;
            ioManager = null;
            port = null;
            connection = null;
        }
        if (reader != null) {
            reader.stop();
        }
        if (openedPort != null) {
            try {
                openedPort.close();
            } catch (IOException ignored) {
                // Best effort during detach.
            }
        }
        if (openedConnection != null) {
            openedConnection.close();
            postState("USB disconnected", false);
        }
    }

    @Override
    public void onNewData(byte[] data) {
        byte[] copy = Arrays.copyOf(data, data.length);
        mainHandler.post(() -> listener.onUsbBytes(copy));
    }

    @Override
    public void onRunError(Exception error) {
        disconnect();
        postError("UNO Q USB read stopped: " + safeMessage(error));
    }

    private void finishOpening() {
        synchronized (lock) {
            opening = false;
        }
    }

    private static String safeMessage(Throwable error) {
        String message = error.getMessage();
        return message == null || message.isBlank()
                ? error.getClass().getSimpleName()
                : message;
    }

    private void postState(String state, boolean connected) {
        mainHandler.post(() -> listener.onUsbState(state, connected));
    }

    private void postError(String message) {
        mainHandler.post(() -> listener.onUsbError(message));
    }

    @Override
    public void close() {
        disconnect();
        operations.shutdownNow();
    }
}
