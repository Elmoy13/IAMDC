import asyncio
import sys

# Windows: uvicorn's reloader spawns workers with SelectorEventLoop by default,
# which does NOT support subprocesses (required by Playwright).
# Switching to ProactorEventLoop fixes this.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as v1_router
from app.config import settings
from app.core.logging import setup_logging
from app.db.session import engine
from app.middleware.error_handler import ErrorHandlerMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield
    await engine.dispose()


app = FastAPI(
    title="Chatbot Backend",
    version="1.0.0",
    lifespan=lifespan,
)

_allowed_origins = [
    o.strip() for o in settings.allowed_origins.split(",") if o.strip()
] or ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(ErrorHandlerMiddleware)
app.include_router(v1_router)

# Serve uploaded files (logos, images)
import os
UPLOAD_DIR = "/tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}
