# Build the Dimaagi Cart Windows installer from a clean checkout. Run from the repo root in PowerShell:
#   .\packaging\build.ps1
# Needs: the .venv with requirements.txt + requirements-build.txt, and Node.js 20+.
# Output: desktop\dist\DimaagiCart-Setup-<version>.exe (unsigned: see README, "Windows SmartScreen").
# Not 'Stop': PyInstaller and npm log to stderr, which Windows PowerShell 5.1 would treat as a fatal error.
# Each step's exit code is checked instead.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root '.venv\Scripts\python.exe'

Write-Host '1/5 Tests (offline)'
& $py -m pytest tests -q
if ($LASTEXITCODE) { throw 'Tests failed' }

Write-Host '2/5 Front end'
npm --prefix frontend ci
npm --prefix frontend test
if ($LASTEXITCODE) { throw 'Front-end tests failed' }
npm --prefix frontend run build
if ($LASTEXITCODE) { throw 'Front-end build failed' }

Write-Host '3/5 Backend (PyInstaller, one folder)'
& $py -m PyInstaller dimaagi-backend.spec --noconfirm
if ($LASTEXITCODE) { throw 'PyInstaller failed' }

Write-Host '4/5 Verify the packaged backend (licensing, self-check, first run)'
& $py packaging\verify_backend.py
if ($LASTEXITCODE) { throw 'Packaged backend failed verification' }

Write-Host '5/5 Installer (electron-builder, NSIS x64)'
npm --prefix desktop ci
npm --prefix desktop test
if ($LASTEXITCODE) { throw 'Desktop tests failed' }
$env:ELECTRON_RUN_AS_NODE = $null
npm --prefix desktop run dist
if ($LASTEXITCODE) { throw 'electron-builder failed' }

Get-ChildItem desktop\dist\*.exe | ForEach-Object { '{0}  {1:N1} MB' -f $_.FullName, ($_.Length / 1MB) }
