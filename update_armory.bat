@echo off
rem Double-click to open the updater window; or: update_armory.bat "C:\path\to\DeceasedCraft_CB-x.y.z"
where py >nul 2>nul && (py -3 "%~dp0update_armory.py" %*) || (python "%~dp0update_armory.py" %*)
if not "%~1"=="" pause
