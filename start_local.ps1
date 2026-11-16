$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3 -m venv (Join-Path $projectPath '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3 was not found. Install Python 3.10 or newer, then retry.' }
    & $pythonPath -m pip install -r (Join-Path $projectPath 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the MCP dependency.' }
}

Write-Host 'Starting the local MCP server. Press Ctrl+C to stop.'
& $pythonPath (Join-Path $projectPath 'server.py')
