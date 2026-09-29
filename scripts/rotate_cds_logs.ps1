# path: scripts/rotate_cds_logs.ps1
# Назначение: держать только 3 свежих cds_session-лога + cds_backend.log.
# История сессий для потомков — reports/LAST_SESSION.md (вердикт Мастера, вариант в).
Get-ChildItem backend/logs -Filter "cds_session_*.log" -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -Skip 3 |
  Remove-Item -ErrorAction SilentlyContinue
