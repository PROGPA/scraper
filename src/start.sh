#!/bin/bash

echo "======================================"
echo "Email Scraper - Starting on Railway"
echo "======================================"

# Install Playwright browsers if not already installed
if command -v playwright &> /dev/null; then
    echo "Installing Playwright browsers..."
    playwright install chromium || echo "Warning: Playwright install failed, continuing anyway..."
    playwright install-deps chromium || echo "Warning: Playwright deps install failed, continuing anyway..."
fi

echo "Starting backend server..."
python backend.py
