import { useEffect, useRef, useState } from "react";

import type { GameEvent, GameState, ServerMessage } from "../types";

const WS_BASE =
  import.meta.env.VITE_WS_BASE ??
  `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;

const MAX_EVENTS = 25;
const MAX_BACKOFF_MS = 10_000;

export interface GameSocket {
  state: GameState | null;
  events: GameEvent[];
  connected: boolean;
  /** server_time minus client clock at the last snapshot, in ms. */
  clockOffsetMs: number;
}

/**
 * Read-only state channel. The server is the only writer of game state, so this hook
 * never merges or derives anything: it adopts whole snapshots and drops stale ones.
 */
export function useGameSocket(roomId: string | null, playerId: string | null): GameSocket {
  const [state, setState] = useState<GameState | null>(null);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [clockOffsetMs, setClockOffsetMs] = useState(0);
  const lastSeq = useRef(-1);

  useEffect(() => {
    if (!roomId || !playerId) return;

    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let keepAlive: number | undefined;
    let attempt = 0;
    let closed = false;

    lastSeq.current = -1;

    const connect = () => {
      socket = new WebSocket(`${WS_BASE}/rooms/${roomId}?player_id=${playerId}`);

      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
        // The server has no inbound protocol; this just keeps intermediaries from idling us out.
        keepAlive = window.setInterval(() => socket?.send("ping"), 25_000);
      };

      socket.onmessage = (ev) => {
        const msg = JSON.parse(ev.data as string) as ServerMessage;
        if (msg.type === "state") {
          // Out-of-order or replayed snapshot: ignore it rather than going backwards.
          if (msg.seq <= lastSeq.current) return;
          lastSeq.current = msg.seq;
          setState(msg.state);
          setClockOffsetMs(new Date(msg.state.server_time).getTime() - Date.now());
        } else {
          setEvents((prev) =>
            [...prev, { kind: msg.kind, payload: msg.payload, at: Date.now() }].slice(-MAX_EVENTS),
          );
        }
      };

      socket.onclose = () => {
        setConnected(false);
        window.clearInterval(keepAlive);
        if (closed) return;
        // Reconnect and resync from whatever the server says now -- never from local guesses.
        const delay = Math.min(500 * 2 ** attempt++, MAX_BACKOFF_MS);
        retryTimer = window.setTimeout(connect, delay);
      };

      socket.onerror = () => socket?.close();
    };

    connect();

    return () => {
      closed = true;
      window.clearTimeout(retryTimer);
      window.clearInterval(keepAlive);
      socket?.close();
      setConnected(false);
    };
  }, [roomId, playerId]);

  return { state, events, connected, clockOffsetMs };
}
