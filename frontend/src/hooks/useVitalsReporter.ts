import { useEffect, useRef } from "react";

import { api } from "../api/client";
import type { SpectraMetrics } from "./useSmartSpectra";

/** Backend takes a flat map of numbers and caps the field count (MAX_VITALS_FIELDS). */
const MAX_FIELDS = 24;

/**
 * Keep only the top-level finite numbers.
 *
 * `decodeMetrics()` on the node sidecar returns a loosely-typed object that may carry
 * nested structures and waveform arrays; the endpoint rejects anything that is not a flat
 * number, and a snapshot is not the place for a waveform anyway.
 */
export function numericOnly(metrics: SpectraMetrics | null): Record<string, number> {
  if (!metrics) return {};
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(metrics)) {
    if (typeof value === "number" && Number.isFinite(value)) {
      out[key] = value;
      if (Object.keys(out).length >= MAX_FIELDS) break;
    }
  }
  return out;
}

/**
 * Forward SmartSpectra readings to the game server.
 *
 * This is what stops the vitals being invisible to the authority: the sidecar hands them
 * to the browser, and the browser passes them on so the rest of the room can see them.
 * They are explicitly not scoring input -- see backend/app/api/vitals.py -- so a dropped
 * report costs nothing and failures are swallowed rather than surfaced.
 */
export function useVitalsReporter(opts: {
  roomId: string | null;
  playerId: string | null;
  metrics: SpectraMetrics | null;
  intervalMs?: number;
}): void {
  const { roomId, playerId, metrics, intervalMs = 2000 } = opts;

  // Read inside the interval instead of re-subscribing on every new reading (~1/s).
  const latest = useRef(metrics);
  useEffect(() => {
    latest.current = metrics;
  }, [metrics]);

  useEffect(() => {
    if (!roomId || !playerId) return;

    let stopped = false;
    let inFlight = false;

    const send = async () => {
      if (stopped || inFlight) return;
      const flat = numericOnly(latest.current);
      if (Object.keys(flat).length === 0) return;
      inFlight = true;
      try {
        await api.reportVitals(roomId, playerId, flat);
      } catch {
        /* Cosmetic data: a lost sample is not worth telling the player about. */
      } finally {
        inFlight = false;
      }
    };

    const id = window.setInterval(() => void send(), intervalMs);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, [roomId, playerId, intervalMs]);
}
