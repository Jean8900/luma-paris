"""Construit people_master (CSV + xlsx) : une ligne par personne ayant un lien LinkedIn.

Source : data/events_master.csv, emplacements speaker_1..speaker_10 (nom, lien, infos).
Aucun appel réseau. CSV en stdlib, xlsx avec openpyxl.

Règles :
- Clé = profil LinkedIn normalisé (https://www.linkedin.com/in/<slug>, minuscules, sans / final).
- Lien non LinkedIn ou absent : personne ignorée.
- Nom = le plus fréquent ; Infos = première valeur non vide (ordre du fichier).
- Événements = noms uniques, séparés par "; " ; Calendriers = noms (via calendar_master), sans API id.
- Tri : nombre d'événements décroissant, puis nom.
"""

import csv
import logging
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import config

log = logging.getLogger(__name__)

PEOPLE_CSV_FILE = config.DATA_DIR / "people_master.csv"
PEOPLE_XLSX_FILE = config.DATA_DIR / "people_master.xlsx"
PEOPLE_FIELDNAMES = ["Nom", "LinkedIn", "Infos", "Nb événements", "Événements", "Calendriers"]
SPEAKER_SLOTS = range(1, 11)
SEP = "; "


def linkedin_key(url: str | None) -> str | None:
    """Renvoie la clé canonique d'un profil LinkedIn, ou None si ce n'en est pas un."""
    url = (url or "").strip()
    if not url:
        return None
    parsed = urlparse(url if "://" in url else "https://" + url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return None
    path = parsed.path.rstrip("/").lower()
    if not path.startswith("/in/") or len(path) <= len("/in/"):
        return None
    return f"https://www.linkedin.com{path}"


def load_calendar_names(path: Path = config.CALENDAR_MASTER_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {r["calendar_api_id"]: r["nom"] for r in csv.DictReader(handle) if r.get("calendar_api_id")}


def build_people(
    events_path: Path = config.EVENTS_MASTER_FILE,
    calendars_path: Path = config.CALENDAR_MASTER_FILE,
) -> list[dict]:
    calendar_names = load_calendar_names(calendars_path)
    people: dict[str, dict] = {}

    with events_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            event_key = row.get("api_id") or row.get("url") or ""
            event_name = (row.get("name") or "").strip()
            calendar_name = calendar_names.get(row.get("calendar_api_id") or "", "").strip()
            for i in SPEAKER_SLOTS:
                name = (row.get(f"speaker_{i}") or "").strip()
                key = linkedin_key(row.get(f"speaker_{i}_lien"))
                if not name or key is None:
                    continue
                person = people.setdefault(
                    key, {"names": Counter(), "infos": "", "events": {}, "calendars": {}}
                )
                person["names"][name] += 1
                info = (row.get(f"info_speaker_{i}") or "").strip()
                if info and not person["infos"]:
                    person["infos"] = info
                if event_name:
                    person["events"].setdefault(event_key, event_name)
                if calendar_name:
                    person["calendars"].setdefault(calendar_name, None)

    rows = []
    for key, person in people.items():
        nom = person["names"].most_common(1)[0][0]
        events = list(person["events"].values())
        rows.append(
            {
                "Nom": nom,
                "LinkedIn": key,
                "Infos": person["infos"],
                "Nb événements": len(events),
                "Événements": SEP.join(events),
                "Calendriers": SEP.join(person["calendars"]),
            }
        )
    rows.sort(key=lambda r: (-r["Nb événements"], r["Nom"].casefold()))
    return rows


def write_csv(rows: list[dict], path: Path = PEOPLE_CSV_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PEOPLE_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(rows: list[dict], path: Path = PEOPLE_XLSX_FILE) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Personnes"
    ws.append(PEOPLE_FIELDNAMES)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row[f] for f in PEOPLE_FIELDNAMES])
        link_cell = ws.cell(row=ws.max_row, column=PEOPLE_FIELDNAMES.index("LinkedIn") + 1)
        link_cell.hyperlink = row["LinkedIn"]
        link_cell.style = "Hyperlink"
    widths = {"Nom": 28, "LinkedIn": 40, "Infos": 60, "Nb événements": 14, "Événements": 80, "Calendriers": 50}
    for idx, field in enumerate(PEOPLE_FIELDNAMES, start=1):
        ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = widths[field]
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    rows = build_people()
    write_csv(rows)
    write_xlsx(rows)
    log.info("%d personnes avec lien LinkedIn -> %s et %s", len(rows), PEOPLE_CSV_FILE, PEOPLE_XLSX_FILE)


if __name__ == "__main__":
    main()
