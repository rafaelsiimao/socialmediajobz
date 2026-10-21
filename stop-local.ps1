$ErrorActionPreference = 'Stop'
$state = Join-Path $PSScriptRoot 'media\.local\processes.json'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$commands = @(
    ('"' + $python + '" manage.py runserver 127.0.0.1:8000 --noreload'),
    ('"' + $python + '" manage.py process_tasks')
)
# Windows venv launchers create a second Python process. Stop both, and
# match the complete command to avoid affecting other Python applications.
foreach ($process in @(Get-CimInstance Win32_Process -Filter "name='python.exe'")) {
    if ($process.CommandLine -in $commands) {
        Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
    }
}
if (Test-Path $state) { Remove-Item -LiteralPath $state }
Write-Host 'Aplicacao e worker locais encerrados.'
