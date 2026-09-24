# Démarrage local isolé (Windows PowerShell)

Le backend ne lance ni migration ni seed au démarrage. Pour éviter la base AIGATOS locale, la procédure suivante crée un fichier SQLite vide et unique sous `%TEMP%`, y crée uniquement le schéma ORM, puis pointe explicitement `DATABASE_URL` vers ce fichier. Elle n'utilise pas PostgreSQL. Garder le premier terminal ouvert pendant l'utilisation.

Terminal 1 — backend isolé :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS'
$localRoot = Join-Path $env:TEMP ('AIGATOS-local-' + [guid]::NewGuid().ToString('N'))
$databaseFile = Join-Path $localRoot 'aigatos_local_test_tmp.sqlite'
$tempPrefix = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
$resolvedFile = [System.IO.Path]::GetFullPath($databaseFile)
if (-not $resolvedFile.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Cible hors de TEMP' }
if (Test-Path -LiteralPath $localRoot) { throw 'Le dossier temporaire existe déjà' }
Write-Output ('Base isolée vérifiée : nom=' + [System.IO.Path]::GetFileName($databaseFile) + '; hôte=fichier local')
New-Item -ItemType Directory -Path $localRoot | Out-Null
$env:DATABASE_URL = 'sqlite+pysqlite:///' + $resolvedFile.Replace('\','/')
$env:PYTHONPATH = 'D:\AIGATOS\backend'
$env:AIGATOS_OPERATION_MODE = 'live_simulation'
$env:AIGATOS_REPORT_DIR = Join-Path $localRoot 'reports'
& 'D:\AIGATOS\.venv\Scripts\python.exe' -c "from app.db import Base, engine; from app import models; Base.metadata.create_all(engine); print('Schéma vide créé sans migration ni seed')"
if ($LASTEXITCODE -ne 0) { throw 'Impossible de créer le schéma SQLite isolé' }
& 'D:\AIGATOS\.venv\Scripts\python.exe' -m uvicorn app.main:app --app-dir 'D:\AIGATOS\backend' --host 127.0.0.1 --port 8013
```

Terminal 2 — frontend :

```powershell
Set-Location -LiteralPath 'D:\AIGATOS\frontend'
$env:AIGATOS_API_TARGET = 'http://127.0.0.1:8013'
npm.cmd run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

URL attendue : `http://127.0.0.1:5174/`. Le proxy frontend envoie `/_backend/*` vers le backend local isolé `http://127.0.0.1:8013`. Les pages seront vides, car aucun seed ni donnée métier n'est chargé. Les actions d'écriture de l'interface, si utilisées, ne toucheront que le fichier SQLite temporaire.

Arrêter les deux serveurs avec `Ctrl+C`. Dans le terminal 1, supprimer seulement le dossier créé par cette session après validation de son nom et de son contenu :

```powershell
$tempPrefix = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
$resolvedRoot = [System.IO.Path]::GetFullPath($localRoot)
if (-not $resolvedRoot.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or [System.IO.Path]::GetFileName($resolvedRoot) -notmatch '^AIGATOS-local-[0-9a-f]{32}$') { throw 'Dossier temporaire inattendu' }
$contents = @(Get-ChildItem -LiteralPath $resolvedRoot -Force)
if ($contents.Count -gt 2 -or ($contents | Where-Object { $_.Name -notin @('aigatos_local_test_tmp.sqlite','reports') })) { throw 'Contenu temporaire inattendu' }
Remove-Item -LiteralPath $resolvedRoot -Recurse
```

Le port 8000 et le port frontend 5173 étaient déjà occupés durant la dernière vérification locale ; ils n'ont pas été contactés ni arrêtés. Les ports 8013 et 5174 avaient été utilisés pour le backend/front temporaire, puis arrêtés.
