"""Tests locaux de la fusion events_master (sans réseau)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import config  # noqa: E402
import master_merge  # noqa: E402


def row(**kw) -> dict:
    base = {f: "" for f in config.CSV_FIELDNAMES}
    base.update(kw)
    return base


class MergeRowsTest(unittest.TestCase):
    def test_nouvel_evenement_ajoute(self):
        master, added = master_merge.merge_rows([], [row(api_id="evt-1", url="u1", name="A")])
        self.assertEqual(len(master), 1)
        self.assertEqual(len(added), 1)

    def test_champ_vide_rempli_sans_ecraser(self):
        master = [row(api_id="evt-1", url="u1", name="Ancien", calendar_api_id="")]
        incoming = [row(api_id="evt-1", url="u1", name="Nouveau", calendar_api_id="cal-1")]
        master, added = master_merge.merge_rows(master, incoming)
        self.assertEqual(added, [])
        self.assertEqual(master[0]["name"], "Ancien")
        self.assertEqual(master[0]["calendar_api_id"], "cal-1")

    def test_correspondance_par_url_quand_pas_d_api_id(self):
        master = [row(url="u1", name="A")]
        incoming = [row(api_id="evt-1", url="u1", name="A")]
        master, added = master_merge.merge_rows(master, incoming)
        self.assertEqual(added, [])
        self.assertEqual(master[0]["api_id"], "evt-1")

    def test_bloc_speakers_plus_riche_remplace(self):
        master = [row(api_id="evt-1", url="u1", organisateur="Ancien")]
        incoming = [row(api_id="evt-1", url="u1", organisateur="Hexa", speaker_1="Dupont Jean")]
        master, _ = master_merge.merge_rows(master, incoming)
        self.assertEqual(master[0]["organisateur"], "Hexa")
        self.assertEqual(master[0]["speaker_1"], "Dupont Jean")

    def test_bloc_speakers_egalite_garde_l_existant(self):
        master = [row(api_id="evt-1", url="u1", organisateur="Ancien")]
        incoming = [row(api_id="evt-1", url="u1", organisateur="Nouveau")]
        master, _ = master_merge.merge_rows(master, incoming)
        self.assertEqual(master[0]["organisateur"], "Ancien")

    def test_bloc_speakers_moins_riche_ne_remplace_pas(self):
        master = [row(api_id="evt-1", url="u1", organisateur="Hexa", speaker_1="A", speaker_2="B")]
        incoming = [row(api_id="evt-1", url="u1", organisateur="")]
        master, _ = master_merge.merge_rows(master, incoming)
        self.assertEqual(master[0]["speaker_2"], "B")
        self.assertEqual(master[0]["organisateur"], "Hexa")


if __name__ == "__main__":
    unittest.main()


class MembersOnlyTest(unittest.TestCase):
    def test_marqueur_membres_detecte(self):
        import backfill_calendar
        html = "<h3>This is a members-only calendar.</h3>"
        self.assertTrue(backfill_calendar.has_members_only_marker(html))
        self.assertFalse(backfill_calendar.has_members_only_marker("<h1>AI Salon</h1>"))

    def test_stopbackfill_porte_le_code(self):
        import backfill_calendar
        exc = backfill_calendar.StopBackfill("HTTP 401", 401)
        self.assertEqual(exc.code, 401)
