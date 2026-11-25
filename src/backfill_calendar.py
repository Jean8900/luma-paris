#!/usr/bin/env python3
"""Backfill d'UN calendrier Luma : tous les événements passés et futurs (2 requêtes).

Usage :
    python backfill_calendar.py --calendar-api-id cal-xxxx          # lit et affiche, n'écrit rien
    python backfill_calendar.py --calendar-api-id cal-xxxx --write  # écrit events_master.csv et seen_events.json

Le lancement quotidien (nouveaux calendriers seulement) est dans daily_update.py.

Garde-fous :
- une seule requête à la fois, pause aléatoire entre chaque requête (config.REQUEST_DELAY_*)
- arrêt immédiat sur HTTP 403 / 429 ou erreur réseau : pas de retry, pour ne pas insister
- JSON brut sauvegardé hors dépôt (RAW_DIR/<calendar_api_id>), données personnelles incluses
"""

import argparse
import json
import logging
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import config
import scraper

log = logging.getLogger("backfill")

CALENDAR_ENDPOINT = "https://api.luma.com/calendar/get-items"
PERIODS = ("past", "future")

RAW_DIR = Path.home() / "luma-backfill-raw"


MEMBERS_ONLY_MARKER = "This is a members-only calendar."


class StopBackfill(Exception):
    """Arrêt volontaire : Luma refuse ou le réseau échoue. Pas de retry."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class CalendarTimeout(Exception):
    """Budget de temps du calendrier dépassé : ce calendrier est abandonné, le backfill continue."""


def has_members_only_marker(html: str) -> bool:
    """Vrai si la page du calendrier indique qu'il est réservé aux membres (HTML rendu côté serveur)."""
    return MEMBERS_ONLY_MARKER in html


def is_members_only(calendar_url: str) -> bool:
    """1 requête vers la page publique du calendrier."""
    request = urllib.request.Request(calendar_url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT) as response:
        return has_members_only_marker(response.read().decode("utf-8", errors="replace"))


def fetch_calendar_page(calendar_id: str, period: str, cursor: str | None, page_no: int) -> dict:
    params = {"calendar_api_id": calendar_id, "period": period}
    if cursor:
        params["next_cursor"] = cursor
    url = f"{CALENDAR_ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise StopBackfill(f"HTTP {exc.code} sur {period} page {page_no} : arrêt immédiat", exc.code) from exc
        raise StopBackfill(f"HTTP {exc.code} sur {period} page {page_no}", exc.code) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise StopBackfill(f"erreur réseau sur {period} page {page_no} : {exc}") from exc

    payload = json.loads(body)
    raw_dir = RAW_DIR / calendar_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{period}_{page_no:02d}.json").write_text(body, encoding="utf-8")
    return payload


def _check_deadline(deadline: float | None, budget_s: float | None, where: str) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise CalendarTimeout(f"budget de {budget_s:g} s dépassé ({where})")


def collect_period(calendar_id: str, period: str, deadline: float | None = None, budget_s: float | None = None) -> list[dict]:
    entries: list[dict] = []
    cursor: str | None = None
    page_no = 0
    while True:
        page_no += 1
        _check_deadline(deadline, budget_s, f"{period} page {page_no}")
        payload = fetch_calendar_page(calendar_id, period, cursor, page_no)
        page_entries = scraper.extract_entries(payload)
        entries.extend(page_entries)
        log.info("  %s page %d : %d entrées", period, page_no, len(page_entries))

        cursor = payload.get("next_cursor")
        has_more = payload.get("has_more", bool(cursor))
        if not cursor or not has_more:
            return entries
        time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))


def build_events(entries: list[dict]) -> list[scraper.Event]:
    events: list[scraper.Event] = []
    for entry in entries:
        try:
            event = scraper.parse_entry(entry, "calendrier", "Paris")
        except (KeyError, TypeError, AttributeError, ValueError) as exc:
            log.warning("Entrée non parsée : %s", exc)
            continue
        if event:
            events.append(event)
    return scraper.dedupe_events(events)


def backfill_calendar(calendar_api_id: str, budget_s: float | None = None) -> list[scraper.Event]:
    """Passé + futur d'un calendrier. Lève StopBackfill si Luma refuse ou si le réseau échoue,
    CalendarTimeout si budget_s secondes sont écoulées (vérifié avant chaque requête)."""
    deadline = time.monotonic() + budget_s if budget_s else None
    entries: list[dict] = []
    for period in PERIODS:
        entries.extend(collect_period(calendar_api_id, period, deadline, budget_s))
        time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))
    return build_events(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill d'un calendrier Luma")
    parser.add_argument("--calendar-api-id", required=True, help="calendar_api_id du calendrier (ex. cal-xxxx)")
    parser.add_argument("--write", action="store_true", help="écrire events_master.csv et seen_events.json")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        events = backfill_calendar(args.calendar_api_id)
    except StopBackfill as exc:
        log.error("Arrêt : %s", exc)
        return 1

    seen = set(scraper.load_seen_events())
    new_count = sum(1 for e in events if e.api_id not in seen)
    print(f"\nÉvénements (passé + futur) : {len(events)} · nouveaux : {new_count}")

    if not args.write:
        print("Mode lecture : rien n'a été écrit. Relance avec --write pour sauvegarder.")
        return 0

    total, new = scraper.persist_results(events, date.today())
    log.info("Écrit : %d uniques, %d nouveaux ajoutés à events_master.csv", total, new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
