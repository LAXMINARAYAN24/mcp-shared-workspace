$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$serverPath = Join-Path $projectPath 'server.py'
$secretFile = Join-Path $projectPath '.mcp-secret'
$server = $null
$startedService = $false
$port = 8000

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell as Administrator, then run this script again.'
}

$tailscaleCommand = Get-Command tailscale -ErrorAction SilentlyContinue
$tailscalePath = if ($tailscaleCommand) { $tailscaleCommand.Source } else { $null }
if (-not $tailscalePath) {
    $candidate = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (Test-Path -LiteralPath $candidate) { $tailscalePath = $candidate }
}
if (-not $tailscalePath) { throw 'Tailscale is not installed. Install it and sign in once, then retry.' }

if (-not (Test-Path -LiteralPath $pythonPath)) {
    py -3 -m venv (Join-Path $projectPath '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3 was not found. Install Python 3.10 or newer, then retry.' }
    & $pythonPath -m pip install -r (Join-Path $projectPath 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the MCP dependency.' }
}

if (-not (Test-Path -LiteralPath $secretFile)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RNGCryptoServiceProvider]::new()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $secret = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    [System.IO.File]::WriteAllText($secretFile, $secret)
}
$secret = [System.IO.File]::ReadAllText($secretFile).Trim()
if ($secret.Length -lt 32) { throw 'The .mcp-secret file is invalid. Remove it and run this script again to generate a new secret.' }

$occupied = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
if ($occupied) { throw "Port $port is already in use. Stop the other server before retrying." }

$service = Get-Service -Name 'Tailscale' -ErrorAction SilentlyContinue
try {
    if ($service -and $service.Status -ne 'Running') {
        Start-Service -Name 'Tailscale'
        $startedService = $true
        (Get-Service -Name 'Tailscale').WaitForStatus('Running', [TimeSpan]::FromSeconds(20))
    }

    & $tailscalePath status
    if ($LASTEXITCODE -ne 0) { throw 'Tailscale is not ready. Open the Tailscale app, sign in, then retry.' }

    $env:MCP_TRANSPORT = 'streamable-http'
    $env:MCP_SHARED_PATH_SECRET = $secret
    $env:MCP_PORT = [string]$port

    Write-Host ''
    Write-Host 'Starting MCP and Tailscale Funnel for this session.' -ForegroundColor Cyan
    Write-Host 'Keep this window open. Press Ctrl+C here to stop.'
    Write-Host "Private MCP path: /mcp/$secret" -ForegroundColor Yellow
    Write-Host 'Combine that path with the HTTPS hostname shown by Tailscale.'
    Write-Host ''

    $server = Start-Process -FilePath $pythonPath -ArgumentList @($serverPath) -WorkingDirectory $projectPath -PassThru -NoNewWindow
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        if ($server.HasExited) { throw 'The MCP server stopped during startup.' }
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "The MCP server did not start listening on port $port." }

    & $tailscalePath funnel $port
}
finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
    if ($startedService) { Stop-Service -Name 'Tailscale' -Force -ErrorAction SilentlyContinue }
    Remove-Item Env:MCP_TRANSPORT -ErrorAction SilentlyContinue
    Remove-Item Env:MCP_SHARED_PATH_SECRET -ErrorAction SilentlyContinue
    Remove-Item Env:MCP_PORT -ErrorAction SilentlyContinue
}
