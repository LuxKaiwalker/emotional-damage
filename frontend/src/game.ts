import { useEffect, useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { useGameSocket } from "./hooks/useGameSocket";
import { lookFor, type Look } from "./avatar";
import { phasePath } from "./routes";
import { loadSessionFor, type StoredSession } from "./session";
import type { GameState, Phase, Player, Round, RoundScore, Submission } from "./types";

/**
 * The single bridge between the screens and the server.
 *
 * Round progress used to live in the query string because there was no backend to ask.
 * Now the server owns it: `phase` decides which screen you are on, `round.ends_at` drives
 * the countdown, and `players` is the real roster. Nothing here derives game state -- it
 * only reshapes the snapshot into what the components already expect.
 */

export interface Standing {
  player: Player;
  look: Look;
  rank: number;
  /** Points gained in the round just scored. 0 until the server ends the round. */
  delta: number;
  /** How `delta` was made up; undefined for a player who did not pass. */
  score: RoundScore | undefined;
  total: number;
  isMe: boolean;
}

export interface Game {
  code: string;
  session: StoredSession | null;
  state: GameState | null;
  connected: boolean;
  clockOffsetMs: number;
  phase: Phase | undefined;
  round: Round | null;
  /** This player's own record, once the snapshot has arrived. */
  me: Player | undefined;
  isHost: boolean;
  /** Roster in join order, for lobby slots. */
  roster: { player: Player; look: Look; isHost: boolean; isMe: boolean }[];
  /** Roster ranked by points, for the leaderboard and winner screens. */
  standings: Standing[];
  /** This player's submission in the current round, if any has been scored. */
  mySubmission: Submission | undefined;
  /** Whether I have passed this round: the server takes no more frames from me. */
  iPassed: boolean;
}

export function useGame(): Game {
  const code = (useParams().code ?? "").toUpperCase();
  const session = useMemo(() => loadSessionFor(code), [code]);
  const { state, connected, clockOffsetMs } = useGameSocket(
    session?.room_id ?? null,
    session?.player_id ?? null,
  );

  const me = session && state ? state.players[session.player_id] : undefined;
  const isHost = !!(session && state && state.host_id === session.player_id);

  const roster = useMemo(() => {
    if (!state) return [];
    return Object.values(state.players)
      .slice()
      .sort((a, b) => a.joined_at.localeCompare(b.joined_at))
      .map((player) => ({
        player,
        look: lookFor(player),
        isHost: player.id === state.host_id,
        isMe: player.id === session?.player_id,
      }));
  }, [state, session?.player_id]);

  const standings = useMemo(() => {
    if (!state) return [];
    const awarded = state.round?.points_awarded ?? {};
    return Object.values(state.players)
      .slice()
      .sort(
        (a, b) =>
          b.points - a.points ||
          b.rounds_correct - a.rounds_correct ||
          a.joined_at.localeCompare(b.joined_at),
      )
      .map((player, i) => ({
        player,
        look: lookFor(player),
        rank: i + 1,
        delta: awarded[player.id] ?? 0,
        score: state.round?.scores[player.id],
        total: player.points,
        isMe: player.id === session?.player_id,
      }));
  }, [state, session?.player_id]);

  const mySubmission =
    session && state?.round ? state.round.submissions[session.player_id] : undefined;
  const iPassed = !!(session && state?.round?.passed[session.player_id]);

  return {
    code,
    session,
    state,
    connected,
    clockOffsetMs,
    phase: state?.phase,
    round: state?.round ?? null,
    me,
    isHost,
    roster,
    standings,
    mySubmission,
    iPassed,
  };
}

/**
 * Follow the server's phase.
 *
 * Every screen transition is a consequence of the authoritative state, not of a <Link>:
 * the host pressing start moves *everyone*, and a reload lands you back where the game
 * actually is. Without a seat in this lobby there is nothing to follow, so send the player
 * to the join screen to get one.
 */
export function useFollowServerPhase(game: Game): void {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { state, session, code } = game;

  useEffect(() => {
    if (!session) {
      navigate(code ? `/join?code=${code}` : "/", { replace: true });
      return;
    }
    if (!state) return;
    const target = phasePath(state.phase, code);
    if (pathname !== target) navigate(target, { replace: true });
  }, [state?.phase, state, session, code, pathname, navigate]);
}
