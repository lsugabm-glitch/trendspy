# trendspy — architecture guide for Claude

## Overview

trendspy is a monorepo with three independent services that form a data pipeline:

```
TikTok → scraper → pipeline → ChromaDB → api → client
```

## Folder structure

```
trendspy/
├── scraper/          # Node.js 20+, TypeScript, Playwright
│   ├── src/          # Source files
│   ├── package.json
│   └── tsconfig.json
│
├── pipeline/         # Python 3.11+
│   ├── requirements.txt   # openai-whisper, chromadb, openai, yt-dlp
│   └── (source files go here)
│
├── api/              # Next.js 15, App Router, TypeScript
│   ├── app/          # App Router pages and API routes
│   ├── package.json
│   └── (standard Next.js structure)
│
├── CLAUDE.md         # This file
├── README.md
└── .gitignore
```

## Service responsibilities

### `/scraper`
- Uses **Playwright** to open TikTok and collect trending video metadata (URLs, titles, view counts, hashtags)
- Outputs structured JSON for the pipeline to consume
- Runtime: Node.js, language: TypeScript

### `/pipeline`
- Receives video URLs from the scraper output
- Downloads audio via **yt-dlp**
- Transcribes audio with **openai-whisper**
- Optionally summarises or tags content with the **OpenAI** API
- Stores embeddings and metadata in **ChromaDB**
- Runtime: Python, no web server — runs as a batch job or daemon

### `/api`
- **Next.js 15 App Router** — all routes live under `app/api/`
- Queries ChromaDB for trend data and semantic search
- Exposes REST (or Route Handler) endpoints consumed by a frontend or external clients
- Runtime: Node.js, language: TypeScript

## Data flow

1. `scraper` writes a list of trending video URLs + metadata to a shared store (file, queue, or database — TBD)
2. `pipeline` picks up new URLs, downloads, transcribes, embeds, and upserts into ChromaDB
3. `api` queries ChromaDB and returns results over HTTP

## Key conventions

- Each service manages its own dependencies; do not mix package managers across services
- Secrets go in each service's `.env` file — never committed
- Python virtual environment lives at `pipeline/.venv/` — ignored by git
- The `api` build output (`.next/`) is ignored by git
