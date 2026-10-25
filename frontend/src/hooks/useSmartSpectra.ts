import { useCallback, useEffect, useRef, useState } from "react";

const WS_URL = import.meta.env.VITE_SPECTRA_WS_URL ?? "ws://localhost:3001";

const PROCESSING_LABELS: Record<number, string> = {
  2: "Starting vitals...",
  3: "Measuring...",
  4: "Vitals stopping...",
  5: "Vitals error",
};

/** Matches the old useCamera default: small enough to upload twice a second. */
const JPEG_QUALITY = 0.7;

// Shape comes from decodeMetrics() on the server; log it once and tighten this.
export type SpectraMetrics = Record<string, any>;

export interface Spectra {
  /** The live camera, for a preview `<video>`. Null until the camera is up. */
  stream: MediaStream | null;
  ready: boolean;
  error: string | null;
  status: string;
  measurements: SpectraMetrics | null;
  validation: string;
  /** Current video frame as a JPEG, for `POST /api/rooms/{id}/frames`. Null until the camera is up. */
  captureFrame: () => Promise<Blob | null>;
}

/** Frames per second sent to the sidecar. Presage wants camera rate. */
const FEED_FPS = 30;

/** How long to wait before reopening a sidecar socket that dropped on its own. */
const RECONNECT_MS = 3000;

/**
 * Sole owner of the camera. Mounted once per game by `GameShell`, not per screen: a
 * Presage session takes seconds to start, and tearing it down at every round boundary
 * cost each player the first several seconds of every round.
 *
 * One `getUserMedia` feeds two consumers:
 *   - raw RGBA at camera rate -> the SmartSpectra node server (vitals, and the Presage
 *     expression read that PROCESSOR=presage scores with -- hence the player's ids)
 *   - JPEG stills on demand   -> the game backend via `captureFrame` (scoring)
 *
 * These used to be two hooks each calling `getUserMedia` independently, which meant two
 * MediaStreams off one device. The SmartSpectra socket is optional: if the node server is
 * not running, the camera and `captureFrame` still work and only the vitals go missing.
 */
/** getUserMedia's DOMException names, as something a player can fix. */
function cameraErrorMessage(err: unknown): string {
  switch (err instanceof DOMException ? err.name : "") {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera access is blocked. Allow the camera for this site in your browser, then reload.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No usable camera found. Plug one in, then reload.";
    case "NotReadableError":
    case "AbortError":
      return "Your camera is busy in another app or tab. Close it there, then reload.";
    default:
      return "Couldn't start your camera. Reload the page to try again.";
  }
}

export function useSmartSpectra(opts: {
  roomId: string | null;
  playerId: string | null;
}): Spectra {
  const { roomId, playerId } = opts;
  // Frames are read from a video element of the hook's own, not from whatever screen is
  // showing, so they keep flowing between rounds. Screens preview `stream` themselves.
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("Starting camera...");
  const [measurements, setMeasurements] = useState<SpectraMetrics | null>(null);
  const [validation, setValidation] = useState("");
  const [restartKey, setRestartKey] = useState(0);

  // Kept out of the RGBA loop's canvas on purpose: toBlob is async, and that canvas is
  // overwritten 30 times a second.
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);

  const captureFrame = useCallback(async (): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) return null;

    const canvas = (captureCanvasRef.current ??= document.createElement("canvas"));
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
  }, []);

  useEffect(() => {
    let stream: MediaStream | undefined;
    let socket: WebSocket | undefined;
    let video: HTMLVideoElement | null = null;
    let feed: number | undefined;
    let reconnect: number | undefined;
    let stopped = false;
    let restarting = false;

    function restart() {
      if (stopped || restarting) return;
      restarting = true;
      setStatus("Restarting session...");
      setMeasurements(null);
      setRestartKey((k) => k + 1);
    }

    // Timers are throttled while the tab is hidden, which starves the session. Start a
    // clean one when the tab comes back.
    function onVisibilityChange() {
      if (document.visibilityState === "visible") restart();
    }
    document.addEventListener("visibilitychange", onVisibilityChange);

    async function start() {
      try {
        setError(null);
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: "user",
            width: { ideal: 640 },
            height: { ideal: 480 },
            frameRate: { ideal: 30, min: 25 },
          },
          audio: false,
        });

        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        // In the document but invisible: some browsers (iOS Safari) will not play a video
        // that is not, and one that is not playing yields no frames.
        video = document.createElement("video");
        video.muted = true;
        video.playsInline = true;
        video.setAttribute("aria-hidden", "true");
        Object.assign(video.style, {
          position: "fixed",
          left: "0",
          top: "0",
          width: "1px",
          height: "1px",
          opacity: "0",
          pointerEvents: "none",
        });
        document.body.appendChild(video);
        videoRef.current = video;
        video.srcObject = stream;
        await video.play();
        setStream(stream);
        setReady(true);

        // The sidecar files each expression reading against this player.
        const url = new URL(WS_URL, window.location.href);
        if (roomId && playerId) {
          url.searchParams.set("room_id", roomId);
          url.searchParams.set("player_id", playerId);
        }
        socket = new WebSocket(url);
        socket.binaryType = "arraybuffer";

        // Set when the sidecar explains why it is hanging up, so the close that follows
        // does not overwrite the reason with a generic "offline".
        let fatal: string | null = null;

        socket.onopen = () => setStatus("Connected");
        // The vitals sidecar is optional; say so rather than looking broken.
        socket.onerror = () => setStatus(fatal ?? "Vitals offline");
        socket.onclose = () => {
          if (stopped) return;
          setStatus(fatal ?? "Vitals offline");
          // A socket that dropped on its own (sidecar restart, network blip) comes back:
          // this one is meant to last the whole game. A fatal close stays closed.
          if (!fatal) reconnect = window.setTimeout(restart, RECONNECT_MS);
        };

        socket.onmessage = (event) => {
          const msg = JSON.parse(event.data);

          if (msg.type === "ready") {
            setStatus("Measuring...");
          } else if (msg.type === "metrics") {
            setMeasurements(msg.data);
          } else if (msg.type === "validation") {
            setValidation(msg.hint || "");
          } else if (msg.type === "error") {
            // Fatal messages are written for players by the sidecar; the rest are raw SDK
            // or per-frame errors the next frames usually recover from.
            if (msg.fatal) fatal = msg.message;
            setStatus(msg.fatal ? msg.message : "Vitals hiccup, retrying...");
            // Code 11 = timestamp gap; the session is unusable, so start over.
            if (msg.code === 11) restart();
          } else if (msg.type === "status") {
            // ProcessingStatus from the SDK; idle and uninitialized say nothing useful.
            const label = PROCESSING_LABELS[msg.status];
            if (label) setStatus(label);
          }
        };

        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
        const v = video;
        const ws = socket;

        const t0 = performance.now();
        let lastTsUs = -1;

        // A timer rather than requestVideoFrameCallback, which only fires for a video
        // that is being drawn on screen -- and this one deliberately is not.
        feed = window.setInterval(() => {
          if (stopped || ws.readyState !== WebSocket.OPEN || ws.bufferedAmount >= 8_000_000) {
            return;
          }
          const width = v.videoWidth;
          const height = v.videoHeight;
          if (!width || !height) return;

          // Timestamps must be strictly increasing
          const timestampUs = Math.round((performance.now() - t0) * 1000);
          if (timestampUs <= lastTsUs) return;
          lastTsUs = timestampUs;

          canvas.width = width;
          canvas.height = height;
          ctx.drawImage(v, 0, 0, width, height);
          const pixels = ctx.getImageData(0, 0, width, height).data;

          const packet = new ArrayBuffer(16 + pixels.length);
          const view = new DataView(packet);
          view.setUint32(0, width, true);
          view.setUint32(4, height, true);
          view.setBigUint64(8, BigInt(timestampUs), true);
          new Uint8Array(packet, 16).set(pixels);
          ws.send(packet);
        }, 1000 / FEED_FPS);
      } catch (err) {
        console.error(err);
        setError(cameraErrorMessage(err));
        setStatus("Could not start camera or connection");
      }
    }

    start();

    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.clearInterval(feed);
      window.clearTimeout(reconnect);
      socket?.close();
      stream?.getTracks().forEach((t) => t.stop());
      video?.remove();
      videoRef.current = null;
      setStream(null);
      setReady(false);
    };
  }, [restartKey, roomId, playerId]);

  return { stream, ready, error, status, measurements, validation, captureFrame };
}
