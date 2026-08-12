@echo off
setlocal enabledelayedexpansion
title VORIS
color 0B
cls

:: ── ROOT DIRECTORY (AUTO DETECT) ──────────────────
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║                                              ║
echo  ║        V  O  R  I  S                        ║
echo  ║        Voice-Oriented Responsive             ║
echo  ║        Intelligence System                   ║
echo  ║                                              ║
echo  ╚══════════════════════════════════════════════╝
echo.
echo  Initializing systems...
echo.

:: ── STEP 1: Check Python ──────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo  [CRITICAL] Python not found.
    echo  Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: ── STEP 2: Virtual Environment ───────────────────
if exist "%ROOT%venv\Scripts\activate.bat" (
    call "%ROOT%venv\Scripts\activate.bat"
) else (
    echo  [SETUP] Creating virtual environment...
    python -m venv venv
    call "%ROOT%venv\Scripts\activate.bat"

    echo  [SETUP] Installing dependencies...
    pip install -r requirements.txt -q
)

:: ── STEP 3: .env Check ────────────────────────────
if not exist "%ROOT%.env" (
    echo  [WARNING] .env not found. Creating template...

    echo GROQ_API_KEY=your_key_here > .env
    echo SECRET_KEY=change_this_secret >> .env

    echo.
    echo  Open .env and add your API key.
    notepad .env
    pause
)

:: ── STEP 4: Ensure Folders ────────────────────────
for %%d in (brain agents memory api interface security config voice logs generated) do (
    if not exist "%%d" mkdir "%%d"
)

if not exist "memory\locked" mkdir "memory\locked"

:: ── STEP 5: Free Port 5000 ────────────────────────
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 >nul

:: ── STEP 6: Sync Dependencies ─────────────────────
echo  Checking dependencies...
pip install -r requirements.txt -q 2>nul

:: ── STEP 7: Launch VORIS ───────────────────────────
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║  VORIS is starting...                         ║
echo  ║  Opening browser shortly...                  ║
echo  ║                                              ║
echo  ║  http://localhost:5000                       ║
echo  ╚══════════════════════════════════════════════╝
echo.

:: Open browser (background)
start "" cmd /c "timeout /t 3 >nul && start http://localhost:5000"

:: Start backend
python run_aura.py

:: ── Crash Handling ────────────────────────────────
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║  VORIS stopped unexpectedly.                  ║
echo  ║  Check logs above.                           ║
echo  ╚══════════════════════════════════════════════╝
echo.
pause