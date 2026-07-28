@echo off
REM BiliNote Windows one-click build (ASCII-only for cmd.exe CP936 safety)
REM Usage:
REM   publish.bat
REM   publish.bat 2.5.0
REM   publish.bat 2.5.0 --release
REM Prefer: powershell -ExecutionPolicy Bypass -File publish.ps1

setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%CD%"
set "FRONTEND=%ROOT%\BillNote_frontend"
set "OUT_DIR=%ROOT%\release-artifacts"
set "VERSION_ARG=%~1"
set "DO_RELEASE=0"

if /I "%~2"=="--release" set "DO_RELEASE=1"
if /I "%~1"=="--release" (
  set "DO_RELEASE=1"
  set "VERSION_ARG="
)

echo.
echo ============================================================
echo  BiliNote Windows build
echo  ROOT=%ROOT%
echo ============================================================
echo.

REM ---- [0/5] toolchain ----
echo [0/5] Checking tools...

where rustc >nul 2>&1
if errorlevel 1 (
  echo [ERROR] rustc not found. Install: https://rustup.rs/
  exit /b 1
)
set "TARGET_TRIPLE="
for /f "tokens=2 delims=:" %%A in ('rustc -Vv 2^>nul ^| findstr /i "host"') do set "TARGET_TRIPLE=%%A"
set "TARGET_TRIPLE=%TARGET_TRIPLE: =%"
if "%TARGET_TRIPLE%"=="" (
  echo [ERROR] cannot detect rustc host triple
  exit /b 1
)
echo       rustc OK  target=%TARGET_TRIPLE%

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] node not found. Install Node 20+.
  exit /b 1
)
for /f "delims=" %%V in ('node -v') do echo       node %%V

where pnpm >nul 2>&1
if errorlevel 1 (
  echo       pnpm missing, trying corepack...
  where corepack >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] no pnpm and no corepack. Run: npm install -g pnpm@9.15.0
    exit /b 1
  )
  call corepack enable
  call corepack prepare pnpm@9.15.0 --activate
  where pnpm >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] corepack failed to enable pnpm. Run: npm install -g pnpm@9.15.0
    exit /b 1
  )
)
for /f "delims=" %%V in ('pnpm -v') do echo       pnpm %%V

set "PYTHON_EXE="
where python >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%P in ('where python') do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
  )
)
if not defined PYTHON_EXE if exist "D:\ProgramData\miniconda3\python.exe" set "PYTHON_EXE=D:\ProgramData\miniconda3\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYTHON_EXE (
  echo [ERROR] python not found. Install Python 3.11 and add to PATH.
  exit /b 1
)
echo       python: %PYTHON_EXE%

where pyinstaller >nul 2>&1
if errorlevel 1 (
  echo       pyinstaller missing, installing via pip...
  "%PYTHON_EXE%" -m pip install -q pyinstaller
)
echo.

REM ---- [1/5] version ----
if not "%VERSION_ARG%"=="" (
  echo [1/5] Set tauri version to %VERSION_ARG%
  pushd "%FRONTEND%"
  node -e "const fs=require('fs');const f='src-tauri/tauri.conf.json';const j=JSON.parse(fs.readFileSync(f,'utf8'));j.version=process.argv[1];fs.writeFileSync(f,JSON.stringify(j,null,2)+'\n');console.log('version =',j.version);" "%VERSION_ARG%"
  if errorlevel 1 (
    echo [ERROR] failed to write version
    popd
    exit /b 1
  )
  popd
) else (
  echo [1/5] Keep existing tauri.conf.json version
  pushd "%FRONTEND%"
  node -e "console.log('      version =', require('./src-tauri/tauri.conf.json').version)"
  popd
)
echo.

REM ---- [2/5] backend sidecar ----
echo [2/5] Building backend sidecar via backend\build.bat ...
call "%ROOT%\backend\build.bat"
if errorlevel 1 (
  echo [ERROR] backend\build.bat failed
  exit /b 1
)

set "SIDECAR_DIR=%FRONTEND%\src-tauri\bin\BiliNoteBackend"
set "SIDECAR_EXE=%SIDECAR_DIR%\BiliNoteBackend-%TARGET_TRIPLE%.exe"
if not exist "%SIDECAR_EXE%" (
  echo [ERROR] sidecar not found: %SIDECAR_EXE%
  if exist "%SIDECAR_DIR%" dir /b "%SIDECAR_DIR%"
  exit /b 1
)
echo       sidecar OK: BiliNoteBackend-%TARGET_TRIPLE%.exe
echo.

REM ---- [3/5] frontend deps ----
echo [3/5] Frontend dependencies...
pushd "%FRONTEND%"
if not exist "node_modules\" (
  call pnpm install
  if errorlevel 1 (
    echo [ERROR] pnpm install failed
    popd
    exit /b 1
  )
) else (
  echo       node_modules exists, skip install
)

call pnpm exec tauri --version >nul 2>&1
if errorlevel 1 (
  echo       installing @tauri-apps/cli@2 ...
  call pnpm add -D @tauri-apps/cli@2
  if errorlevel 1 (
    echo [ERROR] failed to install tauri CLI
    popd
    exit /b 1
  )
)
echo.

REM ---- [4/5] tauri build ----
echo [4/5] pnpm tauri build  (first Rust build may take 10-30 min)...
call pnpm tauri build
if errorlevel 1 (
  echo [ERROR] tauri build failed
  popd
  exit /b 1
)
popd
echo.

REM ---- [5/5] collect artifacts ----
echo [5/5] Collecting installers to release-artifacts\
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
mkdir "%OUT_DIR%" 2>nul

set "BUNDLE=%FRONTEND%\src-tauri\target\release\bundle"
set "FOUND=0"

if exist "%BUNDLE%\nsis" (
  for %%F in ("%BUNDLE%\nsis\*.exe") do (
    copy /Y "%%~fF" "%OUT_DIR%\" >nul
    echo       + %%~nxF
    set "FOUND=1"
  )
)
if exist "%BUNDLE%\msi" (
  for %%F in ("%BUNDLE%\msi\*.msi") do (
    copy /Y "%%~fF" "%OUT_DIR%\" >nul
    echo       + %%~nxF
    set "FOUND=1"
  )
)

if "%FOUND%"=="0" (
  for /r "%BUNDLE%" %%F in (*.exe) do (
    echo %%~dpF | findstr /i "\\bundle\\" >nul
    if not errorlevel 1 (
      copy /Y "%%~fF" "%OUT_DIR%\" >nul
      echo       + %%~nxF
      set "FOUND=1"
    )
  )
  for /r "%BUNDLE%" %%F in (*.msi) do (
    echo %%~dpF | findstr /i "\\bundle\\" >nul
    if not errorlevel 1 (
      copy /Y "%%~fF" "%OUT_DIR%\" >nul
      echo       + %%~nxF
      set "FOUND=1"
    )
  )
)

if "%FOUND%"=="0" (
  echo [ERROR] no .exe/.msi under %BUNDLE%
  exit /b 1
)

where certutil >nul 2>&1
if not errorlevel 1 (
  echo.
  echo       SHA256:
  > "%OUT_DIR%\SHA256SUMS.txt" (
    for %%F in ("%OUT_DIR%\*.exe") do (
      if exist "%%~fF" (
        for /f "tokens=1" %%H in ('certutil -hashfile "%%~fF" SHA256 ^| findstr /v /i "hash CertUtil"') do (
          echo %%H  %%~nxF
          echo       %%H  %%~nxF
        )
      )
    )
    for %%F in ("%OUT_DIR%\*.msi") do (
      if exist "%%~fF" (
        for /f "tokens=1" %%H in ('certutil -hashfile "%%~fF" SHA256 ^| findstr /v /i "hash CertUtil"') do (
          echo %%H  %%~nxF
          echo       %%H  %%~nxF
        )
      )
    )
  )
)

echo.
echo ============================================================
echo  BUILD OK
echo  Output: %OUT_DIR%
dir /b "%OUT_DIR%"
echo ============================================================
echo.

if not "%DO_RELEASE%"=="1" (
  echo Next:
  echo   1. Install the setup.exe / .msi under release-artifacts and smoke-test
  echo   2. Optional GitHub upload:  publish.bat 2.5.0 --release
  echo   3. Do NOT: git push upstream --tags
  echo.
  exit /b 0
)

REM ---- optional release to origin only ----
echo [release] Upload to GitHub Release on origin only...
where gh >nul 2>&1
if errorlevel 1 (
  echo [ERROR] gh CLI not found: https://cli.github.com/
  echo         Artifacts are ready under release-artifacts\
  exit /b 1
)

set "ORIGIN_URL="
for /f "delims=" %%R in ('git -C "%ROOT%" remote get-url origin 2^>nul') do set "ORIGIN_URL=%%R"
echo       origin=%ORIGIN_URL%

echo %ORIGIN_URL% | findstr /i "JefferyHcool/BiliNote" >nul
if not errorlevel 1 (
  echo %ORIGIN_URL% | findstr /i "winlend" >nul
  if errorlevel 1 (
    echo [ERROR] origin points at upstream JefferyHcool/BiliNote.
    echo         Refusing --release. Set origin to your fork first.
    exit /b 1
  )
)

if "%VERSION_ARG%"=="" (
  for /f "delims=" %%V in ('node -e "console.log(require(process.argv[1]).version)" "%FRONTEND%\src-tauri\tauri.conf.json"') do set "VERSION_ARG=%%V"
)
set "TAG=v%VERSION_ARG%"
echo       tag=%TAG%

gh release view "%TAG%" --repo winlend/BiliNote >nul 2>&1
if errorlevel 1 (
  gh release create "%TAG%" "%OUT_DIR%\*" --repo winlend/BiliNote --title "BiliNote %TAG% Windows" --notes "Windows desktop build from local publish.bat. Fork-only." --latest
) else (
  gh release upload "%TAG%" "%OUT_DIR%\*" --repo winlend/BiliNote --clobber
)
if errorlevel 1 (
  echo [ERROR] gh release failed. Files remain in release-artifacts\
  exit /b 1
)
echo       Release: https://github.com/winlend/BiliNote/releases/tag/%TAG%
echo.
exit /b 0
