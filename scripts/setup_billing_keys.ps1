# Prompts for the Lemon Squeezy credentials and writes them into .env.
#
# Run it with Setup_Billing_Keys.bat in the flask_app folder.
#
# The values you type go straight from your keyboard into .env on this machine.
# The API key is masked as you type and is never printed back, never logged, and
# never sent anywhere. .env is gitignored, so it cannot reach GitHub.
#
# Safe to run more than once. Anything you leave blank keeps its current value,
# so you can fill in one field today and the rest later.

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

function New-WebhookSecret {
    $chars = (48..57) + (65..90) + (97..122)
    return -join ($chars | Get-Random -Count 48 | ForEach-Object { [char]$_ })
}

# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  Digital Product Factory - Lemon Squeezy key setup" -ForegroundColor White
Write-Host ""

if (-not (Test-Path $EnvPath)) {
    Write-Host "Could not find .env at:" -ForegroundColor Red
    Write-Host "  $EnvPath"
    Write-Host ""
    Write-Host "Nothing was changed."
    exit 1
}

$lines = [System.IO.File]::ReadAllLines($EnvPath)

Write-Title "What is set right now"
foreach ($k in @("LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_WEBHOOK_SECRET",
                 "LEMONSQUEEZY_STORE_ID", "FACTORY_PUBLIC_URL")) {
    $v = Get-EnvValue $lines $k
    if ($k -eq "FACTORY_PUBLIC_URL") {
        # Not a secret - showing it helps you match the webhook URL.
        $shown = if ($v) { $v } else { "(not set)" }
        Write-Host ("  {0,-30} {1}" -f $k, $shown)
    } elseif ($v) {
        Write-Host ("  {0,-30} already set" -f $k) -ForegroundColor Green
    } else {
        Write-Host ("  {0,-30} empty" -f $k) -ForegroundColor Yellow
    }
}

# --- 1. API key ------------------------------------------------------------
Write-Title "1 of 2 - Lemon Squeezy API key"
Write-Host "  Dashboard -> Settings -> API -> create a key, with TEST MODE on."
Write-Host "  Your typing is hidden. Press Enter alone to keep the current value."
Write-Host ""

$apiKey = Read-Secret "  Paste the API key"
if ($apiKey.Trim().Length -gt 0) {
    $apiKey = $apiKey.Trim()
    if ($apiKey.Length -lt 20) {
        Write-Host ""
        Write-Host "  That looks too short for a Lemon Squeezy key. Not saved." -ForegroundColor Red
        Write-Host "  Run this again and paste the whole value."
        exit 1
    }
    $lines = Set-EnvValue $lines "LEMONSQUEEZY_API_KEY" $apiKey
    Write-Host "  Saved ($($apiKey.Length) characters)." -ForegroundColor Green
} else {
    Write-Host "  Left unchanged." -ForegroundColor DarkGray
}

# --- 2. Webhook secret -----------------------------------------------------
Write-Title "2 of 2 - Webhook signing secret"
Write-Host "  This is a password YOU invent. The same value goes in two places:"
Write-Host "  here, and in the Lemon Squeezy webhook settings."
Write-Host ""
Write-Host "  Press Enter and I will generate a strong one for you," -ForegroundColor White
Write-Host "  or type your own." -ForegroundColor White
Write-Host ""

$hook = Read-Host "  Webhook secret (Enter to generate)"
$generated = $false
if ($hook.Trim().Length -eq 0) {
    $existing = Get-EnvValue $lines "LEMONSQUEEZY_WEBHOOK_SECRET"
    if ($existing) {
        Write-Host ""
        $replace = Read-Host "  A secret is already set. Replace it? (y/N)"
        if ($replace -notmatch '^[Yy]') {
            $hook = $existing
            Write-Host "  Keeping the existing secret." -ForegroundColor DarkGray
        } else {
            $hook = New-WebhookSecret
            $generated = $true
        }
    } else {
        $hook = New-WebhookSecret
        $generated = $true
    }
}
$hook = $hook.Trim()
$lines = Set-EnvValue $lines "LEMONSQUEEZY_WEBHOOK_SECRET" $hook

# --- write -----------------------------------------------------------------
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($EnvPath, $lines, $utf8NoBom)

Write-Title "Saved to .env"
Write-Host "  $EnvPath" -ForegroundColor DarkGray

$publicUrl = Get-EnvValue $lines "FACTORY_PUBLIC_URL"

Write-Title "Now put these two things into Lemon Squeezy"
Write-Host "  Settings -> Webhooks -> add endpoint"
Write-Host ""
Write-Host "  Callback URL:" -ForegroundColor White
if ($publicUrl) {
    Write-Host "    $publicUrl/billing/webhook/lemonsqueezy" -ForegroundColor Green
} else {
    Write-Host "    (FACTORY_PUBLIC_URL is not set - ask Claude for the tunnel URL)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Signing secret:" -ForegroundColor White
Write-Host "    $hook" -ForegroundColor Green
if ($generated) {
    Write-Host ""
    Write-Host "    ^ generated for you. Copy it into Lemon Squeezy now -" -ForegroundColor DarkGray
    Write-Host "      it is saved in .env, so you can re-run this file to see it again." -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "  Events to enable:" -ForegroundColor White
foreach ($e in @("subscription_created", "subscription_cancelled",
                 "subscription_expired", "subscription_payment_failed",
                 "subscription_resumed")) {
    Write-Host "    $e"
}

Write-Title "Next"
Write-Host "  Tell Claude the keys are in. The app has to be restarted to read"
Write-Host "  them, and then the four product IDs still need filling in."
Write-Host ""
