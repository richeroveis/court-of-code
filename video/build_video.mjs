// Builds docs/demo-video-subtitled.mp4 from the six per-beat clips recorded by
// record_clips.mjs (paths come from clips/manifest.json, so it never hardcodes the
// random Playwright page ids).
//
// For each beat: probe the clip length, keep its final `keep` seconds (the beat's
// action + settle + toast/confetti always land at the tail because the recorder
// sleeps a hold after the action), burn that beat's caption to span the whole kept
// segment, and re-encode to a uniform 1280x720 / 25fps / yuv420p h264 stream. The
// segments are concatenated, then the synthesized soundtrack (video/soundtrack.wav,
// produced by tools/generate_soundtrack.py with chime accents at these same segment
// boundaries) is muxed on top as AAC so the final file carries both h264 video and
// aac stereo audio.

import { execFileSync } from "child_process";
import { readFileSync, writeFileSync, existsSync, statSync } from "fs";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const FF = require("ffmpeg-static");

// keep = seconds of the clip tail to show; cap = the burned subtitle for that beat.
const beats = [
  { n: 1, keep: 7, cap: "1. One-click juror burner wallet reads the live tribunal, no extension" },
  { n: 2, keep: 9, cap: "2. What-if simulator: drag the AI-consensus sliders, see exact settlement math" },
  { n: 3, keep: 9, cap: "3. Case detail: SVG award gauge, split-screen evidence, prompt inspector" },
  { n: 4, keep: 9, cap: "4. Filing an on-chain amicus brief: leader-only write FINALIZES and fires confetti" },
  { n: 5, keep: 8, cap: "5. Upvoting a fellow juror's brief to boost its signal on the live tribunal" },
  { n: 6, keep: 9, cap: "6. Triggering live GenLayer full-consensus adjudication on the split award" },
];

const STYLE =
  "FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,BackColour=&H80000000,Outline=1,Shadow=0,Alignment=2,MarginV=14";

function probeDuration(path) {
  let s = "";
  try {
    s = execFileSync(FF, ["-i", path], { stdio: ["ignore", "ignore", "pipe"] }).toString();
  } catch (e) {
    s = e.stderr ? e.stderr.toString() : "";
  }
  const d = s.match(/Duration: (\d+):(\d+):([\d.]+)/);
  if (!d) throw new Error(`could not probe duration of ${path}`);
  return Number(d[1]) * 3600 + Number(d[2]) * 60 + Number(d[3]);
}

function srtTime(sec) {
  const ms = Math.round((sec % 1) * 1000);
  const total = Math.floor(sec);
  const h = String(Math.floor(total / 3600)).padStart(2, "0");
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${h}:${m}:${ss},${String(ms).padStart(3, "0")}`;
}

const manifest = JSON.parse(readFileSync("clips/manifest.json", "utf8"));
const clipFor = (n) => (manifest.find((e) => e.n === n) || {}).path;

const parts = [];
let running = 0;
const boundaries = [];
for (const b of beats) {
  const clip = clipFor(b.n);
  if (!clip || !existsSync(clip)) throw new Error(`missing clip for beat ${b.n}: ${clip}`);
  const dur = probeDuration(clip);
  const start = Math.max(0, dur - b.keep);
  boundaries.push(running);
  running += b.keep;

  const srtPath = `capseg${b.n}.srt`;
  writeFileSync(srtPath, `1\n${srtTime(0)} --> ${srtTime(b.keep)}\n${b.cap}\n`, "utf8");
  const out = `capseg${b.n}.mp4`;
  const vf = `fps=25,scale=1280:720,setsar=1,subtitles=${srtPath}:force_style='${STYLE}'`;
  execFileSync(
    FF,
    [
      "-y",
      "-ss", start.toFixed(2),
      "-i", clip,
      "-t", String(b.keep),
      "-vf", vf,
      "-c:v", "libx264", "-crf", "25", "-preset", "medium",
      "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart",
      "-an", out,
    ],
    { stdio: "inherit" },
  );
  if (!existsSync(out)) throw new Error(`missing ${out}`);
  parts.push(out);
}

// Lossless concat of the uniform segments into a silent video track.
writeFileSync("concat.txt", parts.map((f) => `file '${f}'`).join("\n") + "\n", "utf8");
execFileSync(FF, ["-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "video_only.mp4"], {
  stdio: "inherit",
});

// Mux the synthesized soundtrack as AAC. -shortest trims audio to the video length.
if (!existsSync("soundtrack.wav")) {
  throw new Error("video/soundtrack.wav missing: run tools/generate_soundtrack.py --duration 51 first");
}
execFileSync(
  FF,
  [
    "-y",
    "-i", "video_only.mp4",
    "-i", "soundtrack.wav",
    "-map", "0:v:0", "-map", "1:a:0",
    "-c:v", "copy",
    "-c:a", "aac", "-b:a", "128k", "-ac", "2",
    "-shortest", "-movflags", "+faststart",
    "../docs/demo-video-subtitled.mp4",
  ],
  { stdio: "inherit" },
);

const finalPath = "../docs/demo-video-subtitled.mp4";
const mb = statSync(finalPath).size / (1024 * 1024);
console.log(`\nBUILT ${finalPath}  (~${running.toFixed(1)}s, ${mb.toFixed(2)} MB, segment starts: ${boundaries.join(", ")})`);
