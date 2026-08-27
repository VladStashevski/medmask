$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$BuildEnv = ".venv-build"
py -3 -m venv $BuildEnv
& "$BuildEnv\Scripts\python.exe" -m pip install --upgrade pip
& "$BuildEnv\Scripts\python.exe" -m pip install -c constraints.txt ".[build]"
& "$BuildEnv\Scripts\python.exe" scripts\test_all.py

# Нативная app-dist сборка не распаковывается во временную папку при запуске.
& "$BuildEnv\Scripts\python.exe" scripts\build_native.py

& "$BuildEnv\Scripts\python.exe" scripts\verify_protected_build.py `
    "dist\MedMask" "dist\MedMask\MedMask.exe"
& "$BuildEnv\Scripts\python.exe" scripts\smoke_test.py "dist\MedMask\MedMask.exe"

$Version = & "$BuildEnv\Scripts\python.exe" -c "import medmask; print(medmask.__version__)"
$Archive = "dist\MedMask-Windows-x64-$Version.zip"
if (Test-Path $Archive) { Remove-Item $Archive }
Compress-Archive -Path "dist\MedMask" -DestinationPath $Archive

Write-Host ""
Write-Host "Готово: $Archive"
