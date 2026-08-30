# Prompts for the Factory's AI/research API keys and writes them into .env.
#
# Run it with Setup_API_Keys.bat in the flask_app folder.
#
# The values you type go straight from your keyboard into .env on this machine.
# Every key is masked as you type and is never printed back, never logged, and
# never sent anywhere. .env is gitignored, so it cannot reach GitHub.
#
# Safe to run more than once. Anything you leave blank keeps its current value,
# so you can fill in one key today and the rest later.
#
# OPENAI_API_KEY is written twice on purpose: app.py reads OPENAI_API_KEY and
# the integrations layer reads AI_INTEGRATIONS_OPENAI_API_KEY. They are always
# the same key, and letting them drift apart is its own outage, so this script
# keeps them in sync rather than asking twice.

$ErrorActionPreference = "Stop"

$AppDir  = Split-Path $PSScriptRoot -Parent
$EnvPath = Join-Path $AppDir ".env"

function Write-Title($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Cyan
    Write-Host ("-" * 66) -ForegroundColor DarkGray
}

function Get-EnvValue($lines, $key) {
    foreach ($l in $lines) {
        if ($l -match "^$([regex]::Escape($key))=(.*)$") { return $Matches[1] }
    }
    return ""
}

function Set-EnvValue($lines, $key, $value) {
    $found = $false
    $out = @()
    foreach ($l in $lines) {
        if ($l -match "^$([regex]::Escape($key))=") {
            $out += "$key=$value"
            $found = $true
        } else {
            $out += $l
        }
    }
    if (-not $found) { $out += "$key=$value" }
    return $out
}

function Read-Secret($prompt) {
    $secure = Read-Host -Prompt $prompt -AsSecureString
    $ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

# Returns $true if the key was saved, $false if left unchanged.
function Set-KeyInteractive {
    param(
        [string[]]$Prefix,      # expected key prefixes, e.g. @("sk-")
        [int]$MinLength,
        [string[]]$EnvNames     # one or more .env names to write the same value to
    )
    $value = Read-Secret "  Paste the key"
    if ($value.Trim().Length -eq 0) {
        Write-Host "  Left unchanged." -ForegroundColor DarkGray
        return $false
    }
    $value = $value.Trim()
    if ($value.Length -lt $MinLength) {
        Write-Host ""
        Write-Host "  That looks too short ($($value.Length) characters). Not saved." -ForegroundColor Red
        Write-Host "  Run this again and paste the whole value."
        return $false
    }
    if ($Prefix.Count -gt 0) {
        $ok = $false
        foreach ($p in $Prefix) { if ($value.StartsWith($p)) { $ok = $true } }
        if (-not $ok) {
            Write-Host ""
            Write-Host "  That does not start with $($Prefix -join ' or '). Not saved." -ForegroundColor Red
            Write-Host "  Check you copied the right key."
            return $false
        }
    } else {
        # No positive prefix to check (Pexels has none), so check negatively
        # instead: reject a key that plainly belongs to one of the other
        # services. Pasting the same key into two prompts is an easy slip, and
        # Pexels' search endpoint answers 200 even for a junk key -- so without
        # this guard a wrong key here fails silently, much later, on a cover.
        foreach ($foreign in @(@("sk-", "OpenAI"), @("tvly-", "Tavily"))) {
            if ($value.StartsWith($foreign[0])) {
                Write-Host ""
                Write-Host "  That looks like your $($foreign[1]) key (it starts with '$($foreign[0])'). Not saved." -ForegroundColor Red
                Write-Host "  Each service needs its own key -- check you copied the right one."
                return $false
            }
        }
    }
    foreach ($name in $EnvNames) {
        $script:lines = Set-EnvValue $script:lines $name $value
    }
    Write-Host "  Saved ($($value.Length) characters)." -ForegroundColor Green
    return $true
}

# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  Digital Product Factory - API key setup" -ForegroundColor White
Write-Host ""

if (-not (Test-Path $EnvPath)) {
    Write-Host "Could not find .env at:" -ForegroundColor Red
    Write-Host "  $EnvPath"
    Write-Host ""
    Write-Host "Nothing was changed."
    exit 1
}

$script:lines = [System.IO.File]::ReadAllLines($EnvPath)

Write-Title "What is set right now"
foreach ($k in @("OPENAI_API_KEY", "TAVILY_API_KEY", "PEXELS_API_KEY")) {
    $v = Get-EnvValue $script:lines $k
    if ($v) {
        Write-Host ("  {0,-24} already set ({1} characters)" -f $k, $v.Length) -ForegroundColor Green
    } else {
        Write-Host ("  {0,-24} empty" -f $k) -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "  Press Enter alone at any prompt to keep the current value." -ForegroundColor DarkGray

$changed = $false

# --- 1. OpenAI -------------------------------------------------------------
Write-Title "1 of 3 - OpenAI API key  (required: research, ebooks, covers)"
Write-Host "  platform.openai.com -> API keys -> Create new secret key."
Write-Host "  Starts with sk-. Your typing is hidden."
Write-Host ""
if (Set-KeyInteractive -Prefix @("sk-") -MinLength 40 `
        -EnvNames @("OPENAI_API_KEY", "AI_INTEGRATIONS_OPENAI_API_KEY")) {
    $changed = $true
    Write-Host "  Written to both OPENAI_API_KEY and AI_INTEGRATIONS_OPENAI_API_KEY." -ForegroundColor DarkGray
}

# --- 2. Tavily -------------------------------------------------------------
Write-Title "2 of 3 - Tavily API key  (live web research in Market Advantage)"
Write-Host "  app.tavily.com -> API keys. Starts with tvly-."
Write-Host "  Without it, research still runs but uses fewer outside sources."
Write-Host ""
if (Set-KeyInteractive -Prefix @("tvly-") -MinLength 20 -EnvNames @("TAVILY_API_KEY")) {
    $changed = $true
}

# --- 3. Pexels -------------------------------------------------------------
Write-Title "3 of 3 - Pexels API key  (stock photos for ebook covers)"
Write-Host "  pexels.com/api -> your API key. No fixed prefix."
Write-Host ""
if (Set-KeyInteractive -Prefix @() -MinLength 20 -EnvNames @("PEXELS_API_KEY")) {
    $changed = $true
}

# --- write -----------------------------------------------------------------
if (-not $changed) {
    Write-Title "Nothing changed"
    Write-Host "  No keys were entered, so .env was left exactly as it was."
    Write-Host ""
    exit 0
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($EnvPath, $script:lines, $utf8NoBom)

Write-Title "Saved to .env"
Write-Host "  $EnvPath" -ForegroundColor DarkGray

Write-Title "Next"
Write-Host "  The app has to be restarted to read the new keys."
Write-Host "  Close the Factory window and start it again, or tell Claude"
Write-Host "  the keys are in and it will restart the app for you."
Write-Host ""
