# dex.ps1 — Dex Jr. CLI router (mobile-first)
# Usage: dex <command> [args]
#
# Step 54.2 | Dropdown Logistics

param(
    [Parameter(Position=0)]
    [string]$Command,
    [Parameter(Position=1, ValueFromRemainingArguments)]
    [string[]]$Rest
)

$script_dir = Split-Path -Parent $MyInvocation.MyCommand.Path

switch ($Command) {
    { $_ -in "q", "query" }   { python "$script_dir\dex_jr_query.py" @Rest }
    { $_ -in "c", "council" } { python "$script_dir\dex-council.py" @Rest }
    "health"                   { python "$script_dir\dex_health.py" @Rest }
    "status"                   { python "$script_dir\dex_health.py" --quick @Rest }
    "sweep"                    { python "$script_dir\dex-sweep.py" @Rest }
    "backup"                   { python "$script_dir\dex-backup.py" @Rest }
    "ingest"                   { python "$script_dir\dex-ingest.py" --path @Rest }
    "hosts"                    { python "$script_dir\dex-council.py" --host-status @Rest }
    "weights"                  { python "$script_dir\dex_weights.py" --stats @Rest }
    "api"                      { python "$script_dir\dex-search-api.py" @Rest }
    "log" {
        Get-Content "$script_dir\dex-council-log.jsonl" -Encoding UTF8 |
            Select-Object -Last 5 |
            ForEach-Object {
                $d = $_ | ConvertFrom-Json
                $p = $d.prompt
                if ($p.Length -gt 60) { $p = $p.Substring(0, 60) + "..." }
                "$($d.timestamp.Substring(0,16)) | v$($d.version) | $($d.successful)/$($d.model_count) ok | $p"
            }
    }
    default {
        Write-Host ""
        Write-Host "  dex <command> [args]"
        Write-Host ""
        Write-Host "  q, query    Query the corpus"
        Write-Host "  c, council  Run AutoCouncil"
        Write-Host "  health      Full health check (--quick for fast)"
        Write-Host "  status      Quick corpus status"
        Write-Host "  hosts       Host connectivity check"
        Write-Host "  sweep       Run nightly sweep"
        Write-Host "  backup      Run backup"
        Write-Host "  ingest      Ingest files from path"
        Write-Host "  weights     Show weight table"
        Write-Host "  api         Start search API server"
        Write-Host "  log         Last 5 council runs"
        Write-Host ""
    }
}
