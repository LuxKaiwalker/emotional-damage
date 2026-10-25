import { useState, type CSSProperties, type ComponentType } from "react";

import { mediaUrl } from "../api/client";
import { lookFor } from "../avatar";
import type { Highlight, Player, Round } from "../types";
import { CringeFace, Crown, ScreamFace, ShockFace } from "./art";
import { Pill } from "./ui";

/** The words on the wall, for one round's faces or the whole game's. */
const COPY = {
  round: {
    heading: "Hall of faces",
    pill: "the round's most accurate faces",
    empty: "nobody made the face. the wall stays empty. the camera is filing a complaint.",
    unit: "round",
    // What each spot on the podium is called. Index 0 is the most accurate face.
    awards: [
      { title: "FACE OF THE ROUND", quip: "the camera fell in love" },
      { title: "BASICALLY A MIRROR", quip: "close enough to frame" },
      { title: "IT COUNTS", quip: "technically a face" },
    ],
  },
  game: {
    heading: "Hall of fame",
    pill: "the most accurate faces of the whole game",
    empty: "not one face landed all game. the wall of fame is a wall.",
    unit: "round",
    awards: [
      { title: "FACE OF THE GAME", quip: "frame it. sell it." },
      { title: "MUSEUM QUALITY", quip: "the camera kept a copy" },
      { title: "STILL ICONIC", quip: "bronze, but make it face" },
    ],
  },
  // Same wall, different clock: a blitz has faces where a classic game has rounds, so
  // it needs its own noun or every caption would read "round 14" of a game with none.
  blitz: {
    heading: "Hall of fame",
    pill: "the most accurate faces of the whole blitz",
    empty: "not one face landed in the whole blitz. the wall of fame is a wall.",
    unit: "face",
    awards: [
      { title: "FACE OF THE BLITZ", quip: "frame it. sell it." },
      { title: "MUSEUM QUALITY", quip: "the camera kept a copy" },
      { title: "STILL ICONIC", quip: "bronze, but make it face" },
    ],
  },
};
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

/** A highlight, and which round -- or, in a blitz, which face -- it was pulled in. */
type Entry = Highlight & { round: number };

/**
 * The best faces across `rounds`, most accurate first. Each round's `highlights` is
 * already its top three (picked by the server when it ended the round), so the game's
 * top three are always among them. Ties go to the earlier round, then the earlier pass:
 * the same order the server uses within a round.
 */
function bestFaces(rounds: Round[], count = 3): Entry[] {
  return rounds
    .flatMap((r) => (r.highlights ?? []).map((h) => ({ ...h, round: r.number })))
    .sort((a, b) => b.accuracy_points - a.accuracy_points || a.round - b.round || a.place - b.place)
    .slice(0, count);
}

/**
 * The best faces, pinned up like polaroids: one round's on the results screen, the whole
 * game's on the winner screen. Every player sees the same ones.
 */
export function FaceHall({
  scope,
  rounds = [],
  highlights: ranked,
  players,
  myId,
}: {
  scope: keyof typeof COPY;
  /** Classic: the rounds to mine. Each one's `highlights` is already its own top three. */
  rounds?: Round[];
  /**
   * Blitz: the server's ranking, used as-is. A blitz has no rounds to flatten, and its
   * highlights are picked across whole runs rather than per round, so the work is done
   * before it gets here.
   */
  highlights?: Highlight[];
  players: Record<string, Player>;
  myId: string | undefined;
}) {
  const copy = COPY[scope];
  const highlights: Entry[] =
    ranked?.map((h) => ({ ...h, round: h.face_no ?? 0 })) ?? bestFaces(rounds);
  const headingId = `facehall-${scope}`;

  return (
    <section aria-labelledby={headingId} className="facehall">
      <div className="receipts__head">
        <h2 id={headingId}>{copy.heading}</h2>
        <Pill style={{ padding: "6px 12px" }}>{copy.pill}</Pill>
      </div>
      {highlights.length === 0 ? (
        <div className="facehall__empty tilt" style={{ "--tilt": "-1deg" } as CSSProperties}>
          <CringeFace className="facehall__empty-face" />
          <span>{copy.empty}</span>
        </div>
      ) : (
        <ol className="facehall__grid">
          {highlights.map((h, i) => {
            const player = players[h.player_id];
            const name = player?.name ?? "someone who fled";
            const award = copy.awards[i] ?? copy.awards[copy.awards.length - 1];
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
                aria-label={`#${i + 1} ${name}: ${h.accuracy_points}% ${h.label}, ${copy.unit} ${h.round}`}
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
                    {scope === "round"
                      ? `${h.label} · ${award.quip}`
                      : `${h.label} · ${copy.unit} ${h.round}`}
                  </span>
                  {scope !== "round" && <span className="facecard__quip">{award.quip}</span>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
