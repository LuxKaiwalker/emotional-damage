import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import { useMusic, useOnChange } from "../audio/hooks";
import { sfx } from "../audio/sfx";
import { useFollowServerPhase, useGame } from "../game";
import { useFrameUploader } from "../hooks/useFrameUploader";
import { useServerCountdown } from "../hooks/useServerCountdown";
import { useVitalsReporter } from "../hooks/useVitalsReporter";
import { UncleDamage } from "../components/art";
import { useSpectra } from "../components/GameShell";
import { LeaveGame } from "../components/LeaveGame";
import { Webcam } from "../components/Webcam";
import {
  Avatar,
  ChunkyButton,
  ChunkyCard,
  Countdown,
  MeterBar,
  MetricTile,
  PageShell,
  Pill,
} from "../components/ui";

/**
 * Emotional Blitzkrieg: one clock, no rounds, as many faces as you can land.
 *
 * Its own screen rather than a branch in `Round`, because almost nothing survives the
 * change: there is no round number, no shared deadline, no narration, two clocks instead
 * of one, and a control the classic screen has never had. What it does share -- the
 * camera, the webcam preview, the Presage panel -- comes from `GameShell`, `Webcam` and
 * the same `ui` primitives, so the two look like the same game.
 *
 * Every player walks the same sequence of faces in the same order; what differs is how
 * far along they are. That is the fairness guarantee, and the server holds the order so
 * nobody can read ahead.
 */
export function Blitz() {
  const game = useGame();
  useFollowServerPhase(game);

  const {
    code,
    state,
    session,
    me,
    roster,
    standings,
    myRun,
    showLiveBoard,
    clockOffsetMs,
  } = game;

  // Three deadlines, all anchored to the server's own timestamps by the same hook: the
  // blitz clock, this player's current face, and their skip cooldown.
  const blitzLeft = useServerCountdown(state?.game_ends_at, clockOffsetMs);
  const faceLeft = useServerCountdown(myRun?.face_ends_at, clockOffsetMs);
  const skipIn = useServerCountdown(myRun?.skip_ready_at, clockOffsetMs);

  // Started in the lobby and kept running all game; see GameShell.
  const spectra = useSpectra();

  // No `iPassed` gate, unlike the round screen: in blitz a pass moves you straight to
  // the next face, so the server always wants the next frame.
  const uploader = useFrameUploader({
    roomId: session?.room_id ?? null,
    playerId: session?.player_id ?? null,
    phase: state?.phase,
    intervalMs: state?.config.capture_interval_ms ?? 500,
    enabled: spectra.ready && !!session,
    capture: spectra.captureFrame,
  });

  useVitalsReporter({
    roomId: session?.room_id ?? null,
    playerId: session?.player_id ?? null,
    metrics: spectra.measurements,
  });

  const [skipError, setSkipError] = useState<string | null>(null);
  const skipping = useRef(false);

  const skip = async () => {
    if (!session || skipping.current) return;
    skipping.current = true;
    setSkipError(null);
    try {
      // The new face arrives in the next snapshot, like every other mutation.
      await api.skipFace(session.room_id, session.player_id);
    } catch (err) {
      // A 429 inside the cooldown is ordinary: show what the server said.
      setSkipError(err instanceof Error ? err.message : "Could not skip that one");
    } finally {
      skipping.current = false;
    }
  };

  // The blitz has one rising arc instead of a per-round one, so the music tightens as
  // the single clock runs down rather than resetting every few seconds.
  const total = state?.config.blitz_seconds ?? 1;
  const spent = Math.min(1, Math.max(0, 1 - blitzLeft / total));
  useMusic("round", { intensity: 0.45 + 0.5 * spent, tempo: 1.1 + 0.35 * spent });

  useOnChange(myRun?.passed ?? 0, (now, before) => now > before && sfx.pass());
  useOnChange(myRun?.skipped ?? 0, (now, before) => now > before && sfx.leave());
  useOnChange(myRun?.expired ?? 0, (now, before) => now > before && sfx.timeUp());
  useOnChange(skipError, (now) => now && sfx.error());
  useEffect(() => {
    sfx.go();
  }, []);
  // Deliberately no blip when a rival passes: in a blitz that would fire several times
  // a second. The live board carries that information instead.

  const read = myRun?.submission?.result ?? null;
  const match = read ? Math.round(read.confidence * 100) : 0;
  const bar = Math.round((state?.config.blitz_pass_confidence ?? 0) * 100);

  return (
    <PageShell bg="lime" maxWidth={1240} gap={16} className="page--blitz">
      <header className="header" style={{ gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span className="round-badge">FACE {myRun?.face_no ?? "…"}</span>
          <Pill dark style={{ padding: "8px 14px", fontSize: 16 }}>
            lobby {code}
          </Pill>
          <Pill
            thin
            bg="var(--pink)"
            style={{ fontWeight: 700, fontSize: 15, padding: "6px 12px" }}
          >
            blitzkrieg · {blitzLeft}s left
          </Pill>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <div
            role="group"
            aria-label="Players in this blitz"
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
              no time to talk · {myRun?.passed ?? 0} landed
            </Pill>
          </div>
          {/* Keyed by the prompt, so every advance slaps the next one in. */}
          <p className="announcer__prompt" key={myRun?.prompt ?? ""}>
            "{myRun?.prompt ?? "…"}"
          </p>
          <p className="announcer__target">
            show us: <b>{myRun?.target ?? "…"}</b>
            {bar > 0 && ` · needs ${bar}% to count`}
          </p>
          <div className="blitz__skip">
            <ChunkyButton
              color="yellow"
              size="plain"
              onClick={() => void skip()}
              disabled={skipIn > 0 || !myRun}
            >
              {skipIn > 0 ? `skip in ${skipIn}s` : "can't do it → skip"}
            </ChunkyButton>
            {skipError && (
              <p className="form-error" role="alert" key={skipError}>
                {skipError}
              </p>
            )}
          </div>
        </div>
        {/* The per-face dial. A face that runs out is a miss, not a capture. */}
        <Countdown
          seconds={faceLeft}
          label="FACE NOW"
          doneText="too slow"
          doneLabel="next up…"
          hotFrom={3}
        />
      </ChunkyCard>

      <div className="round__main">
        <Webcam stream={spectra.stream} ready={spectra.ready} error={spectra.error} />

        <ChunkyCard as="aside" className="snitch" aria-labelledby="blitz-title">
          <div className="snitch__head">
            <h2 id="blitz-title">Presage reads</h2>
          </div>
          <div className="snitch__reads">
            <MetricTile
              label="Server read"
              value={read?.label ?? "--"}
              caption={myRun ? `target: ${myRun.target}` : "no face"}
              bg="var(--tint-yellow)"
            />
            <MetricTile
              label="Faces landed"
              value={myRun?.passed ?? 0}
              caption={`${myRun?.skipped ?? 0} skipped · ${myRun?.expired ?? 0} ran out`}
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
              <span>{match}%</span>
            </div>
            <MeterBar
              value={match}
              label="Damage match"
              color="var(--pink)"
              height={26}
              divider
            />
          </div>

          {showLiveBoard ? (
            <ol className="blitz__board" aria-label="Live standings">
              {standings.map((row) => (
                <li
                  key={row.player.id}
                  className={`blitz__row ${row.isMe ? "blitz__row--me" : ""}`}
                >
                  <span className="blitz__rank">{row.rank}</span>
                  <Avatar
                    initial={row.look.initial}
                    color={row.look.color}
                    size={44}
                  />
                  <span className="blitz__name">{row.player.name}</span>
                  <span className="blitz__faces">
                    {row.player.rounds_correct} faces
                  </span>
                  <span className="blitz__count" key={row.total}>
                    {row.total}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <div className="aura-box">
              <div>aura so far</div>
              <div key={me?.points ?? 0}>{me?.points ?? 0}</div>
            </div>
          )}

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
