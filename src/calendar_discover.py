#!/usr/bin/env python3
"""Liste les calendriers Luma (tech, IA) à Paris, à partir de la réponse discover.

Usage :
    python calendar_discover.py            # requêtes + affichage, n'écrit rien
    python calendar_discover.py --write    # ajoute les nouveaux calendriers à calendar_master.csv

calendar_master.csv s'accumule : un calendrier déjà présent n'est jamais supprimé
ni recopié. Seuls les calendriers absents sont renvoyés comme « nouveaux ».

Garde-fous :
- 2 catégories (tech, ai), 1 page chacune par défaut, pagination bornée
- une requête à la fois, pause aléatoire de 3 à 5 s
- arrêt immédiat sur HTTP 403 / 429 ou erreur réseau, sans retry
- JSON brut sauvegardé hors dépôt (RAW_DIR)
"""

import argparse
import csv
import json
import logging
import random
import sys
import time
import urllib.error
from pathlib import Path

import config
import scraper

log = logging.getLogger("calendar_discover")

MAX_PAGES_PER_CATEGORY = 5
RAW_DIR = Path.home() / "luma-discover-raw"
CALENDAR_MASTER_FILE = config.CALENDAR_MASTER_FILE
CALENDAR_FIELDNAMES = ["nom", "url", "calendar_api_id", "backfilled"]
BACKFILL_NO = "Non"
BACKFILL_YES = "Oui"
BACKFILL_MEMBERS = "Membres"
CALENDAR_URL_PREFIX = "https://lu.ma/"


class StopDiscover(Exception):
    """Arrêt volontaire : Luma refuse ou le réseau échoue. Pas de retry."""


def fetch_page(category: str, city: dict, cursor: str | None, page_no: int) -> dict:
    try:
        body = _raw_request(category, city, cursor)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise StopDiscover(f"HTTP {exc.code} sur {category} page {page_no} : arrêt immédiat") from exc
        raise StopDiscover(f"HTTP {exc.code} sur {category} page {page_no}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise StopDiscover(f"erreur réseau sur {category} page {page_no} : {exc}") from exc

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"{category}_{page_no:02d}.json").write_text(json.dumps(body), encoding="utf-8")
    return body


def _raw_request(category: str, city: dict, cursor: str | None) -> dict:
    # Même requête que scraper.fetch_page_once, sans la boucle de retry.
    url = scraper.build_request_url(category, city, cursor)
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode())


def collect_calendars(entries: list[dict]) -> dict[str, dict]:
    """Retourne {calendar_api_id: {nom, url, calendar_api_id}} pour les entrées valides."""
    calendars: dict[str, dict] = {}
    for entry in entries:
        calendar = entry.get("calendar")
        if not isinstance(calendar, dict):
            continue
        api_id = calendar.get("api_id")
        slug = calendar.get("slug")
        name = (calendar.get("name") or "").strip()
        if not api_id or not slug or not name:
            continue
        calendars.setdefault(
            api_id,
            {"nom": name, "url": f"{CALENDAR_URL_PREFIX}{slug}", "calendar_api_id": api_id},
        )
    return calendars


def discover_calendars() -> dict[str, dict]:
    """Interroge discover pour chaque catégorie. Lève StopDiscover en cas de refus réseau."""
    city = config.CITIES[0]
    found: dict[str, dict] = {}
    for category in config.CATEGORIES:
        cursor: str | None = None
        for page_no in range(1, MAX_PAGES_PER_CATEGORY + 1):
            payload = fetch_page(category, city, cursor, page_no)
            entries = scraper.extract_entries(payload)
            page_found = collect_calendars(entries)
            found.update({k: v for k, v in page_found.items() if k not in found})
            log.info("%s page %d : %d entrées, %d calendriers", category, page_no, len(entries), len(page_found))
            cursor = payload.get("next_cursor")
            if not cursor or not payload.get("has_more", bool(cursor)):
                break
            time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))
        time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))
    return found


def read_calendar_master() -> list[dict]:
    """Lit calendar_master.csv. Liste vide si le fichier n'existe pas encore."""
    if not CALENDAR_MASTER_FILE.exists():
        return []
    with CALENDAR_MASTER_FILE.open(newline="", encoding="utf-8") as handle:
        return [
            {
                "nom": row.get("nom", ""),
                "url": row.get("url", ""),
                "calendar_api_id": row.get("calendar_api_id", "") or "",
                "backfilled": row.get("backfilled", "") or BACKFILL_NO,
            }
            for row in csv.DictReader(handle)
        ]


def merge_calendars(existing: list[dict], found: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """
    Fusionne les calendriers trouvés dans l'existant, sans doublon.

    Retourne (rows, added) :
    - rows : l'existant, avec calendar_api_id complété quand l'URL était déjà connue
      (ce n'est pas un nouveau calendrier, donc pas de backfill).
    - added : les calendriers réellement nouveaux, à backfiller. Ils ne sont pas
      ajoutés à rows ici : c'est à l'appelant de le faire après un backfill réussi.
    """
    rows = [dict(row) for row in existing]
    by_id = {row["calendar_api_id"]: row for row in rows if row["calendar_api_id"]}
    by_url = {row["url"]: row for row in rows}
    added: list[dict] = []
    for api_id, calendar in found.items():
        if api_id in by_id:
            continue
        known = by_url.get(calendar["url"])
        if known is not None:
            known["calendar_api_id"] = api_id
            by_id[api_id] = known
            continue
        added.append({**calendar, "backfilled": BACKFILL_NO})
    return rows, added


def write_calendar_master(rows: list[dict]) -> None:
    ordered = sorted(rows, key=lambda row: row["nom"].lower())
    with CALENDAR_MASTER_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CALENDAR_FIELDNAMES)
        writer.writeheader()
        writer.writerows(ordered)
    log.info("Écrit : %d calendriers dans %s", len(ordered), CALENDAR_MASTER_FILE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Liste des calendriers Luma tech/IA à Paris")
    parser.add_argument("--write", action="store_true", help="ajouter les nouveaux calendriers à calendar_master.csv")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        found = discover_calendars()
    except StopDiscover as exc:
        log.error("Arrêt : %s", exc)
        return 1

    existing = read_calendar_master()
    rows, added = merge_calendars(existing, found)
    print(f"\nCalendriers trouvés par discover : {len(found)}")
    print(f"Déjà connus : {len(found) - len(added)} · nouveaux : {len(added)}")
    for row in sorted(added, key=lambda r: r["nom"].lower()):
        print(f"  + {row['nom']} — {row['url']}")

    if not args.write:
        print("\nMode lecture : rien n'a été écrit. Relance avec --write.")
        return 0
    # Les nouveaux calendriers ne sont enregistrés qu'après leur backfill : voir daily_update.py.
    write_calendar_master(rows)
    if added:
        print("\nLes nouveaux calendriers ne sont pas ajoutés ici : lance daily_update.py pour les backfiller.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
