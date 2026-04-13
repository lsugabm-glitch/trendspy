"""
bot/github_actions.py — Trigger workflow_dispatch dan poll hasilnya
"""

import asyncio
import os
import time

import httpx

OWNER = os.environ.get("GITHUB_OWNER", "lsugabm-glitch")
REPO = os.environ.get("GITHUB_REPO", "trendspy")
WORKFLOW_FILE = "on-demand.yml"
HEADERS = {
    "Authorization": f"Bearer {os.environ.get('GITHUB_TOKEN', '')}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"


async def trigger_workflow(query: str, mode: str, qualifier: str = "",
                           period_days: int = 7, max_videos: int = 200) -> float:
    """Trigger on-demand workflow. Return trigger timestamp."""
    payload = {
        "ref": "main",
        "inputs": {
            "query": query,
            "mode": mode,
            "qualifier": qualifier,
            "period_days": str(period_days),
            "max_videos": str(max_videos),
        },
    }
    trigger_time = time.time()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE}/actions/workflows/{WORKFLOW_FILE}/dispatches",
            headers=HEADERS,
            json=payload,
            timeout=15,
        )
    resp.raise_for_status()
    return trigger_time


async def poll_run(trigger_time: float, timeout: int = 600, interval: int = 15) -> dict | None:
    """Poll until workflow triggered after trigger_time completes. Return run dict or None."""
    deadline = time.time() + timeout
    await asyncio.sleep(8)  # beri waktu Actions mendaftarkan run baru

    while time.time() < deadline:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE}/actions/runs",
                headers=HEADERS,
                params={"event": "workflow_dispatch", "per_page": 5},
                timeout=15,
            )
        runs = resp.json().get("workflow_runs", [])

        for run in runs:
            # Cari run yang dibuat setelah kita trigger
            from datetime import datetime, timezone
            created = datetime.fromisoformat(
                run["created_at"].replace("Z", "+00:00")
            ).timestamp()
            if created >= trigger_time - 5:
                if run["status"] == "completed":
                    return run
                elif run["status"] in ("in_progress", "queued", "waiting"):
                    break  # masih jalan, tunggu lagi

        await asyncio.sleep(interval)

    return None  # timeout


async def fetch_latest_report(prefix: str = "reports/") -> str | None:
    """Fetch isi file laporan terbaru dari folder reports/."""
    async with httpx.AsyncClient() as client:
        # List isi folder reports/
        resp = await client.get(
            f"{BASE}/contents/reports",
            headers=HEADERS,
            timeout=15,
        )
    if resp.status_code != 200:
        return None

    files = resp.json()
    if not isinstance(files, list):
        return None

    # Sort descending by name (nama file include timestamp)
    md_files = sorted(
        [f for f in files if f["name"].endswith(".md")],
        key=lambda f: f["name"],
        reverse=True,
    )
    if not md_files:
        return None

    latest = md_files[0]

    async with httpx.AsyncClient() as client:
        resp = await client.get(latest["download_url"], headers=HEADERS, timeout=15)

    return resp.text if resp.status_code == 200 else None
