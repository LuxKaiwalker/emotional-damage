import { useCallback, useEffect, useRef, useState } from "react";

const WS_URL = import.meta.env.VITE_SPECTRA_WS_URL ?? "ws://localhost:3001";

/** Matches the old useCamera default: small enough to upload twice a second. */
const JPEG_QUALITY = 0.7;

// Shape comes from decodeMetrics() on the server; log it once and tighten this.
export type SpectraMetrics = Record<string, any>;

export interface Spectra {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  ready: boolean;
  error: string | null;
  status: string;
  measurements: SpectraMetrics | null;
  validation: string;
  /** Current video frame as a JPEG, for `POST /api/rooms/{id}/frames`. Null until the camera is up. */
  captureFrame: () => Promise<Blob | null>;
}

/**
 * Sole owner of the camera.
 *
 * One `getUserMedia` feeds two consumers:
 *   - raw RGBA at camera rate -> the SmartSpectra node server (vitals)
 *   - JPEG stills on demand   -> the game backend via `captureFrame` (scoring)
 *
 * These used to be two hooks each calling `getUserMedia` independently, which meant two
 * MediaStreams off one device. The SmartSpectra socket is optional: if the node server is
 * not running, the camera and `captureFrame` still work and only the vitals go missing.
 */
export function useSmartSpectra(): Spectra {
  const videoRef = useRef<HTMLVideoElement | null>(null);
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
    let vfc: number | undefined;
    let stopped = false;
    let restarting = false;

    function restart() {
      if (stopped || restarting) return;
      restarting = true;
      setStatus("Restarting session...");
      setMeasurements(null);
      setRestartKey((k) => k + 1);
    }

    // Frame callbacks pause while the tab is hidden, which creates a timestamp
    // gap. Start a clean session when the tab comes back.
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

        video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        await video.play();
        setReady(true);

        socket = new WebSocket(WS_URL);
        socket.binaryType = "arraybuffer";

        socket.onopen = () => setStatus("Connected");
        // The vitals sidecar is optional; say so rather than looking broken.
        socket.onerror = () => setStatus("Vitals offline");
        socket.onclose = () => {
          if (!stopped) setStatus("Vitals offline");
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
            setStatus(msg.message);
            // Code 11 = timestamp gap; the session is unusable, so start over.
            if (msg.code === 11) restart();
          } else if (msg.type === "status") {
            setStatus(`Processing status: ${msg.status}`);
          }
        };

        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
        const v = video;
        const ws = socket;

        let t0: number | null = null;
        let lastTsUs = -1;

        // Fires once per real camera frame (not per display refresh).
        const onVideoFrame: VideoFrameRequestCallback = (now, metadata) => {
          if (stopped) return;

          if (ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 8_000_000) {
            const tsMs = metadata.captureTime ?? now;
            if (t0 === null) t0 = tsMs;
            const timestampUs = Math.round((tsMs - t0) * 1000);

            // Timestamps must be strictly increasing
            if (timestampUs > lastTsUs) {
              lastTsUs = timestampUs;

              const width = v.videoWidth;
              const height = v.videoHeight;
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
            }
          }

          vfc = v.requestVideoFrameCallback(onVideoFrame);
        };

        vfc = v.requestVideoFrameCallback(onVideoFrame);
      } catch (err) {
        console.error(err);
        setError(err instanceof Error ? err.message : "Could not start camera or connection");
        setStatus("Could not start camera or connection");
      }
    }

    start();

    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (vfc !== undefined && video) video.cancelVideoFrameCallback(vfc);
      socket?.close();
      stream?.getTracks().forEach((t) => t.stop());
      setReady(false);
    };
  }, [restartKey]);

  return { videoRef, ready, error, status, measurements, validation, captureFrame };
}
