/**
 * Mirror of backend/app/models.py. Hand-written on purpose: it is small, and an explicit
 * copy makes contract drift show up as a type error.
 * If it grows, generate it instead: the backend serves OpenAPI at http://localhost:8000/openapi.json
 */

export type Phase = "lobby" | "round" | "scoring" | "game_over";
export type SubmissionStatus = "pending" | "done" | "failed";

export interface ProcessResult {
  score: number;
  label: string;
  confidence: number;
  meta: Record<string, unknown>;
}

export interface Submission {
  id: string;
  player_id: string;
  round_no: number;
  received_at: string;
  status: SubmissionStatus;
  result: ProcessResult | null;
  error: string | null;
  /** Did this frame hit the round's target? `null` while the result is pending. */
  correct: boolean | null;
}

export interface Player {
  id: string;
  name: string;
  connected: boolean;
  /** One point per round answered correctly. Integer: there is nothing fractional. */
  points: number;
  rounds_correct: number;
  joined_at: string;
  last_frame_at: string | null;
  /**
   * Latest client-reported vitals. Visible to every client and scored by none: the
   * numbers come from the player's own browser, so the server cannot verify them.
   * See backend/app/api/vitals.py.
   */
  vitals: Record<string, number> | null;
  vitals_at: string | null;
}

export interface Round {
  number: number;
  prompt: string;
  /** The label a submission has to carry to be correct. */
  target: string;
  started_at: string;
  ends_at: string;
  submissions: Record<string, Submission>;
  /** player_id -> points gained, filled in when the server ends the round. */
  points_awarded: Record<string, number>;
  /**
   * Uncle Damage's line for this round, and the id of its audio. Both start null and are
   * patched in once generation finishes, so treat them as arriving late. `audio_id` stays
   * null when no TTS key is configured -- the line is still worth showing as text.
   */
  voice_line: string | null;
  audio_id: string | null;
}

export interface GameConfig {
  round_seconds: number;
  rounds_per_game: number;
  game_seconds: number;
  points_per_correct: number;
  capture_interval_ms: number;
  max_players: number;
}

export interface GameState {
  room_id: string;
  join_code: string;
  phase: Phase;
  host_id: string;
  round: Round | null;
  /** Every scored round of this game, oldest first. Emptied by a restart. */
  history: Round[];
  players: Record<string, Player>;
  config: GameConfig;
  /** Bumped by every restart, so "scores reset" is distinguishable from "scores lost". */
  game_no: number;
  /** The game timer. Both null in the lobby. */
  game_started_at: string | null;
  game_ends_at: string | null;
  seq: number;
  server_time: string;
}

export interface PlayerSession {
  room_id: string;
  join_code: string;
  player_id: string;
  state: GameState;
}

export type ServerMessage =
  | { type: "state"; seq: number; state: GameState }
  | { type: "event"; kind: string; payload: Record<string, unknown> };

export interface GameEvent {
  kind: string;
  payload: Record<string, unknown>;
  at: number;
}

export interface LeaveRoomResponse {
  status: "left";
  /** True when that was the last player: the room and its game are gone. */
  room_destroyed: boolean;
}

export interface VitalsAccepted {
  status: "recorded";
  /** Always false. The endpoint exists to show the read, not to pay for it. */
  scored: false;
}

export type FrameUploadResult =
  | { skipped: false; submission_id: string }
  | { skipped: true; reason: string };
