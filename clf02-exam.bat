@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
  where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
  if exist "%~dp0dist\clf02-exam.exe" (
    "%~dp0dist\clf02-exam.exe"
    goto done
  )
  echo Python 3 was not found. Install it, or run dist\clf02-exam.exe.
  pause
  exit /b 1
)
%PY% "%~dp0scripts\exam_terminal.py"
set "CODE=%ERRORLEVEL%"
echo %CMDCMDLINE% | find /i " /c " >nul
if not errorlevel 1 pause
exit /b %CODE%
:done
echo %CMDCMDLINE% | find /i " /c " >nul
if not errorlevel 1 pause
endlocal
