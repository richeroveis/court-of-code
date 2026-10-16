// Records a walkthrough of the live CourtOfCode UI on studionet using Playwright
// driving the system Chrome (Playwright's own browser CDN is geo-blocked here).
// Produces a raw 1280x720 webm into ./raw; subtitles are burned in a later ffmpeg step.

import { chromium } from "playwright";
import { mkdirSync } from "fs";

const URL = "https://richeroveis.github.io/court-of-code/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clickCase(page, n) {
  await page.locator(".case-row", { hasText: `#${n}` }).first().click();
  await sleep(1200);
}

async function connectBurner(page) {
  await page.getByRole("button", { name: /1-Click Instant Juror Wallet/ }).click();
  await page.getByRole("button", { name: /Rotate Identity/ }).waitFor({ timeout: 30000 });
}

async function main() {
  mkdirSync("raw", { recursive: true });
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: "raw", size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await sleep(2000);

  // 1. Burner wallet activation.
  await connectBurner(page);
  await sleep(2500);

  // 2. Inspect a seeded adjudicated case and its split-award bar.
  await clickCase(page, 1);
  await page.locator(".award-bar").waitFor({ timeout: 20000 });
  await sleep(4000);

  // 3. File an on-chain amicus brief on the open case.
  await clickCase(page, 2);
  await page.locator('textarea[placeholder^="technical argument"]').fill(
    "The rust ingestion path holds p99 under 40ms on my load test; claimant delivered",
  );
  await sleep(2500);
  await page.getByRole("button", { name: /File Brief & Vote/ }).click();
  await sleep(4000); // capture the "submitting to consensus" toast

  // Reload to reset the UI busy-lock (the brief tx finalizes on chain independently).
  await page.reload({ waitUntil: "networkidle" });
  await sleep(1500);
  await connectBurner(page);
  await clickCase(page, 2);

  // 4. Upvote a fellow juror's brief (the pre-seeded auditcrew brief).
  const auditcrew = page.locator(".brief", { hasText: "auditcrew" }).first();
  await auditcrew.locator("button", { hasText: "+" }).click();
  await sleep(4000);

  await page.reload({ waitUntil: "networkidle" });
  await sleep(1500);
  await connectBurner(page);
  await clickCase(page, 2);

  // 5. Trigger GenLayer consensus adjudication of the split award.
  await page.getByRole("button", { name: /Trigger Live AI Adjudication/ }).click();
  await sleep(6000); // capture the full-consensus submission toast

  await context.close();
  const video = page.video();
  const path = video ? await video.path() : null;
  await browser.close();
  console.log("VIDEO_PATH=" + path);
}

main().catch((e) => {
  console.error("RECORD ERROR:", e);
  process.exit(1);
});
