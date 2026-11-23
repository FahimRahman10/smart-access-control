@echo off
title Smart Access Control Test Suite
cd /d "%~dp0"
echo Running ML Pipeline Verification Tests...
".venv\Scripts\python.exe" test_pipeline.py
echo.
echo Running API Server Tests...
".venv\Scripts\python.exe" test_server.py
echo.
pause
