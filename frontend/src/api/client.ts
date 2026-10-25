import type {
  FrameUploadResult,
  GameConfig,
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

/** What each request field is called on screen, for validation messages. */
const FIELD_LABELS: Record<string, string> = {
  name: "Your name",
  join_code: "The lobby code",
  round_seconds: "Round 1 length",
  round_decrement_seconds: "The drop per round",
  rounds: "Rounds",
};

/** Fields measured in seconds, so their limits read "at least 1s" rather than "at least 1". */
const SECONDS_FIELDS = new Set(["round_seconds", "round_decrement_seconds"]);

interface ValidationIssue {
  type?: string;
  loc?: (string | number)[];
  ctx?: Record<string, unknown>;
}

/** One FastAPI/pydantic validation issue, as a sentence a player can act on. */
function describeIssue({ type, loc = [], ctx = {} }: ValidationIssue): string {
  const field = String(loc[loc.length - 1] ?? "");
  const label = FIELD_LABELS[field] ?? "That value";
  const unit = SECONDS_FIELDS.has(field) ? "s" : "";
  switch (type) {
    case "greater_than_equal":
      return `${label} has to be at least ${ctx.ge}${unit}.`;
    case "greater_than":
      return `${label} has to be more than ${ctx.gt}${unit}.`;
    case "less_than_equal":
      return `${label} can be at most ${ctx.le}${unit}.`;
    case "less_than":
      return `${label} has to be less than ${ctx.lt}${unit}.`;
    case "string_too_short":
      return ctx.min_length === 1
        ? `${label} can't be empty.`
        : `${label} needs at least ${ctx.min_length} characters.`;
    case "string_too_long":
      return `${label} can be at most ${ctx.max_length} characters.`;
    case "missing":
      return `${label} is missing.`;
    case "int_parsing":
    case "int_type":
    case "int_from_float":
      return `${label} has to be a whole number.`;
    default:
      return `${label} isn't valid.`;
  }
}

/** Turn whatever an error response carried into something fit to show a player. */
function friendlyMessage(status: number, detail: unknown): string {
  // The server's own refusals are already written for players.
  if (typeof detail === "string" && detail && status < 500) return detail;
  // Request validation (422) arrives as a list of issues; one sentence each.
  if (Array.isArray(detail) && detail.length) {
    return [...new Set(detail.map((d) => describeIssue(d as ValidationIssue)))].join(" ");
  }
  if (status === 404) return "We couldn't find that. It may have expired.";
  if (status === 429) return "Slow down a little and try again.";
  if (status >= 500) return "The game server hit a snag. Try again in a moment.";
  return "Something went wrong. Try again.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    // fetch only throws when the request never got an answer.
    throw new ApiError(0, "Can't reach the game server. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json())?.detail ?? null;
    } catch {
      /* non-JSON error body (a proxy page, a crash); fall back on the status */
    }
    throw new ApiError(res.status, friendlyMessage(res.status, detail));
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

  /** Host only, in the lobby: how many rounds the next game plays (5 or 10). */
  setRounds: (roomId: string, playerId: string, rounds: number) =>
    request<{ rounds_per_game: number }>(
      `/rooms/${encodeURIComponent(roomId)}/rounds?player_id=${encodeURIComponent(playerId)}&rounds=${rounds}`,
      { method: "POST" },
    ),

  /**
   * Host only, in the lobby. The server answers 422 with a readable reason when the
   * schedule would leave the last round too short to play.
   */
  setRoundTiming: (
    roomId: string,
    playerId: string,
    roundSeconds: number,
    roundDecrementSeconds: number,
  ) =>
    request<GameConfig>(
      `/rooms/${encodeURIComponent(roomId)}/config?player_id=${encodeURIComponent(playerId)}`,
      json({ round_seconds: roundSeconds, round_decrement_seconds: roundDecrementSeconds }),
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
