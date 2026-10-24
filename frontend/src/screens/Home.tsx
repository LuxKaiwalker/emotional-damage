import { useState } from "react";

import { CringeFace, Mascot, ScreamFace, ShockFace } from "../components/art";
import { ChunkyButton, ChunkyCard, Modal, PageShell, Pill } from "../components/ui";
import { lobby } from "../mock/data";

const steps = [
  { color: "var(--pink)", title: "Uncle Damage speaks.", body: "Our voice agent yells a cursed prompt at the whole lobby." },
  { color: "var(--cyan)", title: "3… 2… 1… FACE.", body: "Pull the expression on webcam before the timer hits zero." },
  { color: "var(--lime)", title: "Farm aura.", body: "Presage reads your vitals, we score the damage. Leaderboard after every round." },
];

export function Home() {
  const [howOpen, setHowOpen] = useState(false);

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
              An AI yells a prompt. You have 3 seconds to pull the face. Your webcam snitches on your vitals. Most aura
              wins.
            </p>
          </div>
          <div className="home__faces home__faces--right">
            <Mascot className="face face--xl" />
            <ScreamFace className="face face--sm" />
          </div>
        </section>

        <section className="home__actions">
          <ChunkyCard className="action-card" tilt="-1deg" style={{ background: "var(--pink)" }}>
            <span style={{ alignSelf: "flex-start" }}>
              <Pill>HOST MODE</Pill>
            </span>
            <h2>Create game</h2>
            <p>Spawn a lobby, get a code, drag up to 4 friends into the trenches. 5 players max, no exceptions, no mercy.</p>
            <ChunkyButton to={`/lobby/${lobby.code}`}>Make a lobby →</ChunkyButton>
          </ChunkyCard>

          <ChunkyCard className="action-card" tilt="1deg" style={{ background: "var(--cyan)" }}>
            <span style={{ alignSelf: "flex-start" }}>
              <Pill>GOT A CODE?</Pill>
            </span>
            <h2>Join game</h2>
            <p>Your friend sent a 4-letter code. Type it in and accept your fate.</p>
            <ChunkyButton to="/join">Enter code →</ChunkyButton>
          </ChunkyCard>
        </section>
      </div>

      <Modal open={howOpen} onClose={() => setHowOpen(false)} labelledBy="how-title" className="how">
        <h2 id="how-title">How it works (it's not that deep)</h2>
        <ol className="how__steps">
          {steps.map((s, i) => (
            <li key={s.title} className="how__step">
              <span className="how__num" style={{ background: s.color }} aria-hidden="true">
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
