@echo off
REM Start Streamlit Dashboard from Virtual Environment
REM This ensures all dependencies (including AI agent) are available

echo.
echo ===============================================
echo   Canadian Housing Affordability Dashboard
echo ===============================================
echo.
echo Starting from virtual environment...
echo.

REM Activate virtual environment and run streamlit
call .venv\Scripts\activate.bat
streamlit run dashboard.py

pause
