import "dotenv/config";
import { WebSocketServer, WebSocket } from "ws";
import {
  SmartSpectraSDK,
  PixelFormat,
  ProcessingStatus,
  SmartSpectraErrorCode,
  breathingMetrics,
  cardioMetrics,
  decodeMetrics,
} from "@smartspectra/node-sdk";

/**
 * Flatten one decoded Metrics message to what the browser shows and reports.
 *
 * The protobuf nests readings as time series (`cardio.pulseRate[]`, `breathing.rate[]`);
 * the UI and POST /vitals both want flat numbers, so take the newest sample of each.
 */
function summarize(metrics) {
  const newest = (series) => (series?.length ? series[series.length - 1] : undefined);
  const round1 = (n) => Math.round(n * 10) / 10;
  const out = {};

  const pulse = newest(metrics.cardio?.pulseRate);
  if (Number.isFinite(pulse?.value)) {
    out.pulse = round1(pulse.value);
    if (Number.isFinite(pulse.confidence)) out.pulse_confidence = round1(pulse.confidence);
  }
  const breathing = newest(metrics.breathing?.rate);
  if (Number.isFinite(breathing?.value)) {
    out.breathing = round1(breathing.value);
    if (Number.isFinite(breathing.confidence)) {
      out.breathing_confidence = round1(breathing.confidence);
    }
  }
  return out;
}

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
  let reachedRunning = false;
  // Frames already in flight keep arriving until the close completes; drop them.
  let failed = false;

  const send = (message) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    }
  };

  // A session the SDK has given up on rejects every frame with kInvalidState, which at
  // 30 fps is a flood of identical errors and a browser stuck on "Invalid video frame".
  // Say what happened once and hang up; the browser shows it instead of "Vitals offline".
  const fail = (message) => {
    if (closing || failed) return;
    failed = true;
    console.error(`session ended: ${message}`);
    send({ type: "error", fatal: true, message });
    ws.close(1011, "vitals session ended");
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
      const data = summarize(decodeMetrics(buffer));
      if (Object.keys(data).length === 0) return;
      send({ type: "metrics", timestampUs, data });
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
      if (status === ProcessingStatus.kRunning) reachedRunning = true;
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
    if (!isBinary || !sdk || closing || failed) return;

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
      if (error?.code === SmartSpectraErrorCode.kInvalidState) {
        // Stopping before ever running is what a refused authorization looks like: the
        // SDK logs the 403s from Presage's API and emits no error event of its own.
        fail(
          reachedRunning
            ? "Vitals stopped: the measurement session ended."
            : "Vitals unavailable: Presage did not authorize this session.",
        );
        return;
      }
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
