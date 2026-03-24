# trendspy

trendspy is a TikTok trend analysis tool that scrapes trending videos, transcribes their audio, embeds the content semantically, and surfaces insights through a web API.

## What it does

1. **Scrapes** trending TikTok videos using a headless browser
2. **Downloads & transcribes** video audio using Whisper
3. **Embeds & stores** transcripts in a vector database (ChromaDB) for semantic search
4. **Exposes** trend data and search via a Next.js API

## Monorepo structure

```
trendspy/
├── scraper/    # Node.js + TypeScript + Playwright — collects TikTok video metadata & URLs
├── pipeline/   # Python — downloads audio, transcribes with Whisper, stores in ChromaDB
└── api/        # Next.js 15 App Router — serves trend data and semantic search
```

## Getting started

### Scraper
```bash
cd scraper
npm install
npm run dev
```

### Pipeline
```bash
cd pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### API
```bash
cd api
npm install
npm run dev
```

## Environment variables

Each service reads its own `.env` file. See each folder for the expected variables.

## License

MIT
