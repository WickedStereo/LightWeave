package com.lightweave.receiver;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Shader;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public final class DemoFrames {
    private DemoFrames() {}

    public static byte[] text() {
        String message = "LightWeave receiver online.\n"
                + "UNO Q reconstruction complete.\n"
                + "Direct USB-C link ready for text and images.";
        return FrameProtocol.encode(
                ReceiverFrame.TYPE_TEXT,
                message.getBytes(StandardCharsets.UTF_8));
    }

    public static byte[] image() {
        int width = 960;
        int height = 540;
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);

        Paint background = new Paint(Paint.ANTI_ALIAS_FLAG);
        background.setShader(new LinearGradient(
                0,
                0,
                width,
                height,
                Color.rgb(5, 19, 15),
                Color.rgb(20, 62, 47),
                Shader.TileMode.CLAMP));
        canvas.drawRect(0, 0, width, height, background);

        Paint beam = new Paint(Paint.ANTI_ALIAS_FLAG);
        beam.setColor(Color.rgb(115, 242, 181));
        beam.setStrokeWidth(9f);
        beam.setStyle(Paint.Style.STROKE);
        float middle = height * 0.52f;
        for (int index = 0; index < 5; index++) {
            float inset = 90f + index * 36f;
            canvas.drawLine(inset, middle, width - inset, middle, beam);
            middle += index % 2 == 0 ? 24f : -36f;
        }

        Paint title = new Paint(Paint.ANTI_ALIAS_FLAG);
        title.setColor(Color.WHITE);
        title.setTextSize(82f);
        title.setFakeBoldText(true);
        canvas.drawText("LIGHTWEAVE", 76f, 145f, title);

        Paint subtitle = new Paint(Paint.ANTI_ALIAS_FLAG);
        subtitle.setColor(Color.rgb(169, 196, 184));
        subtitle.setTextSize(34f);
        canvas.drawText("IMAGE RECONSTRUCTED ON UNO Q", 80f, 205f, subtitle);
        canvas.drawText("DELIVERED TO GALAXY OVER USB-C", 80f, 450f, subtitle);

        ByteArrayOutputStream png = new ByteArrayOutputStream();
        if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, png)) {
            throw new IllegalStateException("Could not create the demo PNG.");
        }
        bitmap.recycle();
        return FrameProtocol.encode(ReceiverFrame.TYPE_IMAGE, png.toByteArray());
    }
}
