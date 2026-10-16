// Quick visual smoke test: load the live upgraded UI, connect a burner, and capture
// the hero simulator plus a case detail (gauge + inspector) for review.
import { chromium } from "playwright";
const URL = "https://richeroveis.github.io/court-of-code/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
page.setDefaultNavigationTimeout(60000);
await page.goto(URL, { waitUntil: "networkidle" });
await sleep(1500);
await page.screenshot({ path: "shot_loggedout.png" });
await page.getByRole("button", { name: /1-Click Instant Juror Wallet/ }).click();
await page.locator(".case-row").first().waitFor({ timeout: 30000 });
await page.getByText(/Amicus Briefs/i).first().waitFor({ timeout: 25000 }).catch(() => {});
await sleep(1500);
await page.screenshot({ path: "shot_hero.png", fullPage: false });
// open case 1 and expand the inspector
await page.locator(".case-row", { hasText: "#1" }).first().click();
await sleep(2500);
await page.locator(".inspector-head").first().click().catch(() => {});
await sleep(1200);
await page.locator(".award-bar").first().scrollIntoViewIfNeeded().catch(() => {});
await sleep(800);
await page.screenshot({ path: "shot_case1_inspector.png", fullPage: false });
await browser.close();
console.log("SHOTS_DONE");
