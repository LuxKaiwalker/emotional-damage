import { useEffect, useState } from "react";

import type { GameState } from "../types";

/** Countdown anchored to the server's `ends_at`, corrected by the measured clock offset,
 *  so the timer can never disagree with the backend that actually ends the round. */
function useCountdown(endsAt: string | undefined, clockOffsetMs: number): number {
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    if (!endsAt) {
      setRemaining(0);
      return;
    }
    const target = new Date(endsAt).getTime();
    const update = () =>
      setRemaining(Math.max(0, Math.ceil((target - (Date.now() + clockOffsetMs)) / 1000)));
    update();
    const handle = window.setInterval(update, 250);
    return () => window.clearInterval(handle);
  }, [endsAt, clockOffsetMs]);

  return remaining;
}

export function RoundView({
  state,
  playerId,
  clockOffsetMs,
  onStart,
}: {
  state: GameState;
  playerId: string;
  clockOffsetMs: number;
  onStart: () => void;
}) {
  const remaining = useCountdown(state.round?.ends_at, clockOffsetMs);
  const isHost = state.host_id === playerId;
  const mine = state.round?.submissions[playerId];

  return (
    <div className="panel round">
      <header className="round-head">
        <span className="badge">{state.phase.replace("_", " ")}</span>
        {state.round && (
          <span className="muted small">
            round {state.round.number} / {state.config.rounds_per_game}
          </span>
        )}
      </header>

      {state.phase === "lobby" && (
        <>
          <h2>Waiting in the lobby</h2>
          <p className="muted">
            Share code <code className="code">{state.join_code}</code>
          </p>
          {isHost ? (
            <button onClick={onStart}>Start game</button>
          ) : (
            <p className="muted small">The host starts the game.</p>
          )}
        </>
      )}

      {state.phase === "round" && state.round && (
        <>
          <h2>{state.round.prompt}</h2>
          <div className="timer">{remaining}s</div>
          <p className="muted small">
            {mine?.result
              ? `latest read: ${mine.result.label} · ${mine.result.score.toFixed(2)} pts (conf ${mine.result.confidence.toFixed(2)})`
              : mine
                ? `frame ${mine.status}…`
                : "capturing…"}
          </p>
        </>
      )}

      {state.phase === "scoring" && (
        <>
          <h2>Scoring</h2>
          <p className="muted">The server is committing this round's points.</p>
        </>
      )}

      {state.phase === "game_over" && (
        <>
          <h2>Game over</h2>
          <p className="muted">Reload to start a new room.</p>
        </>
      )}
    </div>
  );
}
