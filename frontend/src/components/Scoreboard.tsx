import type { GameState } from "../types";

export function Scoreboard({ state, playerId }: { state: GameState; playerId: string }) {
  const players = Object.values(state.players).sort((a, b) => b.score - a.score);

  return (
    <div className="panel">
      <h3>Players</h3>
      <ul className="scoreboard">
        {players.map((p) => {
          const submission = state.round?.submissions[p.id];
          return (
            <li key={p.id} className={p.id === playerId ? "me" : undefined}>
              <span className={`dot ${p.connected ? "on" : "off"}`} />
              <span className="pname">
                {p.name}
                {p.id === state.host_id && <span className="muted small"> (host)</span>}
              </span>
              <span className="muted small">
                {submission?.result ? submission.result.label : (submission?.status ?? "—")}
              </span>
              <span className="pscore">{p.score.toFixed(2)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
