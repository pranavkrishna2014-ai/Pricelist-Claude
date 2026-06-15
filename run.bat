@echo off
echo ============================================
echo   Mattress Price App - Windows Startup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed.
    echo Download Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install Flask if needed
echo Installing/checking dependencies...
pip install flask --quiet

echo.
echo Starting app...
echo Open your browser at: http://localhost:5000
echo For other computers on your network, use this machine's IP address on port 5000
echo.
echo Press Ctrl+C to stop the server.
echo.

python app.py

pause
