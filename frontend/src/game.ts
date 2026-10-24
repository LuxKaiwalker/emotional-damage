import { useSearchParams } from "react-router-dom";

import { lobby, roundState } from "./mock/data";

/**
 * Until the backend is wired in, round progress lives in the query string:
 * `r` = current round, `n` = total rounds, `t` = countdown seconds, `demo=1` shows prototype links.
 */
export type GameParams = { round: number; total: number; countdown: number; demo: boolean };

export function useGameParams(): GameParams {
  const [q] = useSearchParams();
  const num = (key: string, fallback: number) => {
    const v = Number(q.get(key));
    return Number.isFinite(v) && v > 0 ? v : fallback;
  };
  return {
    round: num("r", roundState.round),
    total: num("n", roundState.totalRounds),
    countdown: num("t", lobby.countdown),
    demo: q.get("demo") === "1",
  };
}

export function gameQuery(p: GameParams) {
  const q = new URLSearchParams({ r: String(p.round), n: String(p.total), t: String(p.countdown) });
  if (p.demo) q.set("demo", "1");
  return `?${q}`;
}
