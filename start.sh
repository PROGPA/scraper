#!/bin/bash
echo "Installing Playwright browsers..."
playwright install --with-deps chromium || true

echo "Starting backend..."
uvicorn backend:app --host 0.0.0.0 --port $PORT

