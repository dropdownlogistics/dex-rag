# show-rag-folder.ps1
# Shows all files in C:\Users\dexjr\dex-rag with size and date

Write-Host ""
Write-Host "============================================================"
Write-Host "  DEX-RAG FOLDER CONTENTS"
Write-Host "  C:\Users\dexjr\dex-rag"
Write-Host "============================================================"
Write-Host ""

$folder = "C:\Users\dexjr\dex-rag"

# Top-level files only (no venv)
Get-ChildItem $folder -File | 
    Sort-Object Extension, Name |
    Format-Table Name, 
        @{Label="Size"; Expression={
            if ($_.Length -gt 1MB) { "{0:N1} MB" -f ($_.Length / 1MB) }
            elseif ($_.Length -gt 1KB) { "{0:N1} KB" -f ($_.Length / 1KB) }
            else { "$($_.Length) B" }
        }},
        @{Label="Modified"; Expression={ $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm") }} `
    -AutoSize

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host "  TOP-LEVEL FOLDERS"
Write-Host "------------------------------------------------------------"
Get-ChildItem $folder -Directory |
    Sort-Object Name |
    Format-Table Name,
        @{Label="Modified"; Expression={ $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm") }} `
    -AutoSize

Write-Host ""
Write-Host "============================================================"
