@echo off
title AI Surveillance Framework
color 0A
echo.
echo ============================================================
echo   AI-Driven Intelligent Surveillance Framework
echo   Academic Research Prototype
echo ============================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

REM Set UTF-8 encoding to avoid character issues
set PYTHONIOENCODING=utf-8

REM Generate demo videos if not present
echo [SETUP] Checking demo videos...
python setup_demos.py
echo.

REM Start the application
echo [START] Launching surveillance dashboard...
echo         URL: http://localhost:5000
echo.
echo   Press Ctrl+C to stop the server.
echo.
python app.py

pause
