<#
Puts the CURRENT Neon connection string into the repository-root .env.

Use it when the backend says:
    password authentication failed for user 'neondb_owner'
which means the password in .env is not the one Neon has any more (it was
reset in the console, or .env was overwritten with an old copy).

    powershell -ExecutionPolicy Bypass -File backend\scripts\sync_neon_url.ps1

What it does:
  1. Finds which Neon branch the current DATABASE_URL points at (by its
     endpoint, ep-xxxx), falling back to the project's default branch.
  2. Asks Neon (neonctl) for that branch's connection string. neonctl reads
     the password from Neon, so it is always the current one.
  3. Rewrites DATABASE_URL (pooled) and DATABASE_URL_UNPOOLED (direct) in
     .env. Nothing else in the file changes. The values are never printed.
  4. Removes a DATABASE_URL set in this terminal or in your Windows user
     environment, either of which silently overrides .env.
  5. Connects once to prove it works.

The first run may open a browser to sign in to Neon (neonctl auth).
#>
param(
    [string]$ProjectId = "cold-math-06667567",
    [string]$Branch    = "",              # name or id; blank = whatever .env points at
    [string]$Database  = "neondb",
    [string]$Role      = "neondb_owner"
)

$ErrorActionPreference = "Stop"

$backend = Split-Path -Parent $PSScriptRoot
$root    = Split-Path -Parent $backend
$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) { throw "No .env at $envFile - copy .env.example to .env first." }

# ── neonctl: installed, or through npx ───────────────────────────────────────
if (Get-Command neonctl -ErrorAction SilentlyContinue) {
    function Neon { & neonctl @args }
} elseif (Get-Command npx -ErrorAction SilentlyContinue) {
    function Neon { & npx --yes neonctl @args }
} else {
    throw "neonctl not found. Install it with:  npm install -g neonctl"
}

function NeonJson([string[]]$a) {
    # Windows PowerShell turns any stderr line from a program into an error,
    # and "Stop" would make a harmless notice fatal. Exit codes are checked instead.
    $ErrorActionPreference = "Continue"
    $raw = (Neon @a --project-id $ProjectId --output json 2>$null) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "neonctl $($a -join ' ') failed." }
    # neonctl (and npx) can print notices - "update available", sign-in
    # messages - before the JSON. Keep only the JSON itself.
    $start = $raw.IndexOfAny([char[]]"[{")
    $end   = $raw.LastIndexOfAny([char[]]"]}")
    if ($start -lt 0 -or $end -lt $start) {
        $preview = if ($raw.Length -gt 400) { $raw.Substring(0, 400) } else { $raw }
        throw "neonctl $($a -join ' ') returned no JSON. It said:`n$preview"
    }
    return $raw.Substring($start, $end - $start + 1) | ConvertFrom-Json
}

# ── 1. Which branch? ─────────────────────────────────────────────────────────
$lines = [IO.File]::ReadAllLines($envFile)
if (-not $Branch) {
    $current = ($lines | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1)
    $endpointId = $null
    if ($current -match '@(ep-[a-z0-9-]+?)(-pooler)?\.') { $endpointId = $Matches[1] }

    if ($endpointId) {
        $eps = NeonJson @("endpoints", "list")
        if ($eps.endpoints) { $eps = $eps.endpoints }
        $match = $eps | Where-Object { $_.id -eq $endpointId } | Select-Object -First 1
        if ($match) {
            $Branch = $match.branch_id
            Write-Host "  .env points at endpoint $endpointId (branch $Branch)."
        } else {
            # Do not guess: picking some other branch would point the app at a
            # different database that merely accepts the password.
            throw ("Endpoint $endpointId is not in Neon project $ProjectId. " +
                   "Run again with -Branch <branch name> (and -ProjectId if it is another project).")
        }
    }
    if (-not $Branch) {
        $brs = NeonJson @("branches", "list")
        if ($brs.branches) { $brs = $brs.branches }
        $default = $brs | Where-Object { $_.default -eq $true } | Select-Object -First 1
        if (-not $default) { throw "Could not find the default branch. Run again with -Branch <name>." }
        $Branch = $default.id
        Write-Host "  Using the project's default branch: $($default.name) ($Branch)."
    }
}

# ── 2. Ask Neon for the current strings ──────────────────────────────────────
function ConnString([bool]$pooled) {
    $ErrorActionPreference = "Continue"
    $a = @("connection-string", $Branch, "--project-id", $ProjectId,
           "--database-name", $Database, "--role-name", $Role)
    if ($pooled) { $a += "--pooled" }
    $raw = ((Neon @a 2>$null) -join "`n")
    # Pick the URL out of whatever else was printed around it.
    if ($LASTEXITCODE -ne 0 -or $raw -notmatch '(postgres(ql)?://[^\s"'']+)') {
        throw "neonctl did not return a connection string. Check the project, branch, database and role names."
    }
    return $Matches[1]
}
$pooledUrl = ConnString $true
$directUrl = ConnString $false

# ── 3. Rewrite only those two lines ──────────────────────────────────────────
$seenPooled = $false; $seenDirect = $false
$out = foreach ($l in $lines) {
    if ($l -match '^\s*DATABASE_URL\s*=') { $seenPooled = $true; "DATABASE_URL=""$pooledUrl"""; continue }
    if ($l -match '^\s*DATABASE_URL_UNPOOLED\s*=') { $seenDirect = $true; "DATABASE_URL_UNPOOLED=""$directUrl"""; continue }
    $l
}
if (-not $seenPooled) { $out += "DATABASE_URL=""$pooledUrl""" }
if (-not $seenDirect) { $out += "DATABASE_URL_UNPOOLED=""$directUrl""" }

Copy-Item $envFile "$envFile.bak" -Force          # .env.* is gitignored
[IO.File]::WriteAllText($envFile, (($out -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding($false)))

$hostOnly = ([Uri]($pooledUrl -replace '^postgres(ql)?://', 'http://')).Host
Write-Host "  .env updated -> $hostOnly/$Database  (previous copy: .env.bak)"

# ── 4. Overrides that would hide .env ────────────────────────────────────────
if (Test-Path Env:DATABASE_URL) {
    Remove-Item Env:DATABASE_URL
    Write-Host "  Removed DATABASE_URL set in this terminal (it overrode .env)."
}
if ([Environment]::GetEnvironmentVariable("DATABASE_URL", "User")) {
    [Environment]::SetEnvironmentVariable("DATABASE_URL", $null, "User")
    Write-Host "  Removed DATABASE_URL from your Windows user environment (it overrode .env)."
    Write-Host "  Open a NEW terminal before starting the backend."
}

# ── 5. Prove it ──────────────────────────────────────────────────────────────
$py = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
Push-Location $backend
try {
    & $py -c "import asyncio; from sqlalchemy import text; from app.db.session import AsyncSessionLocal`nasync def m():`n    async with AsyncSessionLocal() as s: await s.execute(text('select 1'))`nasyncio.run(m()); print('  Connected to the database OK.')"
    if ($LASTEXITCODE -ne 0) { throw "Still cannot connect - see the error above." }
} finally { Pop-Location }

Write-Host ""
Write-Host "  Done. Restart the backend:  uvicorn app.main:app --reload --port 8000"
