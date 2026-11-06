@echo off
title Reelwala Server
cd /d "%~dp0"
call .venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
