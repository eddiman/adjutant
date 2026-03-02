#!/usr/bin/env node
/**
 * Adjutant — Playwright screenshot with automatic cookie banner dismissal.
 *
 * Usage:
 *   node playwright_screenshot.mjs <url> <outfile>
 *
 * Strategy:
 *   1. Navigate to the URL
 *   2. Try to dismiss cookie banners by:
 *      a. Scanning all frames (including iframes like CMP tools) for accept buttons
 *      b. Using page.addLocatorHandler() to catch banners that appear late
 *   3. Wait briefly for the page to settle
 *   4. Take a viewport screenshot (1280x900)
 *
 * Cookie accept button labels covered (NO + EN + common):
 *   Norwegian: Godta alle, Aksepter alle, Godkjenn alle, Tillat alle, OK
 *   English:   Accept all, Accept cookies, Allow all, I agree, Got it, Agree
 *   Generic:   Agree & proceed, Continue, I accept
 *
 * Exits 0 on success, 1 on failure.
 * Prints "OK:<outfile>" or "ERROR:<reason>" to stdout.
 */

// Resolve playwright from known locations
let playwright;
const candidatePaths = [
  '/tmp/pwtest/node_modules/playwright',
];
for (const p of candidatePaths) {
  try {
    const { createRequire } = await import('module');
    const req = createRequire(import.meta.url);
    playwright = req(p);
    break;
  } catch (_) {}
}
if (!playwright) {
  console.log('ERROR: playwright module not found. Run: cd /tmp/pwtest && npm install playwright');
  process.exit(1);
}

const { chromium } = playwright;

// --- Args ---
const [,, url, outfile] = process.argv;
if (!url || !outfile) {
  console.log('ERROR: Usage: node playwright_screenshot.mjs <url> <outfile>');
  process.exit(1);
}

// --- Cookie accept labels (broad net, case-insensitive) ---
const ACCEPT_PATTERNS = [
  // Norwegian
  /^godta alle$/i,
  /^aksepter alle$/i,
  /^godkjenn alle$/i,
  /^tillat alle$/i,
  /^godta$/i,
  /^aksepter$/i,
  // English
  /^accept all( cookies)?$/i,
  /^allow all( cookies)?$/i,
  /^i agree$/i,
  /^agree$/i,
  /^got it$/i,
  /^i accept$/i,
  /^ok$/i,
  /^okay$/i,
  /^continue$/i,
  /^agree & proceed$/i,
  /^accept & continue$/i,
];

/**
 * Try to click a cookie accept button in a given frame.
 * Returns true if something was clicked.
 */
async function dismissInFrame(frame) {
  try {
    const buttons = await frame.$$('button');
    for (const btn of buttons) {
      const text = (await btn.innerText().catch(() => '')).trim();
      if (ACCEPT_PATTERNS.some(re => re.test(text))) {
        await btn.click({ timeout: 3000 }).catch(() => {});
        return true;
      }
    }
  } catch (_) {}
  return false;
}

/**
 * Scan all frames on the page and try to dismiss cookie banners.
 * Returns true if anything was clicked.
 */
async function dismissCookieBanners(page) {
  let dismissed = false;
  const frames = page.frames();
  for (const frame of frames) {
    if (await dismissInFrame(frame)) {
      dismissed = true;
    }
  }
  return dismissed;
}

// --- Main ---
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 900 });

  // Register a locator handler that auto-dismisses overlays
  // whenever Playwright is about to perform an action.
  // Uses <body> as the trigger (always visible), with noWaitAfter so it
  // doesn't block on the banner disappearing.
  try {
    await page.addLocatorHandler(
      page.locator('body'),
      async () => { await dismissCookieBanners(page); },
      { noWaitAfter: true }
    );
  } catch (_) {
    // addLocatorHandler not available in older versions — silently skip
  }

  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  } catch (e) {
    console.log(`ERROR: Navigation failed — ${e.message}`);
    await browser.close();
    process.exit(1);
  }

  // Wait for initial render
  await page.waitForTimeout(3000);

  // Actively scan & dismiss banners post-load
  const dismissed = await dismissCookieBanners(page);
  if (dismissed) {
    // Give the page a moment to animate the banner away
    await page.waitForTimeout(1500);
  }

  try {
    await page.screenshot({ path: outfile });
  } catch (e) {
    console.log(`ERROR: Screenshot failed — ${e.message}`);
    await browser.close();
    process.exit(1);
  }

  await browser.close();
  console.log(`OK:${outfile}`);
  process.exit(0);
})();
