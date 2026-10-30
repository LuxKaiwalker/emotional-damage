/**
 * The game's band.
 *
 * A party-game soundtrack -- oom-pah tuba, marimba, pizzicato, brass stabs, a kazoo, claps
 * and woodblocks -- synthesised live with Web Audio. No audio files to license, host or
 * wait for, and every part can react to the game.
 *
 * One engine for the whole app, created on first use and never torn down: music keeps
 * playing straight through route changes, so a screen switch is a handover, not a
 * restart. Browsers refuse to start audio before a user gesture, so the context is
 * created suspended and resumed by the first click or key press anywhere on the page.
 */

const STORAGE_KEY = "ed.audio";

export type Instrument =
  /** Marimba: warm wooden mallet, fast decay. */
  | "mallet"
  /** Glockenspiel: bright metal bell, for sparkle on top. */
  | "glock"
  /** Pizzicato strings. */
  | "pluck"
  /** Bouncy tuba, with a little upward scoop into each note. */
  | "tuba"
  /** Brass section stab: three detuned saws with a swelling filter. */
  | "brass"
  /** Kazoo: nasal, wobbly, the goofy lead. */
  | "kazoo"
  /** Slide whistle: a pure tone, made to glide with `slideTo`. */
  | "whistle";

export type Drum = "kick" | "snare" | "clap" | "hat" | "woodblock" | "cowbell" | "crash";

export interface NoteOpts {
  freq: number;
  /** Start time on the audio clock (seconds). */
  at: number;
  /** Seconds the note holds before release. */
  dur: number;
  gain?: number;
  /** Pitch at the end of the note, for slides. */
  slideTo?: number;
  bus?: "music" | "sfx";
}

interface Settings {
  muted: boolean;
  music: number;
  sfx: number;
}

function loadSettings(): Settings {
  const fallback = { muted: false, music: 0.6, sfx: 0.75 };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

class Band {
  readonly ctx: AudioContext | null;
  private master!: GainNode;
  private musicBus!: GainNode;
  private sfxBus!: GainNode;
  private duckGain!: GainNode;
  private reverbSend!: GainNode;
  private noise!: AudioBuffer;
  private settings = loadSettings();
  private listeners = new Set<() => void>();

  constructor() {
    const Ctx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    this.ctx = Ctx ? new Ctx() : null;
    if (!this.ctx) return;
    const ctx = this.ctx;

    // A small room around everything makes synth instruments sound like a band playing
    // together; the compressor glues them and keeps the drums from spiking.
    const glue = ctx.createDynamicsCompressor();
    glue.threshold.value = -16;
    glue.ratio.value = 3;
    glue.attack.value = 0.005;

    this.master = ctx.createGain();
    this.musicBus = ctx.createGain();
    this.sfxBus = ctx.createGain();
    this.duckGain = ctx.createGain();
    this.reverbSend = ctx.createGain();
    this.reverbSend.gain.value = 0.22;

    const reverb = ctx.createConvolver();
    reverb.buffer = roomImpulse(ctx, 1.3);

    this.musicBus.connect(this.duckGain).connect(this.master);
    this.sfxBus.connect(this.master);
    this.master.connect(glue).connect(ctx.destination);
    this.master.connect(this.reverbSend).connect(reverb).connect(glue);
    this.applySettings();

    this.noise = noiseBuffer(ctx);

    // Resume on the first gesture. Kept registered: some browsers suspend the context
    // again when the tab is backgrounded.
    const unlock = () => {
      if (ctx.state !== "running") void ctx.resume();
    };
    for (const event of ["pointerdown", "keydown", "touchstart"]) {
      window.addEventListener(event, unlock, { capture: true, passive: true });
    }
  }

  get now(): number {
    return this.ctx?.currentTime ?? 0;
  }

  get running(): boolean {
    return this.ctx?.state === "running";
  }

  get muted(): boolean {
    return this.settings.muted;
  }

  setMuted(muted: boolean) {
    this.settings.muted = muted;
    this.persist();
  }

  /** Lower the music while Uncle Damage is talking; sound effects stay put. */
  duck(on: boolean) {
    if (!this.ctx) return;
    this.duckGain.gain.setTargetAtTime(on ? 0.3 : 1, this.ctx.currentTime, 0.15);
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  play(instrument: Instrument, o: NoteOpts) {
    const ctx = this.ctx;
    if (!ctx || !this.running) return;
    const out = o.bus === "sfx" ? this.sfxBus : this.musicBus;
    const g = o.gain ?? 0.2;
    const { at, dur, freq } = o;

    switch (instrument) {
      case "mallet": {
        // Fundamental plus the bar's bright overtone, which dies away first.
        this.partial(freq, at, 0.5, g, "sine", out);
        this.partial(freq * 4, at, 0.08, g * 0.25, "sine", out);
        break;
      }
      case "glock": {
        this.partial(freq, at, 1.1, g, "sine", out);
        this.partial(freq * 2.76, at, 0.5, g * 0.35, "sine", out);
        this.partial(freq * 5.4, at, 0.2, g * 0.15, "sine", out);
        break;
      }
      case "pluck": {
        const osc = this.osc("sawtooth", freq, at, at + 0.4);
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass";
        lp.frequency.setValueAtTime(Math.min(6000, freq * 8), at);
        lp.frequency.exponentialRampToValueAtTime(Math.max(200, freq * 1.5), at + 0.15);
        const env = this.decay(at, 0.28, g);
        osc.connect(lp).connect(env).connect(out);
        break;
      }
      case "tuba": {
        const osc = this.osc("sawtooth", freq * 0.94, at, at + dur + 0.1);
        osc.frequency.exponentialRampToValueAtTime(freq, at + 0.05);
        if (o.slideTo) osc.frequency.exponentialRampToValueAtTime(o.slideTo, at + dur);
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass";
        lp.frequency.value = 520;
        lp.Q.value = 3;
        osc.connect(lp).connect(this.hold(at, dur, g, 0.015, 0.06)).connect(out);
        break;
      }
      case "brass": {
        const lp = ctx.createBiquadFilter();
        lp.type = "lowpass";
        lp.Q.value = 1.5;
        lp.frequency.setValueAtTime(500, at);
        lp.frequency.linearRampToValueAtTime(Math.min(5000, freq * 6), at + 0.06);
        lp.frequency.exponentialRampToValueAtTime(Math.min(2400, freq * 3), at + 0.25);
        const env = this.hold(at, dur, g, 0.03, 0.08);
        lp.connect(env).connect(out);
        for (const cents of [-7, 0, 7]) {
          const osc = this.osc("sawtooth", freq, at, at + dur + 0.12);
          osc.detune.value = cents;
          if (o.slideTo) osc.frequency.exponentialRampToValueAtTime(o.slideTo, at + dur);
          osc.connect(lp);
        }
        break;
      }
      case "kazoo": {
        const osc = this.osc("sawtooth", freq * 0.97, at, at + dur + 0.1);
        osc.frequency.exponentialRampToValueAtTime(freq, at + 0.04);
        if (o.slideTo) osc.frequency.exponentialRampToValueAtTime(o.slideTo, at + dur);
        this.wobble(osc, freq, at, dur, 0.25, 5.5);
        // Two vocal-ish formants: the buzz through a paper membrane.
        const f1 = ctx.createBiquadFilter();
        f1.type = "bandpass";
        f1.frequency.value = 900;
        f1.Q.value = 2.5;
        const f2 = ctx.createBiquadFilter();
        f2.type = "peaking";
        f2.frequency.value = 2400;
        f2.gain.value = 9;
        osc.connect(f1).connect(f2).connect(this.hold(at, dur, g * 1.6, 0.02, 0.05)).connect(out);
        break;
      }
      case "whistle": {
        const osc = this.osc("sine", freq, at, at + dur + 0.1);
        if (o.slideTo) osc.frequency.exponentialRampToValueAtTime(o.slideTo, at + dur);
        this.wobble(osc, freq, at, dur, 0.3, 7);
        osc.connect(this.hold(at, dur, g, 0.02, 0.06)).connect(out);
        break;
      }
    }
  }

  drum(kind: Drum, at: number, gain = 1, bus: "music" | "sfx" = "music") {
    const ctx = this.ctx;
    if (!ctx || !this.running) return;
    const out = bus === "sfx" ? this.sfxBus : this.musicBus;

    switch (kind) {
      case "kick": {
        const osc = this.osc("sine", 130, at, at + 0.35);
        osc.frequency.exponentialRampToValueAtTime(45, at + 0.12);
        osc.connect(this.decay(at, 0.3, 0.75 * gain)).connect(out);
        break;
      }
      case "snare": {
        this.noiseHit(at, 0.16, 0.32 * gain, "bandpass", 1900, 0.7, out);
        this.partial(190, at, 0.07, 0.18 * gain, "triangle", out);
        break;
      }
      case "clap": {
        // Several hands, a few milliseconds apart.
        for (const [dt, level] of [[0, 0.7], [0.011, 0.6], [0.022, 1]] as const) {
          this.noiseHit(at + dt, dt < 0.02 ? 0.02 : 0.14, 0.3 * level * gain, "bandpass", 1300, 1.2, out);
        }
        break;
      }
      case "hat":
        this.noiseHit(at, 0.04, 0.09 * gain, "highpass", 8000, 0.7, out);
        break;
      case "woodblock":
        this.partial(1050, at, 0.07, 0.3 * gain, "sine", out);
        this.partial(1700, at, 0.03, 0.08 * gain, "triangle", out);
        break;
      case "cowbell": {
        const bp = ctx.createBiquadFilter();
        bp.type = "bandpass";
        bp.frequency.value = 900;
        bp.Q.value = 2;
        const env = this.decay(at, 0.25, 0.22 * gain);
        bp.connect(env).connect(out);
        for (const f of [540, 800]) this.osc("square", f, at, at + 0.3).connect(bp);
        break;
      }
      case "crash":
        this.noiseHit(at, 1.2, 0.16 * gain, "highpass", 4500, 0.5, out);
        break;
    }
  }

  // --- building blocks ----------------------------------------------------

  private osc(type: OscillatorType, freq: number, start: number, stop: number): OscillatorNode {
    const osc = this.ctx!.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, start);
    osc.start(start);
    osc.stop(stop);
    return osc;
  }

  /** A single decaying sine/triangle partial. */
  private partial(freq: number, at: number, len: number, gain: number, type: OscillatorType, out: AudioNode) {
    this.osc(type, freq, at, at + len + 0.05).connect(this.decay(at, len, gain)).connect(out);
  }

  /** Percussive envelope: instant attack, exponential fall over `len`. */
  private decay(at: number, len: number, gain: number): GainNode {
    const env = this.ctx!.createGain();
    env.gain.setValueAtTime(0, at);
    env.gain.linearRampToValueAtTime(gain, at + 0.003);
    env.gain.exponentialRampToValueAtTime(0.0008, at + len);
    return env;
  }

  /** Sustained envelope: rise over `attack`, hold for `dur`, fall over `release`. */
  private hold(at: number, dur: number, gain: number, attack: number, release: number): GainNode {
    const env = this.ctx!.createGain();
    env.gain.setValueAtTime(0, at);
    env.gain.linearRampToValueAtTime(gain, at + attack);
    env.gain.setValueAtTime(gain, at + Math.max(attack, dur - release));
    env.gain.linearRampToValueAtTime(0, at + dur + release);
    return env;
  }

  /** Vibrato that eases in, so short notes stay clean and long ones get goofy. */
  private wobble(osc: OscillatorNode, freq: number, at: number, dur: number, semitones: number, rate: number) {
    const ctx = this.ctx!;
    const lfo = this.osc("sine", rate, at, at + dur + 0.1);
    const depth = ctx.createGain();
    depth.gain.setValueAtTime(0, at);
    depth.gain.linearRampToValueAtTime(freq * (2 ** (semitones / 12) - 1), at + Math.min(0.25, dur));
    lfo.connect(depth).connect(osc.frequency);
  }

  private noiseHit(
    at: number,
    len: number,
    gain: number,
    type: BiquadFilterType,
    freq: number,
    q: number,
    out: AudioNode,
  ) {
    const ctx = this.ctx!;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = freq;
    filter.Q.value = q;
    src.connect(filter).connect(this.decay(at, len, gain)).connect(out);
    // Random offset so consecutive hits do not sound like the same sample.
    src.start(at, Math.random() * 0.5);
    src.stop(at + len + 0.02);
  }

  private applySettings() {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    this.master.gain.setTargetAtTime(this.settings.muted ? 0 : 1, t, 0.03);
    this.musicBus.gain.setTargetAtTime(this.settings.music, t, 0.03);
    this.sfxBus.gain.setTargetAtTime(this.settings.sfx, t, 0.03);
  }

  private persist() {
    this.applySettings();
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.settings));
    } catch {
      /* private mode: the setting just does not stick */
    }
    this.listeners.forEach((fn) => fn());
  }
}

function noiseBuffer(ctx: AudioContext): AudioBuffer {
  const buf = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  return buf;
}

/** A small, bright room: exponentially decaying stereo noise. */
function roomImpulse(ctx: AudioContext, seconds: number): AudioBuffer {
  const len = Math.floor(ctx.sampleRate * seconds);
  const buf = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const data = buf.getChannelData(ch);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len) ** 3;
  }
  return buf;
}

let band: Band | null = null;

/** The app's one band. Created lazily so nothing touches Web Audio at import time. */
export function getBand(): Band {
  band ??= new Band();
  return band;
}

export type { Band };

const NOTE_INDEX: Record<string, number> = {
  C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6,
  G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11,
};

/** "A4" -> 440. */
export function freq(note: string): number {
  const m = /^([A-G][#b]?)(-?\d)$/.exec(note);
  if (!m) throw new Error(`bad note ${note}`);
  const midi = NOTE_INDEX[m[1]] + (Number(m[2]) + 1) * 12;
  return 440 * 2 ** ((midi - 69) / 12);
}
