# install.ps1 -- vibe-coding-tools setup script
# Run once on a new machine: cd vibe-coding-tools; .\install.ps1

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot

Write-Host ""
Write-Host "=== vibe-coding-tools installer ===" -ForegroundColor Cyan
Write-Host ""

# -- 1. Check Python ---------------------------------------------------------
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    Write-Host "      OK: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "      ERROR: Python not found. Install from python.org and retry." -ForegroundColor Red
    exit 1
}

# -- 2. Check repo location --------------------------------------------------
Write-Host "[2/5] Checking repo location..." -ForegroundColor Yellow
$expectedPath = "$env:USERPROFILE\vibe-coding-tools"
if ($repoRoot -ne $expectedPath) {
    Write-Host "      WARNING: repo is at $repoRoot" -ForegroundColor Yellow
    Write-Host "               recommended: $expectedPath" -ForegroundColor Yellow
    Write-Host "               Continuing from current location." -ForegroundColor Yellow
} else {
    Write-Host "      OK: $repoRoot" -ForegroundColor Green
}

# -- 3. Install /blog command ------------------------------------------------
Write-Host "[3/5] Installing /blog command..." -ForegroundColor Yellow
$commandsDir = "$env:USERPROFILE\.claude\commands"
New-Item -ItemType Directory -Force -Path $commandsDir | Out-Null
$blogSrc = Join-Path $repoRoot "claude\commands\blog.md"
$blogDst = Join-Path $commandsDir "blog.md"
Copy-Item -Path $blogSrc -Destination $blogDst -Force
Write-Host "      OK: $blogDst" -ForegroundColor Green

# -- 4. Install SessionEnd hook ----------------------------------------------
Write-Host "[4/5] Installing SessionEnd hook..." -ForegroundColor Yellow
$hooksDir = "$env:USERPROFILE\.claude\hooks"
New-Item -ItemType Directory -Force -Path $hooksDir | Out-Null
$hookSrc = Join-Path $repoRoot "claude\hooks\archive_session.py"
$hookDst = Join-Path $hooksDir "archive_session.py"
Copy-Item -Path $hookSrc -Destination $hookDst -Force
Write-Host "      OK: $hookDst" -ForegroundColor Green

# -- 5. Register hook in settings.json --------------------------------------
Write-Host "[5/5] Registering hook in settings.json..." -ForegroundColor Yellow
$settingsPath = "$env:USERPROFILE\.claude\settings.json"

if (Test-Path $settingsPath) {
    $settings = Get-Content $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
} else {
    $settings = [PSCustomObject]@{}
}

$alreadyInstalled = $false
if ($settings.PSObject.Properties["hooks"] -and
    $settings.hooks.PSObject.Properties["SessionEnd"]) {
    foreach ($group in $settings.hooks.SessionEnd) {
        foreach ($h in $group.hooks) {
            if ($h.command -like "*archive_session.py*") {
                $alreadyInstalled = $true
                break
            }
        }
    }
}

if ($alreadyInstalled) {
    Write-Host "      OK: already registered." -ForegroundColor Green
} else {
    if (-not $settings.PSObject.Properties["hooks"]) {
        $settings | Add-Member -NotePropertyName "hooks" -NotePropertyValue ([PSCustomObject]@{})
    }
    if (-not $settings.hooks.PSObject.Properties["SessionEnd"]) {
        $settings.hooks | Add-Member -NotePropertyName "SessionEnd" -NotePropertyValue @()
    }

    $newEntry = [PSCustomObject]@{
        matcher = ""
        hooks   = @(
            [PSCustomObject]@{
                type    = "command"
                command = 'python "%USERPROFILE%\.claude\hooks\archive_session.py"'
            }
        )
    }
    $settings.hooks.SessionEnd += $newEntry

    $json = $settings | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($settingsPath, $json, [System.Text.UTF8Encoding]::new($false))
    Write-Host "      OK: $settingsPath updated." -ForegroundColor Green
}

# -- Done --------------------------------------------------------------------
Write-Host ""
Write-Host "=== Installation complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Restart Claude Code (so /blog is recognized)" -ForegroundColor White
Write-Host "  2. Connect Notion MCP  (Claude Code > Settings > MCP)" -ForegroundColor White
Write-Host "  3. Run /blog in any session" -ForegroundColor White
Write-Host ""
Write-Host "Repo:        $repoRoot" -ForegroundColor Gray
Write-Host "/blog cmd:   $blogDst" -ForegroundColor Gray
Write-Host "Hook:        $hookDst" -ForegroundColor Gray
Write-Host ""
