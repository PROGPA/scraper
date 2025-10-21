#!/bin/bash

echo "======================================"
echo " Email Scraper - Starting on Railway "
echo "======================================"

# Always install Playwright and dependencies
echo "Installing Playwright browsers and dependencies..."
python -m playwright install --with-deps chromium || echo "Warning: Playwright install failed, continuing anyway..."

# Start FastAPI backend with uvicorn (auto-binds to Railway port)
echo "Starting backend server..."
uvicorn backend:app --host 0.0.0.0 --port ${PORT:-8080}
