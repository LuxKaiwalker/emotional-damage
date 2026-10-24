import { useState } from "react";

import { api } from "../api/client";
import type { PlayerSession } from "../types";

export function Lobby({ onJoined }: { onJoined: (session: PlayerSession) => void }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<PlayerSession>) => {
    setBusy(true);
    setError(null);
    try {
      onJoined(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const disabled = busy || name.trim().length === 0;

  return (
    <div className="panel lobby">
      <h1>emotional damage</h1>
      <p className="muted">
        Each browser tab is one player. Open a few tabs to play against yourself.
      </p>

      <label>
        Your name
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="alice"
          maxLength={32}
          autoFocus
        />
      </label>

      <div className="row">
        <button disabled={disabled} onClick={() => void run(() => api.createRoom(name.trim()))}>
          Create room
        </button>
      </div>

      <div className="divider">or</div>

      <label>
        Join code
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="A1B2"
          maxLength={8}
        />
      </label>
      <div className="row">
        <button
          disabled={disabled || code.trim().length === 0}
          onClick={() => void run(() => api.joinRoom(code.trim(), name.trim()))}
        >
          Join room
        </button>
      </div>

      {error && <p className="error">{error}</p>}
    </div>
  );
}
