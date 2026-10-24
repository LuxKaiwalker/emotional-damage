import { useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import { CameraView } from "./components/CameraView";
import { DebugPanel } from "./components/DebugPanel";
import { Lobby } from "./components/Lobby";
import { RoundView } from "./components/RoundView";
import { Scoreboard } from "./components/Scoreboard";
import { useCamera } from "./hooks/useCamera";
import { useFrameUploader } from "./hooks/useFrameUploader";
import { useGameSocket } from "./hooks/useGameSocket";
import type { PlayerSession } from "./types";

const SESSION_KEY = "ed.session";

/** sessionStorage, not localStorage: each tab is its own player, which is how you test
 *  multiplayer locally. */
function loadSession(): Pick<PlayerSession, "room_id" | "player_id"> | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [session, setSession] = useState(loadSession);
  const { state, events, connected, clockOffsetMs } = useGameSocket(
    session?.room_id ?? null,
    session?.player_id ?? null,
  );

  const camera = useCamera();
  const uploader = useFrameUploader({
    roomId: session?.room_id ?? null,
    playerId: session?.player_id ?? null,
    phase: state?.phase,
    intervalMs: state?.config.capture_interval_ms ?? 500,
    enabled: camera.ready,
    capture: camera.captureFrame,
  });

  useEffect(() => {
    if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }, [session]);

  const onJoined = useCallback((s: PlayerSession) => {
    setSession({ room_id: s.room_id, player_id: s.player_id });
  }, []);

  const onStart = useCallback(() => {
    if (!session) return;
    void api.startGame(session.room_id, session.player_id).catch(console.error);
  }, [session]);

  if (!session) return <Lobby onJoined={onJoined} />;
  if (!state) {
    return (
      <div className="panel">
        <p className="muted">connecting to room {session.room_id}…</p>
        <button
          onClick={() => {
            sessionStorage.removeItem(SESSION_KEY);
            setSession(null);
          }}
        >
          Leave
        </button>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="col">
        <RoundView
          state={state}
          playerId={session.player_id}
          clockOffsetMs={clockOffsetMs}
          onStart={onStart}
        />
        <CameraView camera={camera} uploader={uploader} capturing={state.phase === "round"} />
      </div>
      <div className="col">
        <Scoreboard state={state} playerId={session.player_id} />
        <DebugPanel
          state={state}
          events={events}
          connected={connected}
          uploader={uploader}
          clockOffsetMs={clockOffsetMs}
        />
      </div>
    </div>
  );
}
