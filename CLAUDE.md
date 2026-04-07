# trendspy — architecture guide

## Purpose

Internal TikTok intelligence tool for a content team. Scrapes TikTok via
the Apify API, computes engagement metrics in Python, generates strategic
insights with the Claude API, and publishes a dark-themed HTML report to
GitHub Pages — fully automated via GitHub Actions.

## Repository layout

```
trendspy/
├── .github/
│   └── workflows/
│       ├── scheduled.yml    # Runs every Monday 01:00 UTC (08:00 WIB)
│       └── on-demand.yml    # Manually triggered with custom query/mode
│
├── config/
│   └── keywords.json        # Keywords, hashtags, profiles to track
│
├── src/
│   ├── scrape.py            # Step 1 — fetch raw data from Apify
│   ├── analyze.py           # Step 2 — compute metrics & aggregates
│   ├── insights.py          # Step 3 — call Claude API for AI insights
│   └── report.py            # Step 4 — render HTML report
│
├── docs/
│   └── index.html           # GitHub Pages output (auto-committed by CI)
│
├── data/                    # Ephemeral — gitignored, created by CI
│   ├── raw_*.json
│   ├── combined_*.json
│   ├── analyzed_*.json
│   └── insights_*.json
│
├── requirements.txt
├── .env.example
└── CLAUDE.md
```

## Data flow

```
Apify (TikTok)
    ↓  scrape.py  →  data/combined_*.json
    ↓  analyze.py →  data/analyzed_*.json
    ↓  insights.py → data/insights_*.json  (Claude Sonnet)
    ↓  report.py  →  docs/index.html
    ↓  git push   →  GitHub Pages
```

## Pipeline steps

### 1. `src/scrape.py`
- Reads `config/keywords.json` for keywords, hashtags, and profiles.
- Calls the Apify actor `clockworks/tiktok-scraper` once per query.
- Saves individual `raw_<type>_<query>_<ts>.json` files.
- Deduplicates by video ID and writes `combined_<ts>.json`.
- Env var required: `APIFY_API_TOKEN`
- CLI override: `python src/scrape.py --query "#gymtok" --mode hashtag --period_days 14 --max_videos 300`

### 2. `src/analyze.py`
- Reads the latest `combined_*.json`.
- Computes per-video: engagement rate, engagement velocity, performance tier.
- Aggregates: top 10 by views/velocity/engagement, top creators, keyword scores, trending hashtags.
- Writes `analyzed_<ts>.json`.

### 3. `src/insights.py`
- Reads the latest `analyzed_*.json`.
- Builds a detailed prompt including all metrics and top captions.
- Calls `claude-sonnet-4-6` via the Anthropic Python SDK.
- The model returns a 7-section strategic report (executive summary, opportunities, hook patterns, creator insights, niche ROI, content angles, what to avoid).
- Writes `insights_<ts>.json`.
- Env var required: `ANTHROPIC_API_KEY`

### 4. `src/report.py`
- Reads the latest `analyzed_*.json` and `insights_*.json`.
- Renders a self-contained dark-themed HTML page.
- Writes `docs/index.html`.

## GitHub Actions

### Secrets required (Settings → Secrets → Actions)
| Secret | Description |
|--------|-------------|
| `APIFY_API_TOKEN` | Apify personal API token |
| `ANTHROPIC_API_KEY` | Anthropic API key |

### GitHub Pages setup
1. Go to **Settings → Pages**.
2. Set **Source** to `Deploy from a branch`.
3. Set **Branch** to `main` and folder to `/docs`.
4. The report URL will be `https://<org>.github.io/<repo>/`.

## Adding keywords

Edit `config/keywords.json`:

```json
{
  "keywords": ["skincare routine", "gym supplement", "new keyword here"],
  "hashtags": ["#skincareroutine", "#newtag"],
  "profiles": ["@someprofile"],
  "max_videos_per_keyword": 300,
  "period_days": 7
}
```

Commit and push — the next scheduled run picks it up automatically.
You can also trigger an immediate run via the on-demand workflow.

## Running locally

```bash
cp .env.example .env
# Fill in APIFY_API_TOKEN and ANTHROPIC_API_KEY

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/scrape.py
python src/analyze.py
python src/insights.py
python src/report.py
open docs/index.html
```

## On-demand research

Use the **On-Demand TikTok Research** workflow in GitHub Actions:
- **query**: any keyword, `#hashtag`, or `@profile`
- **mode**: `keyword` / `hashtag` / `profile`
- **period_days**: `7` / `14` / `30`
- **max_videos**: `100` / `200` / `300` / `500`

The resulting report overwrites `docs/index.html` and is live within seconds.
