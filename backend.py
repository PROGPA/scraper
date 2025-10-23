#!/usr/bin/env python3
"""
Backend.py (Railway-Optimized Version)
-------------------------------------
This version is safe for Railway deployment:
✅ Global FastAPI app (for Uvicorn)
✅ Argparse moved under __main__
✅ Frontend serving from root
✅ Logging setup safe for container use
"""

import argparse
import asyncio
import logging
import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

# ============================================================
# GLOBAL FASTAPI APP (Required by Railway)
# ============================================================
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve frontend.html"""
    if os.path.exists("frontend.html"):
        with open("frontend.html", "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h2>Frontend not found. Upload frontend.html.</h2>")

@app.get("/health")
async def health_check():
    return {"status": "OK", "message": "Backend running on Railway"}


# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ============================================================
# MAIN SCRAPER / CLI ENTRYPOINT (Safe for Railway)
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Email Scraper Backend")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    logging.info("Starting backend (Railway-safe mode)...")
    logging.info(f"Running on {args.host}:{args.port}")

    # Example async background process (placeholder)
    async def run_scraper():
        while True:
            await asyncio.sleep(10)
            logging.info("Scraper heartbeat...")

    loop = asyncio.get_event_loop()
    loop.create_task(run_scraper())

    import uvicorn
    uvicorn.run("backend:app", host=args.host, port=args.port, reload=False)


# ============================================================
# ENTRY POINT (Protects against Uvicorn import crashes)
# ============================================================
if __name__ == "__main__":
    main()
