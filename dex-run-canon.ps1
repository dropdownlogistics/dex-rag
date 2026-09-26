# dex-run-canon.ps1
# Dex Jr — Sleep-safe Canon Backfill Runner (Windows)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Prevent system sleep
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class SleepBlock {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

function Disable-Sleep {
  $flag = [UInt32]::Parse("80000001", [System.Globalization.NumberStyles]::HexNumber)
  [void][SleepBlock]::SetThreadExecutionState($flag)
}

function Restore-Sleep {
  $flag = [UInt32]::Parse("80000000", [System.Globalization.NumberStyles]::HexNumber)
  [void][SleepBlock]::SetThreadExecutionState($flag)
}

function Resolve-PythonCommand {
  foreach ($c in @("python","py")) {
    & $c --version *> $null
    if ($LASTEXITCODE -eq 0) { return $c }
  }
  throw "Python not found in PATH."
}

function Ensure-PythonDeps {
  param([string]$PythonCmd)

  foreach ($pkg in @("requests","chromadb")) {
    & $PythonCmd -m pip show $pkg *> $null
    if ($LASTEXITCODE -ne 0) {
      Write-Host "Installing: $pkg" -ForegroundColor Yellow
      & $PythonCmd -m pip install $pkg --no-cache-dir
    }
    else {
      Write-Host "OK: $pkg already installed" -ForegroundColor Green
    }
  }
}

# ===== MAIN =====

$ARCHIVE_PATH = "C:\Users\dexjr\99_DexUniverseArchive"

Write-Host ""
Write-Host "DEX JR — CANON BACKFILL STARTING" -ForegroundColor Green
Write-Host "Archive: $ARCHIVE_PATH"
Write-Host "Blocking sleep for the duration of this run."
Write-Host ""

Disable-Sleep
Write-Host "✅ Sleep blocked." -ForegroundColor Green

try {

  $py = Resolve-PythonCommand

  Write-Host ""
  Write-Host "Checking Python dependencies..."
  Ensure-PythonDeps $py

  Write-Host ""
  Write-Host "Launching canon backfill..."
  Write-Host "$py dex-ingest.py --build-canon --path $ARCHIVE_PATH"
  Write-Host ""

  & $py dex-ingest.py --build-canon --path $ARCHIVE_PATH

  if ($LASTEXITCODE -ne 0) {
    throw "dex-ingest.py exited with code $LASTEXITCODE"
  }

}
finally {

  Restore-Sleep

  Write-Host ""
  Write-Host "DEX JR — CANON BACKFILL COMPLETE"
  Write-Host "Sleep behavior restored."
  Write-Host ""

}
