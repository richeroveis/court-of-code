#!/usr/bin/env python3
"""Generate a clean, royalty-free ambient electronic soundtrack for the CourtOfCode
demo video using only the Python standard library (wave, math, struct).

The bed is a warm, low-pass filtered pad playing an A minor / C major chord
progression (Am - F - C - G) with slow swells and gentle stereo width. Short
harmonic chime accents are placed at the subtitle transition timestamps passed on
the command line, so the audio cues land exactly when each caption changes.

Examples:
    python tools/generate_soundtrack.py --duration 50 --out video/soundtrack.wav
    python tools/generate_soundtrack.py --duration 50 --chimes 10,20,31,42
"""

import argparse
import math
import struct
import sys
import wave

SR = 44100

# Equal-tempered note frequencies (Hz) for the pad voices.
NOTES = {
    "F2": 87.31,
    "G2": 98.00,
    "A2": 110.00,
    "B2": 123.47,
    "C3": 130.81,
    "D3": 146.83,
    "E3": 164.81,
    "F3": 174.61,
    "G3": 196.00,
    "A3": 220.00,
    "C4": 261.63,
    "A5": 880.00,
    "C6": 1046.50,
    "E6": 1318.51,
}

# i - VI - III - VII in A minor: warm, hopeful, resolves back to Am.
PROGRESSION = [
    ["A2", "C3", "E3", "A3"],
    ["F2", "A2", "C3", "F3"],
    ["C3", "E3", "G3", "C4"],
    ["G2", "B2", "D3", "G3"],
]


def lowpass(signal, cutoff_hz):
    """Single-pole IIR low-pass for a warm, rounded tone."""
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / SR)
    y = 0.0
    out = [0.0] * len(signal)
    for i, x in enumerate(signal):
        y += alpha * (x - y)
        out[i] = y
    return out


def pad_chord(freqs, n_samples, attack, release, detune):
    """Additive synth of a chord: fundamental plus a few softening harmonics,
    wrapped in a swell envelope. detune shifts the pitch slightly for stereo width."""
    buf = [0.0] * n_samples
    harmonics = [(1, 1.0), (2, 0.42), (3, 0.24), (4, 0.12)]
    for f0 in freqs:
        f0 *= detune
        for mult, amp in harmonics:
            f = f0 * mult
            phase_step = 2.0 * math.pi * f / SR
            for i in range(n_samples):
                buf[i] += amp * math.sin(phase_step * i)
    # Swell envelope (linear attack, linear release, sustain between).
    for i in range(n_samples):
        if i < attack:
            env = i / attack
        elif i > n_samples - release:
            env = max(0.0, (n_samples - i) / release)
        else:
            env = 1.0
        # Smooth the envelope edges with a gentle cosine for a softer swell.
        buf[i] *= env * 0.5
    return buf


def add_at(target, source, start):
    for i, v in enumerate(source):
        j = start + i
        if 0 <= j < len(target):
            target[j] += v


def chime(n_total, at_sample, base_freq):
    """A short bell: a couple of inharmonic-ish partials with exponential decay."""
    out = [0.0] * n_total
    dur = int(2.2 * SR)
    partials = [(1.0, 1.0), (2.0, 0.5), (3.01, 0.28), (4.7, 0.12)]
    for i in range(dur):
        t = i / SR
        decay = math.exp(-t * 3.2)
        s = 0.0
        for mult, amp in partials:
            s += amp * math.sin(2.0 * math.pi * base_freq * mult * t)
        j = at_sample + i
        if 0 <= j < n_total:
            out[j] = s * decay * 0.22
    return out


def generate(duration, chime_times):
    n_total = int(duration * SR)
    left = [0.0] * n_total
    right = [0.0] * n_total

    seg = n_total / len(PROGRESSION)
    attack = int(1.8 * SR)
    release = int(2.2 * SR)
    overlap = int(2.0 * SR)  # crossfade length between chords

    for idx, chord in enumerate(PROGRESSION):
        start = int(idx * seg) - (overlap if idx > 0 else 0)
        length = int(seg) + overlap
        if start < 0:
            length += start
            start = 0
        if start + length > n_total:
            length = n_total - start
        if length <= 0:
            continue
        # Slightly detuned L/R copies create a wide, chorused pad.
        left_buf = pad_chord([NOTES[n] for n in chord], length, attack, release, 0.9975)
        right_buf = pad_chord([NOTES[n] for n in chord], length, attack, release, 1.0025)
        add_at(left, left_buf, start)
        add_at(right, right_buf, start)

    # Warm the whole pad.
    left = lowpass(left, 1400)
    right = lowpass(right, 1400)

    # Chime accents at subtitle transitions (and a soft one at the very start).
    bell_notes = [NOTES["A5"], NOTES["C6"], NOTES["E6"], NOTES["C6"], NOTES["E6"]]
    marks = [0.0] + list(chime_times)
    for k, tsec in enumerate(marks):
        at = int(tsec * SR)
        base = bell_notes[k % len(bell_notes)]
        bell = chime(n_total, at, base)
        for i in range(n_total):
            if bell[i]:
                left[i] += bell[i]
                right[i] += bell[i] * 0.9

    # Normalize to a safe peak and apply a short fade in/out to avoid clicks.
    peak = max(1e-9, max(max(abs(s) for s in left), max(abs(s) for s in right)))
    gain = 0.82 / peak
    fade = int(0.4 * SR)
    for i in range(n_total):
        g = gain
        if i < fade:
            g *= i / fade
        elif i > n_total - fade:
            g *= max(0.0, (n_total - i) / fade)
        left[i] *= g
        right[i] *= g
    return left, right


def write_wav(path, left, right):
    n = len(left)
    frames = bytearray()
    for i in range(n):
        sl = max(-32768, min(32767, int(left[i] * 32767)))
        sr = max(-32768, min(32767, int(right[i] * 32767)))
        frames += struct.pack("<hh", sl, sr)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))


def main():
    ap = argparse.ArgumentParser(description="Synthesize the CourtOfCode demo soundtrack.")
    ap.add_argument("--duration", type=float, default=50.0, help="track length in seconds")
    ap.add_argument("--chimes", type=str, default="", help="comma-separated transition times in seconds")
    ap.add_argument("--out", type=str, default="video/soundtrack.wav", help="output wav path")
    args = ap.parse_args()

    chime_times = [float(x) for x in args.chimes.split(",") if x.strip()]
    print(f"Synthesizing {args.duration:.1f}s stereo ambient bed with {len(chime_times)} chime accents...")
    left, right = generate(args.duration, chime_times)
    write_wav(args.out, left, right)
    print(f"Wrote {args.out} ({args.duration:.1f}s, {SR} Hz, 16-bit stereo)")


if __name__ == "__main__":
    sys.exit(main())
