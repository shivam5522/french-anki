@echo off
cd /d "%~dp0"
python update_anki.py %*
pause
