/**
 * Mirror of backend/app/models.py. Hand-written on purpose: it is small, and an explicit
 * copy makes contract drift show up as a type error.
 * If it grows, generate it instead: the backend serves OpenAPI at http://localhost:8000/openapi.json
 */

export type Phase = "lobby" | "round" | "scoring" | "game_over";
/**
 * Which rules a room plays by. A `GameConfig` field, so it survives a restart.
 * - `classic`: shared rounds, scored on speed and placement against the other players.
 * - `blitz`: one clock, no rounds. Everyone runs asynchronously through a shared sequence
 *   of faces and is paid per face passed. `state.round` stays null the whole game.
 */
export type GameMode = "classic" | "blitz";
export type FaceOutcome = "passed" | "skipped" | "expired";
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
  /**
   * The round number in classic; the submitting player's own `face_no` in blitz, where
   * there are no rounds and every player is at a different point in the sequence.
   */
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
  /** Sum of every round's RoundScore.points (up to 200 a round), in whole points. */
  points: number;
  /** Rounds passed in classic; faces passed in blitz. */
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

/** One player's points for a round. Only players who passed get one. */
export interface RoundScore {
  /** 1 = first to pass, by when the passing frame was captured. */
  place: number;
  /** Up to 100: share of the round left at the pass, times 1.0 / 0.95 / 0.90 ... by place. */
  speed_points: number;
  /** Up to 100: the processor's confidence in the passing read. */
  accuracy_points: number;
  /** speed_points + accuracy_points, at most 200. */
  points: number;
}

/** One of a round's best faces: a passing frame, ranked by the processor's confidence. */
export interface Highlight {
  player_id: string;
  /** The frame itself; see `mediaUrl`. Gone once the server's media TTL reaps it. */
  submission_id: string;
  label: string;
  accuracy_points: number;
  place: number;
  /**
   * Blitz only: which face this was. A classic highlight sits inside the Round it came
   * from, so its number is read off that; a blitz one is loose on `BlitzState`.
   */
  face_no?: number | null;
}

export interface Round {
  number: number;
  prompt: string;
  /** The label a submission has to carry to be correct. */
  target: string;
  started_at: string;
  ends_at: string;
  /** Newest frame per player, frozen on the passing frame once they pass. */
  submissions: Record<string, Submission>;
  /** player_id -> the frame that passed them. No more frames are taken from them. */
  passed: Record<string, Submission>;
  /** Filled in when the server ends the round, for every player who passed. */
  scores: Record<string, RoundScore>;
  /** player_id -> points gained, filled in when the server ends the round. */
  points_awarded: Record<string, number>;
  /** Top faces by accuracy, best first, at most three. Filled in when the round ends. */
  highlights: Highlight[];
  /**
   * Uncle Damage's line for this round, and the id of its audio. Both start null and are
   * patched in once generation finishes, so treat them as arriving late. `audio_id` stays
   * null when no TTS key is configured -- the line is still worth showing as text.
   */
  voice_line: string | null;
  audio_id: string | null;
}

/**
 * One finished face in one player's run. Empty all game and filled in once, at game over:
 * thirty faces times twelve players is a lot of JSON to carry in every snapshot.
 */
export interface BlitzFace {
  index: number;
  prompt: string;
  target: string;
  outcome: FaceOutcome;
  /** 0 unless passed. */
  points: number;
  /** The passing read's confidence; null when skipped or run out. */
  confidence: number | null;
  /** The frame that passed it; see `mediaUrl`. Null unless passed. */
  submission_id?: string | null;
  seconds: number;
}

/**
 * One player's cursor into the room's shared sequence: blitz's answer to `Round`.
 *
 * Everyone has their own and they diverge -- that asynchrony is the mode. What keeps it
 * fair is that `cursor` indexes one sequence shared by the whole room, so a given face
 * number asks everyone for the same thing.
 */
export interface BlitzRun {
  player_id: string;
  cursor: number;
  /** 1-based, and what this player's submissions carry as `round_no`. */
  face_no: number;
  prompt: string;
  target: string;
  face_started_at: string;
  /** Clamped to `game_ends_at`, so a face deadline never outlives the game clock. */
  face_ends_at: string;
  /** Newest frame's read. What `round.submissions[player_id]` is in classic. */
  submission: Submission | null;
  passed: number;
  skipped: number;
  expired: number;
  /** How the face just before this one ended, so the UI can react to it. */
  last_outcome: FaceOutcome | null;
  last_points: number;
  last_confidence: number | null;
  /**
   * When the face on screen becomes skippable: `face_started_at` plus
   * `blitz_skip_after_seconds`. Re-armed by every advance, so each face has to be looked
   * at before it can be waved away. Null means skippable right now.
   */
  skip_ready_at: string | null;
  /** Empty until the game is over. */
  faces: BlitzFace[];
}

/**
 * The live working set of a blitz, the way `round` is for classic.
 *
 * Note what is absent: the sequence itself. It stays on the server, both because it is
 * bulky and because a client holding it could read ahead and pre-make the next face --
 * which would defeat the shared sequence's whole purpose.
 */
export interface BlitzState {
  sequence_length: number;
  runs: Record<string, BlitzRun>;
  /**
   * The whole blitz's best faces, filled in once at game over. Already ranked by the
   * server; blitz has no rounds to hang them off, which is why they live here.
   */
  highlights: Highlight[];
}

export interface GameConfig {
  /** Round 1's length; each later round is `round_decrement_seconds` shorter. Host-set. */
  round_seconds: number;
  round_decrement_seconds: number;
  rounds_per_game: number;
  game_seconds: number;
  /** 100 for speed + 100 for accuracy. */
  max_points_per_round: number;
  capture_interval_ms: number;
  max_players: number;

  /** Which rules this room plays by. Host-set in the lobby; survives a restart. */
  mode: GameMode;
  /** Blitz only. `game_seconds` is ignored in blitz: this is the clock. */
  blitz_seconds: number;
  blitz_face_seconds: number;
  blitz_pass_confidence: number;
  /**
   * A UI preference, not a privacy control: every snapshot carries every `Player.points`
   * whatever this says, because the server has no per-recipient serializer.
   */
  blitz_live_leaderboard: boolean;
  /** Seconds a face must be on screen before it can be skipped. Not host-settable. */
  blitz_skip_after_seconds: number;
  /** 100 flat plus up to 100 for accuracy. */
  max_points_per_face: number;
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
  /**
   * The live blitz, when `config.mode` is `"blitz"`. `round` stays null for the whole
   * game in that mode, and this stays null in classic: exactly one is ever set.
   */
  blitz: BlitzState | null;
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

/** What the skipping player gets back: the face they just moved on to. */
export interface BlitzSkipResponse {
  status: "skipped";
  face_no: number;
  prompt: string;
  target: string;
  skip_ready_at: string;
}

export type FrameUploadResult =
  | { skipped: false; submission_id: string }
  | { skipped: true; reason: string };

/** One browser's best final score. `best` is null until it has finished a game. */
export interface HighScore {
  best: number | null;
  /** The name played under when the best was set. */
  best_name: string | null;
  best_at: string | null;
  games_played: number;
}
