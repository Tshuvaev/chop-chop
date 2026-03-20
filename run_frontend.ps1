$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendRoot = Join-Path $projectRoot "frontend"

Set-Location $frontendRoot
node .\node_modules\vite\bin\vite.js --host 127.0.0.1 --port 5173
