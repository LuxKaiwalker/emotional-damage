import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { gameQuery, useGameParams } from "../game";
import { useCamera } from "../hooks/useCamera";
import { UncleDamage } from "../components/art";
import { LeaveGame } from "../components/LeaveGame";
import { Avatar, ChunkyCard, Countdown, MeterBar, MetricTile, PageShell, Pill } from "../components/ui";
import { allPlayers, lobby, roundState } from "../mock/data";

const BAR_HEIGHTS = [10, 22, 14, 28, 18, 24, 8, 20];

function useCountdown(from: number) {
  const [left, setLeft] = useState(from);
  useEffect(() => {
    const id = window.setInterval(() => {
      setLeft((s) => {
        if (s <= 1) window.clearInterval(id);
        return Math.max(s - 1, 0);
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [from]);
  return left;
}

function Webcam() {
  const { videoRef, ready, error } = useCamera();
  return (
    <section className="webcam" aria-label="Your webcam">
      <video ref={videoRef} autoPlay muted playsInline hidden={!ready} />
      {error && (
        <p className="webcam__msg">
          <b>camera said no</b>
          {error}
        </p>
      )}
    </section>
  );
}

export function Round() {
  const code = (useParams().code ?? lobby.code).toUpperCase();
  const params = useGameParams();
  const left = useCountdown(params.countdown);
  const speaking = left > 0;
  const { live } = roundState;

  return (
    <PageShell bg="lime" maxWidth={1240} gap={16} className="page--round">
      <header className="header" style={{ gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span className="round-badge">
            ROUND {params.round} / {params.total}
          </span>
          <Pill dark style={{ padding: "8px 14px", fontSize: 16 }}>
            lobby {code}
          </Pill>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <div role="group" aria-label="Players in this round" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {allPlayers.map((p) => (
              <span key={p.id} title={p.name}>
                <Avatar initial={p.initial} color={p.color} size={44} />
                <span className="sr-only">{p.name}</span>
              </span>
            ))}
          </div>
          <LeaveGame />
        </div>
      </header>

      <ChunkyCard as="section" className="announcer">
        <UncleDamage className="announcer__face" />
        <div className="announcer__mid">
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 700, fontSize: 17 }}>Uncle Damage</span>
            <Pill thin bg="var(--yellow)" style={{ fontWeight: 600, fontSize: 13, padding: "3px 10px" }}>
              ElevenLabs voice agent ·{" "}
              <span className="voice-status">
                <span hidden={!speaking}>speaking</span>
                <span hidden={speaking}>listening</span>
              </span>
            </Pill>
            <div className={`voice-bars ${speaking ? "voice-bars--speaking" : ""}`} aria-hidden="true">
              {BAR_HEIGHTS.map((h, i) => (
                <span key={i} style={{ height: h }} />
              ))}
            </div>
          </div>
          <p className="announcer__prompt">"{roundState.prompt}"</p>
        </div>
        <Countdown seconds={left} />
      </ChunkyCard>

      <div className="round__main">
        <Webcam />

        <ChunkyCard as="aside" className="snitch" aria-labelledby="snitch-title">
          <div className="snitch__head">
            <h2 id="snitch-title">Presage reads</h2>
          </div>
          <div className="grid2">
            <MetricTile label="Pulse" value={live.pulse} unit="bpm" caption="↑ panicking" bg="var(--tint-pink)" />
            <MetricTile label="Breathing" value={live.breathing} unit="/min" caption="hyperventilating" bg="var(--tint-cyan)" />
            <MetricTile label="Blinks" value={live.blinks} caption="sus amount" bg="var(--tint-yellow)" />
            <MetricTile
              label="Talking"
              value={live.talking ? "yes" : "no"}
              caption={live.talking ? "screaming, prob" : "silent treatment"}
              bg="var(--tint-lime)"
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, fontSize: 16 }}>
              <span>Damage match</span>
              <span>{live.damageMatch}%</span>
            </div>
            <MeterBar value={live.damageMatch} label="Damage match" color="var(--pink)" height={26} divider />
          </div>
          <div className="aura-box">
            <div>aura this round</div>
            <div>+{live.aura}</div>
          </div>
          {/* always rendered so the panel (and the webcam beside it) keeps its height when the countdown ends */}
          {params.demo || !speaking ? (
            <Link className="btn proto-link" to={`/play/${code}/results${gameQuery(params)}`}>
              {speaking ? "(prototype) skip to results →" : "see who got cooked →"}
            </Link>
          ) : (
            <span className="btn proto-link proto-link--reserved" aria-hidden="true">
              see who got cooked →
            </span>
          )}
        </ChunkyCard>
      </div>
    </PageShell>
  );
}
