import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { gameQuery } from "../game";
import { Avatar, ChunkyButton, ChunkyCard, Header, PageShell, Pill } from "../components/ui";
import { lobby, type Player } from "../mock/data";

const TAG_BG: Record<NonNullable<Player["tag"]>, string> = {
  HOST: "var(--yellow)",
  READY: "var(--lime)",
  "NOT READY": "var(--white)",
};

function Segmented<T extends number>({
  label,
  options,
  value,
  onChange,
  format = String,
}: {
  label: string;
  options: T[];
  value: T;
  onChange: (v: T) => void;
  format?: (v: T) => string;
}) {
  return (
    <div className="rules__row">
      <span id={`seg-${label}`}>{label}</span>
      <div className="seg" role="group" aria-labelledby={`seg-${label}`}>
        {options.map((o) => (
          <button key={o} type="button" aria-pressed={o === value} onClick={() => onChange(o)}>
            {format(o)}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Lobby() {
  const code = (useParams().code ?? lobby.code).toUpperCase();
  const [rounds, setRounds] = useState(lobby.rounds);
  const [countdown, setCountdown] = useState(lobby.countdown);
  const [copied, setCopied] = useState(false);

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

  const slots = Array.from({ length: lobby.maxPlayers }, (_, i) => lobby.players[i]);

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
              <Segmented label="Rounds" options={[3, 5, 10]} value={rounds} onChange={setRounds} />
              <Segmented
                label="Countdown"
                options={[3, 5]}
                value={countdown}
                onChange={setCountdown}
                format={(v) => `${v}s`}
              />
              <div className="rules__row">
                <span>Uncle Damage vibe</span>
                <span className="sticker rules__vibe">
                  {lobby.vibe}
                </span>
              </div>
            </ChunkyCard>
          </section>

          <ChunkyCard as="section" className="victims">
            <div className="victims__head">
              <h1>The victims</h1>
              <span className="victims__count" aria-label={`${lobby.players.length} of ${lobby.maxPlayers} players`}>
                {lobby.players.length} / {lobby.maxPlayers}
              </span>
            </div>

            <ul className="slots">
              {slots.map((p, i) =>
                p ? (
                  <li key={p.id} className="slot slot--filled">
                    <Avatar initial={p.initial} color={p.color} size={44} />
                    <div className="slot__who">
                      <span className="slot__name">{p.name}</span>
                      <span className="slot__status">{p.status}</span>
                    </div>
                    {p.tag && (
                      <Pill bg={TAG_BG[p.tag]} style={{ flex: "0 0 auto", fontSize: 13, padding: "4px 10px" }}>
                        {p.tag}
                      </Pill>
                    )}
                  </li>
                ) : (
                  <li key={`empty-${i}`} className="slot slot--empty">
                    <Avatar initial="?" size={44} />
                    <span className="slot__wait">waiting for victim #{i + 1}…</span>
                  </li>
                ),
              )}
            </ul>

            <div className="lobby__foot">
              <span>All cams on? Everyone's face is mid-buffering. Ready when you are.</span>
              {lobby.isHost ? (
                <ChunkyButton
                  to={`/play/${code}${gameQuery({ round: 1, total: rounds, countdown, demo: false })}`}
                  color="lime"
                >
                  Start the damage →
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
