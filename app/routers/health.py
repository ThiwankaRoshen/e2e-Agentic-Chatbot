from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", status_code=200)
async def health_check() -> dict:
    """Return a simple health status."""
    return {"status": "ok"}
