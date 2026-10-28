@echo off
REM Start the desktop GUI. Builds rag.exe first if it is missing.
cd /d "%~dp0"
if not exist rag.exe call build.bat
start "" pythonw gui\rag_gui.py
