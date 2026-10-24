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

/** Iris sits at `gaze` (-1..1 per axis) inside the eye. */
export function Eye({ gaze, label }: { gaze: { x: number; y: number }; label: string }) {
  const cx = 60 + gaze.x * 30;
  const cy = 25 + gaze.y * 20;
  return (
    <svg viewBox="0 0 120 50" width="120" height="50" role="img" aria-label={label} style={{ flex: "0 0 auto" }}>
      <ellipse cx="60" cy="25" rx="54" ry="20" fill="#fff" stroke="#111" strokeWidth="4" />
      <circle cx={cx} cy={cy} r="13" fill="#3EC6FF" stroke="#111" strokeWidth="4" />
      <circle cx={cx + 2} cy={cy - 1} r="5" fill="#111" />
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

export function Confetti({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 1280 900" preserveAspectRatio="none" className={className} aria-hidden="true">
      <rect x="90" y="120" width="26" height="14" rx="3" fill="#FF4FA3" stroke="#111" strokeWidth="3" transform="rotate(25 103 127)" />
      <rect x="1120" y="90" width="26" height="14" rx="3" fill="#FFE135" stroke="#111" strokeWidth="3" transform="rotate(-30 1133 97)" />
      <circle cx="220" cy="420" r="10" fill="#9BF04B" stroke="#111" strokeWidth="3" />
      <circle cx="1060" cy="460" r="10" fill="#FF4FA3" stroke="#111" strokeWidth="3" />
      <rect x="160" y="720" width="26" height="14" rx="3" fill="#FFE135" stroke="#111" strokeWidth="3" transform="rotate(-15 173 727)" />
      <rect x="1150" y="700" width="26" height="14" rx="3" fill="#9BF04B" stroke="#111" strokeWidth="3" transform="rotate(40 1163 707)" />
      <path d="M330 80l8 18 20 2-15 13 5 20-18-11-18 11 5-20-15-13 20-2z" fill="#FFE135" stroke="#111" strokeWidth="3" />
      <path d="M940 230l8 18 20 2-15 13 5 20-18-11-18 11 5-20-15-13 20-2z" fill="#fff" stroke="#111" strokeWidth="3" />
    </svg>
  );
}
