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
}

export interface Player {
  id: string;
  name: string;
  connected: boolean;
  score: number;
  joined_at: string;
  last_frame_at: string | null;
}

export interface Round {
  number: number;
  prompt: string;
  started_at: string;
  ends_at: string;
  submissions: Record<string, Submission>;
}

export interface GameConfig {
  round_seconds: number;
  rounds_per_game: number;
  capture_interval_ms: number;
}

export interface GameState {
  room_id: string;
  join_code: string;
  phase: Phase;
  host_id: string;
  round: Round | null;
  players: Record<string, Player>;
  config: GameConfig;
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

export type FrameUploadResult =
  | { skipped: false; submission_id: string }
  | { skipped: true; reason: string };
