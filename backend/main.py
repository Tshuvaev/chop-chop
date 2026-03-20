from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import router
from backend.utils.cleanup import cleanup_storage
from backend.utils.config import (
    ALLOWED_ORIGINS,
    CLEANUP_INTERVAL_SECONDS,
    CLEANUP_TTL_MINUTES,
    ensure_directories,
)


async def _cleanup_worker() -> None:
    while True:
        await asyncio.to_thread(cleanup_storage, CLEANUP_TTL_MINUTES)
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_directories()
    worker = asyncio.create_task(_cleanup_worker())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(
    title="Slicer API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
