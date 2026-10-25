import { useState, type CSSProperties, type ComponentType } from "react";

import { mediaUrl } from "../api/client";
import { lookFor } from "../avatar";
import type { Player, Round } from "../types";
import { CringeFace, Crown, ScreamFace, ShockFace } from "./art";
import { Pill } from "./ui";

/** What each spot on the podium is called. Index 0 is the most accurate face. */
const AWARDS = [
  { title: "FACE OF THE ROUND", quip: "the camera fell in love" },
  { title: "BASICALLY A MIRROR", quip: "close enough to frame" },
  { title: "IT COUNTS", quip: "technically a face" },
];
const TILTS = ["-2deg", "2.5deg", "-3deg"];
const TAPE = ["var(--tint-pink)", "var(--tint-cyan)", "var(--tint-lime)"];
const STAMP = ["var(--yellow)", "var(--pink)", "var(--cyan)"];
/** Drawn instead of the photo when the frame has already been reaped or will not load. */
const STAND_INS: ComponentType<{ className?: string }>[] = [ScreamFace, ShockFace, CringeFace];

/** A cartoon price sticker. The number sits on top of it in HTML so it stays real text. */
function Starburst({ fill }: { fill: string }) {
  const points = Array.from({ length: 24 }, (_, i) => {
    const r = i % 2 ? 40 : 50;
    const a = (Math.PI * i) / 12;
    return `${(50 + r * Math.cos(a)).toFixed(1)},${(50 + r * Math.sin(a)).toFixed(1)}`;
  }).join(" ");
  return (
    <svg viewBox="-4 -4 108 108" className="facecard__burst" aria-hidden="true">
      <polygon points={points} fill={fill} stroke="#111" strokeWidth="5" strokeLinejoin="round" />
    </svg>
  );
}

function Photo({ submissionId, rank, name }: { submissionId: string; rank: number; name: string }) {
  const [broken, setBroken] = useState(false);
  const StandIn = STAND_INS[rank] ?? CringeFace;
  if (broken) {
    return (
      <div className="facecard__photo facecard__photo--standin" role="img" aria-label={`${name}'s face (photo expired)`}>
        <StandIn className="facecard__standin" />
      </div>
    );
  }
  return (
    <div className="facecard__photo">
      <img src={mediaUrl(submissionId)} alt={`${name}'s face`} onError={() => setBroken(true)} />
    </div>
  );
}

/**
 * The round's best faces, pinned up like polaroids. The server picks them when it ends
 * the round (`round.highlights`), so every player sees the same three.
 */
export function FaceHall({
  round,
  players,
  myId,
}: {
  round: Round | null;
  players: Record<string, Player>;
  myId: string | undefined;
}) {
  const highlights = round?.highlights ?? [];

  return (
    <section aria-labelledby="facehall" className="facehall">
      <div className="receipts__head">
        <h2 id="facehall">Hall of faces</h2>
        <Pill style={{ padding: "6px 12px" }}>the round's most accurate faces</Pill>
      </div>
      {highlights.length === 0 ? (
        <div className="facehall__empty tilt" style={{ "--tilt": "-1deg" } as CSSProperties}>
          <CringeFace className="facehall__empty-face" />
          <span>nobody made the face. the wall stays empty. the camera is filing a complaint.</span>
        </div>
      ) : (
        <ol className="facehall__grid">
          {highlights.map((h, i) => {
            const player = players[h.player_id];
            const name = player?.name ?? "someone who fled";
            const award = AWARDS[i] ?? AWARDS[AWARDS.length - 1];
            return (
              <li
                key={h.submission_id}
                className={`facecard facecard--${i + 1} tilt`}
                style={
                  {
                    "--tilt": TILTS[i % TILTS.length],
                    "--tape": TAPE[i % TAPE.length],
                    background: player ? lookFor(player).color : "var(--white)",
                  } as CSSProperties
                }
                aria-label={`#${i + 1} ${name}: ${h.accuracy_points}% ${h.label}`}
              >
                {i === 0 && <Crown className="facecard__crown" />}
                <span className="facecard__rank" aria-hidden="true">
                  #{i + 1}
                </span>
                <div className="facecard__frame">
                  <Photo submissionId={h.submission_id} rank={i} name={name} />
                  <span className="facecard__stamp" aria-hidden="true">
                    <Starburst fill={STAMP[i % STAMP.length]} />
                    <span className="facecard__pct">{h.accuracy_points}%</span>
                  </span>
                </div>
                <div className="facecard__caption">
                  <span className="facecard__award">{award.title}</span>
                  <span className="facecard__name">
                    {name}
                    {h.player_id === myId ? " (you)" : ""}
                  </span>
                  <span className="facecard__quip">
                    {h.label} · {award.quip}
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
