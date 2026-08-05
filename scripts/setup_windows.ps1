[CmdletBinding()]
param(
    [string]$X64Python = "$env:LOCALAPPDATA\Programs\Python\Python311-x64\python.exe",
    [string]$Arm64Python = "$env:LOCALAPPDATA\Programs\Python\Python311-arm64\python.exe"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

foreach ($Interpreter in @($X64Python, $Arm64Python)) {
    if (-not (Test-Path -LiteralPath $Interpreter -PathType Leaf)) {
        throw "Python interpreter not found: $Interpreter"
    }
}

Push-Location $ProjectRoot
try {
    & $X64Python -m venv .venv-x64
    & .\.venv-x64\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
    & .\.venv-x64\Scripts\python.exe -m pip install -r requirements-codec.txt
    & .\.venv-x64\Scripts\python.exe -m pip install -r requirements-dev.txt
    & .\.venv-x64\Scripts\python.exe -m pip install --no-deps encodec==0.1.1
    & .\.venv-x64\Scripts\python.exe -m pip install --no-deps -e .

    & $Arm64Python -m venv .venv-arm64
    & .\.venv-arm64\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv-arm64\Scripts\python.exe -m pip install -r requirements-npu.txt
    & .\.venv-arm64\Scripts\python.exe -m pip install --no-deps -e .

    & .\.venv-x64\Scripts\python.exe scripts\prepare_models.py
    & .\.venv-x64\Scripts\python.exe scripts\generate_demo_images.py
    & .\.venv-x64\Scripts\python.exe scripts\generate_demo_audio.py
    & .\.venv-x64\Scripts\python.exe scripts\export_image_decoder.py
    & .\.venv-x64\Scripts\python.exe scripts\quantize_image_decoder.py
    & .\.venv-x64\Scripts\python.exe scripts\export_audio_tail.py
    & .\.venv-x64\Scripts\python.exe scripts\quantize_audio_tail.py

    Write-Host "LightWeave setup complete. Run: .\.venv-x64\Scripts\lightweave.exe --help"
}
finally {
    Pop-Location
}
