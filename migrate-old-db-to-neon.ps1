<#
  Move the data from the old local Docker Postgres into Neon.

  TWO PHASES — inspect before you overwrite anything.

      .\migrate-old-db-to-neon.ps1              # phase 1: look, change nothing
      .\migrate-old-db-to-neon.ps1 -Restore     # phase 2: actually copy it over

  Phase 1 brings the old database back up from its Docker volume and prints
  what is in it — row counts and the actual employee list. Nothing is written
  anywhere. Read that output and decide whether it is the data you want.

  Phase 2 backs up the current Neon contents to a file, then replaces them with
  the old database. Neon currently holds only seed data, so there is little to
  lose, but the backup means the step is reversible either way.

  Requires Docker Desktop running.
#>

param(
    [switch]$Restore
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

$OldDb   = 'biometric'      # database name in the old container
$OldUser = 'grid'           # role in the old container
$Container = 'gridsphere_db'

function Section($text) {
    Write-Host ""
    Write-Host "── $text " -ForegroundColor Cyan -NoNewline
    Write-Host ("─" * [Math]::Max(0, 60 - $text.Length)) -ForegroundColor DarkCyan
}

# ── read the Neon direct URL out of .env ─────────────────────────────────────
# The POOLED endpoint cannot be used for a restore: it is PgBouncer in
# transaction mode, which breaks pg_restore's session state halfway through and
# leaves the database half-populated. DATABASE_URL_UNPOOLED is the direct one.
function Get-EnvValue($key) {
    $line = Select-String -Path (Join-Path $root '.env') -Pattern "^\s*$key\s*=" |
            Select-Object -First 1
    if (-not $line) { return $null }
    $v = ($line.Line -split '=', 2)[1].Trim()
    return $v.Trim('"').Trim("'")
}

$neonUrl = Get-EnvValue 'DATABASE_URL_UNPOOLED'
if (-not $neonUrl) { $neonUrl = Get-EnvValue 'DATABASE_URL' }
if (-not $neonUrl) { throw "Could not read a Neon URL from .env" }
if ($neonUrl -match '-pooler\.') {
    Write-Host "WARNING: only the pooled Neon URL was found. pg_restore over PgBouncer" -ForegroundColor Yellow
    Write-Host "         is unreliable. Add DATABASE_URL_UNPOOLED to .env first." -ForegroundColor Yellow
    if ($Restore) { throw "Refusing to restore through the pooled endpoint." }
}

# ── make sure Docker is up ───────────────────────────────────────────────────
docker version --format '{{.Server.Version}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Start it, wait for 'Engine running', then re-run."
}

# ── bring the old database back ──────────────────────────────────────────────
Section "Old database"

$existing = docker ps -a --filter "name=^/$Container$" --format '{{.Names}}'
if ($existing -eq $Container) {
    Write-Host "Container '$Container' still exists - starting it." -ForegroundColor Green
    docker start $Container | Out-Null
} else {
    # Container was removed but the volume outlives it. Find it and mount it.
    $volumes = @(docker volume ls --format '{{.Name}}' | Where-Object { $_ -match 'pgdata' })
    if ($volumes.Count -eq 0) {
        throw "No Docker volume matching 'pgdata' found. The old data is gone - nothing to migrate."
    }
    if ($volumes.Count -gt 1) {
        Write-Host "Several candidate volumes found:" -ForegroundColor Yellow
        $volumes | ForEach-Object { Write-Host "    $_" }
        Write-Host "Edit `$vol in this script to pick one, then re-run." -ForegroundColor Yellow
    }
    $vol = $volumes[0]
    Write-Host "Mounting volume '$vol' on a temporary container." -ForegroundColor Green
    # POSTGRES_* is ignored when the data directory already exists - initdb is
    # skipped and the original roles and passwords are kept.
    docker run -d --name $Container -v "${vol}:/var/lib/postgresql/data" -p 5432:5432 postgres:16 | Out-Null
}

Write-Host "Waiting for Postgres to accept connections..." -NoNewline
for ($i = 0; $i -lt 30; $i++) {
    docker exec $Container pg_isready -U $OldUser -d $OldDb 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
    Write-Host "." -NoNewline
}
Write-Host ""
if ($LASTEXITCODE -ne 0) { throw "Old Postgres never became ready. Check: docker logs $Container" }

# ── show what is actually in there ───────────────────────────────────────────
Section "What the old database contains"

$counts = @"
SELECT 'tenants' AS table, count(*) FROM tenants
UNION ALL SELECT 'departments', count(*) FROM departments
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'devices', count(*) FROM devices
UNION ALL SELECT 'attendance_logs', count(*) FROM attendance_logs
UNION ALL SELECT 'tasks', count(*) FROM tasks
ORDER BY 1;
"@
docker exec $Container psql -U $OldUser -d $OldDb -c $counts

Section "Employees in the old database"
docker exec $Container psql -U $OldUser -d $OldDb -c `
  "SELECT id, employee_code, name, email, role FROM users ORDER BY role, id;"

if (-not $Restore) {
    Write-Host ""
    Write-Host "Phase 1 complete - nothing was changed." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Look at the employee list above." -ForegroundColor Yellow
    Write-Host "  If it is the data you want in Neon, re-run with:" -ForegroundColor Yellow
    Write-Host "      .\migrate-old-db-to-neon.ps1 -Restore" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  If it only shows the 5 test employees, this volume holds nothing" -ForegroundColor Yellow
    Write-Host "  but seed data and there is no point copying it." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Stop the container when done:  docker stop $Container" -ForegroundColor DarkGray
    exit 0
}

# ── phase 2 ──────────────────────────────────────────────────────────────────
Section "Backing up current Neon contents"

# Reversibility first. This runs inside the container so no local psql needed.
$backupCmd = "pg_dump --no-owner --no-privileges -Fc --dbname='$neonUrl' -f /tmp/neon-before.dump"
docker exec $Container sh -c $backupCmd
if ($LASTEXITCODE -ne 0) { throw "Could not back up Neon. Stopping before any destructive step." }
docker cp "${Container}:/tmp/neon-before.dump" (Join-Path $root 'neon-before-restore.dump')
Write-Host "Saved neon-before-restore.dump" -ForegroundColor Green

Section "Dumping the old database"
docker exec $Container pg_dump -U $OldUser -d $OldDb --no-owner --no-privileges -Fc -f /tmp/old.dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump of the old database failed." }
docker cp "${Container}:/tmp/old.dump" (Join-Path $root 'old-database.dump')
Write-Host "Saved old-database.dump" -ForegroundColor Green

Section "Restoring into Neon"

# --clean --if-exists drops each object before recreating it, so the seeded
# rows and their id sequences go too. Without it the restore collides on
# tenant id=1 and every seeded user id.
$restoreCmd = "pg_restore --clean --if-exists --no-owner --no-privileges " +
              "--dbname='$neonUrl' /tmp/old.dump"
docker exec $Container sh -c $restoreCmd

# pg_restore returns non-zero for benign 'does not exist' notices on --clean.
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "pg_restore reported warnings (exit $LASTEXITCODE)." -ForegroundColor Yellow
    Write-Host "That is normal for --clean on a fresh target - it complains about" -ForegroundColor Yellow
    Write-Host "dropping objects that were not there. Verify below before worrying." -ForegroundColor Yellow
}

Section "Verifying Neon"
$verify = "psql '$neonUrl' -c ""SELECT id, employee_code, name, email, role FROM users ORDER BY role, id;"""
docker exec $Container sh -c $verify

Write-Host ""
Write-Host "Done. If that list matches the old database, the migration worked." -ForegroundColor Cyan
Write-Host ""
Write-Host "Then:" -ForegroundColor Yellow
Write-Host "    docker stop $Container        # old database no longer needed"
Write-Host "    cd backend; alembic current   # confirm the migration version came across"
Write-Host ""
Write-Host "To undo, restore neon-before-restore.dump the same way." -ForegroundColor DarkGray
