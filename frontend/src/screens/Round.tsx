import { useEffect, useState, type CSSProperties } from "react";
import { Link, useParams } from "react-router-dom";

import { gameQuery, useGameParams } from "../game";
import { useCamera } from "../hooks/useCamera";
import { Eye, UncleDamage } from "../components/art";
import { LeaveGame } from "../components/LeaveGame";
import { Avatar, ChunkyCard, Countdown, MeterBar, MetricTile, PageShell, Pill, Waveform } from "../components/ui";
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
      <span className="webcam__tl">
        <Pill bg="var(--pink)" style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 14px" }}>
          <span className="live-dot" aria-hidden="true" />
          LIVE · you
        </Pill>
      </span>
      <span className="webcam__tr">
        <Pill style={{ padding: "6px 14px" }}>{ready ? "face locked ✓" : error ? "no cam, no face" : "finding face…"}</Pill>
      </span>
      <div className="webcam__bottom">
        <span
          className="sticker tilt"
          style={{ background: "var(--yellow)", padding: "8px 14px", fontSize: 16, "--tilt": "-2deg" } as CSSProperties}
        >
          {roundState.roast}
        </span>
      </div>
    </section>
  );
}

export function Round() {
  const code = (useParams().code ?? lobby.code).toUpperCase();
  const params = useGameParams();
  const left = useCountdown(params.countdown);
  const speaking = left > 0;
  const { live, deepScan: ds } = roundState;

  return (
    <PageShell bg="lime" maxWidth={1240} gap={22} padding="24px 24px 40px">
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
              ElevenLabs voice agent · {speaking ? "speaking" : "listening"}
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
            <h2 id="snitch-title">Snitch-o-meter</h2>
            <Pill thin style={{ fontWeight: 600, fontSize: 12, padding: "3px 8px" }}>
              via Presage
            </Pill>
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
          {(params.demo || !speaking) && (
            <Link className="btn proto-link" to={`/play/${code}/results${gameQuery(params)}`}>
              {speaking ? "(prototype) skip to results →" : "see who got cooked →"}
            </Link>
          )}
        </ChunkyCard>
      </div>

      <ChunkyCard as="section" className="deepscan" aria-labelledby="deepscan">
        <div className="deepscan__head">
          <h2 id="deepscan">
            Deep scan <small>(Presage is reading your soul)</small>
          </h2>
          <Pill bg="var(--lime)" style={{ padding: "6px 14px" }}>
            signal confidence {ds.signalConfidence}% · {ds.stability}
          </Pill>
        </div>

        <div className="scan-grid">
          <div className="scan" style={{ background: "var(--tint-pink)" }}>
            <div className="scan__head">
              <h3>Heart goes brr</h3>
              <span>pulse pleth</span>
            </div>
            <Waveform points={ds.pulseWave} label="Pulse waveform, five sharp beats" />
            <div className="scan__row">
              <span className="scan__big">HRV {ds.hrv} ms</span>
              <span className="scan__sub">
                {ds.hrvVsBaseline < 0 ? "↓" : "↑"} {Math.abs(ds.hrvVsBaseline)}% vs your baseline = stressed fr
              </span>
            </div>
          </div>

          <div className="scan" style={{ background: "var(--tint-cyan)" }}>
            <div className="scan__head">
              <h3>Panic breathing</h3>
              <span>upper vs lower</span>
            </div>
            <div className="overlay" role="img" aria-label="Breathing waveforms: chest line large and fast, belly line small">
              <Waveform points={ds.breathingUpper} smooth decorative />
              <Waveform points={ds.breathingLower} smooth dashed decorative />
            </div>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontWeight: 600, fontSize: 14 }}>
              <span>— chest (upper)</span>
              <span>- - belly (lower)</span>
            </div>
            <div className="scan__big">chest-heavy: shallow &amp; fast. certified panic.</div>
          </div>

          <div className="scan" style={{ background: "var(--tint-yellow)" }}>
            <div className="scan__head">
              <h3>Pressure check</h3>
              <span>relative BP waveform</span>
            </div>
            <Waveform points={ds.bpWave} smooth label="Relative blood pressure waveform trending upward" />
            <div className="scan__row">
              <span className="scan__big">
                trend {{ up: "↑ climbing", down: "↓ dropping", flat: "→ flat" }[ds.bpTrend]}
              </span>
              <span className="scan__sub">relative, not a medical reading</span>
            </div>
          </div>

          <div className="scan" style={{ background: "var(--tint-lime)" }}>
            <div className="scan__head">
              <h3>Face classifier</h3>
              <span>expression</span>
            </div>
            {ds.expressions.map((e) => (
              <div key={e.label} className="classifier-row">
                <span>{e.label}</span>
                <MeterBar value={e.pct} label={e.label} color={e.color} />
                <span>{e.pct}%</span>
              </div>
            ))}
          </div>

          <div className="scan">
            <div className="scan__head">
              <h3>Eye snitch</h3>
              <span>iris + blinks</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
              <Eye gaze={ds.gazeVector} label={`Eye looking ${ds.gaze}`} />
              <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <span className="scan__big">gaze: {ds.gaze}</span>
                <span className="scan__sub">
                  looked away {ds.lookAways}× (sus) · {live.blinks} blinks · {ds.squints} squint
                  {ds.squints === 1 ? "" : "s"}
                </span>
              </div>
            </div>
            <div className="penalty">eye contact penalty: {ds.eyePenalty < 0 ? "−" : "+"}{Math.abs(ds.eyePenalty)} aura</div>
          </div>

          <div className="scan">
            <div className="scan__head">
              <h3>Commitment</h3>
              <span>face points + talking</span>
            </div>
            <div className="grid2" style={{ gap: 10 }}>
              {[
                ["mouth stretch", `${ds.face.mouthStretch}%`],
                ["brow crunch", `${ds.face.browCrunch}%`],
                ["held the face", `${ds.face.heldSeconds}s`],
                ["screamed", ds.face.screamed ? "yes" : "no"],
              ].map(([k, v]) => (
                <div key={k}>
                  <div className="scan__sub">{k}</div>
                  <div className="commit-val">{v}</div>
                </div>
              ))}
            </div>
            <div className="scan__sub">
              lighting {ds.face.lighting} · face {ds.face.inFrame}% in frame · stability good
            </div>
          </div>
        </div>

        <div className="vibe">
          <span className="vibe__tag">AI vibe check</span>
          <span className="vibe__quote">"{ds.vibeCheck}"</span>
        </div>
      </ChunkyCard>
    </PageShell>
  );
}
