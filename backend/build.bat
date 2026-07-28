@echo off
REM BiliNote backend sidecar build (ASCII-only for Chinese Windows cmd CP936)
REM Called from repo root context: cd to parent of backend\
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0.."
echo CWD=%CD%

echo [clean] removing old build dirs...
if exist backend\dist rmdir /s /q backend\dist
if exist backend\build rmdir /s /q backend\build
if exist BillNote_frontend\src-tauri\bin rmdir /s /q BillNote_frontend\src-tauri\bin
echo [clean] done.

mkdir BillNote_frontend\src-tauri\bin 2>nul

set "TARGET_TRIPLE="
for /f "tokens=2 delims=:" %%A in ('rustc -Vv 2^>nul ^| findstr /i "host"') do set "TARGET_TRIPLE=%%A"
set "TARGET_TRIPLE=%TARGET_TRIPLE: =%"
if "%TARGET_TRIPLE%"=="" (
  echo [ERROR] cannot detect rustc host triple. Is rustc installed?
  exit /b 1
)
echo Detected target triple: %TARGET_TRIPLE%

echo [env] copy .env.example to backend\.env for PyInstaller data...
copy /Y .env.example backend\.env
if errorlevel 1 (
  echo [ERROR] failed to copy .env.example
  exit /b 1
)

echo [pyinstaller] building BiliNoteBackend...
pyinstaller ^
  -y ^
  --name BiliNoteBackend ^
  --paths backend ^
  --distpath BillNote_frontend\src-tauri\bin ^
  --workpath backend\build ^
  --specpath backend ^
  --hidden-import uvicorn ^
  --hidden-import fastapi ^
  --hidden-import starlette ^
  --add-data "app\db\builtin_providers.json;." ^
  --add-data ".env;." ^
  backend\main.py

if errorlevel 1 (
  echo [ERROR] pyinstaller failed
  if exist backend\.env del /f /q backend\.env
  exit /b 1
)

echo [env] remove temporary backend\.env
if exist backend\.env del /f /q backend\.env

set "SRC_EXE=BillNote_frontend\src-tauri\bin\BiliNoteBackend\BiliNoteBackend.exe"
set "DST_EXE=BillNote_frontend\src-tauri\bin\BiliNoteBackend\BiliNoteBackend-%TARGET_TRIPLE%.exe"
if not exist "%SRC_EXE%" (
  echo [ERROR] expected exe not found: %SRC_EXE%
  exit /b 1
)
move /Y "%SRC_EXE%" "%DST_EXE%"
if errorlevel 1 (
  echo [ERROR] failed to rename sidecar exe
  exit /b 1
)

echo [ok] PyInstaller sidecar ready:
dir BillNote_frontend\src-tauri\bin\BiliNoteBackend
echo Check that .env exists under the BiliNoteBackend folder as a FILE.
endlocal
exit /b 0
