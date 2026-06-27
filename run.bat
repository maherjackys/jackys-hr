@echo off
title HR Policy Assistant

:: Kill any existing Streamlit / Python processes
taskkill /f /im streamlit.exe >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq streamlit run*" >nul 2>&1

:: Move to this script's directory (always correct, regardless of where you launch from)
cd /d "%~dp0"

:: Clear Python bytecode cache so changes always load fresh
if exist "ui\__pycache__" rd /s /q "ui\__pycache__"
if exist "__pycache__"    rd /s /q "__pycache__"
if exist "core\__pycache__" rd /s /q "core\__pycache__"

echo.
echo  Starting HR Policy Assistant...
echo  Folder: %~dp0
echo.

streamlit run app.py --server.port 8501 --server.headless false

pause
