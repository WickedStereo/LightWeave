package com.lightweave.receiver;

import android.content.Context;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
import android.os.Handler;
import android.os.Looper;

import com.hoho.android.usbserial.driver.UsbSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialPort;
import com.hoho.android.usbserial.driver.UsbSerialProber;
import com.hoho.android.usbserial.util.SerialInputOutputManager;

import java.io.IOException;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class UsbSerialController
        implements AutoCloseable, SerialInputOutputManager.Listener {
    public static final int BAUD_RATE = 115200;

    public interface Listener {
        void onState(String state, boolean connected);
        void onBytes(byte[] bytes);
        void onError(String message);
    }

    private final UsbManager usbManager;
    private final Listener listener;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService operationExecutor = Executors.newSingleThreadExecutor();
    private final Object lock = new Object();

    private UsbDeviceConnection connection;
    private UsbSerialPort port;
    private SerialInputOutputManager inputOutputManager;
    private boolean opening;

    public UsbSerialController(Context context, Listener listener) {
        usbManager = (UsbManager) context.getSystemService(Context.USB_SERVICE);
        this.listener = listener;
    }

    public UsbDevice findUnoQ() {
        for (UsbDevice device : usbManager.getDeviceList().values()) {
            if (UnoQIdentity.matches(device)) {
                return device;
            }
        }
        return null;
    }

    public boolean hasPermission(UsbDevice device) {
        return device != null && usbManager.hasPermission(device);
    }

    public boolean isConnected() {
        synchronized (lock) {
            return port != null;
        }
    }

    public void connect(UsbDevice device) {
        if (!UnoQIdentity.matches(device)) {
            postError("The selected USB device is not UNO Q 2341:0078.");
            return;
        }
        if (!usbManager.hasPermission(device)) {
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
        operationExecutor.execute(() -> open(device));
    }

    private void open(UsbDevice device) {
        UsbSerialDriver driver = findDriver(device);
        if (driver == null) {
            finishOpening();
            postError(
                    "UNO Q is attached, but Android did not find a CDC/ACM serial interface.");
            return;
        }
        if (driver.getPorts().isEmpty()) {
            finishOpening();
            postError("The UNO Q USB serial driver exposed no ports.");
            return;
        }

        UsbDeviceConnection openedConnection = usbManager.openDevice(device);
        if (openedConnection == null) {
            finishOpening();
            postError("Android could not open the UNO Q. Reconnect it and grant permission.");
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
                // Some CDC gadgets do not expose control-line state.
            }

            SerialInputOutputManager manager =
                    new SerialInputOutputManager(openedPort, this);
            synchronized (lock) {
                connection = openedConnection;
                port = openedPort;
                inputOutputManager = manager;
                opening = false;
            }
            manager.start();
            postState("USB connected - reading framed text and images", true);
        } catch (IOException | RuntimeException error) {
            try {
                openedPort.close();
            } catch (IOException ignored) {
                // The original open/configuration error is more useful.
            }
            openedConnection.close();
            finishOpening();
            postError("Could not configure UNO Q USB serial: " + safeMessage(error));
        }
    }

    private UsbSerialDriver findDriver(UsbDevice device) {
        List<UsbSerialDriver> drivers =
                UsbSerialProber.getDefaultProber().findAllDrivers(usbManager);
        for (UsbSerialDriver driver : drivers) {
            if (driver.getDevice().getDeviceId() == device.getDeviceId()) {
                return driver;
            }
        }
        return null;
    }

    public void disconnect() {
        SerialInputOutputManager manager;
        UsbSerialPort openedPort;
        UsbDeviceConnection openedConnection;
        synchronized (lock) {
            opening = false;
            manager = inputOutputManager;
            openedPort = port;
            openedConnection = connection;
            inputOutputManager = null;
            port = null;
            connection = null;
        }
        if (manager != null) {
            manager.stop();
        }
        if (openedPort != null) {
            try {
                openedPort.close();
            } catch (IOException ignored) {
                // Disconnect remains best-effort after the device is removed.
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
        mainHandler.post(() -> listener.onBytes(copy));
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
        mainHandler.post(() -> listener.onState(state, connected));
    }

    private void postError(String message) {
        mainHandler.post(() -> listener.onError(message));
    }

    @Override
    public void close() {
        disconnect();
        operationExecutor.shutdownNow();
    }
}
