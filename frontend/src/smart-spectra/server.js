import "dotenv/config";
import { fork } from "node:child_process";
import { fileURLToPath } from "node:url";
import { WebSocketServer, WebSocket } from "ws";

const PORT = Number(process.env.PORT ?? 3001);
const WEB_ORIGIN = process.env.WEB_ORIGIN;
const API_KEY = process.env.SMARTSPECTRA_API_KEY;
// Where expression readings go: the game backend's loopback-only ingest route.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const INGEST_TOKEN = process.env.PRESAGE_INGEST_TOKEN;
// Each player gets an expressions session (what PROCESSOR=presage scores with) and, unless
// this is off, a vitals session too. Each is a process costing about a third of a core and
// half a gigabyte, so on a small box SPECTRA_VITALS=off doubles how many players fit.
const VITALS = process.env.SPECTRA_VITALS !== "off";

const SESSION_JS = fileURLToPath(new URL("./session.js", import.meta.url));
// A session process that has said nothing for this long is wedged; see session.js.
const WATCHDOG_MS = 6000;
// Until it first speaks, though, it is in start(): authorizing with Presage (through the
// proxy, on the VPS) and loading the model, which blocks it for ten seconds or more.
const STARTUP_GRACE_MS = 45000;
// Frames handed to a session process and not yet written to its pipe. Past this the
// newest frame is dropped: a stale frame is worth nothing to a live measurement.
const MAX_FRAMES_IN_FLIGHT = 2;
// Respawns allowed per session within a minute before giving up on it.
const MAX_RESPAWNS_PER_MINUTE = 3;

if (!API_KEY) {
  throw new Error("Missing SMARTSPECTRA_API_KEY");
}
if (!INGEST_TOKEN) {
  console.warn("PRESAGE_INGEST_TOKEN is unset: expressions will not be sent to the backend");
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

/** Push one expression reading to the backend. Resolves to the HTTP status, or 0 on failure. */
async function forwardExpression(roomId, playerId, reading) {
  try {
    const res = await fetch(`${BACKEND_URL}/internal/presage/expressions`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-presage-token": INGEST_TOKEN },
      body: JSON.stringify({ room_id: roomId, player_id: playerId, ...reading }),
      signal: AbortSignal.timeout(2000),
    });
    return res.status;
  } catch {
    return 0;
  }
}

/**
 * Own one session process: start it, feed it, watch it, replace it if it wedges.
 * `onMessage` gets everything the process says except its heartbeat.
 */
function supervise(kind, onMessage, onGiveUp) {
  let child = null;
  let lastHeard = 0;
  let started = false;
  let inFlight = 0;
  let respawns = [];
  let stopped = false;

  const spawn = () => {
    inFlight = 0;
    lastHeard = Date.now();
    started = false;
    child = fork(SESSION_JS, [kind], { serialization: "advanced" });
    const self = child;
    self.on("message", (msg) => {
      lastHeard = Date.now();
      started = true;
      if (msg.type !== "alive") onMessage(msg);
    });
    self.on("exit", (code, signal) => {
      if (stopped || self !== child) return;
      console.error(`${kind} session exited (${signal ?? code}); restarting`);
      restart();
    });
  };

  const restart = () => {
    child?.kill("SIGKILL");
    const now = Date.now();
    respawns = [...respawns.filter((t) => now - t < 60_000), now];
    if (respawns.length > MAX_RESPAWNS_PER_MINUTE) {
      stopped = true;
      onGiveUp(`${kind} session kept failing`);
      return;
    }
    spawn();
  };

  const watchdog = setInterval(() => {
    const limit = started ? WATCHDOG_MS : STARTUP_GRACE_MS;
    if (!stopped && Date.now() - lastHeard > limit) {
      console.error(`${kind} session unresponsive for ${limit} ms; replacing it`);
      restart();
    }
  }, 1000);

  spawn();

  return {
    kind,
    send(frame) {
      if (stopped || !child?.connected || inFlight >= MAX_FRAMES_IN_FLIGHT) return;
      inFlight++;
      child.send({ type: "frame", ...frame }, () => {
        inFlight--;
      });
    },
    stop() {
      if (stopped) return;
      stopped = true;
      clearInterval(watchdog);
      const last = child;
      if (last?.connected) last.send({ type: "stop" });
      // Let it stop the SDK cleanly; a wedged one never will.
      setTimeout(() => last?.kill("SIGKILL"), 5000).unref();
    },
  };
}

wss.on("connection", (ws, req) => {
  // Which player this camera belongs to, so expression readings can be filed against them.
  // Without both, the socket still serves vitals; it just cannot score anyone.
  const query = new URL(req.url ?? "/", "http://sidecar").searchParams;
  const roomId = query.get("room_id");
  const playerId = query.get("player_id");

  const sessions = [];
  let closing = false;
  // Frames already in flight keep arriving until the close completes; drop them.
  let failed = false;

  const send = (message) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    }
  };

  // Say what happened once and hang up; the browser shows it instead of "Vitals offline".
  const fail = (message) => {
    if (closing || failed) return;
    failed = true;
    console.error(`session ended: ${message}`);
    send({ type: "error", fatal: true, message });
    ws.close(1011, "vitals session ended");
  };

  const dead = new Set();
  const lost = (kind, why) => {
    dead.add(kind);
    if (dead.size === sessions.length) {
      fail(`Presage unavailable: ${why}`);
    } else {
      console.error(`${kind} session ended: ${why}`);
      send({ type: "error", message: `${kind} stopped: ${why}` });
    }
  };

  // Status and validation hints go to the browser from one session only, so two sessions
  // do not talk over each other in one caption.
  const primary = VITALS ? "vitals" : "expressions";

  const relay = (kind) => (msg) => {
    if (msg.type === "dead") {
      lost(kind, msg.message);
    } else if (msg.type === "error") {
      send({ type: "error", code: msg.code, message: msg.message, retryable: msg.retryable });
    } else if (msg.type === "status" || msg.type === "validation") {
      if (kind === primary) send(msg);
    } else if (msg.type === "metrics") {
      send({ type: "metrics", data: msg.metrics });
    } else if (msg.type === "expression") {
      forward({ scores: msg.scores, stable: msg.stable });
    }
  };

  // One reading in flight per player; a newer one simply waits for the next event.
  let forwarding = false;
  let refused = false;
  const forward = (reading) => {
    if (forwarding || refused) return;
    forwarding = true;
    void forwardExpression(roomId, playerId, reading).then((status) => {
      forwarding = false;
      // The backend does not know this player (left, or room reaped), or this sidecar is
      // misconfigured; nothing this socket sends will ever land, so stop asking.
      if (status === 404 || status === 401 || status === 503) {
        refused = true;
        console.error(`backend refused expressions for ${playerId}: HTTP ${status}`);
      }
    });
  };

  if (VITALS) sessions.push(supervise("vitals", relay("vitals"), (why) => lost("vitals", why)));
  if (roomId && playerId && INGEST_TOKEN) {
    sessions.push(
      supervise("expressions", relay("expressions"), (why) => lost("expressions", why)),
    );
  }

  if (sessions.length === 0) {
    fail("Presage is not set up for this player: no vitals and no expression session.");
    return;
  }

  send({ type: "ready" });

  ws.on("message", (data, isBinary) => {
    if (!isBinary || closing || failed) return;

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

    const frame = { width, height, timestampUs, sentAt: Date.now(), pixels: packet.subarray(16) };
    for (const session of sessions) {
      if (!dead.has(session.kind)) session.send(frame);
    }
  });

  ws.on("close", () => {
    cleanup();
  });

  ws.on("error", (error) => {
    console.error("WebSocket error:", error);
    cleanup();
  });

  function cleanup() {
    if (closing) return;
    closing = true;
    for (const session of sessions) session.stop();
  }
});

wss.on("listening", () => {
  console.log(
    `SmartSpectra server listening on ${PORT} (vitals ${VITALS ? "on" : "off"}, ` +
      `expressions ${INGEST_TOKEN ? `-> ${BACKEND_URL}` : "off"})`,
  );
});
