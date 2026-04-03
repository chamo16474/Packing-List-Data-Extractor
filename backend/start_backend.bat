@echo off
REM ============================================================
REM Start Backend Server for Packing List Extractor
REM ============================================================

echo.
echo ============================================================
echo   Starting Packing List Extraction Backend
echo   Server: http://localhost:8080
echo   API Docs: http://localhost:8080/docs
echo ============================================================
echo.

cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.10+ and try again
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo Please copy .env.example to .env and add your API keys
    echo.
    echo Creating .env from .env.example...
    copy ".env.example" ".env"
    echo.
    echo [ACTION REQUIRED] Edit .env and add your OPENROUTER_API_KEY
    echo Then run this script again
    pause
    exit /b 1
)

REM Check if OPENROUTER_API_KEY is set
findstr /C:"OPENROUTER_API_KEY=your-openrouter-api-key-here" ".env" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo [WARNING] OPENROUTER_API_KEY is not configured!
    echo Please edit .env and add your actual API key
    echo Get your key from: https://openrouter.ai/keys
    echo.
    pause
)

REM Install dependencies if needed
if not exist "Lib\site-packages" (
    echo Installing Python dependencies...
    pip install -r requirements.txt
    echo.
)

REM Start the server
echo Starting Uvicorn server on port 8080...
echo.
echo Press Ctrl+C to stop the server
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload

pause
