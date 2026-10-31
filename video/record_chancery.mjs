// Records the Milestone v1 CourtOfCode Chancery demo as six narrated beats against the
// locally served frontend build (which points at the live studionet deployment). Each beat
// is its own browser context producing its own webm, later concatenated and subtitled by
// scripts/render_chancery_briefing_media.py. This recorder is bespoke to the redesigned
// judicial workbench and deliberately carries no legacy template labels.

import { chromium } from "playwright";
import { mkdirSync, rmSync, writeFileSync } from "fs";

const URL = process.env.CHANCERY_URL || "http://localhost:4173/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function swearIn(page) {
  await page.getByRole("button", { name: /1-Click Burner Counsel/ }).click();
  await page.getByRole("button", { name: /^Rotate$/ }).waitFor({ timeout: 30000 });
  await page.locator(".registry-row").first().waitFor({ timeout: 25000 });
  await sleep(500);
}

async function openDocket(page, id) {
  for (let attempt = 0; attempt < 6; attempt++) {
    await page.locator(".registry-row", { hasText: `№ ${id}` }).first().click({ timeout: 4000 }).catch(() => {});
    try {
      await page.locator(".registry-row.active", { hasText: `№ ${id}` }).first().waitFor({ timeout: 2500 });
      await sleep(600);
      return;
    } catch {
      /* reload may reset the selection; retry */
    }
  }
}

async function scrollTo(page, selector) {
  await page.locator(selector).first().scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
  await sleep(800);
}

async function setRange(page, nth, value) {
  await page.locator('.matrix input[type="range"]').nth(nth).evaluate((el, v) => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    setter.call(el, String(v));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}

const beats = {
  1: { hold: 3200, run: async (p) => { await swearIn(p); } },
  2: { hold: 3000, run: async (p) => {
    await swearIn(p);
    await scrollTo(p, ".registry");
    await openDocket(p, "M1");
    await scrollTo(p, ".diff-bench");
  } },
  3: { hold: 3000, run: async (p) => {
    await swearIn(p);
    await openDocket(p, "M1");
    await scrollTo(p, ".timeline");
    await scrollTo(p, ".cosign");
  } },
  4: { hold: 3200, run: async (p) => {
    await swearIn(p);
    await scrollTo(p, ".matrix");
    await setRange(p, 0, 8200);
    await sleep(700);
    await setRange(p, 1, 6100);
    await sleep(900);
  } },
  5: { hold: 3000, run: async (p) => {
    await swearIn(p);
    await openDocket(p, "M1");
    await scrollTo(p, ".transcript");
  } },
  6: { hold: 3400, run: async (p) => {
    await swearIn(p);
    await scrollTo(p, ".rulebench");
    await scrollTo(p, ".custody");
  } },
};

async function recordBeat(browser, n) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: "clips", size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  page.setDefaultNavigationTimeout(60000);
  for (let i = 0; i < 3; i++) {
    try {
      await page.goto(URL, { waitUntil: "domcontentloaded" });
      break;
    } catch (e) {
      console.log(`goto attempt ${i} failed: ${e.message}`);
      if (i === 2) throw e;
      await sleep(3000);
    }
  }
  await sleep(900);
  try {
    await beats[n].run(page);
  } catch (e) {
    console.log(`beat ${n} interaction warning: ${e.message}`);
  }
  await sleep(beats[n].hold);
  await context.close();
  const path = await page.video().path();
  console.log(`CLIP ${n} = ${path}`);
  return { n, path };
}

async function main() {
  rmSync("clips", { recursive: true, force: true });
  mkdirSync("clips", { recursive: true });
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const manifest = [];
  const only = process.argv[2] ? Number(process.argv[2]) : null;
  for (const n of only ? [only] : [1, 2, 3, 4, 5, 6]) {
    manifest.push(await recordBeat(browser, n));
  }
  await browser.close();
  writeFileSync("clips/manifest.json", JSON.stringify(manifest, null, 2));
  console.log("MANIFEST=" + JSON.stringify(manifest));
}

main().catch((e) => {
  console.error("RECORD ERROR:", e);
  process.exit(1);
});
