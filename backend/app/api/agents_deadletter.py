"""Dead-letter queue inspection for retention jobs."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query

from app.core.auth import AuthContext, require_min_role
from app.core.config import get_settings
from app.services.retention_queue import get_job, redis_client
from app.api.agents_common import router


@router.get("/agents/retention/dead-letter")
async def list_retention_dead_letters(
    limit: int = Query(50, ge=1, le=500),
    auth: AuthContext = Depends(require_min_role("coordinator")),
):
    redis = redis_client()
    try:
        job_ids = await redis.lrange(get_settings().retention_dead_letter_queue_name, -limit, -1)
        jobs = []
        for job_id in reversed(job_ids):
            job = await get_job(job_id, tenant_id=auth.tenant_id, redis=redis)
            if job:
                jobs.append(job)
        return {"count": len(jobs), "jobs": jobs}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Fila dead-letter indisponível") from exc
    finally:
        await redis.aclose()
