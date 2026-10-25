import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useMusic, useOnChange } from "../audio/hooks";
import { sfx } from "../audio/sfx";
import { CringeFace, Mascot, ScreamFace, ShockFace } from "../components/art";
import {
  ChunkyButton,
  ChunkyCard,
  Modal,
  PageShell,
  Pill,
} from "../components/ui";
import { getClientId, saveSession } from "../session";
import type { HighScore } from "../types";
import askForCameraPermission from "../hooks/useCameraPermission";

const steps = [
  {
    color: "var(--pink)",
    title: "Uncle Damage speaks.",
    body: "Our voice agent yells a cursed prompt at the whole lobby.",
  },
  {
    color: "var(--cyan)",
    title: "3… 2… 1… FACE.",
    body: "Pull the expression on webcam before the timer hits zero.",
  },
  {
    color: "var(--lime)",
    title: "Farm aura.",
    body: "Presage reads your vitals, we score the damage. Leaderboard after every round.",
  },
];

/** The backend requires a name of 1-32 chars on both create and join. */
export const NAME_MAX = 32;

/** This browser's best final score, as the server recorded it. Hidden when the server can't say. */
function HighScoreBadge() {
  const [score, setScore] = useState<HighScore | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getHighScore(getClientId())
      .then((s) => !cancelled && setScore(s))
      .catch(() => {
        /* server unreachable: no badge beats a broken one, and creating a lobby will say why */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!score) return null;
  const games = score.games_played;
  return (
    <div className="high-score" role="status">
      <span className="high-score__label">your high score</span>
      {score.best === null ? (
        <span className="high-score__sub">none yet. finish a game to set one.</span>
      ) : (
        <>
          <span className="high-score__num">{score.best.toLocaleString()}</span>
          <span className="high-score__sub">
            aura as {score.best_name} · best of {games} game{games === 1 ? "" : "s"}
          </span>
        </>
      )}
    </div>
  );
}

export function Home() {
  useMusic("menu");
  const navigate = useNavigate();
  const [howOpen, setHowOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useOnChange(error, (now) => now && sfx.error());

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      // The room and this player's seat are minted together; persist the seat before leaving.
      const sess = await api.createRoom(trimmed, getClientId());
      saveSession(sess, trimmed);
      navigate(`/lobby/${sess.join_code.toUpperCase()}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create a lobby");
      setBusy(false);
    }
  };

  return (
    <PageShell bg="yellow" className="page--fit" innerClassName="home" gap={0}>
      <header className="header" style={{ justifyContent: "flex-end" }}>
        <button
          type="button"
          className="btn pill-link"
          style={{ fontWeight: 600 }}
          aria-haspopup="dialog"
          onClick={() => setHowOpen(true)}
        >
          How to play
        </button>
      </header>

      <div className="home__main">
        <section className="home__hero">
          <div className="home__faces home__faces--left">
            <ShockFace className="face face--lg" />
            <CringeFace className="face face--sm" />
          </div>
          <div className="home__hero-copy">
            <h1 className="title-outline" style={{ letterSpacing: 1 }}>
              EMOTIONAL
              <br />
              DAMAGE
            </h1>
            <p className="home__tagline">
              An AI yells a prompt. You have limited time to pull the face. Your
              webcam snitches on your vitals. Most aura wins.
            </p>
            <HighScoreBadge />
          </div>
          <div className="home__faces home__faces--right">
            <Mascot className="face face--xl" />
            <ScreamFace className="face face--sm" />
          </div>
        </section>

        <section className="home__actions">
          <ChunkyCard
            className="action-card"
            tilt="-1deg"
            style={{ background: "var(--pink)" }}
          >
            <span style={{ alignSelf: "flex-start" }}>
              <Pill>HOST MODE</Pill>
            </span>
            <h2>Create game</h2>
            <p>
              Spawn a lobby, get a code, drag your friends into the trenches.
              The server picks the prompts; no mercy.
            </p>
            <ChunkyButton onClick={() => setCreateOpen(true)}>
              Make a lobby →
            </ChunkyButton>
          </ChunkyCard>

          <ChunkyCard
            className="action-card"
            tilt="1deg"
            style={{ background: "var(--cyan)" }}
          >
            <span style={{ alignSelf: "flex-start" }}>
              <Pill>GOT A CODE?</Pill>
            </span>
            <h2>Join game</h2>
            <p>
              Your friend sent a 4-letter code. Type it in and accept your fate.
            </p>
            <ChunkyButton to="/join">Enter code →</ChunkyButton>
          </ChunkyCard>
        </section>
      </div>

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        labelledBy="create-title"
        describedBy="create-desc"
      >
        <Mascot className="modal__face" />
        <h2 id="create-title">What do we call you?</h2>
        <p id="create-desc">
          This is the name on the leaderboard when you get cooked.
        </p>
        <form
          className="name-form"
          onSubmit={async (e) => {
            e.preventDefault();
            const granted = await askForCameraPermission();
            if (granted) {
              void create();
            } else {
              setError("You need to enable your webcam to play");
            }
          }}
        >
          <label className="sr-only" htmlFor="host-name">
            Your name
          </label>
          <input
            id="host-name"
            className="name-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={NAME_MAX}
            placeholder="e.g. rizzlord"
            autoComplete="nickname"
            autoFocus
          />
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="modal__actions">
            <ChunkyButton
              color="lime"
              type="submit"
              disabled={!name.trim() || busy}
            >
              {busy ? "spawning…" : "Spawn the lobby →"}
            </ChunkyButton>
          </div>
        </form>
      </Modal>

      <Modal
        open={howOpen}
        onClose={() => setHowOpen(false)}
        labelledBy="how-title"
        className="how"
      >
        <h2 id="how-title">How it works (it's not that deep)</h2>
        <ol className="how__steps">
          {steps.map((s, i) => (
            <li key={s.title} className="how__step">
              <span
                className="how__num"
                style={{ background: s.color }}
                aria-hidden="true"
              >
                {i + 1}
              </span>
              <p>
                <b>{s.title}</b> {s.body}
              </p>
            </li>
          ))}
        </ol>
        <div className="modal__actions">
          <ChunkyButton color="lime" onClick={() => setHowOpen(false)}>
            Got it, let's go
          </ChunkyButton>
        </div>
      </Modal>
    </PageShell>
  );
}
