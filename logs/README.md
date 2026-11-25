# Logs des runs quotidiens

Un fichier par jour et par étape, écrit par le workflow `backfill.yml` (heure UTC) :

- `AAAA-MM-JJ_discover.txt` : étape « Discover et backfill des nouveaux calendriers » (`src/daily_update.py`)
- `AAAA-MM-JJ_backfill.txt` : étape « Backfill des calendriers non backfillés » (`src/backfill_all.py`)

Les logs ne contiennent que des noms et des liens de calendriers publics, pas de secrets.
Le scrape quotidien (`scrape.yml`) n'écrit pas de log ici.
