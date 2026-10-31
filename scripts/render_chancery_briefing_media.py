"""Bespoke Chancery briefing-media renderer for CourtOfCode Milestone v1.

This single Python tool:
  1. synthesizes an original classical / chancery ambient stereo soundtrack with the
     standard library only (no samples, no third-party audio libraries), and
  2. captures the redesigned judicial workbench with the bespoke Playwright recorder, and
  3. assembles a crisp 48..52 second, 1280x720, libx264 + aac subtitled demo film via a
     bundled ffmpeg, publishing it to docs/ and frontend/public/.

Run from the repository root, after `npm --prefix frontend run build`:

    python scripts/render_chancery_briefing_media.py

Useful flags:
    --skip-record   reuse the existing video/clips webm captures (only re-render)
    --audio-only    just write video/soundtrack.wav
"""

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
VIDEO_DIR = ROOT / "video"
CLIPS_DIR = VIDEO_DIR / "clips"
MANIFEST = CLIPS_DIR / "manifest.json"
SOUNDTRACK = VIDEO_DIR / "soundtrack.wav"
DOCS_VIDEO = ROOT / "docs" / "demo-video-subtitled.mp4"
PUBLIC_VIDEO = FRONTEND / "public" / "demo-video-subtitled.mp4"
SAMPLE_RATE = 44100

# beat -> (tail seconds kept, burned caption). Domain-native narration only.
BEATS = [
    (1, 8, "One-click burner counsel reads the live Chancery registry, no extension needed"),
    (2, 9, "Bilateral PR diff bench: claimant proof against the maintainer rebuttal"),
    (3, 8, "Live rebuttal and appeal timeline beside the co-sign settlement panel"),
    (4, 9, "Chancery award apportionment: discrete 5-anchor ladder and 500-bps baseline grid"),
    (5, 8, "Equivalence principle decree transcript bound by full validator consensus"),
    (6, 9, "Soft-fail refund ledger and the procedural rule verification bench"),
]

SUBSTYLE = (
    "FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00F2E6C8,"
    "OutlineColour=&H00000000,BorderStyle=3,BackColour=&H800C0E14,"
    "Outline=1,Shadow=0,Alignment=2,MarginV=16"
)


# ---------------------------------------------------------------------------
# ffmpeg resolution
# ---------------------------------------------------------------------------


def find_ffmpeg():
    env = os.environ.get("FFMPEG")
    if env and Path(env).exists():
        return env
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    bundled = VIDEO_DIR / "node_modules" / "ffmpeg-static" / exe
    if bundled.exists():
        return str(bundled)
    which = shutil.which("ffmpeg")
    if which:
        return which
    raise SystemExit("ffmpeg not found; set FFMPEG or install video/node_modules (npm --prefix video install)")


def run(cmd):
    print("+ " + " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, cwd=str(VIDEO_DIR))


# ---------------------------------------------------------------------------
# Original soundtrack synthesis (stdlib only)
# ---------------------------------------------------------------------------


def _note(freq, start, dur, amp, decay):
    n0 = int(start * SAMPLE_RATE)
    n1 = int((start + dur) * SAMPLE_RATE)
    out = []
    for i in range(n1 - n0):
        t = i / SAMPLE_RATE
        env = math.exp(-decay * t)
        # soft harp/strings voicing: fundamental + a couple of quiet harmonics
        s = (
            math.sin(2 * math.pi * freq * t)
            + 0.35 * math.sin(2 * math.pi * freq * 2 * t)
            + 0.15 * math.sin(2 * math.pi * freq * 3 * t)
        )
        out.append(amp * env * s)
    return n0, n1, out


def synthesize_soundtrack(total_seconds, path):
    n = total_seconds * SAMPLE_RATE
    left = [0.0] * n
    right = [0.0] * n

    # Warm sustained drone in D minor (a solemn chancery bed).
    for freq, pan in ((73.42, 0.5), (146.83, 0.5), (220.0, 0.6)):
        for i in range(n):
            t = i / SAMPLE_RATE
            swell = 0.5 + 0.5 * math.sin(2 * math.pi * 0.05 * t)
            v = 0.03 * swell * math.sin(2 * math.pi * freq * t)
            left[i] += v * pan
            right[i] += v * (1 - pan)

    # Plucked arpeggio motif (D minor) repeated over the runtime, panning left to right.
    motif = [293.66, 349.23, 440.00, 587.33, 440.00, 349.23]  # D F A D' A F
    bar = 4.0
    idx = 0
    t = 1.0
    while t < total_seconds - 1.0:
        for _ in range(6):
            freq = motif[idx % len(motif)]
            pan = 0.5 + 0.25 * math.sin(idx * 0.7)
            n0, n1, samples = _note(freq, t, 1.6, 0.16, 2.6)
            for j, s in enumerate(samples):
                k = n0 + j
                if k < n:
                    left[k] += s * pan
                    right[k] += s * (1 - pan)
            idx += 1
            t += bar / 6.0
        t += bar / 3.0  # breathing gap between phrases

    # Gentle bell accents at each beat boundary to sync with the on-screen cuts.
    for (bnum, keep, cap) in BEATS:
        pass
    boundary = 0.0
    for (_, keep, _) in BEATS:
        boundary += keep
        n0, n1, samples = _note(880.0, boundary - 0.15, 1.2, 0.12, 3.2)
        for j, s in enumerate(samples):
            k = n0 + j
            if k < n:
                left[k] += s * 0.5
                right[k] += s * 0.5

    peak = max(max(abs(x) for x in left), max(abs(x) for x in right), 1e-6)
    gain = 0.89 / peak
    frames = bytearray()
    for i in range(n):
        l = int(max(-1.0, min(1.0, left[i] * gain)) * 32767)
        r = int(max(-1.0, min(1.0, right[i] * gain)) * 32767)
        frames += struct.pack("<hh", l, r)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))
    print(f"synthesized {path.name}: {total_seconds}s stereo")


# ---------------------------------------------------------------------------
# Recording + assembly
# ---------------------------------------------------------------------------


def start_preview():
    proc = subprocess.Popen(
        ["npm", "run", "preview", "--", "--port", "4173", "--strictPort"],
        cwd=str(FRONTEND),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        try:
            urlopen("http://localhost:4173/", timeout=2).read()
            print("preview server ready on :4173")
            return proc
        except Exception:
            time.sleep(1)
    return proc


def record_clips():
    env = dict(os.environ, CHANCERY_URL="http://localhost:4173/")
    node = "node.cmd" if os.name == "nt" else "node"
    subprocess.run([node, "record_chancery.mjs"], cwd=str(VIDEO_DIR), env=env, check=True)


def srt_time(sec):
    ms = int(round((sec % 1) * 1000))
    total = int(sec)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def probe_duration(ff, path):
    try:
        res = subprocess.run([ff, "-i", path], capture_output=True, text=True)
        out = res.stderr
    except Exception:
        out = ""
    import re
    mm = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    if not mm:
        return 0.0
    return int(mm.group(1)) * 3600 + int(mm.group(2)) * 60 + float(mm.group(3))


def assemble():
    ff = find_ffmpeg()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    clip_for = {e["n"]: e["path"] for e in manifest}
    parts = []
    running = 0.0
    for (n, keep, cap) in BEATS:
        clip = clip_for.get(n)
        if not clip or not Path(clip).exists():
            raise SystemExit(f"missing clip for beat {n}: {clip}")
        dur = probe_duration(ff, clip)
        start = max(0.0, dur - keep) if dur else 0.0
        srt = VIDEO_DIR / f"capseg{n}.srt"
        srt.write_text(f"1\n{srt_time(0)} --> {srt_time(keep)}\n{cap}\n", encoding="utf-8")
        out = VIDEO_DIR / f"capseg{n}.mp4"
        vf = f"fps=25,scale=1280:720,setsar=1,subtitles={srt.name}:force_style='{SUBSTYLE}'"
        run([
            ff, "-y", "-ss", f"{start:.2f}", "-i", clip, "-t", str(keep),
            "-vf", vf, "-c:v", "libx264", "-crf", "26", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart", "-an", out,
        ])
        parts.append(out)
        running += keep

    concat = VIDEO_DIR / "concat_v1.txt"
    concat.write_text("\n".join(f"file '{p.name}'" for p in parts) + "\n", encoding="utf-8")
    video_only = VIDEO_DIR / "video_only_v1.mp4"
    run([ff, "-y", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", video_only])

    total = int(round(running))
    synthesize_soundtrack(total, SOUNDTRACK)

    DOCS_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    run([
        ff, "-y", "-i", video_only, "-i", SOUNDTRACK,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-shortest", "-movflags", "+faststart",
        DOCS_VIDEO,
    ])
    shutil.copyfile(DOCS_VIDEO, PUBLIC_VIDEO)
    mb = DOCS_VIDEO.stat().st_size / (1024 * 1024)
    print(f"\nBUILT {DOCS_VIDEO}  ~{running:.1f}s  {mb:.2f} MB")
    if mb >= 15:
        raise SystemExit(f"final video {mb:.2f} MB exceeds the 15 MB budget")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-record", action="store_true")
    ap.add_argument("--audio-only", action="store_true")
    args = ap.parse_args()

    if args.audio_only:
        synthesize_soundtrack(int(sum(k for (_, k, _) in BEATS)), SOUNDTRACK)
        return

    ff = find_ffmpeg()
    print(f"using ffmpeg: {ff}")

    preview = None
    try:
        if not args.skip_record:
            preview = start_preview()
            record_clips()
        assemble()
    finally:
        if preview is not None:
            preview.terminate()


if __name__ == "__main__":
    main()
