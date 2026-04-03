@echo off
REM ============================================================
REM Start Frontend for Packing List Extractor
REM ============================================================

echo.
echo ============================================================
echo   Starting Packing List Extraction Frontend
echo   App: http://localhost:5173
echo ============================================================
echo.
echo [IMPORTANT] Make sure the backend is running on port 8080!
echo Run start_backend.bat first (in backend folder)
echo.

cd /d "%~dp0"

REM Check if Node.js is available
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed or not in PATH
    echo Please install Node.js 18+ and try again
    pause
    exit /b 1
)

REM Check if node_modules exists
if not exist "node_modules" (
    echo Installing npm dependencies...
    echo This may take a few minutes on first run
    echo.
    npm install
    echo.
)

REM Start the dev server
echo Starting Vite dev server...
echo.
echo Press Ctrl+C to stop the server
echo.

npm run dev

pause
