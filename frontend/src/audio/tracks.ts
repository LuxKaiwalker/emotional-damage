/**
 * The soundtrack, as data: bouncy, goofy, party-game.
 *
 * Each track is a loop of bars. A bar is one chord -- bass, stabs and the mallet
 * counter-line are derived from it -- plus a 16-step lead line and a 16-step drum line.
 * Steps are sixteenth notes.
 *
 * Lead lines: one token per step. A note name starts a note, "-" holds the previous one,
 * "." is silence. Drum lines: one character per step:
 *   k kick   s snare   c clap   w woodblock   b cowbell   x crash   . nothing
 * Bass lines (per track): r root, f fifth, o octave, . nothing -- the oom of oom-pah.
 */

import type { Instrument } from "./engine";

export interface Bar {
  /** Bass root, low. */
  bass: string;
  /** Chord tones, low to high, around middle C: stabs and the counter-line use them. */
  chord: string[];
  lead: string;
  drums: string;
}

export interface Track {
  bpm: number;
  /** 0 straight, ~0.3 heavy shuffle: how late the off-sixteenths land. */
  swing: number;
  lead: Instrument;
  /** The "pah": short chords on the off-beats. */
  stab: Instrument;
  /** Bouncing chord tones under the lead. */
  counter: Instrument;
  bassLine: string;
  bars: Bar[];
}

export type TrackName =
  | "menu"
  | "lobby"
  | "round"
  | "roundPassed"
  | "results"
  | "victory"
  | "gameover";

const OOMPAH = "r...f...r...f...";

export const TRACKS: Record<TrackName, Track> = {
  // Home and join: the show is about to start.
  menu: {
    bpm: 142,
    swing: 0.12,
    lead: "mallet",
    stab: "pluck",
    counter: "glock",
    bassLine: OOMPAH,
    bars: [
      { bass: "F2", chord: ["F4", "A4", "C5"], drums: "k...s.w.k.k.s...", lead: "C5 . F5 . A5 . F5 . C5 . . . A4 . C5 ." },
      { bass: "Bb1", chord: ["F4", "Bb4", "D5"], drums: "k...s.w.k.k.s...", lead: "D5 . F5 . Bb5 . F5 . D5 . . . Bb4 . D5 ." },
      { bass: "C2", chord: ["E4", "G4", "Bb4"], drums: "k...s.w.k.k.s...", lead: "E5 . G5 . Bb5 - A5 . G5 . E5 . C5 . . ." },
      { bass: "F2", chord: ["F4", "A4", "C5"], drums: "k...s.w.k.k.s.c.", lead: "F5 . . . E5 . F5 . A5 - - - . . . ." },
      { bass: "F2", chord: ["F4", "A4", "C5"], drums: "k...s.w.k.k.s...", lead: "A5 . G5 . F5 . E5 . F5 . . . C5 . . ." },
      { bass: "Bb1", chord: ["F4", "Bb4", "D5"], drums: "k...s.w.k.k.s...", lead: "D5 . E5 . F5 . G5 . A5 . Bb5 . A5 . G5 ." },
      { bass: "G2", chord: ["G4", "B4", "D5"], drums: "k...s.w.k.k.s...", lead: "B5 . A5 . G5 . F5 . E5 . D5 . C5 . . ." },
      { bass: "C2", chord: ["E4", "G4", "Bb4"], drums: "k...s.s.k.k.cccc", lead: "C5 . C#5 . D5 . D#5 . E5 . G5 . C6 . . ." },
    ],
  },

  // Waiting for everyone: sneaky tiptoe pizzicato, so it can loop for minutes.
  lobby: {
    bpm: 116,
    swing: 0.22,
    lead: "pluck",
    stab: "mallet",
    counter: "mallet",
    bassLine: "r..f..o.r..f.o..",
    bars: [
      { bass: "Bb1", chord: ["F4", "Bb4", "D5"], drums: "k..w..s.k.w...s.", lead: "Bb4 . . D5 . . F5 . . . D5 . Bb4 . . ." },
      { bass: "G2", chord: ["G4", "Bb4", "D5"], drums: "k..w..s.k.w...s.", lead: "G4 . . Bb4 . . D5 . . . Bb4 . G4 . . ." },
      { bass: "Eb2", chord: ["G4", "Bb4", "Eb5"], drums: "k..w..s.k.w...s.", lead: "Eb5 . . G5 . . Bb5 . . . G5 . Eb5 . . ." },
      { bass: "F2", chord: ["F4", "A4", "Eb5"], drums: "k..w..s.k.w.b.s.", lead: "F5 . E5 . Eb5 . D5 . C5 . . . F4 . . ." },
      { bass: "Bb1", chord: ["F4", "Bb4", "D5"], drums: "k..w..s.k.w...s.", lead: "D5 . . F5 . . Bb5 . . . A5 . Bb5 . . ." },
      { bass: "G2", chord: ["G4", "Bb4", "D5"], drums: "k..w..s.k.w...s.", lead: "G5 . . F5 . . D5 . . . Bb4 . D5 . . ." },
      { bass: "C2", chord: ["G4", "C5", "Eb5"], drums: "k..w..s.k.w...s.", lead: "C5 . Eb5 . G5 . C6 . Bb5 . G5 . Eb5 . . ." },
      { bass: "F2", chord: ["F4", "A4", "Eb5"], drums: "k..w..s.k.w.b.s.", lead: "F5 . . . A4 . . . C5 . Eb5 . F5 - - ." },
    ],
  },

  // Pull the face! Hyped and bouncing; speeds up as the clock runs down.
  round: {
    bpm: 158,
    swing: 0,
    lead: "kazoo",
    stab: "brass",
    counter: "mallet",
    bassLine: "r.r.f...r.r.f.o.",
    bars: [
      { bass: "G2", chord: ["G4", "B4", "D5"], drums: "k.w.s..wk.k.s.w.", lead: "G4 . B4 . D5 . G5 . . . F#5 . G5 . . ." },
      { bass: "C2", chord: ["G4", "C5", "E5"], drums: "k.w.s..wk.k.s.w.", lead: "E5 . . . G5 . . . C6 . B5 . A5 . G5 ." },
      { bass: "D2", chord: ["F#4", "A4", "D5"], drums: "k.w.s..wk.k.s.w.", lead: "F#5 . . . A5 . . . D6 . C6 . B5 . A5 ." },
      { bass: "G2", chord: ["G4", "B4", "D5"], drums: "k.w.s..wk.k.c.cc", lead: "G5 . D5 . B4 . G4 . A4 . B4 . C5 . C#5 ." },
    ],
  },

  // You got it: same tempo, but the band celebrates while the others sweat.
  roundPassed: {
    bpm: 158,
    swing: 0,
    lead: "brass",
    stab: "pluck",
    counter: "glock",
    bassLine: OOMPAH,
    bars: [
      { bass: "C2", chord: ["E4", "G4", "C5"], drums: "k...c...k...c...", lead: "C5 . E5 . G5 - - . E5 . G5 . C6 - - ." },
      { bass: "F2", chord: ["F4", "A4", "C5"], drums: "k...c...k...c...", lead: "A5 - - . G5 . F5 . A5 - - . C6 - - ." },
      { bass: "G2", chord: ["G4", "B4", "D5"], drums: "k...c...k...c...", lead: "B5 - - . A5 . G5 . D6 - - . B5 - - ." },
      { bass: "C2", chord: ["E4", "G4", "C5"], drums: "k...c...k.k.c.cc", lead: "C6 . G5 . E5 . G5 . C6 - - - . . . ." },
    ],
  },

  // Between rounds: show-tune scoreboard bounce.
  results: {
    bpm: 128,
    swing: 0.18,
    lead: "mallet",
    stab: "brass",
    counter: "pluck",
    bassLine: OOMPAH,
    bars: [
      { bass: "D2", chord: ["F#4", "A4", "D5"], drums: "k..wc.w.k.w.c...", lead: "F#5 . A5 . . F#5 . D5 . . E5 . F#5 . . ." },
      { bass: "B1", chord: ["F#4", "B4", "D5"], drums: "k..wc.w.k.w.c...", lead: "D5 . F#5 . . D5 . B4 . . C#5 . D5 . . ." },
      { bass: "G2", chord: ["G4", "B4", "D5"], drums: "k..wc.w.k.w.c...", lead: "B4 . D5 . G5 . . . F#5 . E5 . D5 . . ." },
      { bass: "A1", chord: ["G4", "A4", "C#5"], drums: "k..wc.w.k.w.cccc", lead: "C#5 . E5 . A5 . G5 . F#5 . E5 . C#5 . A4 ." },
    ],
  },

  // You won: the big brass finish.
  victory: {
    bpm: 136,
    swing: 0,
    lead: "brass",
    stab: "brass",
    counter: "glock",
    bassLine: "r...f...r.r.f...",
    bars: [
      { bass: "C2", chord: ["E4", "G4", "C5"], drums: "x...s...k...s...", lead: "G4 . C5 . E5 . G5 - - - E5 . G5 - - -" },
      { bass: "F2", chord: ["F4", "A4", "C5"], drums: "k...s...k...s...", lead: "A5 - - - G5 . F5 . A5 - - - C6 - - -" },
      { bass: "G2", chord: ["F4", "G4", "B4"], drums: "k...s...k...s...", lead: "B5 - - - A5 . G5 . F5 . E5 . D5 - - -" },
      { bass: "C2", chord: ["E4", "G4", "C5"], drums: "k...s...k.k.s.ss", lead: "C6 - - - G5 . C6 . E6 - - - - - . ." },
    ],
  },

  // Somebody else won: the sad-trombone wah-wah, played for laughs.
  gameover: {
    bpm: 96,
    swing: 0.2,
    lead: "kazoo",
    stab: "pluck",
    counter: "mallet",
    bassLine: "r.......f.......",
    bars: [
      { bass: "C2", chord: ["G4", "C5", "Eb5"], drums: "k.......s.......", lead: "G4 - - - F#4 - - - F4 - - - E4 - - -" },
      { bass: "F2", chord: ["F4", "Ab4", "C5"], drums: "k.......s.......", lead: "Ab4 - - . G4 - - . F4 - - . Eb4 - - ." },
      { bass: "G2", chord: ["F4", "G4", "B4"], drums: "k.......s...w.w.", lead: "D4 - - . F4 - - . Ab4 - - . G4 - - ." },
      { bass: "C2", chord: ["G4", "C5", "Eb5"], drums: "k.......s.......", lead: "C4 - - - - - - - . . . . G3 - . ." },
    ],
  },
};
