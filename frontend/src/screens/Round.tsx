import { useCallback } from "react";

import { useFollowServerPhase, useGame } from "../game";
import { useFrameUploader } from "../hooks/useFrameUploader";
import { useNarration } from "../hooks/useNarration";
import { useServerCountdown } from "../hooks/useServerCountdown";
import { useVitalsReporter } from "../hooks/useVitalsReporter";
import { UncleDamage } from "../components/art";
import { useSpectra } from "../components/GameShell";
import { LeaveGame } from "../components/LeaveGame";
import {
  Avatar,
  ChunkyCard,
  Countdown,
  MeterBar,
  MetricTile,
  PageShell,
  Pill,
} from "../components/ui";

const BAR_HEIGHTS = [10, 22, 14, 28, 18, 24, 8, 20];

function Webcam({
  stream,
  ready,
  error,
}: {
  stream: MediaStream | null;
  ready: boolean;
  error: string | null;
}) {
  // A preview of the game's camera, which GameShell keeps running between rounds.
  const attach = useCallback(
    (video: HTMLVideoElement | null) => {
      if (video && video.srcObject !== stream) video.srcObject = stream;
    },
    [stream],
  );

  return (
    <section className="webcam" aria-label="Your webcam">
      <video ref={attach} autoPlay muted playsInline hidden={!ready} />
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
  const game = useGame();
  useFollowServerPhase(game);

  const { code, state, session, round, me, roster, mySubmission, iPassed, clockOffsetMs } = game;

  // Anchored to the server's own round deadline, not a local timer.
  const left = useServerCountdown(round?.ends_at, clockOffsetMs);

  // Started in the lobby and kept running all game; see GameShell.
  const spectra = useSpectra();

  // One camera, two consumers: raw frames to the Presage sidecar (vitals and the expression
  // read the server scores with), JPEG stills to the game server.
  const uploader = useFrameUploader({
    roomId: session?.room_id ?? null,
    playerId: session?.player_id ?? null,
    phase: state?.phase,
    intervalMs: state?.config.capture_interval_ms ?? 500,
    // Passing ends your round: the server takes no more frames from you until the next.
    enabled: spectra.ready && !!session && !iPassed,
    capture: spectra.captureFrame,
  });

  // Vitals go to the server so the whole room can see them. They are not scoring input.
  useVitalsReporter({
    roomId: session?.room_id ?? null,
    playerId: session?.player_id ?? null,
    metrics: spectra.measurements,
  });

  // Uncle Damage speaks as soon as the generated line lands on the round.
  const narration = useNarration(round?.audio_id);
  const speaking = left > 0 && !!round?.voice_line;

  const m = spectra.measurements;
  // Until a reading lands, say why: a face-position hint, or the sidecar's own status.
  const vitalsCaption = spectra.validation || spectra.status;
  const result = mySubmission?.result ?? null;

  return (
    <PageShell bg="lime" maxWidth={1240} gap={16} className="page--round">
      <header className="header" style={{ gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span className="round-badge">
            ROUND {round?.number ?? "…"} / {state?.config.rounds_per_game ?? "…"}
          </span>
          <Pill dark style={{ padding: "8px 14px", fontSize: 16 }}>
            lobby {code}
          </Pill>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <div
            role="group"
            aria-label="Players in this round"
            style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
          >
            {roster.map((seat) => (
              <span key={seat.player.id} title={seat.player.name}>
                <Avatar initial={seat.look.initial} color={seat.look.color} size={44} />
                <span className="sr-only">{seat.player.name}</span>
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
            <Pill
              thin
              bg="var(--yellow)"
              style={{ fontWeight: 600, fontSize: 13, padding: "3px 10px" }}
            >
              ElevenLabs voice agent ·{" "}
              <span className="voice-status">
                <span hidden={!speaking}>speaking</span>
                <span hidden={speaking}>listening</span>
              </span>
            </Pill>
            <div
              className={`voice-bars ${speaking ? "voice-bars--speaking" : ""}`}
              aria-hidden="true"
            >
              {BAR_HEIGHTS.map((h, i) => (
                <span key={i} style={{ height: h }} />
              ))}
            </div>
          </div>
          {/* The generated line once it lands, with the prompt the server is actually
              scoring against underneath it. Before then the prompt is the line. */}
          <p className="announcer__prompt">"{round?.voice_line ?? round?.prompt ?? "…"}"</p>
          {round?.voice_line && (
            <p className="announcer__target">
              show us: <b>{round.target}</b>
              {narration.blocked && " · tap anywhere to hear Uncle Damage"}
            </p>
          )}
        </div>
        <Countdown seconds={left} />
      </ChunkyCard>

      <div className="round__main">
        <Webcam stream={spectra.stream} ready={spectra.ready} error={spectra.error} />

        <ChunkyCard as="aside" className="snitch" aria-labelledby="snitch-title">
          <div className="snitch__head">
            <h2 id="snitch-title">Presage reads</h2>
          </div>
          <div className="snitch__reads">
            {/* The server's actual verdict on the frames you uploaded, stacked full width. */}
            <MetricTile
              label="Server read"
              value={result?.label ?? "--"}
              caption={round ? `target: ${round.target}` : "no round"}
              bg="var(--tint-yellow)"
            />
            <MetricTile
              label="Matched"
              value={
                iPassed
                  ? "passed!"
                  : mySubmission?.correct === null
                    ? "…"
                    : mySubmission?.correct
                      ? "yes"
                      : "no"
              }
              caption={
                iPassed
                  ? "locked in · waiting for the others"
                  : mySubmission
                    ? `frame ${mySubmission.status}`
                    : "no frame scored yet"
              }
              bg="var(--tint-lime)"
            />
            {/* Breathing comes from the SmartSpectra sidecar and is forwarded to the server so
                the whole room can see it -- but it is never scoring input. */}
            <MetricTile
              label="Breathing"
              value={m?.breathing ?? "--"}
              unit="/min"
              caption={m ? "live read" : vitalsCaption}
              bg="var(--tint-cyan)"
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontWeight: 700,
                fontSize: 16,
              }}
            >
              <span>Damage match</span>
              <span>{result ? Math.round(result.confidence * 100) : 0}%</span>
            </div>
            {/* The processor's own confidence in its read -- the closest thing the backend
                has to the design's "damage match". */}
            <MeterBar
              value={result ? Math.round(result.confidence * 100) : 0}
              label="Damage match"
              color="var(--pink)"
              height={26}
              divider
            />
          </div>
          <div className="aura-box">
            <div>aura so far</div>
            <div>{me?.points ?? 0}</div>
          </div>
          <p className="snitch__uplink">
            frames sent {uploader.sent} · skipped {uploader.skipped} · failed {uploader.failed}
            {uploader.lastError ? ` · ${uploader.lastError}` : ""}
          </p>
        </ChunkyCard>
      </div>
    </PageShell>
  );
}
