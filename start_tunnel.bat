@echo off
title Reelwala ngrok Tunnel
cd /d "%~dp0"
echo Starting ngrok tunnel on port 8000...
ngrok http 8000
pause

