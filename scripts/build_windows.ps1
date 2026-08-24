$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$BuildEnv = ".venv-build"
py -3 -m venv $BuildEnv
& "$BuildEnv\Scripts\python.exe" -m pip install --upgrade pip
& "$BuildEnv\Scripts\python.exe" -m pip install ".[build]"
& "$BuildEnv\Scripts\pyinstaller.exe" `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --additional-hooks-dir hooks `
  --collect-data medmask `
  --name MedMask `
  main.py

Write-Host ""
Write-Host "Готово: dist\MedMask.exe"
