// Records the CourtOfCode demo as six independent short clips (one per narrated
// beat) using Playwright driving the system Chrome. Each beat is its own browser
// context, so each produces its own webm. Because a caption is burned to span an
// entire clip, Playwright's non-linear video timing no longer matters. The clips are
// concatenated afterwards and a synthesized soundtrack is muxed on top.

import { chromium } from "playwright";
import { mkdirSync, rmSync, writeFileSync } from "fs";

const URL = "https://richeroveis.github.io/court-of-code/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connectBurner(page) {
  await page.getByRole("button", { name: /1-Click Instant Juror Wallet/ }).click();
  await page.getByRole("button", { name: /Rotate Identity/ }).waitFor({ timeout: 30000 });
  await page.locator(".case-row").first().waitFor({ timeout: 25000 });
  await page.getByText(/Amicus Briefs/i).first().waitFor({ timeout: 20000 }).catch(() => {});
  await sleep(500);
}

async function openCase(page, n) {
  for (let attempt = 0; attempt < 5; attempt++) {
    await page.locator(".case-row", { hasText: `#${n}` }).first().click({ timeout: 4000 }).catch(() => {});
    try {
      await page.locator(".case-row.active", { hasText: `#${n}` }).first().waitFor({ timeout: 2500 });
      await sleep(600);
      return;
    } catch {
      /* load() reset the selection; retry */
    }
  }
}

async function scrollSel(page, selector) {
  await page.locator(selector).first().scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
  await sleep(900);
}

// Wait until a write reaches a terminal toast (ok => FINALIZED + confetti + chime,
// err => reverted), so the clip actually captures the settlement payoff instead of
// ending on "submitting to consensus". leaderOnly writes settle in a few seconds.
async function waitToast(page, timeoutMs = 40000) {
  await Promise.race([
    page.locator(".toast.ok, .toast.err").first().waitFor({ state: "visible", timeout: timeoutMs }),
    sleep(timeoutMs),
  ]).catch(() => {});
}

// Set a React-controlled range input via the native setter so onChange fires.
async function setRange(page, nth, value) {
  await page
    .locator('.sim input[type="range"]')
    .nth(nth)
    .evaluate((el, v) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(el, String(v));
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }, value);
}

async function clickAdjudicate(page) {
  await scrollSel(page, "button:has-text('Trigger Live AI Adjudication')");
  const btn = page.getByRole("button", { name: /Trigger Live AI Adjudication/ });
  for (let attempt = 0; attempt < 4; attempt++) {
    await btn.click();
    await sleep(1800);
    if ((await page.locator(".toast.err").count()) > 0) {
      await page.locator(".toast").first().click({ timeout: 2000 }).catch(() => {});
      await sleep(700);
      continue;
    }
    break;
  }
}

const beats = {
  1: { hold: 3000, run: async (p) => { await connectBurner(p); } },
  2: { hold: 2600, run: async (p) => {
    await connectBurner(p);
    await p.locator(".sim").first().scrollIntoViewIfNeeded().catch(() => {});
    await setRange(p, 0, 8000);
    await sleep(800);
    await setRange(p, 1, 600000);
    await sleep(800);
    await p.locator(".sim .chip").first().click().catch(() => {}); // token missing -> cap
    await sleep(900);
    await p.locator(".sim .chip").first().click().catch(() => {}); // token found again
  } },
  3: { hold: 3000, run: async (p) => {
    await connectBurner(p);
    await openCase(p, 1);
    await p.locator(".evidence-bench").first().scrollIntoViewIfNeeded().catch(() => {});
    await sleep(700);
    await scrollSel(p, ".award-bar");
    await p.locator(".inspector-head").first().click().catch(() => {});
    await sleep(700);
  } },
  4: { hold: 3600, run: async (p) => {
    await connectBurner(p);
    await openCase(p, 2);
    await scrollSel(p, 'textarea[placeholder^="technical argument"]');
    await p.locator('textarea[placeholder^="technical argument"]').fill(
      "The rust ingestion path holds p99 under 40ms on my load test; claimant delivered",
    );
    await sleep(1200);
    await p.getByRole("button", { name: /File Brief & Vote/ }).click();
    await waitToast(p);
  } },
  5: { hold: 3600, run: async (p) => {
    await connectBurner(p);
    await openCase(p, 2);
    await scrollSel(p, ".brief");
    await p.locator(".brief", { hasText: "auditcrew" }).first().locator("button", { hasText: "+" }).click();
    await waitToast(p);
  } },
  6: { hold: 3600, run: async (p) => {
    await connectBurner(p);
    await openCase(p, 2);
    await clickAdjudicate(p);
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
  await sleep(800);
  await beats[n].run(page);
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
