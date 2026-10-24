import { useEffect, useState } from "react";

/**
 * Seconds left until a server timestamp, corrected for clock skew.
 *
 * The backend sends `round.ends_at` / `game_ends_at` in its own clock and `server_time` with
 * every snapshot; `useGameSocket` turns the latter into `clockOffsetMs`. Anchoring to that
 * instead of counting down locally means the timer survives a reload, cannot drift away from
 * the server's own round timer, and reads the same on every player's screen.
 */
function remaining(endsAt: string | null | undefined, clockOffsetMs: number): number {
  if (!endsAt) return 0;
  const serverNow = Date.now() + clockOffsetMs;
  return Math.max(0, Math.ceil((new Date(endsAt).getTime() - serverNow) / 1000));
}

export function useServerCountdown(endsAt: string | null | undefined, clockOffsetMs: number): number {
  // The deadline is the state; this only forces a re-render so the derived value refreshes.
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!endsAt) return;
    // Sub-second tick so the number flips close to when the server's own deadline passes.
    const id = window.setInterval(() => setTick((t) => t + 1), 250);
    return () => window.clearInterval(id);
  }, [endsAt]);

  // Derived during render: a new `endsAt` is reflected immediately, with no resync effect.
  return remaining(endsAt, clockOffsetMs);
}
