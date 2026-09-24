# Isolation des tests PostgreSQL (Windows PowerShell)

Les tests backend ordinaires utilisent une SQLite en mémoire créée par `tests/conftest.py` et remplacent `get_db`; ils n'utilisent pas `DATABASE_URL`. Le test d'intégration PostgreSQL/Redis est volontairement séparé et exige `TEST_DATABASE_URL`. Il refuse toute URL non PostgreSQL locale, une base dont le nom ne contient pas `test` et `tmp`, un port non explicite ou identique au port de `DATABASE_URL`, et la cible métier résolue. La validation a lieu avant `create_engine`.

Pour l'intégration, créer un cluster PostgreSQL jetable dans un répertoire temporaire dédié et sur un port distinct. Exemple avec `initdb.exe`, `pg_ctl.exe` et `createdb.exe` provenant de la même installation PostgreSQL :

```powershell
$pgTemp = Join-Path $env:TEMP ("aigatos-pg-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $pgTemp | Out-Null
& 'C:\Program Files\PostgreSQL\17\bin\initdb.exe' -D (Join-Path $pgTemp 'data') -U postgres --auth-local trust --auth-host trust
& 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe' -D (Join-Path $pgTemp 'data') -l (Join-Path $pgTemp 'postgres.log') -o '-h 127.0.0.1 -p 55433' start
& 'C:\Program Files\PostgreSQL\17\bin\createdb.exe' -h 127.0.0.1 -p 55433 -U postgres aigatos_test_tmp
$env:TEST_DATABASE_URL = 'postgresql+psycopg://postgres@127.0.0.1:55433/aigatos_test_tmp'
$env:REDIS_URL = 'redis://127.0.0.1:6379/15'
```

Avant tout test d'intégration, confirmer visuellement seulement la base et l'hôte (sans imprimer l'URL complète ni ses identifiants) :

```powershell
$u = [uri]$env:TEST_DATABASE_URL
[pscustomobject]@{ Database = $u.AbsolutePath.TrimStart('/'); Host = $u.Host }
```

L'application ne crée ni ne supprime la base PostgreSQL. Pour l'arrêter puis supprimer le cluster, vérifier que `$pgTemp` commence par `$env:TEMP\aigatos-pg-test-`, arrêter ce cluster précis, puis retirer ce seul répertoire temporaire :

```powershell
if (-not $pgTemp.StartsWith((Join-Path $env:TEMP 'aigatos-pg-test-'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Chemin temporaire inattendu' }
& 'C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe' -D (Join-Path $pgTemp 'data') stop
Remove-Item -LiteralPath $pgTemp -Recurse
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Adapter le chemin de PostgreSQL à la version installée. Ne jamais substituer `DATABASE_URL` à `TEST_DATABASE_URL`. Aucun `alembic upgrade` n'est nécessaire pour le test de disponibilité (`SELECT 1`).
