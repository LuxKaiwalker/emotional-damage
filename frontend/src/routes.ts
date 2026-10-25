import type { GameMode, Phase } from "./types";

/**
 * Which screen a phase belongs on.
 *
 * The server's `phase` is the only navigation authority: the host pressing start moves
 * everyone, and a reload lands you back where the game actually is. Kept free of imports
 * so the mapping can be tested on its own.
 *
 * `mode` is what splits the one `round` phase across two screens. Resolved here rather
 * than by a dispatcher component on `/play/:code`, because every screen gets its state
 * from `useGame()` and `useGame()` opens its own socket -- a dispatcher plus its child
 * would hold two per player for the whole game.
 */
export function phasePath(phase: Phase, code: string, mode: GameMode = "classic"): string {
  switch (phase) {
    case "lobby":
      return `/lobby/${code}`;
    case "round":
      return mode === "blitz" ? `/play/${code}/blitz` : `/play/${code}`;
    case "scoring":
      return `/play/${code}/results`;
    case "game_over":
      return `/play/${code}/winner`;
  }
}
