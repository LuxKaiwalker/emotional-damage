import type { PlayerSession } from "./types";

/**
 * The backend mints a `player_id` once, in the response to `POST /rooms` or `/rooms/{code}/join`,
 * and then requires it for every other call -- the websocket closes 4403 without it. Nothing in
 * the UI can talk to the server until that identity is persisted, so it lives here.
 *
 * One seat at a time: joining a second room replaces the stored session. A reload keeps the seat
 * (the server holds the room for `empty_room_grace_seconds` after the socket drops).
 */

const KEY = "ed.session";

export interface StoredSession {
  room_id: string;
  join_code: string;
  player_id: string;
  name: string;
}

function isStored(v: unknown): v is StoredSession {
  if (!v || typeof v !== "object") return false;
  const s = v as Record<string, unknown>;
  return (
    typeof s.room_id === "string" &&
    typeof s.join_code === "string" &&
    typeof s.player_id === "string" &&
    typeof s.name === "string"
  );
}

export function saveSession(s: PlayerSession, name: string): StoredSession {
  const stored: StoredSession = {
    room_id: s.room_id,
    join_code: s.join_code,
    player_id: s.player_id,
    name,
  };
  try {
    localStorage.setItem(KEY, JSON.stringify(stored));
  } catch {
    /* private mode / storage disabled: the session still works for this page's lifetime */
  }
  return stored;
}

export function loadSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isStored(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** The stored seat, but only if it belongs to the lobby in the URL. */
export function loadSessionFor(code: string | undefined): StoredSession | null {
  const s = loadSession();
  if (!s) return null;
  if (!code) return s;
  return s.join_code.toUpperCase() === code.toUpperCase() ? s : null;
}

export function clearSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
}
