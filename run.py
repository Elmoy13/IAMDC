"""
Development launcher — sets WindowsProactorEventLoopPolicy BEFORE uvicorn
creates its event loop, so Playwright (which needs subprocess support) works.

Usage:
    python run.py

NOTE: reload=False because uvicorn's reload mode spawns a SEPARATE worker
subprocess that won't inherit our event loop policy, causing Playwright to fail.
For hot-reload, restart the server manually after code changes.
"""
import asyncio
import sys

# Must be set before uvicorn imports or creates any event loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
