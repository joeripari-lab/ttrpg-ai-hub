@echo off
title Start Local Qwen AI + VS Code (100% Offline)
cd /d "C:\AI_Workspace"

echo ============================================================================
echo   LOCAL QWEN AI FOR VS CODE (RTX 4070 - 100%% OFFLINE)
echo ============================================================================
echo.

set "LMS_EXE=C:\Users\Joe\.lmstudio\bin\lms.exe"
set "CONTINUE_DIR=%USERPROFILE%\.continue"

if not exist "%CONTINUE_DIR%" mkdir "%CONTINUE_DIR%"

echo [1/4] Syncing Continue local model configuration (%CONTINUE_DIR%\config.yaml)...
copy /Y "C:\AI_Workspace\.continue\agents\local-qwen.yaml" "%CONTINUE_DIR%\config.yaml" >nul

if exist "%LMS_EXE%" (
    echo [2/4] Starting LM Studio Local Server on http://127.0.0.1:1235/v1 ...
    "%LMS_EXE%" server start --port 1235
    
    echo [3/4] Loading local model qwen2.5-vl-7b-instruct onto RTX 4070 GPU...
    "%LMS_EXE%" load qwen2.5-vl-7b-instruct --gpu max -c 8192 --identifier qwen2.5-vl-7b-instruct -y
) else (
    echo [!] LM Studio CLI not found at %LMS_EXE%. Please make sure LM Studio Server is running.
)

echo [4/4] Launching Microsoft VS Code in C:\AI_Workspace ...
call code "C:\AI_Workspace"
echo.
echo Done! In VS Code:
echo   - Press Ctrl+L to open the Continue Local AI Chat sidebar.
echo   - Highlight code and press Ctrl+I to edit code inline with Local Qwen.
echo   - Or click the Cline icon in the left sidebar and set API Provider to "LM Studio" (http://127.0.0.1:1235).
timeout /t 5
