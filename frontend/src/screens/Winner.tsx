import { useEffect, useState, type CSSProperties } from "react";

import { api } from "../api/client";
import { useMusic, useOnChange } from "../audio/hooks";
import { sfx } from "../audio/sfx";
import { useFollowServerPhase, useGame } from "../game";
import { Confetti, Crown } from "../components/art";
import { DeepScanSummary } from "../components/DeepScanSummary";
import { Avatar, ChunkyButton, ChunkyCard, PageShell, Pill } from "../components/ui";

const PLACING_BG = ["var(--yellow)", "var(--white)", "var(--white)", "var(--grey)"];

export function Winner() {
  const game = useGame();
  useFollowServerPhase(game);

  const { state, session, isHost, standings } = game;
  const [scanOpen, setScanOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useOnChange(error, (now) => now && sfx.error());

  const champion = standings[0];

  const iWon = !!champion?.isMe;
  useMusic(iWon ? "victory" : "gameover", { intensity: 0.8 });
  useEffect(() => {
    if (iWon) sfx.fanfare();
  }, [iWon]);
  const others = standings.slice(1);
  const lastRank = others[others.length - 1]?.rank;
  const totalRounds = state?.config.rounds_per_game ?? 0;

  const playAgain = async () => {
    if (!session || busy) return;
    setBusy(true);
    setError(null);
    try {
      // Host only: clears every score, bumps game_no and returns the room to its lobby.
      // Everyone else is moved by the phase change that follows.
      await api.restartGame(session.room_id, session.player_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not restart the game");
      setBusy(false);
    }
  };

  return (
    <div className="winner">
      <Confetti className="confetti" />
      <PageShell bg="cyan" maxWidth={1060} gap={26} innerClassName="winner__inner">
        <Pill dark style={{ padding: "8px 16px", fontSize: 16 }}>
          game over · {totalRounds} rounds of suffering complete
        </Pill>

        <div className="champion">
          <Crown className="crown" />
          <Avatar
            initial={champion?.look.initial ?? "?"}
            color="var(--white)"
            size={170}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "center", maxWidth: "100%" }}>
          <h1 className="title-outline winner__name">{champion?.player.name ?? "nobody"}</h1>
          <span className="badge tilt" style={{ "--tilt": "-2deg" } as CSSProperties}>
            MOST EMOTIONALLY DAMAGED
          </span>
        </div>

        {/* Every stat here is a real field off the final snapshot. */}
        <div className="stats">
          <ChunkyCard className="stat">
            <div>Total aura</div>
            <div>{champion?.total ?? 0}</div>
          </ChunkyCard>
          <ChunkyCard className="stat">
            <div>Faces nailed</div>
            <div>
              {champion?.player.rounds_correct ?? 0} <small>/ {totalRounds}</small>
            </div>
          </ChunkyCard>
          <ChunkyCard className="stat">
            <div>Victims</div>
            <div>{standings.length}</div>
          </ChunkyCard>
        </div>

        <ol className="placings" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {others.map((o, i) => (
            <li
              key={o.player.id}
              className="placing"
              style={{ background: PLACING_BG[Math.min(i, PLACING_BG.length - 1)] }}
            >
              #{o.rank} {o.player.name}
              {o.isMe ? " (you)" : ""} · {o.total}
              {o.rank === lastRank && others.length > 1 && " (down bad)"}
            </li>
          ))}
        </ol>

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <div className="row-wrap">
          <ChunkyButton color="yellow" size="lg" onClick={() => setScanOpen(true)}>
            Your deep scan
          </ChunkyButton>
          {isHost ? (
            <ChunkyButton color="lime" size="lg" onClick={() => void playAgain()} disabled={busy}>
              {busy ? "resetting…" : "Run it back"}
            </ChunkyButton>
          ) : (
            <ChunkyButton color="lime" size="lg" disabled>
              waiting for host…
            </ChunkyButton>
          )}
          <ChunkyButton to="/" color="white" size="lg">
            Touch grass
          </ChunkyButton>
        </div>
      </PageShell>
      <DeepScanSummary
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        rounds={state?.history ?? []}
        playerId={session?.player_id}
      />
    </div>
  );
}
