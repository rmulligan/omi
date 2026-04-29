#!/usr/bin/env python3
"""Omi → FalkorDB provenance bridge.

Reads new events from the TimescaleDB `events` table (source_type='omi_audio'),
extracts entities/facts using the local LLM, and pushes them to FalkorDB
via Graphiti's add_memory tool.

Run as a cron job or systemd service:
  python3 scripts/omi_provenance_bridge.py --since 1h

Environment:
  TIMESCALE_URL  — PostgreSQL connection string (e.g. "postgresql://postgres@localhost:5432/omi")
  LLM_BASE_URL   — Local LLM proxy URL (e.g. "http://localhost:10601/v1")
  LLM_MODEL      — Model to use for fact extraction (default: magnum-opus:35b)
  LILLY_FALKORDB_URL — FalkorDB HTTP URL for Graphiti (e.g. "http://localhost:6379")
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import asyncpg

LOG = logging.getLogger("omi_provenance_bridge")

# Default config
DEFAULT_DB_URL = os.environ.get(
    "TIMESCALE_URL",
    "postgresql://postgres@localhost:5432/omi",
)

DEFAULT_LLM_URL = os.environ.get(
    "LLM_BASE_URL",
    "http://localhost:10601/v1",
)

DEFAULT_LLM_MODEL = os.environ.get(
    "LLM_MODEL",
    "magnum-opus:35b",
)

FALKORDB_URL = os.environ.get(
    "LILLY_FALKORDB_URL",
    "http://localhost:6379",
)

FALKORDB_FORK = os.environ.get(
    "FALKORDB_FORK",
    "chat",
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bridge Omi events to FalkorDB")
    p.add_argument("--since", default="1h", help="Only process events newer than this (e.g. '1h', '30m', '2026-04-28T10:00:00Z')")
    p.add_argument("--limit", type=int, default=50, help="Max events to process per run")
    p.add_argument("--db-url", default=DEFAULT_DB_URL)
    p.add_argument("--llm-url", default=DEFAULT_LLM_URL)
    p.add_argument("--llm-model", default=DEFAULT_LLM_MODEL)
    p.add_argument("--dry-run", action="store_true", help="Only show what would be extracted")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


async def fetch_events(db_url: str, since: str, limit: int) -> list[dict]:
    """Fetch new events from the events table."""
    conn = await asyncpg.connect(db_url)
    try:
        # Convert ISO timestamp or relative offset
        if since.endswith("Z") or "T" in since:
            # ISO timestamp
            query = """
                SELECT e.id, e.source_type, e.source_id, e.content,
                       e.metadata, e.timestamp
                FROM events e
                WHERE e.timestamp > $1
                ORDER BY e.timestamp ASC
                LIMIT $2
            """
            await conn.execute("SELECT 1")  # Test connection
            rows = await conn.fetch(
                query,
                datetime.fromisoformat(since.replace("Z", "+00:00")),
                limit,
            )
        else:
            # Relative time — calculate from now
            # Parse "1h", "30m", "2d"
            match = __import__("re").search(r"(\d+)([hmd])", since)
            if match:
                val = int(match.group(1))
                unit = match.group(2)
                if unit == "h":
                    delta = timedelta(hours=val)
                elif unit == "m":
                    delta = timedelta(minutes=val)
                else:
                    delta = timedelta(days=val)
                cutoff = datetime.now(timezone.utc) - delta
            else:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

            rows = await conn.fetch(
                """
                SELECT e.id, e.source_type, e.source_id, e.content,
                       e.metadata, e.timestamp
                FROM events e
                WHERE e.timestamp > $1
                ORDER BY e.timestamp ASC
                LIMIT $2
                """,
                cutoff,
                limit,
            )
    finally:
        await conn.close()

    return [
        {
            "id": str(row["id"]),
            "source_type": row["source_type"],
            "source_id": str(row["source_id"]),
            "content": row["content"],
            "metadata": row["metadata"] or {},
            "timestamp": row["timestamp"].isoformat(),
        }
        for row in rows
    ]


def _extract_facts(content: str, llm_url: str, llm_model: str) -> list[dict]:
    """Use LLM to extract entities/facts from event content."""
    prompt = (
        "Extract all important facts, entities, and relationships from the following "
        "conversation transcript. Return a JSON array of objects, each with:\n"
        "  - fact: the extracted fact as a complete sentence\n"
        "  - entities: list of named entities (people, places, organizations)\n"
        "  - confidence: high/medium/low\n"
        "\nOnly include facts you're confident about. Do not include speculative claims.\n\n"
        "TRANSCRIPT:\n"
        f"{content[:2000]}\n\n"
        "Return ONLY the JSON array. No introduction, no explanation."
    )

    try:
        import httpx
        client = httpx.AsyncClient(timeout=120)
        resp = asyncio.run(
            client.post(
                f"{llm_url}/chat/completions",
                json={
                    "model": llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
        )
        if resp.status_code == 200:
            data = resp.json()
            extracted = data["choices"][0]["message"]["content"].strip()
            try:
                facts = json.loads(extracted)
                if isinstance(facts, list):
                    return facts
            except json.JSONDecodeError:
                pass
            return [{"fact": extracted, "entities": [], "confidence": "low"}]
    except Exception as e:
        LOG.warning("LLM extraction failed for event %s: %s", content[:50], e)

    return []


async def push_to_falkordb(facts: list[dict], event_id: str, fork: str) -> None:
    """Push extracted facts to FalkorDB via Graphiti's add_memory tool."""
    import httpx

    async with httpx.AsyncClient(timeout=30) as client:
        # Call Graphiti's add_memory tool
        resp = await client.post(
            f"{FALKORDB_URL}",
            json={
                "type": "add_memory",
                "body": facts[0]["fact"] if facts else "",
                "group_id": fork,
                "source_description": f"omi_provenance_bridge:{event_id}",
            },
        )
        if resp.status_code != 200:
            LOG.warning("FalkorDB push failed: %s", resp.text[:200])


async def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    LOG.info(
        "Provenance bridge: since=%s limit=%s model=%s",
        args.since, args.limit, args.llm_model,
    )

    # Fetch events
    events = await fetch_events(args.db_url, args.since, args.limit)
    LOG.info("Fetched %d events", len(events))

    processed = 0
    for event in events:
        if event["source_type"] != "omi_audio":
            continue

        LOG.info(
            "Processing event %s (source_id=%s)",
            event["id"], event["source_id"],
        )

        # Extract facts
        if not args.dry_run:
            facts = _extract_facts(
                event["content"],
                args.llm_url,
                args.llm_model,
            )
            if facts:
                LOG.info("  → %d facts extracted", len(facts))
                await push_to_falkordb(facts, event["id"], FALKORDB_FORK)
                processed += 1
        else:
            LOG.info("  [DRY RUN] Would extract facts from event %s", event["id"])

    LOG.info("Processed %d events", processed)


if __name__ == "__main__":
    asyncio.run(main())
