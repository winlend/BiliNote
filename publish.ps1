# BiliNote Windows one-click build (PowerShell, UTF-8 safe)
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\publish.ps1
#   powershell -ExecutionPolicy Bypass -File .\publish.ps1 -Version 2.5.0
#   powershell -ExecutionPolicy Bypass -File .\publish.ps1 -Version 2.5.0 -Release

[CmdletBinding()]
param(
    [string]$Version = "",
    [switch]$Release
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Frontend = Join-Path $Root "BillNote_frontend"
$OutDir = Join-Path $Root "release-artifacts"

function Write-Step($msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host $msg -ForegroundColor Green }
function Write-Err($msg) { Write-Host $msg -ForegroundColor Red }

Write-Host ""
Write-Host "============================================================"
Write-Host " BiliNote Windows build"
Write-Host " ROOT=$Root"
Write-Host "============================================================"
Write-Host ""

# --- tools ---
Write-Step "[0/5] Checking tools..."
if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    Write-Err "[ERROR] rustc not found. Install https://rustup.rs/"
    exit 1
}
$hostLine = & rustc -Vv 2>$null | Select-String -Pattern "host:"
$TargetTriple = ($hostLine -split ":", 2)[1].Trim()
if (-not $TargetTriple) {
    Write-Err "[ERROR] cannot detect rustc host triple"
    exit 1
}
Write-Host "      rustc OK  target=$TargetTriple"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Err "[ERROR] node not found"
    exit 1
}
Write-Host "      node $(node -v)"

if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    Write-Host "      pnpm missing, trying corepack..."
    if (-not (Get-Command corepack -ErrorAction SilentlyContinue)) {
        Write-Err "[ERROR] no pnpm/corepack. Run: npm install -g pnpm@9.15.0"
        exit 1
    }
    corepack enable
    corepack prepare pnpm@9.15.0 --activate
}
Write-Host "      pnpm $(pnpm -v)"

$Python = $null
foreach ($c in @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "D:\ProgramData\miniconda3\python.exe",
    "$env:USERPROFILE\miniconda3\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
)) {
    if ($c -and (Test-Path $c)) { $Python = $c; break }
}
if (-not $Python) {
    Write-Err "[ERROR] python not found"
    exit 1
}
Write-Host "      python: $Python"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "      installing pyinstaller..."
    & $Python -m pip install -q pyinstaller
}

# --- version ---
if ($Version) {
    Write-Step "[1/5] Set tauri version to $Version"
    Push-Location $Frontend
    node -e "const fs=require('fs');const f='src-tauri/tauri.conf.json';const j=JSON.parse(fs.readFileSync(f,'utf8'));j.version=process.argv[1];fs.writeFileSync(f,JSON.stringify(j,null,2)+'\n');console.log('version =',j.version);" $Version
    Pop-Location
} else {
    Write-Step "[1/5] Keep existing tauri.conf.json version"
    Push-Location $Frontend
    node -e "console.log('      version =', require('./src-tauri/tauri.conf.json').version)"
    Pop-Location
}

# --- backend ---
Write-Step "[2/5] Building backend sidecar (backend\build.bat)..."
& cmd.exe /c "`"$Root\backend\build.bat`""
if ($LASTEXITCODE -ne 0) {
    Write-Err "[ERROR] backend\build.bat failed"
    exit 1
}
$Sidecar = Join-Path $Frontend "src-tauri\bin\BiliNoteBackend\BiliNoteBackend-$TargetTriple.exe"
if (-not (Test-Path $Sidecar)) {
    Write-Err "[ERROR] sidecar not found: $Sidecar"
    exit 1
}
Write-Ok "      sidecar OK"

# --- frontend ---
Write-Step "[3/5] Frontend dependencies..."
Push-Location $Frontend
if (-not (Test-Path "node_modules")) {
    pnpm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
} else {
    Write-Host "      node_modules exists, skip install"
}
pnpm exec tauri --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    pnpm add -D @tauri-apps/cli@2
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
}

Write-Step "[4/5] pnpm tauri build (first Rust build may take 10-30 min)..."
pnpm tauri build
if ($LASTEXITCODE -ne 0) {
    Write-Err "[ERROR] tauri build failed"
    Pop-Location
    exit 1
}
Pop-Location

# --- collect ---
Write-Step "[5/5] Collecting installers..."
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutDir | Out-Null
$Bundle = Join-Path $Frontend "src-tauri\target\release\bundle"
$copied = @()
foreach ($pat in @("nsis\*.exe", "msi\*.msi")) {
    $files = Get-ChildItem -Path (Join-Path $Bundle $pat) -ErrorAction SilentlyContinue
    foreach ($f in $files) {
        Copy-Item $f.FullName $OutDir
        $copied += $f.Name
        Write-Host "      + $($f.Name)"
    }
}
if ($copied.Count -eq 0) {
    Get-ChildItem -Path $Bundle -Recurse -Include *.exe,*.msi -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\bundle\\' } |
        ForEach-Object {
            Copy-Item $_.FullName $OutDir
            $copied += $_.Name
            Write-Host "      + $($_.Name)"
        }
}
if ($copied.Count -eq 0) {
    Write-Err "[ERROR] no installers under $Bundle"
    exit 1
}

$sums = Join-Path $OutDir "SHA256SUMS.txt"
Get-ChildItem $OutDir -Include *.exe,*.msi -File | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
    "$h  $($_.Name)" | Add-Content $sums
    Write-Host "      $h  $($_.Name)"
}

Write-Host ""
Write-Ok "BUILD OK"
Write-Host "Output: $OutDir"
Get-ChildItem $OutDir | ForEach-Object { Write-Host "  $($_.Name)" }
Write-Host ""

if (-not $Release) {
    Write-Host "Next: install setup under release-artifacts and smoke-test."
    Write-Host "Optional: .\publish.ps1 -Version 2.5.0 -Release"
    Write-Host "Do NOT: git push upstream --tags"
    exit 0
}

Write-Step "[release] Upload to origin only (winlend)..."
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Err "[ERROR] gh not found"
    exit 1
}
$origin = git -C $Root remote get-url origin 2>$null
Write-Host "      origin=$origin"
if ($origin -match "JefferyHcool/BiliNote" -and $origin -notmatch "winlend") {
    Write-Err "[ERROR] origin is upstream; refusing -Release"
    exit 1
}
if (-not $Version) {
    $Version = node -e "console.log(require(process.argv[1]).version)" (Join-Path $Frontend "src-tauri\tauri.conf.json")
}
$Tag = "v$Version"
Write-Host "      tag=$Tag"
$files = Get-ChildItem $OutDir -File | ForEach-Object { $_.FullName }
gh release view $Tag --repo winlend/BiliNote 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    gh release create $Tag @files --repo winlend/BiliNote --title "BiliNote $Tag Windows" --notes "Windows desktop build from publish.ps1. Fork-only." --latest
} else {
    gh release upload $Tag @files --repo winlend/BiliNote --clobber
}
if ($LASTEXITCODE -ne 0) {
    Write-Err "[ERROR] gh release failed"
    exit 1
}
Write-Ok "Release: https://github.com/winlend/BiliNote/releases/tag/$Tag"
exit 0
