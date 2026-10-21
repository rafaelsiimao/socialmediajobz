$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$runtime = Join-Path $PSScriptRoot 'media\.local'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if (Test-Path (Join-Path $runtime 'processes.json')) {
    throw 'Use stop-local.ps1 antes de iniciar novamente.'
}
& $python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Falha nas migracoes.' }
$started = @()
try {
    foreach ($service in @(
        @{ Name = 'web'; Args = @('manage.py', 'runserver', '127.0.0.1:8000', '--noreload') },
        @{ Name = 'worker'; Args = @('manage.py', 'process_tasks') }
    )) {
        $process = Start-Process -FilePath $python -ArgumentList $service.Args -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime "$($service.Name).log") -RedirectStandardError (Join-Path $runtime "$($service.Name).error.log")
        $started += @{ Id = $process.Id; Started = $process.StartTime.ToUniversalTime().ToString('o') }
    }
} finally {
    if ($started.Count) { ConvertTo-Json -InputObject @($started) | Set-Content (Join-Path $runtime 'processes.json') }
}
Write-Host 'Aplicacao: http://127.0.0.1:8000'
Write-Host 'Para parar: .\stop-local.ps1'
