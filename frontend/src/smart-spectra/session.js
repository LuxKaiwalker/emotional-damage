/**
 * One SmartSpectra session, alone in its own process. Forked by server.js.
 *
 * Why a process per session:
 *   - SDK state is process-global. Presage's own Electron bridge says two sessions "must
 *     never run concurrently" in one process, so a sidecar holding one SDK per browser in
 *     a single process breaks as soon as a second player connects.
 *   - Isolation. If a session does wedge, it takes down one player's read and the
 *     parent's heartbeat watchdog replaces it; every other player carries on.
 *
 * Why frames are sent off the JS thread: the SDK relays its callbacks onto this event
 * loop from worker threads that block until the callback has run, and its sendFrame()
 * is synchronous and can wait on those same workers. Call it on the JS thread while a
 * callback is pending and the two wait on each other forever -- within seconds, on a
 * single-core box. So frames go through our own binding of the same native function,
 * run with koffi's `.async` on the libuv pool, and the JS thread stays free to deliver
 * callbacks. The binding reuses the types the SDK registered with koffi.
 *
 * Protocol (IPC, advanced serialization so pixel Buffers cross without base64):
 *   parent -> child  { type: "frame", width, height, timestampUs, pixels }
 *                    { type: "stop" }
 *   child -> parent  { type: "alive" } once a second
 *                    { type: "metrics", metrics } for kind=vitals
 *                    { type: "expression", scores, stable } for kind=expressions
 *                    { type: "status" | "validation" | "error" | "dead", ... }
 */
import {
  SmartSpectraSDK,
  PixelFormat,
  ProcessingStatus,
  SmartSpectraErrorCode,
  MetricType,
  breathingMetrics,
  cardioMetrics,
  decodeMetrics,
} from "@smartspectra/node-sdk";
import { presage } from "@smartspectra/node-sdk/messages";
import { createRequire } from "node:module";

// Resolved from the SDK's own directory, so this is the koffi instance (and the type
// registry) the SDK already loaded. Signature copied from the SDK's js/ffi.js.
const sdkRequire = createRequire(createRequire(import.meta.url).resolve("@smartspectra/node-sdk"));
const koffi = sdkRequire("koffi");
const { resolveNativeLibrary } = sdkRequire("./resolve-native.js");
const sendFrameOffThread = koffi.load(resolveNativeLibrary()).func(
  "int smartspectra_session_send_frame(smartspectra_session_t *sess, " +
    "const uint8_t *data, size_t data_len, int width, int height, " +
    "int stride_bytes, int pixel_format, int64_t timestamp_us, " +
    "_Out_ smartspectra_error_t *out_err)",
);

const KIND = process.argv[2];
const API_KEY = process.env.SMARTSPECTRA_API_KEY;

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

/**
 * The newest expression in a Metrics message, as `{ scores: { happy: 97.2, ... }, stable }`.
 * Scores are Presage's own percentages; the backend maps names onto the game's labels.
 */
function newestExpression(metrics) {
  const series = metrics.face?.expression;
  const last = series?.length ? series[series.length - 1] : undefined;
  if (!last?.scores?.length) return null;

  const scores = {};
  for (const { type, confidence } of last.scores) {
    const name = presage.smartspectra.ExpressionType[type];
    if (!name || name === "UNSPECIFIED" || !Number.isFinite(confidence)) continue;
    scores[name.toLowerCase()] = Math.round(confidence * 10) / 10;
  }
  if (Object.keys(scores).length === 0) return null;
  return { scores, stable: Boolean(last.stable) };
}

const tell = (message) => {
  if (process.connected) process.send(message);
};

// Vitals and expressions cannot share a session: breathing and cardio refuse to run until
// the chest is in view, and a session that is refusing emits nothing at all, expressions
// included -- so a webcam head shot would never be scored.
const METRICS = {
  vitals: [...breathingMetrics, ...cardioMetrics],
  expressions: [MetricType.EXPRESSIONS],
};
if (!METRICS[KIND]) throw new Error(`unknown session kind ${KIND}`);

const sdk = new SmartSpectraSDK({
  apiKey: API_KEY,
  requestedMetrics: METRICS[KIND],
  enableTelemetry: false,
});
let reachedRunning = false;
let dead = false;

sdk.on("metrics", (buffer) => {
  const metrics = decodeMetrics(buffer);
  if (KIND === "vitals") {
    const data = summarize(metrics);
    if (Object.keys(data).length) tell({ type: "metrics", metrics: data });
  } else {
    const reading = newestExpression(metrics);
    if (reading) tell({ type: "expression", ...reading });
  }
});
sdk.on("validationStatus", (code, timestampUs, hint) => {
  tell({ type: "validation", code, timestampUs, hint });
});
sdk.on("processingStatus", (status) => {
  if (status === ProcessingStatus.kRunning) reachedRunning = true;
  tell({ type: "status", status });
});
sdk.on("error", (code, message, retryable) => {
  tell({ type: "error", code, message, retryable });
});

sdk.useCustomInput();
sdk.start();

// The native handle sendFrameOffThread() needs. Private to the SDK, hence the check: if
// an upgrade moves it, fail loudly here rather than wedge on the first frame.
const session = sdk._session?._sess;
if (!session) throw new Error("@smartspectra/node-sdk internals changed: no session handle");

// Latest-frame mailbox: a frame that arrives while one is being sent replaces any frame
// still waiting, and only one send is ever in flight -- the SDK needs timestamps in order,
// and a live measurement wants the newest frame, not a backlog.
let pending = null;
let sending = false;

// Pixels are copied out of each IPC message into one of two buffers allocated outside
// the V8 heap: one being read by the native send, one holding the pending frame. The
// deserialized message's own memory is not guaranteed to stay put for the length of an
// async native call, and a send reading memory that moved under it fails as "processing
// failed" and takes the session down -- every ten to twenty seconds, in practice.
const slots = [null, null];
let sendingSlot = -1;

function intoSlot(pixels) {
  const index = sendingSlot === 0 ? 1 : 0;
  if (slots[index]?.length !== pixels.byteLength) slots[index] = Buffer.allocUnsafeSlow(pixels.byteLength);
  slots[index].set(pixels);
  return index;
}

// Frames that sat in the pipe this long (start() alone blocks for seconds while the SDK
// authorizes and loads its model) describe a moment that has passed.
const STALE_MS = 1000;

// The session's own clock. The SDK refuses a frame more than 2 s after the last one it
// accepted, permanently: one stale frame followed by fresh ones kills the session. So
// each frame advances this clock by the real gap between captures, capped below that
// threshold -- normal spacing stays exact, and a stall costs one short interval instead
// of the whole session. Also absorbs a browser that restarts its own clock.
const MAX_STEP_US = 1_500_000;
// Presage abandons a session fed much below camera rate ("processing failed", about ten
// seconds in at 15 fps), and on a single core frames do get dropped on the way here. An
// expression is read from each frame on its own, so that session runs on a nominal
// 30 fps clock whatever the real arrival rate. Vitals are rates over time and keep the
// real one.
const NOMINAL_STEP_US = 33_333;
let clockUs = 0;
let lastSourceUs = null;

// "Invalid video frame" at 30 fps is a flood; once every few seconds says the same thing.
let lastErrorAt = 0;

let idle = null; // resolves the wait in stop() once the in-flight send lands

function pump() {
  const frame = pending;
  pending = null;
  if (!frame || dead || Date.now() - frame.sentAt > STALE_MS) return;

  const step = lastSourceUs === null ? 0 : frame.timestampUs - lastSourceUs;
  lastSourceUs = frame.timestampUs;
  clockUs += KIND === "expressions" ? NOMINAL_STEP_US : Math.min(Math.max(step, 1), MAX_STEP_US);

  sending = true;
  sendingSlot = frame.slot;
  const err = {};
  sendFrameOffThread.async(
    session,
    frame.pixels,
    frame.pixels.byteLength,
    frame.width,
    frame.height,
    frame.width * 4,
    PixelFormat.kRGBA,
    BigInt(clockUs),
    err,
    (callError, rc) => {
      sending = false;
      sendingSlot = -1;
      if (callError || rc !== 0) rejected(err.code, callError?.message ?? err.message);
      if (idle) idle();
      else pump();
    },
  );
}

function rejected(code, message) {
  if (dead) return;
  if (code === SmartSpectraErrorCode.kInvalidState && !reachedRunning) {
    // Stopping before ever running is what a refused authorization looks like: the
    // SDK logs the 403s from Presage's API and emits no error event of its own. A new
    // session would be refused the same way, so this one is final.
    dead = true;
    tell({ type: "dead", message: "Presage did not authorize this session." });
    return;
  }
  if (
    code === SmartSpectraErrorCode.kInvalidState ||
    code === SmartSpectraErrorCode.kTimestampGap
  ) {
    // A session that was running and has stopped, or one that hit a timestamp gap (the
    // session clock should prevent it), refuses every later frame. The parent starts a
    // fresh one.
    console.error(`${KIND} session stopped (${message}); exiting for a restart`);
    process.exit(1);
  }
  if (Date.now() - lastErrorAt > 5000) {
    lastErrorAt = Date.now();
    console.error(`${KIND} frame rejected:`, message);
    tell({ type: "error", message: "Invalid video frame" });
  }
}

async function stop() {
  dead = true;
  try {
    // Never tear the session down under a send that is still using it.
    if (sending) await new Promise((resolve) => (idle = resolve));
    await sdk.stopAsync();
    await sdk.destroy();
  } finally {
    process.exit(0);
  }
}

process.on("message", (msg) => {
  if (msg.type === "frame") {
    const slot = intoSlot(msg.pixels);
    pending = { ...msg, slot, pixels: slots[slot] };
    if (!sending) pump();
  } else if (msg.type === "stop") {
    void stop();
  }
});

// Orphaned by a crashed parent: nothing will ever stop this session otherwise.
process.on("disconnect", () => void stop());

// The parent's watchdog: a frozen event loop stops sending these.
setInterval(() => tell({ type: "alive" }), 1000);
