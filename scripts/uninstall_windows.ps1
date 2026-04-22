<#
.SYNOPSIS
    Undo what install_windows.ps1 did.
#>
$ErrorActionPreference = "Continue"
$flSettings = Join-Path $env:USERPROFILE "Documents\Image-Line\FL Studio\Settings"
Remove-Item -Recurse -Force (Join-Path $flSettings "Hardware\fLMCP Bridge") -ErrorAction SilentlyContinue
Remove-Item -Force (Join-Path $flSettings "Piano roll scripts\ComposeWithLLM.pyscript") -ErrorAction SilentlyContinue

$paths = @(
    (Join-Path $env:APPDATA "Claude\claude_desktop_config.json"),
    (Join-Path $env:USERPROFILE ".claude\mcp_settings.json")
)
foreach ($p in $paths) {
    if (Test-Path $p) {
        $cfg = Get-Content $p -Raw | ConvertFrom-Json -Depth 20
        if ($cfg.mcpServers -and $cfg.mcpServers.'fl-studio-mcp') {
            $cfg.mcpServers.PSObject.Properties.Remove('fl-studio-mcp') | Out-Null
            ($cfg | ConvertTo-Json -Depth 20) | Set-Content -Path $p -Encoding UTF8
            Write-Host "cleaned $p"
        }
    }
}
Write-Host "Uninstalled fLMCP." -ForegroundColor Green
