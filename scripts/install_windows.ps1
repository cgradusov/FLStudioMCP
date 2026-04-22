<#
.SYNOPSIS
    Install fLMCP bridge script into FL Studio and register the MCP server
    with Claude Desktop / Claude Code.

.DESCRIPTION
    1. Copies `fl_bridge/device_FLStudioMCP.py` into
       %USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Hardware\fLMCP Bridge\
    2. Copies `fl_bridge/piano_roll/ComposeWithLLM.pyscript` into
       %USERPROFILE%\Documents\Image-Line\FL Studio\Settings\Piano roll scripts\
    3. Installs the Python MCP package into an editable venv at .venv
    4. Merges a `fl-studio-mcp` entry into:
         - %APPDATA%\Claude\claude_desktop_config.json
         - %USERPROFILE%\.claude\mcp_settings.json  (if present)
    5. Prints next-steps for the user.

.EXAMPLE
    PS> .\scripts\install_windows.ps1
#>

param(
    [switch]$SkipVenv,
    [switch]$SkipClaudeConfig,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Write-Host "fLMCP installer - repo: $repo" -ForegroundColor Cyan

# --- 1) FL Studio settings folder -------------------------------------------
$flSettings = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings"
if (-not (Test-Path $flSettings)) {
    throw "FL Studio settings folder not found: $flSettings  (Install FL Studio first.)"
}

$hwDir = Join-Path $flSettings "Hardware\fLMCP Bridge"
$prDir = Join-Path $flSettings "Piano roll scripts"
New-Item -ItemType Directory -Path $hwDir -Force | Out-Null
New-Item -ItemType Directory -Path $prDir -Force | Out-Null

Write-Host "[1/4] Copying FL Studio bridge scripts..." -ForegroundColor Cyan
Copy-Item -Force (Join-Path $repo "fl_bridge\device_FLStudioMCP.py") $hwDir
Copy-Item -Force (Join-Path $repo "fl_bridge\piano_roll\ComposeWithLLM.pyscript") $prDir
Write-Host "    bridge -> $hwDir"
Write-Host "    piano-roll pyscript -> $prDir"

# --- 2) Python venv + install -----------------------------------------------
if (-not $SkipVenv) {
    Write-Host "[2/4] Creating virtualenv and installing package..." -ForegroundColor Cyan
    $venv = Join-Path $repo ".venv"
    if (-not (Test-Path $venv)) {
        & $PythonExe -m venv $venv
    }
    $venvPython = Join-Path $venv "Scripts\python.exe"
    & $venvPython -m pip install --upgrade pip --quiet
    & $venvPython -m pip install -e $repo --quiet
    Write-Host "    installed fl-studio-mcp into $venv"
} else {
    Write-Host "[2/4] Skipping venv step."
    $venvPython = $PythonExe
}

# --- 3) Claude config -------------------------------------------------------
function Merge-ClaudeConfig {
    param([string]$path, [string]$pyExe, [string]$repoPath)

    # Build the new server entry as a hashtable so Json output stays an object, not an array.
    $newServer = @{
        command = $pyExe
        args    = @("-m", "fl_studio_mcp")
        env     = @{ FL_MCP_LOG_LEVEL = "INFO" }
    }

    # Load existing config as a hashtable (PS 5.1 has no -AsHashtable, so reconstruct manually).
    $servers = @{}
    $topExtras = @{}
    if (Test-Path $path) {
        try {
            $raw = Get-Content $path -Raw
            if ($raw -and $raw.Trim().Length -gt 0) {
                $existing = $raw | ConvertFrom-Json
                foreach ($prop in $existing.PSObject.Properties) {
                    if ($prop.Name -eq "mcpServers" -and $prop.Value) {
                        foreach ($s in $prop.Value.PSObject.Properties) {
                            # Preserve each existing server entry as-is (PSCustomObject).
                            $servers[$s.Name] = $s.Value
                        }
                    } else {
                        $topExtras[$prop.Name] = $prop.Value
                    }
                }
            }
        } catch {
            Write-Host "    (existing config was not valid JSON - overwriting)" -ForegroundColor Yellow
        }
    } else {
        $parent = Split-Path $path
        if (-not (Test-Path $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
    }

    # Upsert our entry.
    $servers["fl-studio-mcp"] = $newServer

    # Rebuild the top-level object.
    $out = @{}
    foreach ($k in $topExtras.Keys) { $out[$k] = $topExtras[$k] }
    $out["mcpServers"] = $servers

    ($out | ConvertTo-Json -Depth 20) | Set-Content -Path $path -Encoding UTF8
    Write-Host "    merged into $path"
}

if (-not $SkipClaudeConfig) {
    Write-Host "[3/4] Registering with Claude clients..." -ForegroundColor Cyan
    $claudeDesktop = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    $claudeCode = Join-Path $env:USERPROFILE ".claude\mcp_settings.json"
    Merge-ClaudeConfig $claudeDesktop $venvPython $repo
    if (Test-Path (Split-Path $claudeCode)) {
        Merge-ClaudeConfig $claudeCode $venvPython $repo
    }
} else {
    Write-Host "[3/4] Skipping Claude config step."
}

# --- 4) Done ----------------------------------------------------------------
Write-Host "[4/4] Done!" -ForegroundColor Green
Write-Host ""
Write-Host "NEXT STEPS IN FL STUDIO:" -ForegroundColor Yellow
Write-Host "  1. Open FL Studio 2025."
Write-Host "  2. Options -> MIDI Settings -> Input: enable any input row and set"
Write-Host "     Controller type = 'fLMCP Bridge' (the bridge TCP server starts"
Write-Host "     as soon as the script initialises)."
Write-Host "  3. Allow FL64.exe through Windows Firewall on 127.0.0.1:9876"
Write-Host "  4. Open any piano roll, click the scripts dropdown, pick"
Write-Host "     'ComposeWithLLM' as the active piano-roll script."
Write-Host "  5. Restart Claude Desktop / Claude Code so it picks up the MCP."
Write-Host ""
Write-Host "Check connectivity after starting FL:" -ForegroundColor Gray
$smokeCmd = $venvPython + " scripts\smoke_test.py"
Write-Host "  $smokeCmd" -ForegroundColor Gray
Write-Host ""
