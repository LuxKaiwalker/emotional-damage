/** Inline SVGs lifted from the design artboards (plus extra mascot faces). All decorative. */

const BLOB = "M60 8c30 0 52 20 52 50s-18 54-52 54S8 90 8 58 30 8 60 8z";

export function Mascot({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <path d={BLOB} fill="#9BF04B" stroke="#111" strokeWidth="5" />
      <ellipse cx="42" cy="50" rx="11" ry="14" fill="#fff" stroke="#111" strokeWidth="4" />
      <ellipse cx="80" cy="50" rx="11" ry="14" fill="#fff" stroke="#111" strokeWidth="4" />
      <circle cx="45" cy="55" r="5" fill="#111" />
      <circle cx="77" cy="55" r="5" fill="#111" />
      <path d="M30 34l20 6M92 34l-20 6" stroke="#111" strokeWidth="5" strokeLinecap="round" />
      <path d="M42 92q18-16 36 0" fill="none" stroke="#111" strokeWidth="5" strokeLinecap="round" />
      <path d="M36 66q-5 14 0 26" fill="none" stroke="#3EC6FF" strokeWidth="7" strokeLinecap="round" />
      <path d="M86 66q5 14 0 26" fill="none" stroke="#3EC6FF" strokeWidth="7" strokeLinecap="round" />
    </svg>
  );
}

/** Shook: wide eyes, tiny pupils, brows up, little "o" mouth. */
export function ShockFace({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <path d={BLOB} fill="#FF4FA3" stroke="#111" strokeWidth="5" />
      <circle cx="42" cy="52" r="14" fill="#fff" stroke="#111" strokeWidth="4" />
      <circle cx="80" cy="52" r="14" fill="#fff" stroke="#111" strokeWidth="4" />
      <circle cx="42" cy="52" r="3.5" fill="#111" />
      <circle cx="80" cy="52" r="3.5" fill="#111" />
      <path d="M28 30q12-10 24-2M94 30q-12-10-24-2" fill="none" stroke="#111" strokeWidth="5" strokeLinecap="round" />
      <ellipse cx="61" cy="88" rx="10" ry="13" fill="#111" />
    </svg>
  );
}

/** Cringe: squeezed >< eyes, wobbly mouth, sweat drop. */
export function CringeFace({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <path d={BLOB} fill="#3EC6FF" stroke="#111" strokeWidth="5" />
      <path d="M32 42l16 10-16 10M90 42L74 52l16 10" fill="none" stroke="#111" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M36 86q6-8 12 0t12 0 12 0 12 0" fill="none" stroke="#111" strokeWidth="5" strokeLinecap="round" />
      <path d="M100 24q8 12 0 18q-8-6 0-18z" fill="#fff" stroke="#111" strokeWidth="3" strokeLinejoin="round" />
    </svg>
  );
}

/** Screaming: eyes clenched shut, mouth wide open with tongue. */
export function ScreamFace({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <path d={BLOB} fill="#fff" stroke="#111" strokeWidth="5" />
      <path d="M30 50q10-10 20 0M70 50q10-10 20 0" fill="none" stroke="#111" strokeWidth="5" strokeLinecap="round" />
      <path d="M28 34l18 6M92 34l-18 6" stroke="#111" strokeWidth="5" strokeLinecap="round" />
      <path d="M38 70q22-8 44 0q-2 30-22 30T38 70z" fill="#111" stroke="#111" strokeWidth="4" strokeLinejoin="round" />
      <path d="M48 92q12-10 24 0q-12 8-24 0z" fill="#FF4FA3" />
    </svg>
  );
}

export function UncleDamage({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <circle cx="60" cy="62" r="50" fill="#FF4FA3" stroke="#111" strokeWidth="5" />
      <path d="M22 40q38-40 76 0" fill="#111" />
      <circle cx="44" cy="62" r="8" fill="#fff" stroke="#111" strokeWidth="4" />
      <circle cx="78" cy="62" r="8" fill="#fff" stroke="#111" strokeWidth="4" />
      <circle cx="44" cy="62" r="3" fill="#111" />
      <circle cx="78" cy="62" r="3" fill="#111" />
      <ellipse cx="61" cy="90" rx="16" ry="10" fill="#111" />
      <path d="M30 50l22 4M92 50l-22 4" stroke="#111" strokeWidth="5" strokeLinecap="round" />
    </svg>
  );
}

export function Crown({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 140 80" className={className} aria-hidden="true">
      <path d="M10 70L18 16l30 28L70 6l22 38 30-28 8 54z" fill="#FFE135" stroke="#111" strokeWidth="6" strokeLinejoin="round" />
      <circle cx="70" cy="48" r="7" fill="#FF4FA3" stroke="#111" strokeWidth="3" />
    </svg>
  );
}

/** One scrap of confetti: its own viewBox, so nothing can stretch it out of shape. */
type Scrap = {
  /** Where on the screen, as a share of it, so the spread survives any viewport. */
  left: string;
  top: string;
  kind: "tag" | "dot" | "star";
  fill: string;
  /** Static lean, applied inside the SVG -- see the note on Confetti. */
  tilt?: number;
};

const SCRAPS: Scrap[] = [
  { left: "7%", top: "13%", kind: "tag", fill: "#FF4FA3", tilt: 25 },
  { left: "87%", top: "10%", kind: "tag", fill: "#FFE135", tilt: -30 },
  { left: "17%", top: "47%", kind: "dot", fill: "#9BF04B" },
  { left: "83%", top: "51%", kind: "dot", fill: "#FF4FA3" },
  { left: "12%", top: "80%", kind: "tag", fill: "#FFE135", tilt: -15 },
  { left: "90%", top: "78%", kind: "tag", fill: "#9BF04B", tilt: 40 },
  { left: "26%", top: "9%", kind: "star", fill: "#FFE135" },
  { left: "73%", top: "26%", kind: "star", fill: "#fff" },
];

const STAR = "M30 2l8 18 20 2-15 13 5 20-18-11-18 11 5-20-15-13 20-2z";

/* No width/height here on purpose: the wrapper is sized in CSS so the scraps can grow
   with the viewport the way the old stretched SVG did, without the distortion. */
function Scrap({ kind, fill, tilt = 0 }: Omit<Scrap, "left" | "top">) {
  const spin = tilt ? `rotate(${tilt} 17 16)` : undefined;
  if (kind === "tag") {
    // 34x32 for a 26x14 rect because it is rotated: at 40deg its bounding box is about
    // 32x30, and an SVG clips whatever leaves its viewBox. A snug 32x20 box sliced the
    // corners off every tilted tag -- which is only invisible until you look at one.
    return (
      <svg viewBox="0 0 34 32" aria-hidden="true">
        <rect x="4" y="9" width="26" height="14" rx="3" fill={fill} stroke="#111" strokeWidth="3" transform={spin} />
      </svg>
    );
  }
  if (kind === "dot") {
    return (
      <svg viewBox="0 0 26 26" aria-hidden="true">
        <circle cx="13" cy="13" r="10" fill={fill} stroke="#111" strokeWidth="3" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 60 57" aria-hidden="true">
      <path d={STAR} fill={fill} stroke="#111" strokeWidth="3" />
    </svg>
  );
}

/**
 * Winner-screen confetti.
 *
 * Each scrap is its own small SVG dropped at a percentage of the screen, rather than one
 * 1280x900 SVG stretched corner to corner. That stretch used `preserveAspectRatio="none"`,
 * which scales x and y independently: harmless on a desktop roughly as wide as the viewBox,
 * but on a phone it squeezed x to about a third while leaving y almost alone, so every
 * piece arrived as a sliver. Percentages keep the spread; per-piece viewBoxes keep the
 * shapes.
 *
 * The lean lives inside each SVG rather than on the wrapper because `drift` in motion.css
 * animates the wrapper's CSS `rotate`, and would otherwise overwrite it. The wrappers stay
 * direct children of `.confetti` so the existing `:nth-child` timing still applies.
 */
export function Confetti({ className }: { className?: string }) {
  return (
    <div className={className} aria-hidden="true">
      {SCRAPS.map((scrap, i) => (
        <span
          key={i}
          className={`confetti__bit confetti__bit--${scrap.kind}`}
          style={{ left: scrap.left, top: scrap.top }}
        >
          <Scrap kind={scrap.kind} fill={scrap.fill} tilt={scrap.tilt} />
        </span>
      ))}
    </div>
  );
}
