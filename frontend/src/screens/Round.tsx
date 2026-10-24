import { useFollowServerPhase, useGame } from "../game";
import { useFrameUploader } from "../hooks/useFrameUploader";
import { useServerCountdown } from "../hooks/useServerCountdown";
import { useSmartSpectra } from "../hooks/useSmartSpectra";
import { UncleDamage } from "../components/art";
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
  videoRef,
  ready,
  error,
}: {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  ready: boolean;
  error: string | null;
}) {
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
  const game = useGame();
  useFollowServerPhase(game);

  const { code, state, session, round, me, roster, mySubmission, clockOffsetMs } = game;

  // Anchored to the server's own round deadline, not a local timer.
  const left = useServerCountdown(round?.ends_at, clockOffsetMs);
  const speaking = left > 0;

  const spectra = useSmartSpectra();

  // One camera, two consumers: raw frames to the vitals sidecar, JPEG stills to the game server.
  const uploader = useFrameUploader({
    roomId: session?.room_id ?? null,
    playerId: session?.player_id ?? null,
    phase: state?.phase,
    intervalMs: state?.config.capture_interval_ms ?? 500,
    enabled: spectra.ready && !!session,
    capture: spectra.captureFrame,
  });

  const m = spectra.measurements;
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
          {/* The real prompt the server is scoring this round against. */}
          <p className="announcer__prompt">"{round?.prompt ?? "…"}"</p>
        </div>
        <Countdown seconds={left} />
      </ChunkyCard>

      <div className="round__main">
        <Webcam videoRef={spectra.videoRef} ready={spectra.ready} error={spectra.error} />

        <ChunkyCard as="aside" className="snitch" aria-labelledby="snitch-title">
          <div className="snitch__head">
            <h2 id="snitch-title">Presage reads</h2>
          </div>
          <div className="grid2">
            {/* Pulse and breathing come straight from the SmartSpectra sidecar: a local read
                that the game server never sees, so it cannot affect scoring. */}
            <MetricTile
              label="Pulse"
              value={m?.pulse ?? "--"}
              unit="bpm"
              caption={m ? "live read" : "waiting for vitals"}
              bg="var(--tint-pink)"
            />
            <MetricTile
              label="Breathing"
              value={m?.breathing ?? "--"}
              unit="/min"
              caption={m ? "live read" : "waiting for vitals"}
              bg="var(--tint-cyan)"
            />
            {/* These two are the server's actual verdict on the frames you uploaded. */}
            <MetricTile
              label="Server read"
              value={result?.label ?? "--"}
              caption={round ? `target: ${round.target}` : "no round"}
              bg="var(--tint-yellow)"
            />
            <MetricTile
              label="Matched"
              value={mySubmission?.correct === null ? "…" : mySubmission?.correct ? "yes" : "no"}
              caption={mySubmission ? `frame ${mySubmission.status}` : "no frame scored yet"}
              bg="var(--tint-lime)"
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
