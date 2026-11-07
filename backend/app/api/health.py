from fastapi import APIRouter
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from app.core.schema_readiness import SchemaReadinessError, assert_schema_ready

router = APIRouter()


@router.get("/health")
async def health_check():
    # Liveness only. Readiness must use /ready.
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "beacon-api",
    }


@router.get("/ready")
async def readiness_check():
    try:
        revision = await assert_schema_ready()
    except SchemaReadinessError:
        return JSONResponse(
            status_code=503,
            content={"status": "unready", "reason": "schema_or_database_unavailable"},
        )
    return {"status": "ready", "schema_revision": revision}
