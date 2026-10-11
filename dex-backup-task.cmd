@echo off
rem The scheduled backup (task DexChromaBackup, daily 05:30), third of the three nightly jobs.
rem FND-0034, 2026-10-11: it now WAITS for the sweep (04:00) and the corpus refresh (04:40) to finish
rem before it copies the live store, so nothing is writing to the store while it is copied and the
rem backup holds everything the night's two ingests wrote. 05:30 is a "not before" time.
rem Operator, 2026-10-11: "three jobs in a row is fine with me."
rem If the earlier jobs are still running after four hours, or the process list cannot be read,
rem this does NOT back up and says why in the log: that needs a person, not a copy taken mid-write.
setlocal
set RAG=C:\Users\dexjr\dex-rag
set PY=%RAG%\.venv\Scripts\python.exe
set LOG=D:\DDL_Backup\chromadb_backups\_dex-backup-task.log
cd /d %RAG% || exit /b 9
"%PY%" dex_wait_quiet.py --not dex-sweep.py corpus_refresh.cmd >> "%LOG%" 2>&1 || (
  echo %date% %time% backup task: earlier jobs still running or unknown; no backup taken >> "%LOG%" & exit /b 7 )
if "%DRYRUN%"=="1" (
  "%PY%" dex-backup.py --check-only --json >> "%LOG%" 2>&1
  echo %date% %time% backup task: dry run, no copy made >> "%LOG%"
  exit /b 0
)
"%PY%" dex-backup.py >> "%LOG%" 2>&1
exit /b %ERRORLEVEL%
