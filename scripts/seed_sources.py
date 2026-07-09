#!/usr/bin/env python3
"""
Seed initial document sources and index sample content.
Usage: python scripts/seed_sources.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from uuid import uuid4
from backend.services.indexing.indexer import DocumentIndexingService


SAMPLE_SOURCES = [
    {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "name": "Sample Technical Documentation",
        "content": (
            "The Evidence-Gated AI System (EGAS) is a reliability gateway that sits between "
            "user queries and LLM responses. It enforces four pipeline gates: retrieval, "
            "claim extraction, NLI verification, and policy decision. "
            "The system supports three response states: VERIFIED, QUALIFIED, and REFUSED."
        ),
        "trust_tier": 2,
    }
]


async def main():
    indexer = DocumentIndexingService()
    for source in SAMPLE_SOURCES:
        result = await indexer.index_document(
            content=source["content"],
            source_id=source["id"],
            tenant_id=source["tenant_id"],
            metadata={"source_name": source["name"], "trust_tier": source["trust_tier"]},
        )
        print(f"Source '{source['name']}': {result}")


if __name__ == "__main__":
    asyncio.run(main())
