@echo off
setlocal

set "BUILD_VERSION=%~1"
if not defined BUILD_VERSION (
    for /f "usebackq delims=" %%V in (`python -c "import publish; print(publish.get_current_version())"`) do set "BUILD_VERSION=%%V"
)

echo Building YouTube Downloader Pro v%BUILD_VERSION%...
python publish.py build "%BUILD_VERSION%"
if errorlevel 1 exit /b %errorlevel%

echo Build completed in dist\
endlocal
