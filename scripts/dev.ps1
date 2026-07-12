#Requires -Version 5.1
<#
.SYNOPSIS
    Start, stop, or check InfDrawing local dev services (ComfyUI, backend, frontend).

.DESCRIPTION
    One-click launcher for Windows. Ollama is checked but not started (usually runs as a
    background app). ComfyUI, FastAPI, and Next.js each open in a dedicated terminal window.

.PARAMETER Action
    start   — launch missing services and wait for health checks (default)
    stop    — stop processes recorded in .cursor/dev-services.json
    status  — print health of Ollama, ComfyUI, backend, and frontend
    restart — stop then start

.EXAMPLE
    .\scripts\dev.ps1
    .\scripts\dev.ps1 status
    .\scripts\dev.ps1 stop

.ENVIRONMENT
    INFD_COMFYUI_DIR       ComfyUI repo path (default: D:\ComfyUI)
    INFD_COMFYUI_ENV       Conda env name for ComfyUI (default: comfyui)
    INFD_COMFYUI_PORT      ComfyUI port (default: 8188)
    INFD_BACKEND_PORT      FastAPI port (default: 8000)
    INFD_FRONTEND_PORT     Next.js port (default: 3000)
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "status", "restart")]
    [string]$Action = "start",

    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$StatePath = Join-Path $RepoRoot ".cursor\dev-services.json"

$ComfyDir = if ($env:INFD_COMFYUI_DIR) { $env:INFD_COMFYUI_DIR } else { "D:\ComfyUI" }
$ComfyEnv = if ($env:INFD_COMFYUI_ENV) { $env:INFD_COMFYUI_ENV } else { "comfyui" }
$ComfyPort = if ($env:INFD_COMFYUI_PORT) { [int]$env:INFD_COMFYUI_PORT } else { 8188 }
$BackendPort = if ($env:INFD_BACKEND_PORT) { [int]$env:INFD_BACKEND_PORT } else { 8000 }
$FrontendPort = if ($env:INFD_FRONTEND_PORT) { [int]$env:INFD_FRONTEND_PORT } else { 3000 }

$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

function Write-Info([string]$Message) {
    Write-Host "[infDrawing] $Message" -ForegroundColor Cyan
}

function Write-Warn([string]$Message) {
    Write-Host "[infDrawing] $Message" -ForegroundColor Yellow
}

function Write-Ok([string]$Message) {
    Write-Host "[infDrawing] $Message" -ForegroundColor Green
}

function Write-Err([string]$Message) {
    Write-Host "[infDrawing] $Message" -ForegroundColor Red
}

function Test-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSec = 5
    )
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Get-ServiceDefinitions {
    return @(
        @{
            Name    = "ollama"
            Url     = "http://localhost:11434/api/tags"
            Managed = $false
        },
        @{
            Name    = "comfyui"
            Url     = "http://127.0.0.1:$ComfyPort"
            Port    = $ComfyPort
            Managed = $true
        },
        @{
            Name    = "backend"
            Url     = "http://127.0.0.1:$BackendPort/health"
            Port    = $BackendPort
            Managed = $true
        },
        @{
            Name    = "frontend"
            Url     = "http://127.0.0.1:$FrontendPort"
            Port    = $FrontendPort
            Managed = $true
        }
    )
}

function Show-Status {
    Write-Info "Service status:"
    foreach ($svc in Get-ServiceDefinitions) {
        $ok = Test-HttpOk -Url $svc.Url
        $label = $svc.Name.PadRight(9)
        if ($ok) {
            Write-Ok ("  {0} OK   {1}" -f $label, $svc.Url)
        }
        else {
            Write-Err ("  {0} DOWN {1}" -f $label, $svc.Url)
        }
    }
}

function Read-DevState {
    if (-not (Test-Path $StatePath)) {
        return @()
    }
    $json = Get-Content $StatePath -Raw | ConvertFrom-Json
    if (-not $json.processes) {
        return @()
    }
    return @($json.processes)
}

function Save-DevState {
    param([array]$Processes)
    $dir = Split-Path $StatePath -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    @{ processes = $Processes } | ConvertTo-Json -Depth 4 | Set-Content -Path $StatePath -Encoding UTF8
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$Command
    )

    Write-Info "Starting $Name ..."
    $proc = Start-Process -FilePath "powershell.exe" -WorkingDirectory $WorkingDirectory -PassThru `
        -ArgumentList @("-NoExit", "-Command", $Command)
    return @{
        name       = $Name
        pid        = $proc.Id
        started_at = (Get-Date).ToString("o")
    }
}

function Assert-Prerequisites {
    if (-not (Test-Path $BackendPython)) {
        throw "Backend venv not found: $BackendPython`nRun: cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    }
    if (-not (Test-Path (Join-Path $FrontendDir "package.json"))) {
        throw "Frontend not found: $FrontendDir"
    }
    if (-not (Test-Path (Join-Path $ComfyDir "main.py"))) {
        throw "ComfyUI not found at $ComfyDir`nSet INFD_COMFYUI_DIR or install ComfyUI (see docs/environment_setup.md)"
    }
    $conda = Get-Command conda -ErrorAction SilentlyContinue
    if (-not $conda) {
        throw "conda not found in PATH. Install Miniconda/Anaconda and ensure 'conda init powershell' was run."
    }
}

function Start-DevServices {
    Assert-Prerequisites

    $newProcesses = @()

    if (-not (Test-HttpOk -Url "http://localhost:11434/api/tags")) {
        Write-Warn "Ollama is not reachable at http://localhost:11434 — start the Ollama app, then retry."
    }
    else {
        Write-Ok "Ollama already running."
    }

    if (-not (Test-HttpOk -Url "http://127.0.0.1:$ComfyPort")) {
        $comfyCmd = "conda run -n $ComfyEnv python main.py --lowvram --port $ComfyPort"
        $newProcesses += Start-ManagedProcess -Name "comfyui" -WorkingDirectory $ComfyDir -Command $comfyCmd
    }
    else {
        Write-Ok "ComfyUI already running on port $ComfyPort."
    }

    if (-not (Test-HttpOk -Url "http://127.0.0.1:$BackendPort/health")) {
        $backendCmd = "& '$BackendPython' -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
        $newProcesses += Start-ManagedProcess -Name "backend" -WorkingDirectory $BackendDir -Command $backendCmd
    }
    else {
        Write-Ok "Backend already running on port $BackendPort."
    }

    if (-not (Test-HttpOk -Url "http://127.0.0.1:$FrontendPort")) {
        # Next.js 16 treats bare "3000" as a directory; use -p or PORT env instead.
        $frontendCmd = "npx next dev -p $FrontendPort"
        $newProcesses += Start-ManagedProcess -Name "frontend" -WorkingDirectory $FrontendDir -Command $frontendCmd
    }
    else {
        Write-Ok "Frontend already running on port $FrontendPort."
    }

    if ($newProcesses.Count -gt 0) {
        $existing = @(Read-DevState)
        Save-DevState -Processes ($existing + $newProcesses)
    }

    Write-Info "Waiting for services (up to 120s) ..."
    $deadline = (Get-Date).AddSeconds(120)
    $targets = @(
        @{ Name = "comfyui"; Url = "http://127.0.0.1:$ComfyPort" },
        @{ Name = "backend"; Url = "http://127.0.0.1:$BackendPort/health" },
        @{ Name = "frontend"; Url = "http://127.0.0.1:$FrontendPort" }
    )

    while ((Get-Date) -lt $deadline) {
        $pending = @($targets | Where-Object { -not (Test-HttpOk -Url $_.Url -TimeoutSec 3) })
        if ($pending.Count -eq 0) {
            break
        }
        Start-Sleep -Seconds 2
    }

    Show-Status

    $allOk = ($targets | ForEach-Object { Test-HttpOk -Url $_.Url -TimeoutSec 5 }) -notcontains $false
    if (-not $allOk) {
        Write-Warn "Some services are still starting. Check the opened terminal windows for errors."
        exit 1
    }

    Write-Ok "All services ready."
    Write-Info "  App:     http://127.0.0.1:$FrontendPort"
    Write-Info "  API:     http://127.0.0.1:$BackendPort/docs"
    Write-Info "  ComfyUI: http://127.0.0.1:$ComfyPort"

    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:$FrontendPort"
    }
}

function Stop-DevServices {
    $processes = @(Read-DevState)
    if ($processes.Count -eq 0) {
        Write-Warn "No recorded dev processes ($StatePath). Nothing to stop."
        return
    }

    foreach ($entry in $processes) {
        $procId = [int]$entry.pid
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Info "Stopping $($entry.name) (PID $procId) ..."
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
        else {
            Write-Warn "$($entry.name) (PID $procId) is not running."
        }
    }

    Remove-Item $StatePath -Force -ErrorAction SilentlyContinue
    Write-Ok "Stop signal sent. Close any remaining ComfyUI/backend/frontend windows manually if needed."
}

switch ($Action) {
    "start" { Start-DevServices }
    "stop" { Stop-DevServices }
    "status" { Show-Status }
    "restart" {
        Stop-DevServices
        Start-Sleep -Seconds 2
        Start-DevServices
    }
}
