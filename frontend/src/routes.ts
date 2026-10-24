import type { Phase } from "./types";

/**
 * Which screen a phase belongs on.
 *
 * The server's `phase` is the only navigation authority: the host pressing start moves
 * everyone, and a reload lands you back where the game actually is. Kept free of imports
 * so the mapping can be tested on its own.
 */
export function phasePath(phase: Phase, code: string): string {
  switch (phase) {
    case "lobby":
      return `/lobby/${code}`;
    case "round":
      return `/play/${code}`;
    case "scoring":
      return `/play/${code}/results`;
    case "game_over":
      return `/play/${code}/winner`;
  }
}
