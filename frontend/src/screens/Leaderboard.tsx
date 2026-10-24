import { useEffect, useState, type CSSProperties } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { gameQuery, useGameParams } from "../game";
import { LeaveGame } from "../components/LeaveGame";
import { Avatar, ChunkyButton, ChunkyCard, PageShell, Pill } from "../components/ui";
import { lobby, results, roundState } from "../mock/data";

const NEXT_IN = 5;

export function Leaderboard() {
  const code = (useParams().code ?? lobby.code).toUpperCase();
  const params = useGameParams();
  const navigate = useNavigate();
  const [left, setLeft] = useState(NEXT_IN);
  // Freeze the auto-advance while the leave dialog is open.
  const [paused, setPaused] = useState(false);

  const last = params.round >= params.total;
  const next = last
    ? `/play/${code}/winner${gameQuery(params)}`
    : `/play/${code}${gameQuery({ ...params, round: params.round + 1 })}`;

  useEffect(() => {
    if (paused) return;
    const id = window.setInterval(() => setLeft((s) => Math.max(s - 1, 0)), 1000);
    return () => window.clearInterval(id);
  }, [paused]);

  useEffect(() => {
    if (left === 0) navigate(next);
  }, [left, next, navigate]);

  const rows = results.rows;

  return (
    <PageShell bg="yellow" maxWidth={1000} gap={26}>
      <div className="header">
        <LeaveGame onOpenChange={setPaused} />
      </div>
      <header className="lb__header">
        <Pill dark style={{ padding: "8px 16px", fontSize: 16 }}>
          round {params.round} of {params.total} · "{roundState.promptShort}"
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
          {rows.map((r, i) => {
            const first = i === 0;
            const lastRow = i === rows.length - 1;
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
                  <Avatar initial={r.player.initial} color={r.player.color} size={50} />
                  <span className="result-row__name">{r.player.name}</span>
                  <Pill thin style={{ fontSize: 13, padding: "4px 10px" }}>
                    {r.tag}
                  </Pill>
                </div>
                <span className="col-num result-row__delta">{r.delta}</span>
                <span className="col-num result-row__total">{r.total}</span>
              </li>
            );
          })}
        </ol>
      </ChunkyCard>

      <section aria-labelledby="receipts" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="receipts__head">
          <h2 id="receipts">Presage receipts</h2>
          <Pill style={{ padding: "6px 12px" }}>this round's biometrics, exposed</Pill>
        </div>
        <div className="receipts__grid">
          {results.receipts.map((r) => (
            <div
              key={r.label}
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
          {results.roast}
        </div>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          {params.demo && (
            <ChunkyButton to={`/play/${code}/winner${gameQuery(params)}`} color="white" size="plain">
              (prototype) final →
            </ChunkyButton>
          )}
          <ChunkyButton to={next} color="lime">
            <span aria-live="polite">
              {last ? "Final results" : "Next round"} in {left}…
            </span>
          </ChunkyButton>
        </div>
      </div>
    </PageShell>
  );
}
