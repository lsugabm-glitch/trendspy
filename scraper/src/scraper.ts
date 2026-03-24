import { chromium } from "playwright";
import * as fs from "fs";
import * as path from "path";

const TARGET_URL = "https://www.tiktok.com/tag/skincare";
const OUTPUT_PATH = path.resolve(__dirname, "../../data/videos.json");
const SCROLL_TIMES = 5;
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

interface VideoData {
  url: string;
  caption: string;
  viewCount: string;
  username: string;
  hashtags: string[];
}

function randomDelay(minMs: number, maxMs: number): Promise<void> {
  const ms = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
  console.log(`  Waiting ${ms}ms...`);
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractHashtags(text: string): string[] {
  const matches = text.match(/#[\w\u00C0-\u024F\u4e00-\u9fff]+/g);
  return matches ? [...new Set(matches)] : [];
}

async function scrape(): Promise<void> {
  console.log("Launching Chromium...");
  const browser = await chromium.launch({ headless: true });

  const context = await browser.newContext({
    userAgent: USER_AGENT,
    viewport: { width: 1280, height: 900 },
    locale: "en-US",
    timezoneId: "America/New_York",
  });

  const page = await context.newPage();

  // Block images and fonts to speed up loading
  await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", (route) =>
    route.abort()
  );

  console.log(`Navigating to ${TARGET_URL}`);
  await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 30000 });

  // Wait for the video grid to appear
  console.log("Waiting for video grid to load...");
  await page.waitForSelector('[data-e2e="challenge-item"]', { timeout: 15000 }).catch(() => {
    console.log("  Selector [data-e2e=challenge-item] not found — will try after scrolling.");
  });

  // Scroll to load more videos
  for (let i = 1; i <= SCROLL_TIMES; i++) {
    console.log(`Scroll ${i}/${SCROLL_TIMES}...`);
    await page.evaluate(() => window.scrollBy({ top: 1200, behavior: "smooth" }));
    await randomDelay(1000, 3000);
  }

  console.log("Extracting video data...");

  const videos: VideoData[] = await page.evaluate(() => {
    const results: VideoData[] = [];

    // TikTok renders video cards under several possible selectors — try them all
    const cardSelectors = [
      '[data-e2e="challenge-item"]',
      '[class*="DivItemContainer"]',
      'div[class*="video-feed-item"]',
    ];

    let cards: Element[] = [];
    for (const sel of cardSelectors) {
      const found = Array.from(document.querySelectorAll(sel));
      if (found.length > 0) {
        cards = found;
        break;
      }
    }

    for (const card of cards) {
      // --- URL ---
      const linkEl = card.querySelector("a[href*='/video/']") as HTMLAnchorElement | null;
      const url = linkEl ? linkEl.href : "";

      // --- Username ---
      const usernameEl =
        card.querySelector('[data-e2e="challenge-item-username"]') ??
        card.querySelector("a[href^='/@']") ??
        card.querySelector('[class*="AuthorTitle"]');
      const username = usernameEl?.textContent?.trim() ?? "";

      // --- Caption ---
      const captionEl =
        card.querySelector('[data-e2e="video-desc"]') ??
        card.querySelector('[class*="video-meta-caption"]') ??
        card.querySelector('[class*="DivDescription"]');
      const caption = captionEl?.textContent?.trim() ?? "";

      // --- View count ---
      const viewEl =
        card.querySelector('[data-e2e="video-views"]') ??
        card.querySelector('[class*="video-count"]') ??
        card.querySelector('[class*="SpanViews"]');
      const viewCount = viewEl?.textContent?.trim() ?? "";

      // --- Hashtags from caption ---
      const hashtagMatches = caption.match(/#[\w\u00C0-\u024F\u4e00-\u9fff]+/g);
      const hashtags = hashtagMatches ? [...new Set(hashtagMatches)] : [];

      if (url) {
        results.push({ url, caption, viewCount, username, hashtags });
      }
    }

    return results;
  });

  console.log(`Found ${videos.length} video(s).`);

  if (videos.length > 0) {
    videos.forEach((v, i) => {
      console.log(`  [${i + 1}] ${v.username || "(unknown)"} — ${v.viewCount || "? views"} — ${v.url}`);
    });
  } else {
    console.warn(
      "No videos extracted. TikTok may have changed its markup or blocked the request.\n" +
        "Try running with headless: false to debug."
    );
  }

  // Ensure output directory exists
  const outDir = path.dirname(OUTPUT_PATH);
  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  fs.writeFileSync(OUTPUT_PATH, JSON.stringify(videos, null, 2), "utf-8");
  console.log(`Results saved to ${OUTPUT_PATH}`);

  await browser.close();
  console.log("Browser closed. Done.");
}

scrape().catch((err) => {
  console.error("Scraper failed:", err);
  process.exit(1);
});
