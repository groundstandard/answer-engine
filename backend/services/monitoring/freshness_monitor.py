"""Background freshness monitor (PRD Section 12: real-time freshness monitoring).

Periodically scans every tenant's sources for stale or empty evidence and records
a FRESHNESS_SCAN entry in the immutable audit log listing what needs refreshing.
This is the *monitoring* half of the PRD item — it detects and reports staleness so
operators (or the /admin/freshness surface) can act.

Note on AUTO re-index: actually re-fetching source content requires a per-source
fetcher/parser. Ingestion here is push-based (content is POSTed to
/v1/documents/index), so the monitor flags stale sources for re-indexing rather
than silently re-fetching content it has no fetcher for. Re-indexing a flagged
source is done by POSTing fresh content to /v1/documents/index.

Gated by settings.ENABLE_FRESHNESS_MONITOR so it is inert unless turned on.
"""

import asyncio
import logging

from sqlalchemy import text

from backend.config.settings import settings
from backend.database.connection import AsyncSessionLocal
from backend.database.repositories.audit_repo import AuditRepository

logger = logging.getLogger(__name__)

_SCAN_SQL = """
    SELECT s.tenant_id AS tenant_id, s.id AS source_id, s.name AS source_name,
           COUNT(e.id) AS chunks,
           EXTRACT(EPOCH FROM (NOW() - MAX(e.created_at))) / 86400 AS age_days
    FROM sources s
    LEFT JOIN evidence_items e ON e.source_id = s.id
    GROUP BY s.tenant_id, s.id, s.name
"""


async def scan_stale_sources() -> int:
    """Run one freshness scan; record a FRESHNESS_SCAN audit row per tenant with
    stale sources. Returns the number of stale sources found."""
    stale_by_tenant: dict = {}
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text(_SCAN_SQL))).fetchall()
        for r in rows:
            age = float(r.age_days) if r.age_days is not None else None
            is_stale = (r.chunks == 0) or (age is not None and age > settings.FRESHNESS_STALE_DAYS)
            if not is_stale:
                continue
            stale_by_tenant.setdefault(str(r.tenant_id), []).append({
                "source_id": str(r.source_id),
                "source_name": r.source_name,
                "chunks": int(r.chunks or 0),
                "age_days": round(age, 2) if age is not None else None,
                "recommended_action": "reindex",
            })

        audit = AuditRepository(session)
        total = 0
        for tenant_id, stale in stale_by_tenant.items():
            total += len(stale)
            await audit.write(
                event_type="FRESHNESS_SCAN",
                tenant_id=tenant_id,
                detail={"stale_count": len(stale), "stale_sources": stale,
                        "stale_days_threshold": settings.FRESHNESS_STALE_DAYS},
            )
    logger.info("Freshness scan complete: %d stale source(s) across %d tenant(s)",
                total, len(stale_by_tenant))
    return total


async def freshness_monitor_loop() -> None:
    """Long-running loop; sleeps FRESHNESS_CHECK_INTERVAL_MIN between scans."""
    interval = max(1, settings.FRESHNESS_CHECK_INTERVAL_MIN) * 60
    logger.info("Freshness monitor started (every %d min)", settings.FRESHNESS_CHECK_INTERVAL_MIN)
    while True:
        try:
            await scan_stale_sources()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — a scan failure must not kill the loop
            logger.warning("Freshness scan failed: %s", e)
        await asyncio.sleep(interval)
