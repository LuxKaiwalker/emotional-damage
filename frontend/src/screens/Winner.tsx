import type { CSSProperties } from "react";
import { useParams } from "react-router-dom";

import { useGameParams } from "../game";
import { Confetti, Crown } from "../components/art";
import { Avatar, ChunkyButton, ChunkyCard, PageShell, Pill } from "../components/ui";
import { lobby, winner } from "../mock/data";

export function Winner() {
  const code = (useParams().code ?? lobby.code).toUpperCase();
  const { total } = useGameParams();
  const lastRank = winner.others[winner.others.length - 1]?.rank;

  return (
    <div className="winner">
      <Confetti className="confetti" />
      <PageShell bg="cyan" maxWidth={1060} gap={26} innerClassName="winner__inner">
        <Pill dark style={{ padding: "8px 16px", fontSize: 16 }}>
          game over · {total} rounds of suffering complete
        </Pill>

        <div className="champion">
          <Crown className="crown" />
          <Avatar initial={winner.player.initial} color="var(--white)" size={170} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "center", maxWidth: "100%" }}>
          <h1 className="title-outline winner__name">{winner.player.name}</h1>
          <span className="badge tilt" style={{ "--tilt": "-2deg" } as CSSProperties}>
            MOST EMOTIONALLY DAMAGED
          </span>
        </div>

        <div className="stats">
          <ChunkyCard className="stat">
            <div>Total aura</div>
            <div>{winner.totalAura}</div>
          </ChunkyCard>
          <ChunkyCard className="stat">
            <div>Peak pulse</div>
            <div>
              {winner.peakPulse} <small>bpm</small>
            </div>
          </ChunkyCard>
          <ChunkyCard className="stat">
            <div>Best round</div>
            <div>"{winner.bestRound}"</div>
          </ChunkyCard>
        </div>

        <ol className="placings" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {winner.others.map((o) => (
            <li key={o.rank} className="placing" style={{ background: o.bg }}>
              #{o.rank} {o.name} · {o.total}
              {o.rank === lastRank && " (down bad)"}
            </li>
          ))}
        </ol>

        <div className="row-wrap">
          <ChunkyButton to={`/lobby/${code}`} color="lime" size="lg">
            Back to lobby
          </ChunkyButton>
          <ChunkyButton to="/" color="white" size="lg">
            Touch grass
          </ChunkyButton>
        </div>
      </PageShell>
    </div>
  );
}
