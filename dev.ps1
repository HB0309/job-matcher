# dev.ps1 — start backend + frontend in parallel
# Backend:  uvicorn --reload  (auto-restarts on .py changes)
# Frontend: next dev          (HMR, auto-reloads on .ts/.tsx changes)
#
# Usage:  .\dev.ps1
# Stop:   Ctrl+C  (kills both processes)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$backendBlock = {
    param($r)
    Set-Location "$r\backend"
    python -m uvicorn app.main:app --reload --port 8000
}

$frontendBlock = {
    param($r)
    Set-Location "$r\frontend"
    npm run dev
}

$backendJob  = Start-Job -ScriptBlock $backendBlock  -ArgumentList $root -Name "backend"
$frontendJob = Start-Job -ScriptBlock $frontendBlock -ArgumentList $root -Name "frontend"

Write-Host "Backend  -> http://localhost:8000" -ForegroundColor Cyan
Write-Host "Frontend -> http://localhost:3000" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop both.`n" -ForegroundColor Yellow

try {
    while ($true) {
        Receive-Job -Job $backendJob  | ForEach-Object { Write-Host "[backend]  $_" -ForegroundColor Cyan }
        Receive-Job -Job $frontendJob | ForEach-Object { Write-Host "[frontend] $_" -ForegroundColor Green }

        if ($backendJob.State -in "Failed","Completed") {
            Write-Host "[backend] crashed — restarting..." -ForegroundColor Red
            Remove-Job $backendJob -Force
            $backendJob = Start-Job -ScriptBlock $backendBlock -ArgumentList $root -Name "backend"
        }
        if ($frontendJob.State -in "Failed","Completed") {
            Write-Host "[frontend] crashed — restarting..." -ForegroundColor Red
            Remove-Job $frontendJob -Force
            $frontendJob = Start-Job -ScriptBlock $frontendBlock -ArgumentList $root -Name "frontend"
        }

        Start-Sleep -Milliseconds 500
    }
} finally {
    Write-Host "`nStopping servers..." -ForegroundColor Yellow
    Stop-Job  $backendJob, $frontendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob, $frontendJob -Force -ErrorAction SilentlyContinue
    Write-Host "Done." -ForegroundColor Yellow
}
