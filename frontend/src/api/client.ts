import type {
  FrameUploadResult,
  GameState,
  LeaveRoomResponse,
  PlayerSession,
  VitalsAccepted,
} from "../types";

// Default to relative paths so the vite dev proxy handles it; override for a deployed build.
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json())?.detail ?? res.statusText;
    } catch {
      /* non-JSON error body; keep the status text */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  createRoom: (name: string) => request<PlayerSession>("/rooms", json({ name })),

  /** `roomOrCode` takes either a full room id or the 4-character join code. */
  joinRoom: (roomOrCode: string, name: string) =>
    request<PlayerSession>(`/rooms/${encodeURIComponent(roomOrCode)}/join`, json({ name })),

  getState: (roomId: string) => request<GameState>(`/rooms/${encodeURIComponent(roomId)}`),

  startGame: (roomId: string, playerId: string) =>
    request<{ status: string }>(
      `/rooms/${encodeURIComponent(roomId)}/start?player_id=${encodeURIComponent(playerId)}`,
      { method: "POST" },
    ),

  /** Host only, after `game_over`: clears every score and returns the room to its lobby. */
  restartGame: (roomId: string, playerId: string) =>
    request<{ status: string }>(
      `/rooms/${encodeURIComponent(roomId)}/restart?player_id=${encodeURIComponent(playerId)}`,
      { method: "POST" },
    ),

  /** Give up this player's seat. The last player out destroys the room. */
  leaveRoom: (roomId: string, playerId: string) =>
    request<LeaveRoomResponse>(
      `/rooms/${encodeURIComponent(roomId)}/leave?player_id=${encodeURIComponent(playerId)}`,
      { method: "POST" },
    ),

  /**
   * Upload one camera still. Resolves as soon as the server accepts it; the score
   * arrives separately over the websocket.
   */
  uploadFrame: (roomId: string, playerId: string, frame: Blob) => {
    const form = new FormData();
    form.append("player_id", playerId);
    form.append("file", frame, "frame.jpg");
    return request<FrameUploadResult>(`/rooms/${encodeURIComponent(roomId)}/frames`, {
      method: "POST",
      body: form,
    });
  },

  /**
   * Report one vitals sample. Accepted in any phase and scored in none -- the server
   * stores it so the whole room can see the read, never to award points.
   */
  reportVitals: (roomId: string, playerId: string, metrics: Record<string, number>) =>
    request<VitalsAccepted>(
      `/rooms/${encodeURIComponent(roomId)}/vitals`,
      json({ player_id: playerId, metrics }),
    ),

  mediaUrl: (submissionId: string) => `${API_BASE}/media/${encodeURIComponent(submissionId)}`,

  /** Audio for a round's narration. 404 is ordinary: it expires on a TTL. */
  voiceUrl: (audioId: string) => `${API_BASE}/voice/${encodeURIComponent(audioId)}`,
};
