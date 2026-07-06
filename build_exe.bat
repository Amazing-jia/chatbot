@echo off
setlocal

cd /d "%~dp0"

set APP_NAME=Chatbot
set VERSION=0.1.0
set ZIP_NAME=chatbot-windows-v%VERSION%.zip
set PYTHON_EXE=python

if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
)

echo [1/6] Checking Python environment...
%PYTHON_EXE% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed in this Python environment.
    echo Please run:
    echo   pip install pyinstaller
    exit /b 1
)

echo [2/6] Cleaning old build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release

echo [3/6] Building %APP_NAME%.exe...
%PYTHON_EXE% -m PyInstaller --clean --noconfirm chatbot.spec
if errorlevel 1 (
    echo PyInstaller build failed.
    exit /b 1
)

echo [4/6] Creating clean release folder...
mkdir release
mkdir release\prompts

copy /Y dist\%APP_NAME%.exe release\%APP_NAME%.exe >nul
copy /Y config.example.yaml release\config.example.yaml >nul
copy /Y prompts\persona.md release\prompts\persona.md >nul
copy /Y README.md release\README.md >nul
copy /Y README_BUILD.md release\README_BUILD.md >nul
copy /Y LICENSE release\LICENSE >nul

echo [5/6] Creating release zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'release\%APP_NAME%.exe','release\config.example.yaml','release\prompts','release\README.md','release\README_BUILD.md','release\LICENSE' -DestinationPath 'release\%ZIP_NAME%' -Force"
if errorlevel 1 (
    echo Failed to create release zip.
    exit /b 1
)

echo [6/6] Done.
echo.
echo Release exe:
echo   %cd%\release\%APP_NAME%.exe
echo.
echo Release zip:
echo   %cd%\release\%ZIP_NAME%
echo.
echo Before running the exe, make sure Ollama is installed and the model exists:
echo   ollama pull qwen3:8b
echo.
endlocal
