import { useEffect, useState } from "react";

import { api } from "../api/client";
import { useFollowServerPhase, useGame } from "../game";
import { Avatar, ChunkyButton, ChunkyCard, Header, PageShell, Pill } from "../components/ui";

const TAG_BG: Record<string, string> = {
  HOST: "var(--yellow)",
  READY: "var(--lime)",
  "NOT READY": "var(--white)",
};

export function Lobby() {
  const game = useGame();
  useFollowServerPhase(game);

  const { code, state, session, isHost, roster, connected } = game;
  const [copied, setCopied] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(t);
  }, [copied]);

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(`${location.origin}/join?code=${code}`);
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

  // The server is the source of truth for both the roster and the rules.
  const config = state?.config;
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
              <button className="btn copy-btn" type="button" onClick={copyInvite} aria-live="polite">
                {copied ? "copied!" : "Copy invite link"}
              </button>
              <span className="code-card__roast">send it to the group chat. or don't. coward.</span>
            </ChunkyCard>

            <ChunkyCard className="rules">
              <h2>House rules</h2>
              {/* Set by the server (backend/.env); there is no endpoint to change them mid-lobby. */}
              <div className="rules__row">
                <span>Rounds</span>
                <span className="sticker rules__vibe">{config?.rounds_per_game ?? "…"}</span>
              </div>
              <div className="rules__row">
                <span>Seconds per round</span>
                <span className="sticker rules__vibe">{config ? `${config.round_seconds}s` : "…"}</span>
              </div>
              <div className="rules__row">
                <span>Points per correct face</span>
                <span className="sticker rules__vibe">{config?.points_per_correct ?? "…"}</span>
              </div>
            </ChunkyCard>
          </section>

          <ChunkyCard as="section" className="victims">
            <div className="victims__head">
              <h1>The victims</h1>
              <span
                className="victims__count"
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
                      <span className="slot__wait">waiting for victim #{i + 1}…</span>
                    </li>
                  );
                }
                const tag = seat.isHost ? "HOST" : seat.player.connected ? "READY" : "NOT READY";
                return (
                  <li key={seat.player.id} className="slot slot--filled">
                    <Avatar initial={seat.look.initial} color={seat.look.color} size={44} />
                    <div className="slot__who">
                      <span className="slot__name">
                        {seat.player.name}
                        {seat.isMe ? " (you)" : ""}
                      </span>
                      <span className="slot__status">
                        {seat.player.connected ? "cam on · vibes questionable" : "connecting…"}
                      </span>
                    </div>
                    <Pill bg={TAG_BG[tag]} style={{ flex: "0 0 auto", fontSize: 13, padding: "4px 10px" }}>
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
                <p className="form-error" role="alert">
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
