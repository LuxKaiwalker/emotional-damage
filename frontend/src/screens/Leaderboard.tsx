import { useState, type CSSProperties } from "react";

import { useFollowServerPhase, useGame } from "../game";
import { LeaveGame } from "../components/LeaveGame";
import { Avatar, ChunkyCard, PageShell, Pill } from "../components/ui";

const ROASTS = [
  "the camera saw everything. we all did.",
  "some of you peaked in the lobby.",
  "that was a choice. respect.",
  "uncle damage is disappointed but not surprised.",
];

const RECEIPT_BG = ["var(--tint-pink)", "var(--tint-cyan)", "var(--tint-yellow)", "var(--tint-lime)"];
const RECEIPT_TILT = ["-1deg", "0.5deg", "1deg", "-0.5deg"];

/** 1 -> "1st", 2 -> "2nd", 11 -> "11th": the place a player passed in. */
function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13;
  const suffix = teen ? "th" : (["th", "st", "nd", "rd"][n % 10] ?? "th");
  return `${n}${suffix}`;
}

export function Leaderboard() {
  const game = useGame();
  useFollowServerPhase(game);

  const { state, round, standings, roster } = game;
  // The leave dialog no longer needs to pause anything: advancing is the server's job.
  const [, setPaused] = useState(false);

  const last = !!state && !!round && round.number >= state.config.rounds_per_game;
  const roast = ROASTS[(round?.number ?? 0) % ROASTS.length];

  // "Biometrics exposed" built from what the server actually decided about each player's frame.
  const receipts = roster
    .map((seat, i) => {
      const sub = round?.submissions[seat.player.id];
      return {
        key: seat.player.id,
        who: seat.player.name,
        label: sub?.correct ? "nailed it" : sub ? "missed it" : "no frame",
        value: sub?.result ? sub.result.label : "--",
        sub: sub?.result ? `${Math.round(sub.result.confidence * 100)}% sure` : "camera saw nothing",
        bg: RECEIPT_BG[i % RECEIPT_BG.length],
        tilt: RECEIPT_TILT[i % RECEIPT_TILT.length],
      };
    })
    .slice(0, 8);

  return (
    <PageShell bg="yellow" maxWidth={1000} gap={26}>
      <div className="header">
        <LeaveGame onOpenChange={setPaused} />
      </div>
      <header className="lb__header">
        <Pill dark style={{ padding: "8px 16px", fontSize: 16 }}>
          round {round?.number ?? "…"} of {state?.config.rounds_per_game ?? "…"} · "
          {round?.target ?? "…"}"
        </Pill>
        <h1 className="title-outline">WHO GOT COOKED</h1>
      </header>

      <ChunkyCard as="section" className="results" aria-labelledby="results-title">
        <h2 id="results-title" className="sr-only">
          Round results
        </h2>
        <div className="results__cols" aria-hidden="true">
          <span className="col-rank">RANK</span>
          <span className="col-player">PLAYER</span>
          <span className="col-num">THIS ROUND</span>
          <span className="col-num">TOTAL AURA</span>
        </div>
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 14 }}>
          {standings.map((r, i) => {
            const first = i === 0;
            const lastRow = i === standings.length - 1 && standings.length > 1;
            const bg = first ? "var(--pink)" : lastRow ? "var(--grey)" : "var(--tint-yellow)";
            const tilt = first ? "-1deg" : lastRow ? "1deg" : i === 1 ? "0.5deg" : "0deg";
            return (
              <li
                key={r.player.id}
                className="result-row tilt"
                style={{ background: bg, "--tilt": tilt } as CSSProperties}
                aria-label={`#${r.rank} ${r.player.name}, ${r.delta} this round, ${r.total} total aura`}
              >
                <span className="col-rank">#{r.rank}</span>
                <div className="col-player">
                  <Avatar initial={r.look.initial} color={r.look.color} size={50} />
                  <span className="result-row__name">
                    {r.player.name}
                    {r.isMe ? " (you)" : ""}
                  </span>
                  <Pill thin style={{ fontSize: 13, padding: "4px 10px" }}>
                    {r.delta > 0 ? "cooked" : "survived"}
                  </Pill>
                  {r.score && (
                    <Pill thin style={{ fontSize: 13, padding: "4px 10px" }}>
                      {ordinal(r.score.place)} · {r.score.speed_points} speed · {r.score.accuracy_points} face
                    </Pill>
                  )}
                </div>
                <span className="col-num result-row__delta">
                  {r.delta > 0 ? `+${r.delta}` : "0"}
                </span>
                <span className="col-num result-row__total">{r.total}</span>
              </li>
            );
          })}
        </ol>
      </ChunkyCard>

      <section aria-labelledby="receipts" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="receipts__head">
          <h2 id="receipts">Presage receipts</h2>
          <Pill style={{ padding: "6px 12px" }}>what the server actually saw</Pill>
        </div>
        <div className="receipts__grid">
          {receipts.map((r) => (
            <div
              key={r.key}
              className="receipt tilt"
              style={{ background: r.bg, "--tilt": r.tilt } as CSSProperties}
            >
              <span className="receipt__label">{r.label}</span>
              <span className="receipt__who">{r.who}</span>
              <span className="receipt__value">{r.value}</span>
              <span className="receipt__sub">{r.sub}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="lb__foot">
        <div className="roast-bubble tilt" style={{ "--tilt": "-1deg" } as CSSProperties}>
          {roast}
        </div>
        {/* No local timer: the server starts the next round after its intermission and the
            phase change moves everyone at once. */}
        <Pill dark style={{ padding: "10px 18px", fontSize: 16 }}>
          <span aria-live="polite">
            {last ? "final results" : "next round"} incoming…
          </span>
        </Pill>
      </div>
    </PageShell>
  );
}
