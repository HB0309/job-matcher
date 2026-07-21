# Start both backend and frontend dev servers
$root = $PSScriptRoot

Write-Host "Starting backend (uvicorn)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; uvicorn app.main:app --reload --port 8000"

Write-Host "Starting frontend (Next.js)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Write-Host "Both servers starting. Backend: http://localhost:8000 | Frontend: http://localhost:3000" -ForegroundColor Green
