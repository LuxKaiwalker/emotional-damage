import { useCallback, useEffect, useRef, useState } from "react";

export interface UseCameraOptions {
  width?: number;
  height?: number;
  quality?: number;
}

export interface Camera {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  ready: boolean;
  error: string | null;
  start: () => void;
  captureFrame: () => Promise<Blob | null>;
}

function explain(err: unknown): string {
  if (!(err instanceof Error)) return String(err);
  switch (err.name) {
    case "NotAllowedError":
      return "Camera permission denied. Allow it in the browser's site settings and retry.";
    case "NotFoundError":
      return "No camera found on this device.";
    case "NotReadableError":
      return "The camera is in use by another application.";
    case "SecurityError":
      return "Camera needs a secure context. Use http://localhost or serve over HTTPS.";
    default:
      return `${err.name}: ${err.message}`;
  }
}

/**
 * getUserMedia plus a canvas grab. `captureFrame` encodes the current video frame as JPEG.
 *
 * Note: getUserMedia only exists in a secure context. http://localhost counts, but opening
 * this page over plain HTTP from another device will have no camera at all (see README).
 */
export function useCamera({ width = 640, height = 480, quality = 0.7 }: UseCameraOptions = {}): Camera {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const start = useCallback(() => {
    setError(null);
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function open() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This browser has no camera API (or the page is not a secure context).");
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: width }, height: { ideal: height }, facingMode: "user" },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => undefined);
        }
        setReady(true);
      } catch (err) {
        if (!cancelled) {
          setError(explain(err));
          setReady(false);
        }
      }
    }

    void open();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setReady(false);
    };
  }, [width, height, attempt]);

  const captureFrame = useCallback(async (): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || video.readyState < 2 || !video.videoWidth) return null;

    const canvas = (canvasRef.current ??= document.createElement("canvas"));
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  }, [quality]);

  return { videoRef, ready, error, start, captureFrame };
}
