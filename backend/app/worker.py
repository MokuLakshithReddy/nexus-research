from __future__ import annotations

import asyncio
import logging
import signal

from . import db
from .research.providers import run_research
from .services import index_pending_sources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("nexus.worker")


async def process_job(job: dict) -> None:
    job_id = job["id"]
    owner_id = int(job["owner_id"])
    project_id = int(job["project_id"])
    logger.info("starting job=%s project=%s attempt=%s", job_id, project_id, job["attempts"])
    try:
        sources, provider_status = await run_research(job["query"], job.get("providers") or None)
        added = db.add_sources(owner_id, project_id, sources)
        indexed = await index_pending_sources(owner_id, project_id)
        db.finish_research_job(job_id, len(sources), added, provider_status)
        logger.info("completed job=%s discovered=%s added=%s indexed_chunks=%s",
                    job_id, len(sources), added, indexed)
    except Exception as exc:
        logger.exception("research job failed: %s", job_id)
        db.fail_research_job(job_id, f"{type(exc).__name__}: {str(exc)}", retry=True)


async def run_worker(poll_seconds: float = 2.0) -> None:
    recovered = db.recover_stale_jobs()
    if recovered:
        logger.warning("recovered %s stale research jobs", recovered)
    logger.info("Nexus Research worker started")
    while True:
        job = db.claim_next_job()
        if job is None:
            await asyncio.sleep(poll_seconds)
            continue
        await process_job(job)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
