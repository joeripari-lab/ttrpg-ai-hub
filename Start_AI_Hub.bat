@echo off
title Unified Local AI Hub & Action Agent
cd /d "C:\AI_Workspace"

echo ============================================================================
echo   UNIFIED LOCAL AI HUB ^& MARKETPLACE ACTION AGENT (RTX 4070)
echo ============================================================================
echo.

set "PY_EXE=C:\Python314\python.exe"
if not exist "%PY_EXE%" (
    set "PY_EXE=C:\ComfyUI_windows_portable\python_embeded\python.exe"
)

if not exist "C:\AI_Workspace\venv\Scripts\python.exe" (
    echo [1/3] First-time setup: Creating isolated Python environment in C:\AI_Workspace\venv ...
    "%PY_EXE%" -m venv "C:\AI_Workspace\venv"
)

if exist "C:\AI_Workspace\venv\Scripts\python.exe" (
    set "PY_EXE=C:\AI_Workspace\venv\Scripts\python.exe"
)

if not exist "C:\AI_Workspace\.playwright_ready" (
    echo [2/3] Installing Playwright Browser Automation Engine for Etsy ^& Mayhem Marketplace...
    "%PY_EXE%" -m pip install --upgrade pip playwright
    "%PY_EXE%" -m playwright install chromium
    echo ready > "C:\AI_Workspace\.playwright_ready"
)

echo [3/3] Starting Unified Local AI Hub on http://127.0.0.1:7860 ...
start "" "http://127.0.0.1:7860"
"%PY_EXE%" "C:\AI_Workspace\hub_server.py"
pause
