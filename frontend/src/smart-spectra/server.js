import "dotenv/config";
import { WebSocketServer, WebSocket } from "ws";
import {
  SmartSpectraSDK,
  PixelFormat,
  breathingMetrics,
  cardioMetrics,
  decodeMetrics,
} from "@smartspectra/node-sdk";

const PORT = Number(process.env.PORT ?? 3001);
const WEB_ORIGIN = process.env.WEB_ORIGIN;
const API_KEY = process.env.SMARTSPECTRA_API_KEY;

if (!API_KEY) {
  throw new Error("Missing SMARTSPECTRA_API_KEY");
}

const wss = new WebSocketServer({
  port: PORT,
  maxPayload: 2 * 1024 * 1024,

  verifyClient: ({ origin }, done) => {
    if (origin === WEB_ORIGIN) {
      done(true);
    } else {
      done(false, 403, "Origin not allowed");
    }
  },
});

// One SDK session per connected browser.
// Confirm concurrent-session licensing/capacity with Presage.
const sessions = new Map();

wss.on("connection", (ws) => {
  let sdk;
  let closing = false;

  const send = (message) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    }
  };

  try {
    sdk = new SmartSpectraSDK({
      apiKey: API_KEY,
      requestedMetrics: [
        ...breathingMetrics,
        ...cardioMetrics,
      ],
      enableTelemetry: false,
    });

    sdk.on("metrics", (buffer, timestampUs) => {
      console.log(buffer);
      send({
        type: "metrics",
        timestampUs,
        data: decodeMetrics(buffer),
      });
    });

    sdk.on("validationStatus", (code, timestampUs, hint) => {
      send({
        type: "validation",
        code,
        timestampUs,
        hint,
      });
    });

    sdk.on("processingStatus", (status) => {
      send({ type: "status", status });
    });

    sdk.on("error", (code, message, retryable) => {
      send({
        type: "error",
        code,
        message,
        retryable,
      });
    });

    sdk.useCustomInput();
    sdk.start();
    sessions.set(ws, sdk);

    send({ type: "ready" });
  } catch (error) {
    send({
      type: "error",
      message: "Could not start measurement session",
    });
    ws.close(1011, "SDK initialization failed");
    console.error("SDK initialization failed:", error);
    return;
  }

  ws.on("message", (data, isBinary) => {
    if (!isBinary || !sdk || closing) return;

    try {
      // Binary frame protocol:
      // 16-byte header:
      // uint32 width, uint32 height, uint64 timestampUs
      const packet = Buffer.from(data);

      if (packet.length < 16) return;

      const width = packet.readUInt32LE(0);
      const height = packet.readUInt32LE(4);
      const timestampUs = Number(packet.readBigUInt64LE(8));

      if (
        width < 1 ||
        height < 1 ||
        width > 1280 ||
        height > 720
      ) return;

      const expectedBytes = width * height * 4;
      if (packet.length !== 16 + expectedBytes) return;

      const pixels = packet.subarray(16);

      sdk.sendFrame(
        pixels,
        width,
        height,
        width * 4,
        PixelFormat.kRGBA,
        timestampUs,
      );
    } catch (error) {
      console.error("Frame processing error:", error);
      send({ type: "error", message: "Invalid video frame" });
    }
  });

  ws.on("close", () => {
    void cleanup();
  });

  ws.on("error", (error) => {
    console.error("WebSocket error:", error);
    void cleanup();
  });

  async function cleanup() {
    if (closing) return;
    closing = true;

    sessions.delete(ws);

    try {
      await sdk?.stopAsync();
      await sdk?.destroy();
    } catch (error) {
      console.error("SDK cleanup failed:", error);
    }
  }
});

wss.on("listening", () => {
  console.log(`SmartSpectra server listening on ${PORT}`);
});
