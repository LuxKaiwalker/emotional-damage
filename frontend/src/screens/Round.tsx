import { useEffect, useRef } from "react";

import { useMusic, useOnChange } from "../audio/hooks";
import { sfx } from "../audio/sfx";
import { useFollowServerPhase, useGame } from "../game";
import { useFrameUploader } from "../hooks/useFrameUploader";
import { useNarration } from "../hooks/useNarration";
import { useServerCountdown } from "../hooks/useServerCountdown";
import { useVitalsReporter } from "../hooks/useVitalsReporter";
import { UncleDamage } from "../components/art";
import { useSpectra } from "../components/GameShell";
import { LeaveGame } from "../components/LeaveGame";
import { Webcam } from "../components/Webcam";
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

/**
 * The round's soundtrack, driven by the clock and the scoreboard.
 *
 * The music speeds up and fills out as time runs down, turns major and relieved once
 * you have passed, and the last five seconds tick. Other players passing gets a quiet
 * blip, so you hear the room pulling ahead of you.
 */
function useRoundAudio({
  roundNo,
  totalS,
  left,
  iPassed,
  othersPassed,
}: {
  roundNo: number | undefined;
  totalS: number;
  left: number;
  iPassed: boolean;
  othersPassed: number;
}) {
  const elapsed = totalS > 0 ? Math.min(1, Math.max(0, 1 - left / totalS)) : 0;
  const finalStretch = left > 0 && left <= 5;
  useMusic(iPassed ? "roundPassed" : "round", {
    // Rounded so the player is not re-tuned on every 250 ms countdown tick.
    tempo:
      Math.round((1 + 0.12 * elapsed + (finalStretch ? 0.08 : 0)) * 50) / 50,
    intensity: iPassed ? 0.6 : Math.round((0.5 + 0.5 * elapsed) * 10) / 10,
  });

  // "GO" once per round, however often the screen re-renders or remounts.
  const announced = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (roundNo === undefined || left <= 0 || announced.current === roundNo)
      return;
    announced.current = roundNo;
    sfx.go();
  }, [roundNo, left]);

  useOnChange(left, (now, before) => {
    if (now === 0 && before > 0) sfx.timeUp();
    else if (now > 0 && now <= 5 && now < before) sfx.tick(now);
  });
  useOnChange(iPassed, (passed) => passed && sfx.pass());
  useOnChange(othersPassed, (now, before) => now > before && sfx.otherPassed());
}

export function Round() {
  const game = useGame();
  useFollowServerPhase(game);

  const {
    code,
    state,
    session,
    round,
    me,
    roster,
    mySubmission,
    iPassed,
    clockOffsetMs,
  } = game;

  // Anchored to the server's own round deadline, not a local timer.
  const left = useServerCountdown(round?.ends_at, clockOffsetMs);

  useRoundAudio({
    roundNo: round?.number,
    totalS: round
      ? (Date.parse(round.ends_at) - Date.parse(round.started_at)) / 1000
      : 0,
    left,
    iPassed,
    othersPassed: round
      ? Object.keys(round.passed).filter((id) => id !== session?.player_id)
          .length
      : 0,
  });

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

  const result = mySubmission?.result ?? null;

  return (
    <PageShell bg="lime" maxWidth={1240} gap={16} className="page--round">
      <header className="header" style={{ gap: 14 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <span className="round-badge">
            ROUND {round?.number ?? "…"} /{" "}
            {state?.config.rounds_per_game ?? "…"}
          </span>
          <Pill dark style={{ padding: "8px 14px", fontSize: 16 }}>
            lobby {code}
          </Pill>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            flexWrap: "wrap",
          }}
        >
          <div
            role="group"
            aria-label="Players in this round"
            style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
          >
            {roster.map((seat) => (
              <span key={seat.player.id} title={seat.player.name}>
                <Avatar
                  initial={seat.look.initial}
                  color={seat.look.color}
                  size={44}
                />
                <span className="sr-only">{seat.player.name}</span>
              </span>
            ))}
          </div>
          <LeaveGame />
        </div>
      </header>

      <ChunkyCard
        as="section"
        className={`announcer ${speaking ? "announcer--speaking" : ""}`}
      >
        <UncleDamage className="announcer__face" />
        <div className="announcer__mid">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontWeight: 700, fontSize: 17 }}>Uncle Damage</span>
            <Pill
              thin
              bg="var(--yellow)"
              style={{ fontWeight: 600, fontSize: 13, padding: "3px 10px" }}
            >
              {" "}
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
          {/* Keyed by the text, so the generated line pops in when it replaces the prompt. */}
          <p
            className="announcer__prompt"
            key={round?.voice_line ?? round?.prompt ?? ""}
          >
            "{round?.voice_line ?? round?.prompt ?? "…"}"
          </p>
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
        <Webcam
          stream={spectra.stream}
          ready={spectra.ready}
          error={spectra.error}
        />

        <ChunkyCard
          as="aside"
          className="snitch"
          aria-labelledby="snitch-title"
        >
          <div className="snitch__head">
            <h2 id="snitch-title">Presage reads</h2>
          </div>
          <div className="snitch__reads">
            {/* Just the server's verdict on your frames: the emotion it read, and whether it
                matched. Vitals still go to the server (useVitalsReporter) but are not shown. */}
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
            <div key={me?.points ?? 0}>{me?.points ?? 0}</div>
          </div>
          {spectra.readerDown && (
            <p className="snitch__uplink" role="status">
              <b>{spectra.readerDown}</b>
            </p>
          )}
          <p className="snitch__uplink">
            frames sent {uploader.sent} · skipped {uploader.skipped} · failed{" "}
            {uploader.failed}
            {uploader.lastError ? ` · ${uploader.lastError}` : ""}
          </p>
        </ChunkyCard>
      </div>
    </PageShell>
  );
}
