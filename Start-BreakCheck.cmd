@echo off
setlocal EnableExtensions DisableDelayedExpansion
title BreakCheck
pushd "%~dp0" || exit /b 1
if not exist "breakcheck\__main__.py" goto missing
set "CHECK_ONLY=0"
if /i "%~1"=="--check" set "CHECK_ONLY=1"
set "INSTALL_TRIED=0"

:detect
set "PY_EXE=py.exe"
set "PY_ARGS=-3"
where py.exe >nul 2>&1
if not errorlevel 1 (
    call :probe
    if not errorlevel 1 goto launch
)
set "PY_ARGS="
for %%V in (314 313 312 311 310) do (
    if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
        set "PY_EXE=%LocalAppData%\Programs\Python\Python%%V\python.exe"
        call :probe
        if not errorlevel 1 goto launch
    )
)
for /f "delims=" %%P in ('where python.exe 2^>nul') do (
    if /i not "%%P"=="%LocalAppData%\Microsoft\WindowsApps\python.exe" (
        set "PY_EXE=%%P"
        call :probe
        if not errorlevel 1 goto launch
    )
)
if "%CHECK_ONLY%"=="1" goto fail
if "%INSTALL_TRIED%"=="1" goto manual
echo.
echo BreakCheck needs Python 3.10 or newer with Tk for this source launcher.
echo The standalone Windows installer does not require Python.
echo.
echo [D] Open BreakCheck downloads (recommended)
echo [I] Install Python 3.12 using Windows Package Manager, then start BreakCheck
echo [Q] Quit
choice /c DIQ /n /m "Choose an option: "
if errorlevel 3 goto done
if errorlevel 2 goto install
if errorlevel 1 goto downloads
goto done

:install
where winget.exe >nul 2>&1
if errorlevel 1 goto manual
echo Installing the official Python 3.12 package for your user account...
winget install --id Python.Python.3.12 --exact --source winget --scope user
if errorlevel 1 goto manual
set "INSTALL_TRIED=1"
goto detect

:downloads
start "" "https://github.com/PCTestAdmin/BreakCheck/releases/latest"
goto done

:manual
echo Python installation or detection did not succeed.
echo Install Python with Tk from the official website and double-click this file again.
start "" "https://www.python.org/downloads/windows/"
pause
goto fail

:launch
if "%CHECK_ONLY%"=="1" (
    "%PY_EXE%" %PY_ARGS% -m breakcheck --version
    if errorlevel 1 goto fail
    goto done
)
echo Starting BreakCheck...
"%PY_EXE%" %PY_ARGS% -m breakcheck gui
if errorlevel 1 (
    echo BreakCheck could not start. See the error above.
    pause
    goto fail
)
goto done

:probe
"%PY_EXE%" %PY_ARGS% -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
exit /b %errorlevel%

:missing
echo Please extract the entire BreakCheck ZIP before running this file.
pause
goto fail

:done
popd
exit /b 0

:fail
popd
exit /b 1
