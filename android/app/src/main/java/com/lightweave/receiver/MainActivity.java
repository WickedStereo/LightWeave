package com.lightweave.receiver;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbManager;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.TextView;

import java.nio.charset.CharacterCodingException;

public final class MainActivity extends Activity
        implements UsbSerialController.Listener, ReceiverFrameParser.Listener {
    private static final String ACTION_USB_PERMISSION =
            "com.lightweave.receiver.USB_PERMISSION";
    private static final int MAX_EVENT_LOG_CHARACTERS = 12_288;
    private static final long MAX_IMAGE_PIXELS = 16_000_000L;

    private UsbManager usbManager;
    private UsbSerialController serialController;
    private ReceiverFrameParser frameParser;
    private final ReceiverStats stats = new ReceiverStats();

    private TextView statusValue;
    private TextView deviceValue;
    private TextView bytesValue;
    private TextView framesValue;
    private TextView errorsValue;
    private TextView contentType;
    private TextView receivedText;
    private ImageView receivedImage;
    private TextView eventLog;
    private Button connectButton;
    private boolean eventLogIsPlaceholder = true;

    private final BroadcastReceiver permissionReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (!ACTION_USB_PERMISSION.equals(intent.getAction())) {
                return;
            }
            UsbDevice device = usbDeviceExtra(intent);
            if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                    && UnoQIdentity.matches(device)) {
                serialController.connect(device);
            } else {
                showError("USB permission was denied.");
            }
        }
    };

    private final BroadcastReceiver usbEventReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            UsbDevice device = usbDeviceExtra(intent);
            if (!UnoQIdentity.matches(device)) {
                return;
            }
            if (UsbManager.ACTION_USB_DEVICE_DETACHED.equals(intent.getAction())) {
                serialController.disconnect();
                frameParser.reset();
                refreshUsbDevice();
            } else if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) {
                appendEvent("UNO Q attached.");
                refreshUsbDevice();
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        usbManager = (UsbManager) getSystemService(Context.USB_SERVICE);
        serialController = new UsbSerialController(this, this);
        frameParser = new ReceiverFrameParser(this);

        statusValue = findViewById(R.id.status_value);
        deviceValue = findViewById(R.id.device_value);
        bytesValue = findViewById(R.id.bytes_value);
        framesValue = findViewById(R.id.frames_value);
        errorsValue = findViewById(R.id.errors_value);
        contentType = findViewById(R.id.content_type);
        receivedText = findViewById(R.id.received_text);
        receivedImage = findViewById(R.id.received_image);
        eventLog = findViewById(R.id.event_log);
        connectButton = findViewById(R.id.connect_button);
        Button demoTextButton = findViewById(R.id.demo_text_button);
        Button demoImageButton = findViewById(R.id.demo_image_button);
        Button clearButton = findViewById(R.id.clear_button);

        connectButton.setOnClickListener(view -> connectUsb());
        demoTextButton.setOnClickListener(view -> injectDemo("text", DemoFrames.text()));
        demoImageButton.setOnClickListener(view -> injectDemo("image", DemoFrames.image()));
        clearButton.setOnClickListener(view -> clearResults());

        registerUsbReceivers();
        handleAttachIntent(getIntent());
        refreshUsbDevice();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleAttachIntent(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshUsbDevice();
    }

    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    private void registerUsbReceivers() {
        IntentFilter permissionFilter = new IntentFilter(ACTION_USB_PERMISSION);
        IntentFilter usbFilter = new IntentFilter();
        usbFilter.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        usbFilter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(permissionReceiver, permissionFilter, Context.RECEIVER_NOT_EXPORTED);
            registerReceiver(usbEventReceiver, usbFilter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(permissionReceiver, permissionFilter);
            registerReceiver(usbEventReceiver, usbFilter);
        }
    }

    private void handleAttachIntent(Intent intent) {
        if (intent != null
                && UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) {
            UsbDevice device = usbDeviceExtra(intent);
            if (UnoQIdentity.matches(device)) {
                deviceValue.setText(UnoQIdentity.displayName(device));
            }
        }
    }

    private void refreshUsbDevice() {
        UsbDevice device = serialController.findUnoQ();
        deviceValue.setText(UnoQIdentity.displayName(device));
        connectButton.setEnabled(device != null && !serialController.isConnected());
        if (device == null && !serialController.isConnected()) {
            showWaiting("UNO Q is not attached - text/image demos are available");
        }
    }

    private void connectUsb() {
        UsbDevice device = serialController.findUnoQ();
        if (device == null) {
            showError("UNO Q 2341:0078 was not found.");
            return;
        }
        if (serialController.hasPermission(device)) {
            serialController.connect(device);
            return;
        }
        Intent permissionIntent = new Intent(ACTION_USB_PERMISSION)
                .setPackage(getPackageName());
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            flags |= PendingIntent.FLAG_MUTABLE;
        }
        PendingIntent pendingIntent =
                PendingIntent.getBroadcast(this, 0, permissionIntent, flags);
        usbManager.requestPermission(device, pendingIntent);
        showWaiting("Waiting for Android USB permission...");
    }

    private void injectDemo(String label, byte[] frame) {
        appendEvent("Injecting local " + label + " demo frame.");
        showConnected("Local demo - no USB hardware claim");
        onBytes(frame);
    }

    @Override
    public void onBytes(byte[] bytes) {
        stats.recordWireBytes(bytes.length);
        updateCounters();
        frameParser.accept(bytes);
    }

    @Override
    public void onFrame(ReceiverFrame frame) {
        stats.recordFrame();
        updateCounters();
        if (frame.type() == ReceiverFrame.TYPE_TEXT) {
            showTextFrame(frame);
        } else if (frame.type() == ReceiverFrame.TYPE_IMAGE) {
            showImageFrame(frame);
        }
    }

    private void showTextFrame(ReceiverFrame frame) {
        try {
            String text = FramePayloads.decodeUtf8(frame.payload());
            contentType.setText(getString(R.string.received_text, frame.payloadLength()));
            receivedText.setText(text);
            receivedText.setVisibility(View.VISIBLE);
            receivedImage.setImageDrawable(null);
            receivedImage.setVisibility(View.GONE);
            appendEvent("Displayed UTF-8 text frame (" + frame.payloadLength() + " bytes).");
        } catch (CharacterCodingException error) {
            recordContentError("Text frame is not valid UTF-8.");
        }
    }

    private void showImageFrame(ReceiverFrame frame) {
        byte[] payload = frame.payload();
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(payload, 0, payload.length, bounds);
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            recordContentError("Image frame is not a supported PNG or JPEG.");
            return;
        }
        long pixels = (long) bounds.outWidth * bounds.outHeight;
        if (pixels > MAX_IMAGE_PIXELS) {
            recordContentError("Image dimensions exceed the 16-megapixel app limit.");
            return;
        }
        Bitmap bitmap = BitmapFactory.decodeByteArray(payload, 0, payload.length);
        if (bitmap == null) {
            recordContentError("Android could not decode the received image.");
            return;
        }
        contentType.setText(getString(
                R.string.received_image,
                frame.payloadLength(),
                bitmap.getWidth(),
                bitmap.getHeight()));
        receivedText.setText(null);
        receivedText.setVisibility(View.GONE);
        receivedImage.setImageBitmap(bitmap);
        receivedImage.setVisibility(View.VISIBLE);
        appendEvent(
                "Displayed image frame ("
                        + frame.payloadLength()
                        + " bytes, "
                        + bitmap.getWidth()
                        + "x"
                        + bitmap.getHeight()
                        + ").");
    }

    @Override
    public void onProtocolError(String message) {
        stats.recordError();
        updateCounters();
        showError(message);
    }

    private void recordContentError(String message) {
        stats.recordError();
        updateCounters();
        showError(message);
    }

    private void clearResults() {
        frameParser.reset();
        stats.reset();
        updateCounters();
        contentType.setText(R.string.content_waiting);
        receivedText.setText(null);
        receivedText.setVisibility(View.GONE);
        receivedImage.setImageDrawable(null);
        receivedImage.setVisibility(View.GONE);
        eventLog.setText(R.string.empty_log);
        eventLogIsPlaceholder = true;
    }

    private void updateCounters() {
        bytesValue.setText(getString(R.string.count_value, stats.wireBytes()));
        framesValue.setText(getString(R.string.count_value, stats.frames()));
        errorsValue.setText(getString(R.string.count_value, stats.errors()));
    }

    private void appendEvent(String message) {
        String current = eventLogIsPlaceholder ? "" : eventLog.getText().toString();
        String combined = current + message + "\n";
        if (combined.length() > MAX_EVENT_LOG_CHARACTERS) {
            combined = combined.substring(combined.length() - MAX_EVENT_LOG_CHARACTERS);
        }
        eventLog.setText(combined);
        eventLogIsPlaceholder = false;
    }

    private void showWaiting(String message) {
        statusValue.setText(message);
        statusValue.setTextColor(getColor(R.color.amber));
        statusValue.setBackgroundResource(R.drawable.status_waiting);
    }

    private void showConnected(String message) {
        statusValue.setText(message);
        statusValue.setTextColor(getColor(R.color.mint));
        statusValue.setBackgroundResource(R.drawable.status_connected);
    }

    private void showError(String message) {
        statusValue.setText(message);
        statusValue.setTextColor(getColor(R.color.coral));
        statusValue.setBackgroundResource(R.drawable.status_error);
        appendEvent("ERROR: " + message);
    }

    @Override
    public void onState(String state, boolean connected) {
        if (connected) {
            showConnected(state);
        } else {
            showWaiting(state);
        }
        appendEvent(state);
        connectButton.setEnabled(!connected && serialController.findUnoQ() != null);
    }

    @Override
    public void onError(String message) {
        showError(message);
        connectButton.setEnabled(serialController.findUnoQ() != null);
    }

    @Override
    protected void onDestroy() {
        unregisterReceiver(permissionReceiver);
        unregisterReceiver(usbEventReceiver);
        serialController.close();
        super.onDestroy();
    }

    @SuppressWarnings("deprecation")
    private static UsbDevice usbDeviceExtra(Intent intent) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return intent.getParcelableExtra(UsbManager.EXTRA_DEVICE, UsbDevice.class);
        }
        return intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
    }
}
