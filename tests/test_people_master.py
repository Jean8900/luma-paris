"""Tests locaux de people_master (sans réseau) : python -m unittest discover -s tests"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import people_master  # noqa: E402


class LinkedinKeyTests(unittest.TestCase):
    def test_normalise_profil(self):
        self.assertEqual(people_master.linkedin_key("https://www.linkedin.com/in/Virgile-Rault/"),
                         "https://www.linkedin.com/in/virgile-rault")
        self.assertEqual(people_master.linkedin_key("https://fr.linkedin.com/in/abc?trk=1"),
                         "https://www.linkedin.com/in/abc")

    def test_rejette_non_linkedin(self):
        self.assertIsNone(people_master.linkedin_key("https://flonocode.fr/"))
        self.assertIsNone(people_master.linkedin_key("https://www.linkedin.com/company/x"))
        self.assertIsNone(people_master.linkedin_key(""))


class BuildPeopleTests(unittest.TestCase):
    def test_regroupe_par_linkedin_et_filtre(self):
        header = "name,url,api_id,calendar_api_id,speaker_1,speaker_1_lien,info_speaker_1,speaker_2,speaker_2_lien,info_speaker_2\n"
        events = header + (
            "E1,https://lu.ma/e1,a1,cal-1,Ada L,https://www.linkedin.com/in/ada/,CTO,Bob,https://flonocode.fr/,\n"
            "E2,https://lu.ma/e2,a2,cal-1,Ada Lovelace,https://linkedin.com/in/ada,,,,\n"
        )
        calendars = "nom,url,calendar_api_id,backfilled\nMon cal,https://lu.ma/cal,cal-1,Oui\n"
        with tempfile.TemporaryDirectory() as tmp:
            ev, cal = Path(tmp) / "ev.csv", Path(tmp) / "cal.csv"
            ev.write_text(events, encoding="utf-8")
            cal.write_text(calendars, encoding="utf-8")
            rows = people_master.build_people(ev, cal)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["LinkedIn"], "https://www.linkedin.com/in/ada")
        self.assertEqual(rows[0]["Infos"], "CTO")
        self.assertEqual(rows[0]["Nb événements"], 2)
        self.assertEqual(rows[0]["Événements"], "E1; E2")
        self.assertEqual(rows[0]["Calendriers"], "Mon cal")


if __name__ == "__main__":
    unittest.main()
