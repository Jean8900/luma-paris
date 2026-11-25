"""Configuration du scraper — modifiable sans toucher à la logique centrale (RF-10)."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CHARTS_DIR = ROOT_DIR / "charts"

CATEGORIES = ["tech", "ai"]

CITIES = [
    {"name": "Paris", "lat": 48.8566, "lon": 2.3522},
]

MAX_PAGES = 50
REQUEST_DELAY_MIN = 3.0
REQUEST_DELAY_MAX = 5.0
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0
REQUEST_TIMEOUT = 30
# Backfill : temps maximum par calendrier (secondes). Au-delà, le calendrier est abandonné pour ce run
# (statut « timeout », pas marqué Oui) et le backfill passe au suivant. Un run dure au plus N × cette valeur.
CALENDAR_TIME_BUDGET_S = 30

API_BASE_URL = "https://api.luma.com/discover/get-paginated-events"
USER_AGENT = "luma-event-scraper/0.1"

SEEN_EVENTS_FILE = DATA_DIR / "seen_events.json"
EVENTS_MASTER_FILE = DATA_DIR / "events_master.csv"
NEW_EVENTS_DIR = DATA_DIR / "new_events"
NEW_EVENTS_FILE_PREFIX = "new_events_"
CALENDAR_MASTER_FILE = DATA_DIR / "calendar_master.csv"
STATS_DAILY_FILE = DATA_DIR / "stats_daily.csv"

# Nombre de speakers pris en compte par événement. Chaque speaker ajoute
# 3 colonnes : speaker_i (Nom Prénom), speaker_i_lien (LinkedIn ou réseau), info_speaker_i.
MAX_SPEAKERS = 10

BASE_CSV_FIELDNAMES = ["name", "url", "start_date", "city", "category", "organisateur", "first_seen", "api_id", "calendar_api_id"]
SPEAKER_CSV_FIELDNAMES = [
    field
    for i in range(1, MAX_SPEAKERS + 1)
    for field in (f"speaker_{i}", f"speaker_{i}_lien", f"info_speaker_{i}")
]
CSV_FIELDNAMES = BASE_CSV_FIELDNAMES + SPEAKER_CSV_FIELDNAMES
