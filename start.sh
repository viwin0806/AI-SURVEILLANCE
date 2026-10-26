#!/usr/bin/env bash
# AI Surveillance Framework — Linux/macOS Launcher
# Usage: bash start.sh

set -e
export PYTHONIOENCODING=utf-8

echo "============================================================"
echo "  AI-Driven Intelligent Surveillance Framework"
echo "  Academic Research Prototype"
echo "============================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[ERROR] Python 3.10+ not found."
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo "[INFO] Using Python: $($PYTHON --version)"
echo ""

# Generate demo videos if missing
echo "[SETUP] Checking demo videos..."
$PYTHON setup_demos.py
echo ""

# Start the app
echo "[START] Launching surveillance dashboard..."
echo "        URL: http://localhost:5000"
echo ""
echo "  Press Ctrl+C to stop the server."
echo ""

$PYTHON app.py
