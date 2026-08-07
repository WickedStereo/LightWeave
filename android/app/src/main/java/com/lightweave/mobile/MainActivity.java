package com.lightweave.mobile;

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
import android.media.MediaPlayer;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public final class MainActivity extends Activity
        implements UsbLink.Listener, ResultFrameParser.Listener {
    private static final String ACTION_USB_PERMISSION =
            "com.lightweave.mobile.USB_PERMISSION";
    private static final int SAVE_REQUEST = 3107;
    private static final int MAX_LOG_CHARACTERS = 12_000;
    private static final long MAX_IMAGE_PIXELS = 16_000_000L;

    private UsbManager usbManager;
    private UsbLink usbLink;
    private ResultFrameParser parser;
    private TextView statusValue;
    private TextView deviceValue;
    private TextView resultSummary;
    private TextView textOutput;
    private ImageView imageOutput;
    private LinearLayout audioControls;
    private TextView evidenceValue;
    private TextView eventLog;
    private ProgressBar progress;
    private Button connectButton;
    private Button listenButton;
    private Button cancelButton;
    private Button saveButton;
    private byte[] currentPayload;
    private String currentMime;
    private String currentFilename;
    private File audioFile;
    private MediaPlayer mediaPlayer;

    private final BroadcastReceiver permissionReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (!ACTION_USB_PERMISSION.equals(intent.getAction())) {
                return;
            }
            UsbDevice device = usbDeviceExtra(intent);
            if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                    && UnoQDevice.matches(device)) {
                usbLink.connect(device);
            } else {
                showError("USB permission was denied.");
            }
        }
    };

    private final BroadcastReceiver usbEvents = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            UsbDevice device = usbDeviceExtra(intent);
            if (!UnoQDevice.matches(device)) {
                return;
            }
            if (UsbManager.ACTION_USB_DEVICE_DETACHED.equals(intent.getAction())) {
                usbLink.disconnect();
                parser.reset();
                refreshDevice();
            } else if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) {
                appendLog("UNO Q attached.");
                refreshDevice();
                connectUsb();
            }
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        boolean dark = getPreferences(MODE_PRIVATE).getBoolean("dark", false);
        setTheme(dark ? R.style.Theme_LightWeave_Dark : R.style.Theme_LightWeave_Light);
        super.onCreate(state);
        setContentView(R.layout.activity_main);

        usbManager = (UsbManager) getSystemService(Context.USB_SERVICE);
        usbLink = new UsbLink(this, this);
        parser = new ResultFrameParser(this);
        bindViews();
        registerUsbReceivers();

        findViewById(R.id.theme_button).setOnClickListener(view -> {
            boolean next = !getPreferences(MODE_PRIVATE).getBoolean("dark", false);
            getPreferences(MODE_PRIVATE).edit().putBoolean("dark", next).apply();
            recreate();
        });
        connectButton.setOnClickListener(view -> connectUsb());
        listenButton.setOnClickListener(view -> sendCommand(
                ResultProtocol.CONTROL_LISTEN, "Listen requested."));
        cancelButton.setOnClickListener(view -> sendCommand(
                ResultProtocol.CONTROL_CANCEL, "Cancel requested."));
        findViewById(R.id.play_button).setOnClickListener(view -> playAudio());
        findViewById(R.id.stop_button).setOnClickListener(view -> stopAudio());
        saveButton.setOnClickListener(view -> saveResult());

        refreshDevice();
        handleAttachIntent(getIntent());
        UsbDevice attached = usbLink.findUnoQ();
        if (attached != null && usbLink.hasPermission(attached)) {
            usbLink.connect(attached);
        }
    }

    private void bindViews() {
        statusValue = findViewById(R.id.status_value);
        deviceValue = findViewById(R.id.device_value);
        resultSummary = findViewById(R.id.result_summary);
        textOutput = findViewById(R.id.text_output);
        imageOutput = findViewById(R.id.image_output);
        audioControls = findViewById(R.id.audio_controls);
        evidenceValue = findViewById(R.id.evidence_value);
        eventLog = findViewById(R.id.event_log);
        progress = findViewById(R.id.progress);
        connectButton = findViewById(R.id.connect_button);
        listenButton = findViewById(R.id.listen_button);
        cancelButton = findViewById(R.id.cancel_button);
        saveButton = findViewById(R.id.save_button);
    }

    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    private void registerUsbReceivers() {
        IntentFilter permission = new IntentFilter(ACTION_USB_PERMISSION);
        IntentFilter events = new IntentFilter();
        events.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        events.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(permissionReceiver, permission, Context.RECEIVER_NOT_EXPORTED);
            registerReceiver(usbEvents, events, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(permissionReceiver, permission);
            registerReceiver(usbEvents, events);
        }
    }

    private void handleAttachIntent(Intent intent) {
        if (intent != null
                && UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) {
            UsbDevice device = usbDeviceExtra(intent);
            if (UnoQDevice.matches(device)) {
                deviceValue.setText(UnoQDevice.describe(device));
                connectUsb();
            }
        }
    }

    private void refreshDevice() {
        UsbDevice device = usbLink.findUnoQ();
        deviceValue.setText(UnoQDevice.describe(device));
        connectButton.setEnabled(device != null && !usbLink.isConnected());
        listenButton.setEnabled(usbLink.isConnected());
        cancelButton.setEnabled(usbLink.isConnected());
        if (device == null && !usbLink.isConnected()) {
            showStatus("Attach the receiver UNO Q over USB-C.", false);
        }
    }

    private void connectUsb() {
        UsbDevice device = usbLink.findUnoQ();
        if (device == null) {
            showError("UNO Q 2341:0078 was not found.");
            return;
        }
        deviceValue.setText(UnoQDevice.describe(device));
        if (usbLink.hasPermission(device)) {
            usbLink.connect(device);
            return;
        }
        Intent permissionIntent = new Intent(ACTION_USB_PERMISSION)
                .setPackage(getPackageName());
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            flags |= PendingIntent.FLAG_MUTABLE;
        }
        PendingIntent pending = PendingIntent.getBroadcast(this, 0, permissionIntent, flags);
        usbManager.requestPermission(device, pending);
        showStatus("Waiting for Android USB permission...", true);
    }

    private void sendCommand(int command, String log) {
        if (!usbLink.isConnected()) {
            showError("Connect the receiver UNO Q first.");
            return;
        }
        usbLink.send(ResultProtocol.controlFrame(command));
        appendLog(log);
        if (command == ResultProtocol.CONTROL_LISTEN) {
            showStatus("Arming optical receiver...", true);
        } else if (command == ResultProtocol.CONTROL_CANCEL) {
            showStatus("Cancelling optical listen...", true);
        }
    }

    @Override
    public void onUsbState(String state, boolean connected) {
        showStatus(state, !connected);
        connectButton.setEnabled(!connected && usbLink.findUnoQ() != null);
        listenButton.setEnabled(connected);
        cancelButton.setEnabled(connected);
        appendLog(state);
        if (connected) {
            usbLink.send(ResultProtocol.controlFrame(ResultProtocol.CONTROL_STATUS));
        }
    }

    @Override
    public void onUsbBytes(byte[] bytes) {
        parser.accept(bytes);
    }

    @Override
    public void onUsbWrite(int bytes) {
        appendLog("Sent " + bytes + " control bytes to UNO Q.");
    }

    @Override
    public void onUsbError(String message) {
        showError(message);
    }

    @Override
    public void onFrame(ResultFrame frame) {
        if (frame.type() == ResultFrame.TYPE_STATUS) {
            showReceiverStatus(frame);
            return;
        }
        JSONObject metadata;
        try {
            metadata = new JSONObject(frame.metadataJson());
        } catch (JSONException error) {
            showError("UNO Q result metadata is not a JSON object.");
            return;
        }
        clearMediaViews();
        if (frame.type() == ResultFrame.TYPE_TEXT) {
            showText(frame);
        } else if (frame.type() == ResultFrame.TYPE_IMAGE) {
            showImage(frame);
        } else if (frame.type() == ResultFrame.TYPE_AUDIO) {
            showAudio(frame);
        }
        if (currentPayload == null) {
            return;
        }
        currentFilename = metadata.optString("output_filename", defaultFilename(frame.type()));
        evidenceValue.setText(prettyMetadata(metadata, frame));
        String preset = metadata.optString("preset_code", "unknown preset");
        resultSummary.setText(String.format(
                Locale.US,
                "%s / %s / %,d decoded bytes",
                typeName(frame.type()),
                preset,
                frame.payloadLength()));
        saveButton.setEnabled(true);
        showStatus("Decoded result received from UNO Q.", false);
        appendLog("Accepted " + typeName(frame.type()) + " result with valid LWRX/2 CRC-32.");
    }

    private void showReceiverStatus(ResultFrame frame) {
        try {
            String value = decodeUtf8(frame.payload());
            JSONObject state = new JSONObject(value);
            String status = state.optString("status", "unknown");
            boolean working = status.equals("arming")
                    || status.equals("listening")
                    || status.equals("reconstructing")
                    || status.equals("cancelling");
            showStatus("Receiver: " + status, working);
            if (state.has("error")) {
                appendLog("Receiver error: " + state.optString("error"));
            }
        } catch (CharacterCodingException | JSONException error) {
            showError("UNO Q sent malformed receiver status.");
        }
    }

    private void showText(ResultFrame frame) {
        try {
            String text = decodeUtf8(frame.payload());
            textOutput.setText(text);
            textOutput.setVisibility(View.VISIBLE);
            currentPayload = frame.payload();
            currentMime = "text/plain";
        } catch (CharacterCodingException error) {
            showError("Decoded text is not valid UTF-8.");
        }
    }

    private void showImage(ResultFrame frame) {
        byte[] value = frame.payload();
        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(value, 0, value.length, bounds);
        long pixels = (long) bounds.outWidth * bounds.outHeight;
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0 || pixels > MAX_IMAGE_PIXELS) {
            showError("Decoded image is invalid or exceeds 16 megapixels.");
            return;
        }
        Bitmap bitmap = BitmapFactory.decodeByteArray(value, 0, value.length);
        if (bitmap == null) {
            showError("Android could not display the decoded PNG.");
            return;
        }
        imageOutput.setImageBitmap(bitmap);
        imageOutput.setVisibility(View.VISIBLE);
        currentPayload = value;
        currentMime = "image/png";
    }

    private void showAudio(ResultFrame frame) {
        try {
            audioFile = new File(getCacheDir(), "lightweave-received.wav");
            try (FileOutputStream output = new FileOutputStream(audioFile)) {
                output.write(frame.payload());
            }
            audioControls.setVisibility(View.VISIBLE);
            currentPayload = frame.payload();
            currentMime = "audio/wav";
        } catch (IOException error) {
            showError("Could not prepare decoded audio: " + error.getMessage());
        }
    }

    private void playAudio() {
        if (audioFile == null || !audioFile.isFile()) {
            showError("No decoded audio is available.");
            return;
        }
        stopAudio();
        mediaPlayer = new MediaPlayer();
        try {
            mediaPlayer.setDataSource(audioFile.getAbsolutePath());
            mediaPlayer.prepare();
            mediaPlayer.setOnCompletionListener(player -> stopAudio());
            mediaPlayer.start();
            appendLog("Playing decoded audio.");
        } catch (IOException | RuntimeException error) {
            stopAudio();
            showError("Android could not play the decoded WAV: " + error.getMessage());
        }
    }

    private void stopAudio() {
        if (mediaPlayer != null) {
            try {
                mediaPlayer.stop();
            } catch (IllegalStateException ignored) {
                // A prepare failure can leave MediaPlayer before the started state.
            }
            mediaPlayer.release();
            mediaPlayer = null;
        }
    }

    private void saveResult() {
        if (currentPayload == null || currentMime == null || currentFilename == null) {
            showError("No decoded result is available to save.");
            return;
        }
        Intent create = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType(currentMime)
                .putExtra(Intent.EXTRA_TITLE, currentFilename);
        startActivityForResult(create, SAVE_REQUEST);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != SAVE_REQUEST
                || resultCode != RESULT_OK
                || data == null
                || data.getData() == null
                || currentPayload == null) {
            return;
        }
        try (OutputStream output = getContentResolver().openOutputStream(data.getData())) {
            if (output == null) {
                throw new IOException("Android did not provide an output stream.");
            }
            output.write(currentPayload);
            appendLog("Saved decoded result.");
        } catch (IOException error) {
            showError("Could not save result: " + error.getMessage());
        }
    }

    @Override
    public void onProtocolError(String message) {
        showError(message);
    }

    private void clearMediaViews() {
        stopAudio();
        textOutput.setText(null);
        textOutput.setVisibility(View.GONE);
        imageOutput.setImageDrawable(null);
        imageOutput.setVisibility(View.GONE);
        audioControls.setVisibility(View.GONE);
        currentPayload = null;
        currentMime = null;
        currentFilename = null;
        saveButton.setEnabled(false);
    }

    private String prettyMetadata(JSONObject metadata, ResultFrame frame) {
        try {
            JSONObject display = new JSONObject(metadata.toString());
            display.put("downstream_crc32", String.format(Locale.US, "%08x", frame.crc32()));
            display.put("downstream_media_bytes", frame.payloadLength());
            return display.toString(2);
        } catch (JSONException error) {
            return metadata.toString();
        }
    }

    private static String decodeUtf8(byte[] bytes) throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    private static String typeName(int type) {
        if (type == ResultFrame.TYPE_TEXT) return "TEXT";
        if (type == ResultFrame.TYPE_IMAGE) return "IMAGE";
        if (type == ResultFrame.TYPE_AUDIO) return "AUDIO";
        return "STATUS";
    }

    private static String defaultFilename(int type) {
        if (type == ResultFrame.TYPE_TEXT) return "lightweave.txt";
        if (type == ResultFrame.TYPE_IMAGE) return "lightweave.png";
        return "lightweave.wav";
    }

    private void showStatus(String message, boolean busy) {
        statusValue.setText(message);
        progress.setVisibility(busy ? View.VISIBLE : View.GONE);
    }

    private void showError(String message) {
        statusValue.setText(getString(R.string.error_status, message));
        progress.setVisibility(View.GONE);
        appendLog("ERROR / " + message);
    }

    private void appendLog(String message) {
        String value = eventLog.getText().toString() + "\n" + message;
        if (value.length() > MAX_LOG_CHARACTERS) {
            value = value.substring(value.length() - MAX_LOG_CHARACTERS);
        }
        eventLog.setText(value);
    }

    @Override
    protected void onDestroy() {
        unregisterReceiver(permissionReceiver);
        unregisterReceiver(usbEvents);
        stopAudio();
        usbLink.close();
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
