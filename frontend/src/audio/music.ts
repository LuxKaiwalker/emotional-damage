/**
 * The music player: a lookahead step sequencer over the tracks in tracks.ts.
 *
 * A timer wakes every 25 ms and schedules every step due in the next 120 ms on the audio
 * clock, so timing stays sample-accurate even when the main thread is busy -- the
 * standard Web Audio pattern. Tempo and intensity are read at every step, which is what
 * makes the music react: a screen can push them every frame and the change lands on the
 * very next sixteenth note.
 */

import { freq, getBand, type Drum } from "./engine";
import { TRACKS, type Bar, type TrackName } from "./tracks";

const LOOKAHEAD_S = 0.12;
const TICK_MS = 25;

const DRUMS: Record<string, Drum> = {
  k: "kick",
  s: "snare",
  c: "clap",
  w: "woodblock",
  b: "cowbell",
  x: "crash",
};

export interface MusicParams {
  /** 0 to 1: how much of the band plays. */
  intensity: number;
  /** Multiplier on the track's own bpm. */
  tempo: number;
}

/** A parsed lead line: per step, a note to start (with its length in steps) or nothing. */
type LeadStep = { note: string; steps: number } | null;

function parseLead(line: string): LeadStep[] {
  const tokens = line.trim().split(/\s+/);
  if (tokens.length !== 16) throw new Error(`lead line needs 16 steps: ${line}`);
  return tokens.map((token, i) => {
    if (token === "-" || token === ".") return null;
    let steps = 1;
    while (tokens[i + steps] === "-") steps++;
    return { note: token, steps };
  });
}

const parsed = new Map<Bar, LeadStep[]>();
function leadOf(bar: Bar): LeadStep[] {
  let lead = parsed.get(bar);
  if (!lead) parsed.set(bar, (lead = parseLead(bar.lead)));
  return lead;
}

class MusicPlayer {
  private track: TrackName | null = null;
  private step = 0;
  private nextAt = 0;
  private timer: number | undefined;
  params: MusicParams = { intensity: 0.5, tempo: 1 };

  play(name: TrackName | null) {
    if (name === this.track) return;
    this.track = name;
    // Restart at the top of the new loop, on the next step of the old one: a switch
    // lands in time instead of colliding with whatever was mid-bar.
    this.step = 0;
    if (!name) {
      window.clearInterval(this.timer);
      this.timer = undefined;
      return;
    }
    this.timer ??= window.setInterval(() => this.schedule(), TICK_MS);
  }

  private schedule() {
    const band = getBand();
    if (!this.track || !band.running) {
      // Suspended until the first gesture; start cleanly once it is not.
      this.nextAt = 0;
      return;
    }
    if (this.nextAt < band.now) this.nextAt = band.now + 0.05;
    while (this.nextAt < band.now + LOOKAHEAD_S) {
      this.playStep(this.nextAt);
      this.nextAt += this.stepSeconds();
      this.step++;
    }
  }

  private stepSeconds(): number {
    const bpm = TRACKS[this.track!].bpm * this.params.tempo;
    return 60 / bpm / 4;
  }

  private playStep(stepAt: number) {
    const band = getBand();
    const track = TRACKS[this.track!];
    const barNo = Math.floor(this.step / 16);
    const bar = track.bars[barNo % track.bars.length];
    const s = this.step % 16;
    const stepS = this.stepSeconds();
    const { intensity } = this.params;
    // Swing: the off sixteenths land late, which is most of the bounce.
    const at = stepAt + (s % 2 === 1 ? track.swing * stepS : 0);

    // Drums from the pattern; hats and an occasional crash as the energy rises.
    const hit = DRUMS[bar.drums[s]];
    if (hit) band.drum(hit, at, hit === "crash" ? 1 : 0.9);
    if (intensity >= 0.85 || (intensity >= 0.5 && s % 2 === 0)) band.drum("hat", at, s % 4 === 2 ? 1 : 0.6);
    if (intensity >= 0.9 && s === 0 && barNo % 2 === 0) band.drum("crash", at, 0.7);

    // Oom: the tuba on the track's bass line.
    const bassNote = track.bassLine[s];
    if (bassNote !== ".") {
      const root = freq(bar.bass);
      const f = bassNote === "f" ? root * 1.5 : bassNote === "o" ? root * 2 : root;
      band.play("tuba", { freq: f, at, dur: stepS * 1.7, gain: 0.34 });
    }

    // Pah: short chords on beats 2 and 4, then on every off-beat when it gets busy.
    const pah = s === 4 || s === 12 || (intensity >= 0.75 && s % 4 === 2);
    if (intensity >= 0.3 && pah) {
      for (const tone of bar.chord) {
        band.play(track.stab, { freq: freq(tone), at, dur: stepS * 0.9, gain: 0.07 });
      }
    }

    // Counter-line: chord tones bouncing in eighths under the lead.
    if (intensity >= 0.55 && s % 2 === 0) {
      const tone = bar.chord[(s / 2) % bar.chord.length];
      band.play(track.counter, { freq: freq(tone) * 2, at, dur: stepS, gain: 0.05 });
    }

    // Lead, with a glockenspiel doubling on top when things get hype.
    const lead = leadOf(bar)[s];
    if (lead) {
      const f = freq(lead.note);
      const dur = stepS * lead.steps * 0.9;
      band.play(track.lead, { freq: f, at, dur, gain: 0.14 });
      if (intensity >= 0.8) band.play("glock", { freq: f * 2, at, dur, gain: 0.05 });
    }
  }
}

export const music = new MusicPlayer();
