@echo off
echo ======================================
echo Starting Influencer Matcher...
echo ======================================
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Virtual environment not found
    echo Please run setup.bat first
    pause
    exit /b 1
)

REM Run the app
echo Opening web app at http://localhost:5000
echo Press CTRL+C to stop the server
echo.
python app.py
