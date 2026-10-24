import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { Phase } from "../types";

export interface UploaderStatus {
  sent: number;
  skipped: number;
  failed: number;
  lastSubmissionId: string | null;
  lastError: string | null;
}

/**
 * Drives capture from the *server's* phase: frames are only sent while the backend says
 * a round is live. One upload in flight at a time -- a slow network skips the next tick
 * instead of queueing a backlog of stale frames.
 */
export function useFrameUploader(opts: {
  roomId: string | null;
  playerId: string | null;
  phase: Phase | undefined;
  intervalMs: number;
  enabled: boolean;
  capture: () => Promise<Blob | null>;
}): UploaderStatus {
  const { roomId, playerId, phase, intervalMs, enabled, capture } = opts;
  const [status, setStatus] = useState<UploaderStatus>({
    sent: 0,
    skipped: 0,
    failed: 0,
    lastSubmissionId: null,
    lastError: null,
  });

  const inFlight = useRef(false);
  const failures = useRef(0);
  const captureRef = useRef(capture);
  captureRef.current = capture;

  useEffect(() => {
    if (!enabled || !roomId || !playerId || phase !== "round") return;

    let stopped = false;

    const tick = async () => {
      if (stopped || inFlight.current) return;
      inFlight.current = true;
      try {
        const frame = await captureRef.current();
        if (!frame) return;
        const res = await api.uploadFrame(roomId, playerId, frame);
        failures.current = 0;
        setStatus((s) =>
          res.skipped
            ? { ...s, skipped: s.skipped + 1, lastError: null }
            : { ...s, sent: s.sent + 1, lastSubmissionId: res.submission_id, lastError: null },
        );
      } catch (err) {
        failures.current += 1;
        setStatus((s) => ({ ...s, failed: s.failed + 1, lastError: String(err) }));
      } finally {
        inFlight.current = false;
      }
    };

    // Back off on sustained failure so a dead backend is not hammered every tick.
    const period = intervalMs * Math.min(2 ** failures.current, 8);
    const handle = window.setInterval(() => void tick(), period);
    void tick();

    return () => {
      stopped = true;
      window.clearInterval(handle);
    };
  }, [enabled, roomId, playerId, phase, intervalMs, status.failed]);

  return status;
}
