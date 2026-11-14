@echo off
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0extract-fsr4.py" %*
) else (
  python "%~dp0extract-fsr4.py" %*
)
pause
