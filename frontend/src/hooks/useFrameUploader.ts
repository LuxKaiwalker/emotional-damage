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

const EMPTY: UploaderStatus = {
  sent: 0,
  skipped: 0,
  failed: 0,
  lastSubmissionId: null,
  lastError: null,
};

/**
 * Drives capture from the *server's* phase: frames are only sent while the backend says
 * a round is live. Uploads are sequential -- the next tick is scheduled after the previous
 * one settles, so a slow network can never build a backlog of stale frames.
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
  const [status, setStatus] = useState<UploaderStatus>(EMPTY);

  // Latest capture fn without making it an effect dependency: re-subscribing on every
  // render would restart the upload loop constantly.
  const captureRef = useRef(capture);
  useEffect(() => {
    captureRef.current = capture;
  }, [capture]);

  useEffect(() => {
    if (!enabled || !roomId || !playerId || phase !== "round") return;

    let stopped = false;
    let handle: number | undefined;
    let failures = 0;

    const run = async () => {
      if (stopped) return;

      // Back off on sustained failure so a dead backend is not hammered every tick.
      let delay = intervalMs;

      try {
        const frame = await captureRef.current();
        if (frame) {
          const res = await api.uploadFrame(roomId, playerId, frame);
          failures = 0;
          setStatus((s) =>
            res.skipped
              ? { ...s, skipped: s.skipped + 1, lastError: null }
              : { ...s, sent: s.sent + 1, lastSubmissionId: res.submission_id, lastError: null },
          );
        }
      } catch (err) {
        failures += 1;
        delay = intervalMs * Math.min(2 ** failures, 8);
        setStatus((s) => ({ ...s, failed: s.failed + 1, lastError: String(err) }));
      }

      if (!stopped) handle = window.setTimeout(() => void run(), delay);
    };

    void run();

    return () => {
      stopped = true;
      window.clearTimeout(handle);
    };
  }, [enabled, roomId, playerId, phase, intervalMs]);

  return status;
}
