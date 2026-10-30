import { useEffect, useState } from "react";

import { api } from "../api/client";
import { useMusic, useOnChange } from "../audio/hooks";
import { sfx } from "../audio/sfx";
import { useFollowServerPhase, useGame } from "../game";
import type { GameMode } from "../types";
import {
  Avatar,
  ChunkyButton,
  ChunkyCard,
  Header,
  PageShell,
  Pill,
} from "../components/ui";

/** The game lengths the server accepts (ROUND_CHOICES in backend/app/game/engine.py). */
const ROUND_CHOICES = [5, 10];

/** The modes the server accepts (GameMode in backend/app/models.py). */
const MODE_CHOICES: { value: GameMode; label: string }[] = [
  { value: "classic", label: "Classic" },
  { value: "blitz", label: "Blitzkrieg" },
];

/**
 * A row of mutually exclusive options for the host, or a read-only sticker for everyone
 * else. The same markup the rounds picker has always used, so it inherits its pop.
 */
function PickRow<T extends string | number>({
  label,
  value,
  options,
  editable,
  onPick,
}: {
  label: string;
  value: T | undefined;
  options: { value: T; label: string }[];
  editable: boolean;
  onPick: (next: T) => void;
}) {
  const current = options.find((o) => o.value === value);
  return (
    <div className="rules__row">
      <span>{label}</span>
      {editable ? (
        <span className="rounds-pick" role="group" aria-label={label}>
          {options.map((option) => (
            <button
              key={String(option.value)}
              type="button"
              className="sticker rounds-pick__opt"
              aria-pressed={value === option.value}
              onClick={() => onPick(option.value)}
            >
              {option.label}
            </button>
          ))}
        </span>
      ) : (
        <span className="sticker rules__vibe" key={current?.label ?? "…"}>
          {current?.label ?? "…"}
        </span>
      )}
    </div>
  );
}

const TAG_BG: Record<string, string> = {
  HOST: "var(--yellow)",
  READY: "var(--lime)",
  "NOT READY": "var(--white)",
};

/** A number with −/+ steppers for the host, or a plain sticker for everyone else. */
function TimingRow({
  label,
  value,
  step,
  min,
  max,
  editable,
  busy,
  onChange,
  unit = "s",
}: {
  label: string;
  value: number | undefined;
  step: number;
  /** The lowest value the server accepts, so "−" never sends one it will refuse. */
  min: number;
  max: number;
  editable: boolean;
  busy: boolean;
  onChange: (next: number) => void;
  /** Suffix on the value and in the button labels. Seconds unless told otherwise. */
  unit?: string;
}) {
  const shown = value === undefined ? "…" : `${value}${unit}`;
  if (!editable || value === undefined) {
    return (
      <div className="rules__row">
        <span>{label}</span>
        <span className="sticker rules__vibe" key={shown}>{shown}</span>
      </div>
    );
  }
  return (
    <div className="rules__row">
      <span>{label}</span>
      <span className="seg">
        <button
          type="button"
          aria-label={`${label}: ${step}${unit} less`}
          disabled={busy || value <= min}
          onClick={() => onChange(Math.max(min, value - step))}
        >
          −
        </button>
        <span className="sticker rules__vibe" aria-live="polite" key={shown}>
          {shown}
        </span>
        <button
          type="button"
          aria-label={`${label}: ${step}${unit} more`}
          disabled={busy || value + step > max}
          onClick={() => onChange(value + step)}
        >
          +
        </button>
      </span>
    </div>
  );
}

export function Lobby() {
  const game = useGame();
  useFollowServerPhase(game);

  const { code, state, session, isHost, roster, connected } = game;

  // The lobby music fills out as the room does: a lone host gets a sparse groove, a
  // full room the whole band.
  useMusic("lobby", { intensity: Math.min(0.9, 0.2 + 0.15 * roster.length) });
  useOnChange(roster.length, (now, before) => (now > before ? sfx.join() : sfx.leave()));
  const [copied, setCopied] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingTiming, setSavingTiming] = useState(false);
  const [timingError, setTimingError] = useState<string | null>(null);
  const [blitzError, setBlitzError] = useState<string | null>(null);
  useOnChange(error ?? timingError ?? blitzError, (now) => now && sfx.error());

  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(t);
  }, [copied]);

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(
        `${location.origin}/join?code=${code}`,
      );
      setCopied(true);
    } catch {
      /* clipboard blocked (insecure context / permissions): leave the label alone */
    }
  };

  const start = async () => {
    if (!session || starting) return;
    setStarting(true);
    setError(null);
    try {
      // Host only; the server answers 403 for anyone else. Everyone moves when the
      // phase change arrives over the socket, not because of this response.
      await api.startGame(session.room_id, session.player_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the game");
    } finally {
      setStarting(false);
    }
  };

  const pickRounds = async (rounds: number) => {
    if (!session) return;
    setError(null);
    try {
      // The new count arrives with the next snapshot, so every lobby shows it at once.
      await api.setRounds(session.room_id, session.player_id, rounds);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not change the rounds",
      );
    }
  };

  const pickMode = async (mode: GameMode) => {
    if (!session) return;
    setError(null);
    try {
      // Everyone's lobby swaps to the other mode's rows on the next snapshot.
      await api.setMode(session.room_id, session.player_id, mode);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the mode");
    }
  };

  // No optimistic update: the new config arrives in the next snapshot like everything
  // else, and a refused schedule simply never shows up.
  const setTiming = async (roundSeconds: number, decrement: number) => {
    if (!session || savingTiming) return;
    setSavingTiming(true);
    setTimingError(null);
    try {
      await api.setRoundTiming(
        session.room_id,
        session.player_id,
        roundSeconds,
        decrement,
      );
    } catch (err) {
      setTimingError(
        err instanceof Error ? err.message : "Could not change the timing",
      );
    } finally {
      setSavingTiming(false);
    }
  };

  /** Blitz settings go up whole, so the server validates the pair it has to check. */
  const setBlitz = async (over: {
    blitz_seconds?: number;
    blitz_face_seconds?: number;
    blitz_pass_confidence?: number;
    blitz_live_leaderboard?: boolean;
  }) => {
    if (!session || !state || savingTiming) return;
    const current = state.config;
    setSavingTiming(true);
    setBlitzError(null);
    try {
      await api.setBlitzConfig(session.room_id, session.player_id, {
        blitz_seconds: current.blitz_seconds,
        blitz_face_seconds: current.blitz_face_seconds,
        blitz_pass_confidence: current.blitz_pass_confidence,
        blitz_live_leaderboard: current.blitz_live_leaderboard,
        ...over,
      });
    } catch (err) {
      setBlitzError(
        err instanceof Error ? err.message : "Could not change the blitz settings",
      );
    } finally {
      setSavingTiming(false);
    }
  };

  // The server is the source of truth for both the roster and the rules.
  const config = state?.config;
  const isBlitz = config?.mode === "blitz";
  const roundLengths = config
    ? Array.from(
        { length: config.rounds_per_game },
        (_, i) => config.round_seconds - i * config.round_decrement_seconds,
      )
    : [];
  const maxPlayers = config?.max_players ?? 0;
  const slots = Array.from({ length: maxPlayers }, (_, i) => roster[i]);

  return (
    <PageShell bg="pink" maxWidth={1040} gap={0} className="page--fit">
      <Header back="← rage quit" />

      <div className="lobby__main">
        <div className="lobby__cols">
          <section className="lobby__left">
            <ChunkyCard className="code-card" tilt="-1.5deg">
              <span className="code-card__label" id="code-label">
                your lobby code
              </span>
              <div className="code-card__code" aria-labelledby="code-label">
                {code}
              </div>
              <button
                className={`btn copy-btn ${copied ? "copy-btn--done" : ""}`}
                type="button"
                onClick={copyInvite}
                aria-live="polite"
              >
                {copied ? "copied!" : "Copy invite link"}
              </button>
              <span className="code-card__roast">
                send it to the group chat. or don't. coward.
              </span>
            </ChunkyCard>

            <ChunkyCard className="rules">
              <h2>House rules</h2>
              {/* The host sets the mode and its settings; everyone sees them. Only the
                  selected mode's rows are shown, so the card keeps fitting one screen. */}
              <PickRow
                label="Mode"
                value={config?.mode}
                options={MODE_CHOICES}
                editable={isHost && !!config}
                onPick={(mode) => void pickMode(mode)}
              />
              {isBlitz ? (
                <>
                  <TimingRow
                    label="Blitz length"
                    value={config?.blitz_seconds}
                    step={15}
                    min={30}
                    max={600}
                    editable={isHost && !!config}
                    busy={savingTiming}
                    onChange={(v) => void setBlitz({ blitz_seconds: v })}
                  />
                  <TimingRow
                    label="Seconds per face"
                    value={config?.blitz_face_seconds}
                    step={1}
                    min={2}
                    max={60}
                    editable={isHost && !!config}
                    busy={savingTiming}
                    onChange={(v) => void setBlitz({ blitz_face_seconds: v })}
                  />
                  <TimingRow
                    label="Pass threshold"
                    unit="%"
                    value={
                      config
                        ? Math.round(config.blitz_pass_confidence * 100)
                        : undefined
                    }
                    step={5}
                    min={0}
                    max={95}
                    editable={isHost && !!config}
                    busy={savingTiming}
                    onChange={(v) =>
                      void setBlitz({ blitz_pass_confidence: v / 100 })
                    }
                  />
                  <PickRow
                    label="Live leaderboard"
                    value={config ? (config.blitz_live_leaderboard ? "on" : "off") : undefined}
                    options={[
                      { value: "on", label: "On" },
                      { value: "off", label: "Off" },
                    ]}
                    editable={isHost && !!config}
                    onPick={(next) =>
                      void setBlitz({ blitz_live_leaderboard: next === "on" })
                    }
                  />
                  <div className="rules__row">
                    <span>Skip unlocks after</span>
                    <span className="sticker rules__vibe">
                      {config ? `${config.blitz_skip_after_seconds}s` : "…"}
                    </span>
                  </div>
                  <div className="rules__row">
                    <span>Max points per face</span>
                    <span className="sticker rules__vibe">
                      {config?.max_points_per_face ?? "…"}
                    </span>
                  </div>
                </>
              ) : (
                <>
                  <PickRow
                    label="Rounds"
                    value={config?.rounds_per_game}
                    options={ROUND_CHOICES.map((n) => ({ value: n, label: String(n) }))}
                    editable={isHost && !!config}
                    onPick={(n) => void pickRounds(n)}
                  />
                  <TimingRow
                    label="Round 1 length"
                    value={config?.round_seconds}
                    step={5}
                    min={1}
                    max={180}
                    editable={isHost && !!config}
                    busy={savingTiming}
                    onChange={(v) =>
                      config && void setTiming(v, config.round_decrement_seconds)
                    }
                  />
                  <TimingRow
                    label="Shorter each round by"
                    value={config?.round_decrement_seconds}
                    step={1}
                    min={0}
                    max={15}
                    editable={isHost && !!config}
                    busy={savingTiming}
                    onChange={(v) =>
                      config && void setTiming(config.round_seconds, v)
                    }
                  />
                  <div className="rules__row">
                    <span>Round lengths</span>
                    <span
                      className="sticker rules__vibe"
                      key={roundLengths.join()}
                    >
                      {roundLengths.length
                        ? roundLengths.map((s) => `${s}s`).join(" → ")
                        : "…"}
                    </span>
                  </div>
                  <div className="rules__row">
                    <span>Max points per round</span>
                    <span className="sticker rules__vibe">
                      {config?.max_points_per_round ?? "…"}
                    </span>
                  </div>
                </>
              )}
              {/* Keyed, so a repeated refusal replays the shake. */}
              {(timingError ?? blitzError) && (
                <p
                  className="form-error"
                  role="alert"
                  key={timingError ?? blitzError ?? ""}
                >
                  {timingError ?? blitzError}
                </p>
              )}
            </ChunkyCard>
          </section>

          <ChunkyCard as="section" className="victims">
            <div className="victims__head">
              <h1>The victims</h1>
              <span
                className="victims__count"
                key={roster.length}
                aria-label={`${roster.length} of ${maxPlayers} players`}
              >
                {roster.length} / {maxPlayers || "…"}
              </span>
            </div>

            <ul className="slots">
              {slots.map((seat, i) => {
                if (!seat) {
                  return (
                    <li key={`empty-${i}`} className="slot slot--empty">
                      <Avatar initial="?" size={44} />
                      <span className="slot__wait">
                        waiting for victim #{i + 1}…
                      </span>
                    </li>
                  );
                }
                const tag = seat.isHost
                  ? "HOST"
                  : seat.player.connected
                    ? "READY"
                    : "NOT READY";
                return (
                  <li key={seat.player.id} className="slot slot--filled">
                    <Avatar
                      initial={seat.look.initial}
                      color={seat.look.color}
                      size={44}
                    />
                    <div className="slot__who">
                      <span className="slot__name">
                        {seat.player.name}
                        {seat.isMe ? " (you)" : ""}
                      </span>
                      <span className="slot__status">
                        {seat.player.connected
                          ? "cam on · vibes questionable"
                          : "connecting…"}
                      </span>
                    </div>
                    <Pill
                      bg={TAG_BG[tag]}
                      style={{
                        flex: "0 0 auto",
                        fontSize: 13,
                        padding: "4px 10px",
                      }}
                    >
                      {tag}
                    </Pill>
                  </li>
                );
              })}
            </ul>

            <div className="lobby__foot">
              <span>
                {!connected
                  ? "reconnecting to the server…"
                  : isHost
                    ? "All cams on? Ready when you are."
                    : "Waiting for the host to start the damage."}
              </span>
              {error && (
                <p className="form-error" role="alert" key={error}>
                  {error}
                </p>
              )}
              {isHost ? (
                <ChunkyButton
                  color="lime"
                  onClick={() => void start()}
                  disabled={starting || !connected || roster.length < 1}
                >
                  {starting ? "starting…" : "Start the damage →"}
                </ChunkyButton>
              ) : (
                <ChunkyButton color="lime" disabled>
                  waiting for host…
                </ChunkyButton>
              )}
            </div>
          </ChunkyCard>
        </div>
      </div>
    </PageShell>
  );
}
