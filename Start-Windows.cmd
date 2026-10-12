@echo off
setlocal
cd /d "%~dp0"
where ffmpeg >nul 2>nul
if errorlevel 1 goto need_ffmpeg
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>nul
if errorlevel 1 goto try_python
py -3.12 scripts\run_trial.py --port 8765
goto finished
:try_python
python -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>nul
if errorlevel 1 goto need_python
python scripts\run_trial.py --port 8765
goto finished
:need_python
echo Python 3.12 is required. In PowerShell, install it with:
echo winget install --id Python.Python.3.12 -e
echo Then close this window and launch Start-Windows.cmd again.
goto finished
:need_ffmpeg
echo FFmpeg is required. In PowerShell, install it with:
echo winget install --id Gyan.FFmpeg -e
echo Then close this window and launch Start-Windows.cmd again.
:finished
echo.
echo Keep this window open while the server is running.
echo If an error is shown, save the message instead of ignoring it.
pause
