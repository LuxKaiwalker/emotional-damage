import { api } from "../api/client";
import type { UploaderStatus } from "../hooks/useFrameUploader";
import type { GameEvent, GameState } from "../types";

/** The thing that makes this boilerplate pleasant to extend: see exactly what the server
 *  received, what it decided, and what it last pushed back. */
export function DebugPanel({
  state,
  events,
  connected,
  uploader,
  clockOffsetMs,
}: {
  state: GameState;
  events: GameEvent[];
  connected: boolean;
  uploader: UploaderStatus;
  clockOffsetMs: number;
}) {
  return (
    <details className="panel debug">
      <summary>
        debug · ws {connected ? "open" : "closed"} · seq {state.seq} · offset{" "}
        {clockOffsetMs >= 0 ? "+" : ""}
        {clockOffsetMs}ms
      </summary>

      {uploader.lastSubmissionId && (
        <div className="debug-row">
          <span className="muted small">last frame the server stored</span>
          <img
            className="thumb"
            src={api.mediaUrl(uploader.lastSubmissionId)}
            alt="last uploaded frame"
          />
        </div>
      )}

      {uploader.lastError && <p className="error small">{uploader.lastError}</p>}

      <div className="debug-row">
        <span className="muted small">recent events</span>
        <ul className="events">
          {[...events].reverse().map((e, i) => (
            <li key={`${e.at}-${i}`}>
              <code>{e.kind}</code> {JSON.stringify(e.payload)}
            </li>
          ))}
        </ul>
      </div>

      <div className="debug-row">
        <span className="muted small">authoritative state</span>
        <pre>{JSON.stringify(state, null, 2)}</pre>
      </div>
    </details>
  );
}
