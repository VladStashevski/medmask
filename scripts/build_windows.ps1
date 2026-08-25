$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$BuildEnv = ".venv-build"
py -3 -m venv $BuildEnv
& "$BuildEnv\Scripts\python.exe" -m pip install --upgrade pip
& "$BuildEnv\Scripts\python.exe" -m pip install -c constraints.txt ".[build]"

# Сборка папкой, а не одним файлом: onefile распаковывает больше сотни мегабайт
# во временный каталог при каждом запуске, и программа стартует по 10-20 секунд.
& "$BuildEnv\Scripts\pyinstaller.exe" --noconfirm --clean MedMask.spec

$Version = & "$BuildEnv\Scripts\python.exe" -c "import medmask; print(medmask.__version__)"
$Archive = "dist\MedMask-Windows-x64-$Version.zip"
if (Test-Path $Archive) { Remove-Item $Archive }
Compress-Archive -Path "dist\MedMask" -DestinationPath $Archive

& "$BuildEnv\Scripts\python.exe" scripts\smoke_test.py "dist\MedMask\MedMask.exe"

Write-Host ""
Write-Host "Готово: $Archive"
