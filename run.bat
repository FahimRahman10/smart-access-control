@echo off
title Smart Access Control Server
cd /d "%~dp0"
echo Starting Smart Access Control Server...
".venv\Scripts\python.exe" run.py
pause
