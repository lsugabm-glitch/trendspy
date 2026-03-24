import { chromium } from "playwright-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import * as path from "path";
import * as readline from "readline";

chromium.use(StealthPlugin());

const SESSION_PATH = path.resolve(__dirname, "../../data/storageState.json");

function waitForEnter(prompt: string): Promise<void> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(prompt, () => {
      rl.close();
      resolve();
    });
  });
}

async function login(): Promise<void> {
  console.log("Launching browser (visible)...");
  const browser = await chromium.launch({
    headless: false,
    executablePath: require("playwright").chromium.executablePath(),
    args: ["--start-maximized"],
  });

  const context = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    viewport: null, // use the full window size from --start-maximized
    locale: "en-US",
    timezoneId: "America/New_York",
  });

  const page = await context.newPage();

  console.log("Navigating to TikTok login...");
  await page.goto("https://www.tiktok.com/login", { waitUntil: "domcontentloaded" });

  console.log("");
  console.log("============================================================");
  console.log("  A browser window has opened.");
  console.log("  Log in to TikTok however you prefer (email, Google, etc.).");
  console.log("  Once you can see your For You feed, come back here and");
  console.log("  press ENTER to save the session.");
  console.log("============================================================");
  console.log("");

  await waitForEnter("Press ENTER when you are logged in and can see the feed > ");

  // Verify we actually landed on a logged-in page
  const url = page.url();
  const cookies = await context.cookies();
  const sessionCookie = cookies.find((c) => c.name === "sessionid" || c.name === "sid_tt");

  if (!sessionCookie) {
    console.warn(
      "\nWarning: could not find a TikTok session cookie. " +
        "Make sure you are fully logged in before pressing ENTER.\n" +
        `Current URL: ${url}\n`
    );
  }

  console.log("Saving session...");
  await context.storageState({ path: SESSION_PATH });
  console.log(`Session saved to ${SESSION_PATH}`);

  await browser.close();
  console.log("Done. You can now run the scraper with: npx ts-node src/scraper.ts");
}

login().catch((err) => {
  console.error("Login helper failed:", err);
  process.exit(1);
});
