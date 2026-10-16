// Zero-dependency Web Audio UI sound synthesizer. No samples, no libraries: every
// cue is generated from oscillators and gain envelopes. A single mute flag (persisted
// in localStorage) gates all output, and the AudioContext is created lazily on the
// first user gesture to satisfy browser autoplay policies.

let ctx: AudioContext | null = null;
let master: GainNode | null = null;

const MUTE_KEY = "courtofcode.muted";

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

let muted = readMuted();

function ensureCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!ctx) {
    const AC: typeof AudioContext | undefined =
      window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
    master = ctx.createGain();
    master.gain.value = 0.5;
    master.connect(ctx.destination);
  }
  if (ctx.state === "suspended") {
    void ctx.resume().catch(() => {});
  }
  return ctx;
}

export function isMuted(): boolean {
  return muted;
}

export function setMuted(next: boolean): void {
  muted = next;
  try {
    localStorage.setItem(MUTE_KEY, next ? "1" : "0");
  } catch {
    /* ignore storage failures */
  }
}

export function toggleMuted(): boolean {
  setMuted(!muted);
  return muted;
}

function tone(
  freq: number,
  startOffset: number,
  dur: number,
  type: OscillatorType,
  peak: number,
): void {
  const c = ensureCtx();
  if (!c || !master || muted) return;
  const t0 = c.currentTime + startOffset;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(peak, t0 + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g);
  g.connect(master);
  osc.start(t0);
  osc.stop(t0 + dur + 0.03);
}

// Crisp futuristic UI click.
export function click(): void {
  tone(680, 0, 0.06, "triangle", 0.16);
  tone(1020, 0.006, 0.05, "sine", 0.09);
}

// Very light hover tick, kept quiet so it never nags.
export function hover(): void {
  tone(1320, 0, 0.03, "sine", 0.04);
}

// Filtered rising sweep for step / panel transitions.
export function hum(): void {
  const c = ensureCtx();
  if (!c || !master || muted) return;
  const t0 = c.currentTime;
  const osc = c.createOscillator();
  const filt = c.createBiquadFilter();
  const g = c.createGain();
  osc.type = "sawtooth";
  osc.frequency.setValueAtTime(170, t0);
  osc.frequency.exponentialRampToValueAtTime(430, t0 + 0.35);
  filt.type = "lowpass";
  filt.frequency.setValueAtTime(420, t0);
  filt.frequency.exponentialRampToValueAtTime(2000, t0 + 0.35);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(0.12, t0 + 0.05);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.42);
  osc.connect(filt);
  filt.connect(g);
  g.connect(master);
  osc.start(t0);
  osc.stop(t0 + 0.45);
}

// Harmonic chord chime when a transaction reaches FINALIZED.
export function chime(): void {
  const notes = [440, 523.25, 659.25, 880, 1046.5];
  notes.forEach((n, i) => tone(n, i * 0.045, 0.95, "sine", 0.15));
  tone(1318.5, 0.22, 1.15, "triangle", 0.07);
}

// Low dissonant buzz for a reverted or failed write.
export function errorBuzz(): void {
  tone(160, 0, 0.18, "square", 0.11);
  tone(118, 0.03, 0.22, "sawtooth", 0.09);
}
