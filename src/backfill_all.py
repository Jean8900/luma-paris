#!/usr/bin/env python3
"""Backfill de tous les calendriers de calendar_master.csv (passé + futur, 2 requêtes chacun).

Usage :
    python src/backfill_all.py            # aperçu : liste les calendriers, n'écrit rien, ne requête rien
    python src/backfill_all.py --write    # requêtes Luma + écriture de events_master.csv et des autres fichiers

Les événements sont fusionnés dans events_master.csv (voir master_merge.py).
Les calendriers sans calendar_api_id sont tentés via leur page Luma (1 requête chacun) avant backfill.
"""

import argparse
import logging
import random
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timezone

import backfill_calendar
import calendar_discover
import charts
import config
import master_merge
import scraper

log = logging.getLogger("backfill_all")

CALENDAR_ID_RE = re.compile(r"\bcal-[A-Za-z0-9]{10,}\b")


def resolve_calendar_id(url: str) -> str:
    """Cherche le calendar_api_id dans la page Luma du calendrier (1 requête)."""
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT) as response:
        html = response.read().decode("utf-8", errors="replace")
    match = CALENDAR_ID_RE.search(html)
    return match.group(0) if match else ""


def run(write: bool, run_date: date) -> int:
    calendars = calendar_discover.read_calendar_master()
    missing = [c for c in calendars if not c["calendar_api_id"] and c.get("backfilled") != calendar_discover.BACKFILL_YES]
    print(f"Calendriers : {len(calendars)} · sans identifiant : {len(missing)}")
    for cal in missing:
        print(f"  ? {cal['nom']} — {cal['url']}")

    if not write:
        print("Mode aperçu : aucune requête, rien n'a été écrit. Relance avec --write.")
        return 0

    for cal in missing:
        try:
            cal["calendar_api_id"] = resolve_calendar_id(cal["url"])
        except OSError as exc:
            log.error("Page introuvable pour %s : %s", cal["nom"], exc)
            continue
        log.info("%s → %s", cal["nom"], cal["calendar_api_id"] or "(identifiant introuvable)")
        time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))

    incoming: list[dict] = []
    done: set[str] = set()
    timings: list[dict] = []
    pending = [
        c for c in calendars
        if c["calendar_api_id"] and c.get("backfilled") not in (
            calendar_discover.BACKFILL_YES,
            calendar_discover.BACKFILL_MEMBERS,
        )
    ]
    log.info("Calendriers à backfiller : %d", len(pending))

    def record(n: int, cal: dict, started: float, status: str, events: int = 0) -> None:
        seconds = time.monotonic() - started
        timings.append({
            "n": n, "nom": cal["nom"], "id": cal["calendar_api_id"], "url": cal["url"],
            "secondes": seconds, "evenements": events, "statut": status,
            "heure_utc": started_at[n],
        })
        log.info("  → %s | %.1f s | %d événements | %s", cal["nom"], seconds, events, status)

    started_at: dict[int, str] = {}
    for n, cal in enumerate(pending, start=1):
        started = time.monotonic()
        started_at[n] = datetime.now(timezone.utc).strftime("%H:%M:%S")
        log.info("[%d/%d] %s | %s | %s | %s", n, len(pending), started_at[n],
                 cal["nom"], cal["calendar_api_id"], cal["url"])
        try:
            events = backfill_calendar.backfill_calendar(cal["calendar_api_id"])
        except backfill_calendar.StopBackfill as exc:
            if exc.code == 401 and backfill_calendar.is_members_only(cal["url"]):
                cal["backfilled"] = calendar_discover.BACKFILL_MEMBERS
                record(n, cal, started, "membres (401 + marqueur)")
                continue
            record(n, cal, started, f"arrêt : {exc}")
            log.error("Arrêt : %s. Les calendriers restants resteront à faire.", exc)
            break
        incoming.extend(scraper.event_to_row(e, scraper.first_seen_value(run_date)) for e in events)
        done.add(cal["calendar_api_id"])
        record(n, cal, started, "ok", len(events))

    if timings:
        log.info("=== TIMELINE (ordre d'exécution) ===")
        for t in timings:
            log.info("%3d | %s | %8.1f s | %5d ev | %-30s | %s | %s | %s",
                     t["n"], t["heure_utc"], t["secondes"], t["evenements"], t["nom"][:30],
                     t["id"], t["statut"], t["url"])
        log.info("=== CLASSEMENT : 15 calendriers les plus longs ===")
        for rank, t in enumerate(sorted(timings, key=lambda x: -x["secondes"])[:15], start=1):
            log.info("%2d. %8.1f s | %-30s | %s | %s | %s",
                     rank, t["secondes"], t["nom"][:30], t["id"], t["statut"], t["url"])
        total = sum(t["secondes"] for t in timings)
        log.info("Total : %d calendriers, %.1f s (%.1f min)", len(timings), total, total / 60)

    master = master_merge.load_master()
    master, added = master_merge.merge_rows(master, incoming)
    master_merge.write_master(master)
    log.info("events_master.csv : %d lignes, %d ajoutées", len(master), len(added))

    if added:
        scraper.append_csv(scraper.new_events_filepath(run_date), added)
        seen = scraper.load_seen_events()
        for row in added:
            if row["api_id"]:
                seen[row["api_id"]] = scraper.first_seen_value(run_date)
        scraper.save_seen_events(seen)

    for cal in calendars:
        if cal["calendar_api_id"] in done:
            cal["backfilled"] = calendar_discover.BACKFILL_YES
    calendar_discover.write_calendar_master(calendars)

    stats = charts.read_stats()
    stats = charts.upsert_stats(
        stats,
        run_date.isoformat(),
        len(scraper.load_seen_events()),
        len(calendar_discover.read_calendar_master()),
    )
    charts.write_stats(stats)
    charts.render_all(stats)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill de tous les calendriers de calendar_master.csv")
    parser.add_argument("--write", action="store_true", help="faire les requêtes et écrire les fichiers")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    return run(args.write, date.today())


if __name__ == "__main__":
    sys.exit(main())
