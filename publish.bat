@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM =============================================================================
REM  BiliNote Windows 一键打包脚本（仅本机产物，不推官方仓库）
REM
REM  用法：
REM    publish.bat
REM    publish.bat 2.5.0
REM    publish.bat 2.5.0 --release
REM
REM  参数：
REM    %1  可选版本号，写入 tauri.conf.json（如 2.5.0）
REM    %2  可选 --release：用 gh 上传到 origin(winlend/BiliNote) 的 GitHub Release
REM        不会 push 到 upstream(JefferyHcool/BiliNote)
REM
REM  产物目录：
REM    release-artifacts\
REM =============================================================================

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
echo   BiliNote Windows 一键打包
echo   根目录: %ROOT%
echo ============================================================
echo.

REM ---------- 0. 环境检查 ----------
echo [0/5] 检查构建环境...

where rustc >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 未找到 rustc。请安装 Rust: https://rustup.rs/
  exit /b 1
)
for /f "tokens=2 delims=:" %%A in ('rustc -Vv 2^>nul ^| findstr /i "host"') do set "TARGET_TRIPLE=%%A"
set "TARGET_TRIPLE=%TARGET_TRIPLE: =%"
echo       rustc OK  target=%TARGET_TRIPLE%

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 未找到 node。请安装 Node 20+。
  exit /b 1
)
for /f "delims=" %%V in ('node -v') do echo       node %%V

where pnpm >nul 2>&1
if errorlevel 1 (
  echo       未找到 pnpm，尝试 corepack 启用 pnpm@9.15.0 ...
  where corepack >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] 无 pnpm 且无 corepack。请执行: npm install -g pnpm@9.15.0
    exit /b 1
  )
  call corepack enable
  call corepack prepare pnpm@9.15.0 --activate
  where pnpm >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] corepack 启用 pnpm 失败。请: npm install -g pnpm@9.15.0
    exit /b 1
  )
)
for /f "delims=" %%V in ('pnpm -v') do echo       pnpm %%V

REM Python / PyInstaller：优先 PATH，否则 miniconda 常见路径
set "PYTHON_EXE="
where python >nul 2>&1 && for /f "delims=" %%P in ('where python') do (
  if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)
if not defined PYTHON_EXE if exist "D:\ProgramData\miniconda3\python.exe" set "PYTHON_EXE=D:\ProgramData\miniconda3\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYTHON_EXE (
  echo [ERROR] 未找到 python。请安装 Python 3.11 并加入 PATH。
  exit /b 1
)
echo       python: %PYTHON_EXE%

where pyinstaller >nul 2>&1
if errorlevel 1 (
  echo       未找到 pyinstaller，尝试用当前 Python 安装...
  "%PYTHON_EXE%" -m pip install -q pyinstaller
  where pyinstaller >nul 2>&1
  if errorlevel 1 (
    echo [WARN] PATH 中仍无 pyinstaller，build.bat 可能失败；将依赖 python -m PyInstaller
  ) else (
    echo       pyinstaller 已安装
  )
) else (
  echo       pyinstaller OK
)

echo.

REM ---------- 1. 可选：写入版本号 ----------
if not "%VERSION_ARG%"=="" (
  echo [1/5] 写入版本号 %VERSION_ARG% -^> tauri.conf.json
  pushd "%FRONTEND%"
  node -e "const fs=require('fs');const f='src-tauri/tauri.conf.json';const j=JSON.parse(fs.readFileSync(f,'utf8'));j.version=process.argv[1];fs.writeFileSync(f,JSON.stringify(j,null,2)+'\n');console.log('version =',j.version);" "%VERSION_ARG%"
  if errorlevel 1 (
    echo [ERROR] 写入版本失败
    popd
    exit /b 1
  )
  popd
) else (
  echo [1/5] 未指定版本，保留 tauri.conf.json 现有 version
  pushd "%FRONTEND%"
  node -e "const j=require('./src-tauri/tauri.conf.json');console.log('      current version =',j.version);"
  popd
)
echo.

REM ---------- 2. 打包 Python 后端 sidecar ----------
echo [2/5] 打包后端 sidecar ^(PyInstaller / build.bat^)...
echo       这可能需要几分钟...
call "%ROOT%\backend\build.bat"
if errorlevel 1 (
  echo [ERROR] backend\build.bat 失败
  exit /b 1
)

set "SIDECAR_DIR=%FRONTEND%\src-tauri\bin\BiliNoteBackend"
if not exist "%SIDECAR_DIR%\BiliNoteBackend-%TARGET_TRIPLE%.exe" (
  echo [ERROR] 未找到 sidecar: %SIDECAR_DIR%\BiliNoteBackend-%TARGET_TRIPLE%.exe
  echo         请检查 build.bat 输出。
  dir /b "%SIDECAR_DIR%" 2>nul
  exit /b 1
)
echo       sidecar OK: BiliNoteBackend-%TARGET_TRIPLE%.exe
echo.

REM ---------- 3. 前端依赖 ----------
echo [3/5] 安装前端依赖 ^(pnpm install^)...
pushd "%FRONTEND%"
if not exist "node_modules\" (
  call pnpm install
  if errorlevel 1 (
    echo [ERROR] pnpm install 失败
    popd
    exit /b 1
  )
) else (
  echo       node_modules 已存在，跳过全量 install ^(如需强制: 删 node_modules 后重跑^)
)

REM 确保 tauri CLI 可用
call pnpm exec tauri --version >nul 2>&1
if errorlevel 1 (
  echo       安装 @tauri-apps/cli@2 ...
  call pnpm add -D @tauri-apps/cli@2
  if errorlevel 1 (
    echo [ERROR] 安装 tauri CLI 失败
    popd
    exit /b 1
  )
)
echo.

REM ---------- 4. Tauri 打包 ----------
echo [4/5] 执行 pnpm tauri build ...
echo       首次编译 Rust 可能需 10-30 分钟，请耐心等待。
call pnpm tauri build
if errorlevel 1 (
  echo [ERROR] tauri build 失败
  popd
  exit /b 1
)
popd
echo.

REM ---------- 5. 收集产物 ----------
echo [5/5] 收集安装包到 release-artifacts\
if exist "%OUT_DIR%" rmdir /s /q "%OUT_DIR%"
mkdir "%OUT_DIR%" >nul 2>&1

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

REM 兜底：任意 bundle 下的安装包
if "%FOUND%"=="0" (
  for /r "%BUNDLE%" %%F in (*.exe *.msi) do (
    echo %%~fF | findstr /i "\\bundle\\" >nul
    if not errorlevel 1 (
      copy /Y "%%~fF" "%OUT_DIR%\" >nul
      echo       + %%~nxF
      set "FOUND=1"
    )
  )
)

if "%FOUND%"=="0" (
  echo [ERROR] 未在 bundle 目录找到 .exe/.msi
  echo         请检查: %BUNDLE%
  exit /b 1
)

REM SHA256（可选）
where certutil >nul 2>&1
if not errorlevel 1 (
  echo.
  echo       校验和:
  > "%OUT_DIR%\SHA256SUMS.txt" (
    for %%F in ("%OUT_DIR%\*.exe" "%OUT_DIR%\*.msi") do (
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
echo   打包完成
echo   产物目录: %OUT_DIR%
dir /b "%OUT_DIR%"
echo ============================================================
echo.

REM ---------- 可选：发布到自己的 GitHub Release（仅 origin） ----------
if "%DO_RELEASE%"=="1" (
  echo [release] 上传到 GitHub Release ^(仅 origin，不推 upstream^)...
  where gh >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] 未找到 gh CLI。安装: https://cli.github.com/
    echo         安装包已打好，可手动上传 Release。
    exit /b 1
  )

  for /f "delims=" %%R in ('git -C "%ROOT%" remote get-url origin 2^>nul') do set "ORIGIN_URL=%%R"
  echo       origin=%ORIGIN_URL%
  echo %ORIGIN_URL% | findstr /i "winlend/BiliNote JefferyHcool/BiliNote" >nul
  echo %ORIGIN_URL% | findstr /i "JefferyHcool/BiliNote" >nul
  if not errorlevel 1 (
    echo %ORIGIN_URL% | findstr /i "winlend" >nul
    if errorlevel 1 (
      echo [ERROR] origin 指向官方 JefferyHcool/BiliNote。
      echo         按你的要求不向官方发版。请把 origin 设为你的 fork 后再加 --release。
      exit /b 1
    )
  )

  if "%VERSION_ARG%"=="" (
    for /f "delims=" %%V in ('node -e "console.log(require(process.argv[1]).version)" "%FRONTEND%\src-tauri\tauri.conf.json"') do set "VERSION_ARG=%%V"
  )
  set "TAG=v%VERSION_ARG%"
  echo       tag=%TAG%

  REM 仅创建 Release + 上传文件，不 git push tag 到任何 remote（避免误推 upstream）
  REM 若要用 CI，请你自己: git tag %TAG% && git push origin %TAG%
  gh release view "%TAG%" --repo winlend/BiliNote >nul 2>&1
  if errorlevel 1 (
    gh release create "%TAG%" "%OUT_DIR%\*" --repo winlend/BiliNote --title "BiliNote %TAG% (Windows)" --notes "Windows desktop build from local publish.bat. Includes local fixes on this fork only." --latest
  ) else (
    gh release upload "%TAG%" "%OUT_DIR%\*" --repo winlend/BiliNote --clobber
  )
  if errorlevel 1 (
    echo [ERROR] gh release 失败。安装包仍在 release-artifacts\
    exit /b 1
  )
  echo       Release 已更新: https://github.com/winlend/BiliNote/releases/tag/%TAG%
)

echo.
echo 下一步:
echo   1. 安装 release-artifacts 里的 setup.exe / .msi 做冒烟测试
echo   2. 需要 GitHub 分发时:  publish.bat 2.5.0 --release
echo      或自行: git tag vX.Y.Z ^&^& git push origin vX.Y.Z  ^(触发 fork 的 Actions^)
echo   3. 切勿: git push upstream --tags
echo.
exit /b 0
