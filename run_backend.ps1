$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "$projectRoot\.pydeps;$projectRoot"

Set-Location $projectRoot
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
