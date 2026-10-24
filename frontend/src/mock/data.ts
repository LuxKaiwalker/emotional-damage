/**
 * Everything the screens render. Copied from the design artboards. Shapes are meant to stay
 * stable so the backend (see ../types.ts, ../hooks) can replace these without touching components.
 */

export type Player = {
  id: string;
  name: string;
  initial: string;
  color: string;
  status?: string;
  tag?: "HOST" | "READY" | "NOT READY";
};

const you: Player = { id: "you", name: "you", initial: "Y", color: "var(--yellow)" };
const sam: Player = { id: "sam", name: "sigma_sam", initial: "S", color: "var(--cyan)" };
const rizz: Player = { id: "rizz", name: "rizzlord", initial: "R", color: "var(--lime)" };
const bigback: Player = { id: "bigback", name: "bigbackdev", initial: "B", color: "var(--pink)" };
const goblin: Player = { id: "goblin", name: "goblinmode", initial: "G", color: "var(--white)" };

export const allPlayers = [you, sam, rizz, bigback, goblin];

export const lobby = {
  code: "BRUH",
  maxPlayers: 5,
  rounds: 5,
  countdown: 3,
  vibe: "Unhinged",
  isHost: true,
  players: [
    { ...you, name: "you (host)", status: "cam on · vibes questionable", tag: "HOST" },
    { ...sam, status: "cam on · already sweating", tag: "READY" },
    { ...rizz, status: "cam loading… lighting is a crime", tag: "NOT READY" },
  ] as Player[],
};

export const roundState = {
  round: 2,
  totalRounds: 5,
  prompt: "Make the face of someone who just stepped on a LEGO… barefoot… at 3am.",
  promptShort: "stepped on a LEGO",
  live: { pulse: 112, breathing: 24, blinks: 7, talking: true, damageMatch: 87, aura: 420 },
};

export type ResultRow = {
  rank: number;
  player: Player;
  tag: string;
  delta: string;
  total: string;
};

export const results = {
  roast: 'Uncle Damage says: "rizzlord, that was not pain. that was mild inconvenience. −aura."',
  rows: [
    { rank: 1, player: sam, tag: "ATE. NO CRUMBS.", delta: "+640", total: "1,180" },
    { rank: 2, player: you, tag: "genuinely in pain", delta: "+420", total: "960" },
    { rank: 3, player: bigback, tag: "mid but trying", delta: "+300", total: "710" },
    { rank: 4, player: goblin, tag: "blinked too much", delta: "+150", total: "520" },
    { rank: 5, player: rizz, tag: "NPC behaviour", delta: "−50", total: "230" },
  ] as ResultRow[],
  receipts: [
    { label: "Biggest pulse spike", who: "sigma_sam", value: "+38 bpm", sub: "92 → 130 in 1.1s", bg: "var(--pink)", tilt: "-1deg" },
    { label: "Lowest HRV (most stressed)", who: "you", value: "29 ms", sub: "nervous system said no", bg: "var(--white)", tilt: "0.5deg" },
    { label: "Most panic breathing", who: "bigbackdev", value: "31 /min", sub: "all chest, zero belly", bg: "var(--cyan)", tilt: "-0.5deg" },
    { label: "Calmest (sus)", who: "rizzlord", value: "64 bpm", sub: "is he even alive", bg: "var(--grey)", tilt: "1deg" },
    { label: "Eye contact crimes", who: "goblinmode", value: "5 look-aways", sub: "+ 14 blinks", bg: "var(--yellow)", tilt: "-1deg" },
  ],
};

export const winner = {
  player: sam,
  totalRounds: 5,
  totalAura: "3,420",
  peakPulse: 131,
  bestRound: "LEGO",
  others: [
    { rank: 2, name: "you", total: "2,980", bg: "var(--yellow)" },
    { rank: 3, name: "bigbackdev", total: "2,410", bg: "var(--white)" },
    { rank: 4, name: "goblinmode", total: "1,760", bg: "var(--white)" },
    { rank: 5, name: "rizzlord", total: "640", bg: "var(--grey)" },
  ],
};
