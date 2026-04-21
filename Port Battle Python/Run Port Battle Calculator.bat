@echo off
cd /d "%~dp0"

echo Running Port Battle Calculator...
echo.

py "Port Battle Calculator.py"
if errorlevel 1 (
    echo.
    echo [py launcher failed, trying python...]
    python "Port Battle Calculator.py"
)

echo.
echo Press any key to close...
pause >nul
