/**
 * One-shot sound effects: cartoon party-game noises, timed from "now" on the sfx bus so
 * they sit on top of the music and are unaffected by narration ducking.
 */

import { freq, getBand, type Instrument } from "./engine";

/** Play `notes` on `instrument` back to back, `step` seconds apart. */
function run(instrument: Instrument, notes: string[], step: number, gain: number, hold = 1) {
  const band = getBand();
  const t = band.now;
  notes.forEach((n, i) =>
    band.play(instrument, { freq: freq(n), at: t + i * step, dur: hold * step, gain, bus: "sfx" }),
  );
}

export const sfx = {
  /** Any button: a dry woodblock tok. */
  click() {
    const band = getBand();
    band.drum("woodblock", band.now, 0.5, "sfx");
  },

  /** Someone walked into the lobby: boing! */
  join() {
    const band = getBand();
    const t = band.now;
    band.play("whistle", { freq: freq("C5"), slideTo: freq("C6"), at: t, dur: 0.18, gain: 0.22, bus: "sfx" });
    band.play("mallet", { freq: freq("G5"), at: t + 0.16, dur: 0.2, gain: 0.25, bus: "sfx" });
  },

  /** Someone left: the slide whistle going down. */
  leave() {
    const band = getBand();
    band.play("whistle", { freq: freq("C6"), slideTo: freq("G4"), at: band.now, dur: 0.35, gain: 0.2, bus: "sfx" });
  },

  /** A new round: brass hit, crash, and a whistle zipping up. */
  go() {
    const band = getBand();
    const t = band.now;
    band.drum("kick", t, 1.2, "sfx");
    band.drum("crash", t, 1, "sfx");
    for (const n of ["C4", "E4", "G4", "C5"]) {
      band.play("brass", { freq: freq(n), at: t, dur: 0.28, gain: 0.1, bus: "sfx" });
    }
    band.play("whistle", { freq: freq("G5"), slideTo: freq("G6"), at: t + 0.05, dur: 0.25, gain: 0.15, bus: "sfx" });
  },

  /** One of the last seconds of a round: tick-tock, up a step for the final three. */
  tick(secondsLeft: number) {
    const band = getBand();
    const t = band.now;
    band.drum(secondsLeft <= 3 ? "cowbell" : "woodblock", t, 1.4, "sfx");
    // Loud on purpose: it has to cut through the round music at its busiest.
    band.play("mallet", { freq: freq(secondsLeft <= 3 ? "A5" : "E5"), at: t, dur: 0.15, gain: 0.35, bus: "sfx" });
  },

  /** You pulled the face: a xylophone run up and a "ding!" */
  pass() {
    run("mallet", ["C5", "E5", "G5", "C6", "E6", "G6"], 0.045, 0.3);
    const band = getBand();
    band.play("glock", { freq: freq("C7"), at: band.now + 0.3, dur: 0.5, gain: 0.25, bus: "sfx" });
    band.drum("clap", band.now + 0.3, 1.2, "sfx");
  },

  /** Another player passed: a small boing, so it reads as news rather than reward. */
  otherPassed() {
    const band = getBand();
    band.play("whistle", { freq: freq("E5"), slideTo: freq("A5"), at: band.now, dur: 0.12, gain: 0.14, bus: "sfx" });
  },

  /** The round is over: a deflating honk. */
  timeUp() {
    const band = getBand();
    const t = band.now;
    for (const n of ["C4", "Eb4", "G4"]) {
      band.play("brass", { freq: freq(n), slideTo: freq(n) * 0.75, at: t, dur: 0.6, gain: 0.11, bus: "sfx" });
    }
    band.drum("crash", t, 0.6, "sfx");
  },

  /** A row on the scoreboard. Pitch climbs with `i` so a list of them reads as a count. */
  score(i: number) {
    const scale = ["C5", "D5", "E5", "G5", "A5", "C6", "D6", "E6"];
    run("mallet", [scale[Math.min(i, scale.length - 1)]], 0.2, 0.3);
  },

  /** The winner reveal: ta-da! */
  fanfare() {
    const band = getBand();
    const t = band.now;
    const hits: [number, string[]][] = [
      [0, ["G3", "C4", "E4"]],
      [0.14, ["G3", "C4", "E4"]],
      [0.28, ["C4", "E4", "G4", "C5"]],
    ];
    for (const [dt, chord] of hits) {
      for (const n of chord) {
        band.play("brass", { freq: freq(n), at: t + dt, dur: dt === 0.28 ? 0.8 : 0.1, gain: 0.1, bus: "sfx" });
      }
    }
    band.drum("crash", t + 0.28, 1.2, "sfx");
    band.play("glock", { freq: freq("C7"), at: t + 0.28, dur: 0.8, gain: 0.2, bus: "sfx" });
  },

  /** Something went wrong: a tuba bwomp. */
  error() {
    const band = getBand();
    band.play("tuba", { freq: freq("Eb2"), slideTo: freq("C2"), at: band.now, dur: 0.35, gain: 0.3, bus: "sfx" });
  },
};
