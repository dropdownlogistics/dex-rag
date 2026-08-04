# =============================================================================
#  verify-dex-wake-persistence.ps1
#  Run this AFTER a reboot. It answers one question: did dex-wake come back by
#  itself, with nobody logged in?
#
#  You do not need to know anything about dex-wake to run this.
#  Just run it and read the VERDICT line at the bottom.
#
#  Author: Ellis Cooper (DDL-4008), 2026-08-03. See ADR-DEXJR-WAKE-001.
# =============================================================================

$ErrorActionPreference = 'Continue'
$rows = [System.Collections.ArrayList]::new()
function Add-Row($n,$exp,$act,$res){ [void]$rows.Add([pscustomobject]@{Check=$n;Expected=$exp;Actual=$act;Result=$res}) }
function PF($b){ if($b){'PASS'}else{'FAIL'} }

$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
Write-Output ""
Write-Output "Last boot: $boot"
Write-Output "Now      : $(Get-Date)"
Write-Output ""

# --- 1. task registered and enabled -----------------------------------------
$task = Get-ScheduledTask -TaskName 'DexWake-Persistent' -ErrorAction SilentlyContinue
if(-not $task){
  Add-Row 'task DexWake-Persistent is registered' 'present' 'NOT FOUND' 'FAIL'
} else {
  Add-Row 'task DexWake-Persistent is registered' 'present' 'present' 'PASS'
  Add-Row 'task is enabled' 'Enabled' $task.State (PF($task.State -ne 'Disabled'))
}

# --- 2. it ran, and it ran BECAUSE of this boot ------------------------------
$info = Get-ScheduledTaskInfo -TaskName 'DexWake-Persistent' -ErrorAction SilentlyContinue
if($info){
  $ranAfterBoot = ($info.LastRunTime -ne $null) -and ($info.LastRunTime -gt $boot)
  Add-Row 'task last ran AFTER the last boot' "> $boot" "$($info.LastRunTime)" (PF $ranAfterBoot)
  # 267009 = currently running. 0 = completed OK.
  $okResult = ($info.LastTaskResult -eq 267009) -or ($info.LastTaskResult -eq 0)
  Add-Row 'task result is running/ok' '267009 (running) or 0' "$($info.LastTaskResult)" (PF $okResult)
} else {
  Add-Row 'task last ran AFTER the last boot' "> $boot" 'no task info' 'FAIL'
}

# --- 3. the service actually answers, and identifies itself ------------------
$code=0; $body=''
try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8789/healthz' -TimeoutSec 5 -SkipHttpErrorCheck -ErrorAction Stop
     $code=[int]$r.StatusCode; $body=[string]$r.Content }catch{ $code=0 }
$identOk = ($code -eq 200) -and ($body -match '"service"\s*:\s*"dex-wake"')
Add-Row '/healthz answers AS dex-wake' '200 + service=dex-wake' "code $code $body" (PF $identOk)

# --- 4. auth is still enforced ----------------------------------------------
$ac=0
try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8789/v1/services' -TimeoutSec 5 -SkipHttpErrorCheck -ErrorAction Stop; $ac=[int]$r.StatusCode }catch{ $ac=0 }
Add-Row 'status endpoint still requires auth' '401' "code $ac" (PF($ac -eq 401))

# --- 5. THE decisive checks: which process, started when, in whose session ---
$conn = Get-NetTCPConnection -LocalPort 8789 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if(-not $conn){
  Add-Row 'a process is listening on 8789' 'listener' 'none' 'FAIL'
} else {
  $procId = $conn.OwningProcess
  $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
  Add-Row 'listener on 8789 is python' 'python' $(if($p){$p.ProcessName}else{'unknown'}) (PF($p -and $p.ProcessName -like 'python*'))

  # started after boot => it is not a leftover from before
  $st = $null; try { $st = $p.StartTime } catch {}
  if($st){
    Add-Row 'listener started AFTER the last boot' "> $boot" "$st" (PF($st -gt $boot))
    # A manual "Run" of the task would also satisfy the check above, which would
    # be a false PASS for "survived a reboot". The service is triggered at boot
    # +30s, so a genuine boot start lands within a couple of minutes of boot.
    # A hand-run hours later does not.
    $gapMin = [math]::Round(($st - $boot).TotalMinutes,1)
    Add-Row 'listener started CLOSE TO boot (not hand-run later)' '<= 10 min after boot' "$gapMin min after boot" (PF($st -gt $boot -and $gapMin -le 10))
  }
  else   { Add-Row 'listener started AFTER the last boot' "> $boot" 'CANNOT READ (rerun elevated)' 'UNKNOWN' }

  # Session 0 => started with NO interactive user. This is the check that
  # actually proves the "nobody logged in" requirement. A process started by
  # hand from a desktop shell lands in session 1 or higher.
  $sess = $null
  try { $sess = (Get-CimInstance Win32_Process -Filter "ProcessId=$procId").SessionId } catch {}
  if($null -ne $sess){
    Add-Row 'listener runs in SESSION 0 (no interactive user)' '0' "$sess" (PF($sess -eq 0))
  } else {
    Add-Row 'listener runs in SESSION 0 (no interactive user)' '0' 'CANNOT READ' 'UNKNOWN'
  }
}

# --- 6. CONTROL: this script must be able to detect a DOWN service -----------
$dead=0
try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:8123/healthz' -TimeoutSec 3 -SkipHttpErrorCheck -ErrorAction Stop; $dead=[int]$r.StatusCode }catch{ $dead=0 }
Add-Row 'CONTROL can detect a down service' 'code 0 on a dead port' "code $dead" (PF($dead -eq 0))

# --- report ------------------------------------------------------------------
Write-Output ($rows | Format-Table -AutoSize | Out-String)
$fail = @($rows | Where-Object {$_.Result -eq 'FAIL'}).Count
$unk  = @($rows | Where-Object {$_.Result -eq 'UNKNOWN'}).Count

Write-Output "============================================================"
if($fail -eq 0 -and $unk -eq 0){
  Write-Output " VERDICT: PASS  dex-wake survived the reboot unattended."
} elseif($fail -eq 0){
  Write-Output " VERDICT: INCOMPLETE  nothing failed, but $unk check(s) could"
  Write-Output "          not be read. Re-run this script As Administrator."
} else {
  Write-Output " VERDICT: FAIL  $fail check(s) failed. dex-wake did NOT come"
  Write-Output "          back correctly. See the FAIL rows above."
  Write-Output "          First place to look: C:\Users\dexjr\dex-rag\dex-wake.boot.log"
}
Write-Output "============================================================"
