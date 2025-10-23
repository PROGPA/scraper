#!/bin/bash
echo "======================================"
echo "Starting Railway Email Scraper Backend"
echo "======================================"

echo "Installing Playwright dependencies..."
playwright install chromium --with-deps || echo "Playwright install skipped"

echo "Launching backend..."
python backend.py
