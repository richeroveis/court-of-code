// Builds docs/demo-video-subtitled.mp4 from the five per-beat clips.
// For each clip: trim off the leading load dead-time, burn the beat's caption to
// span the whole trimmed segment (so Playwright's non-linear timing is irrelevant),
// re-encode to a uniform 1280x720/25fps/yuv420p h264 stream, then concat all five.

import { execFileSync } from "child_process";
import { writeFileSync, existsSync } from "fs";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const FF = require("ffmpeg-static");

const clips = {
  1: "clips/page@5fd5961b9b662d30430f89f40599e74b.webm",
  2: "clips/page@479eea2d122750acce33f13b2a07c9a6.webm",
  3: "clips/page@908125f5ad326d3aaf0f3b6f68a1b2d6.webm",
  4: "clips/page@9485b010b002b297090c39d0020a4c12.webm",
  5: "clips/page@d0bf3bd43a2fd2cec4d04356f39a7c55.webm",
};

// start = clipDuration - keep, tuned per clip so each action + toast is included.
const plan = {
  1: { start: 4.36, keep: 10.0, cap: "1. One-click juror burner wallet, no extension needed" },
  2: { start: 6.6, keep: 10.0, cap: "2. A seeded dispute: split-screen evidence and the split-award bar" },
  3: { start: 7.24, keep: 11.0, cap: "3. Filing an on-chain amicus brief, which also casts a vote" },
  4: { start: 11.92, keep: 11.0, cap: "4. Upvoting a fellow juror's brief to boost its signal" },
  5: { start: 13.14, keep: 6.5, cap: "5. Triggering GenLayer consensus on the split award" },
};

const STYLE =
  "FontName=Arial,FontSize=13,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,BackColour=&H80000000,Outline=1,Shadow=0,Alignment=2,MarginV=14";

function srtTime(s) {
  const ms = Math.round((s % 1) * 1000);
  const total = Math.floor(s);
  const h = String(Math.floor(total / 3600)).padStart(2, "0");
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const sec = String(total % 60).padStart(2, "0");
  return `${h}:${m}:${sec},${String(ms).padStart(3, "0")}`;
}

const parts = [];
for (const n of [1, 2, 3, 4, 5]) {
  const p = plan[n];
  const srtPath = `capseg${n}.srt`;
  writeFileSync(
    srtPath,
    `1\n${srtTime(0)} --> ${srtTime(p.keep)}\n${p.cap}\n`,
    "utf8",
  );
  const out = `capseg${n}.mp4`;
  const vf = `fps=25,scale=1280:720,setsar=1,subtitles=${srtPath}:force_style='${STYLE}'`;
  execFileSync(
    FF,
    [
      "-y",
      "-ss", String(p.start),
      "-i", clips[n],
      "-t", String(p.keep),
      "-vf", vf,
      "-c:v", "libx264", "-crf", "23", "-preset", "medium",
      "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart",
      "-an", out,
    ],
    { stdio: "inherit" },
  );
  if (!existsSync(out)) throw new Error(`missing ${out}`);
  parts.push(out);
}

writeFileSync("concat.txt", parts.map((f) => `file '${f}'`).join("\n") + "\n", "utf8");
execFileSync(
  FF,
  ["-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "../docs/demo-video-subtitled.mp4"],
  { stdio: "inherit" },
);
console.log("BUILT docs/demo-video-subtitled.mp4");
