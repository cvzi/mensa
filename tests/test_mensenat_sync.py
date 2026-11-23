"""Opening hours in the mensen.at canteen sync (mensenat/utils.py).

Runs without network access: python -m pytest tests/test_mensenat_sync.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.relpath(os.path.join(os.path.dirname(__file__), '..', 'mensenat')))

import utils  # noqa: E402

WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday")


def node(slug, hours, database_id=1):
    opening = {day: [] for day, _ in utils.DAY_ORDER}
    opening.update(hours)
    return {"databaseId": database_id, "uri": f"/standort/{slug}/", "slug": slug,
            "title": slug, "locationData": {"address": {"city": "Wien"}},
            "openingHours": opening}


def existing(slug, times):
    return {"reference": slug, "name": slug, "times": times,
            "source": f"https://www.mensen.at/standort/{slug}"}


class SlotTest(unittest.TestCase):
    def test_forms_seen_in_the_wild(self):
        for slot in ("11:30-14:00", "11:30 - 14:00", "11:30 – 14:00", "11.30-14.00 Uhr", "11:30 Uhr - 14:00 Uhr"):
            self.assertEqual(utils.normalize_slot(slot), "11:30-14:00", slot)
        self.assertEqual(utils.normalize_slot("8:00-15:30"), "08:00-15:30")

    def test_free_text_is_not_a_slot(self):
        for slot in ("geschlossen", "nach Vereinbarung", "11:30", "ab 11:30", "11:30-14:00 und 17:00-19:00", "25:00-26:00"):
            self.assertIsNone(utils.normalize_slot(slot), slot)


class SyncTest(unittest.TestCase):
    def run_sync(self):
        canteens = {
            "20": existing("mensa-m-cafe-vet-med", "Mo-Fr 11:00-14:00 Uhr"),
            "21": existing("gleich", "Mo-Fr 11:30-14:00 Uhr"),
            "22": existing("freitext", "Mo-Fr 11:00-14:00 Uhr"),
            "23": existing("weg", "Mo-Fr 11:00-14:00 Uhr"),
        }
        nodes = [
            node("mensa-m-cafe-vet-med", {d: ["11:30-14:00"] for d in WEEK}),
            node("gleich", {d: ["11:30 - 14:00 Uhr"] for d in WEEK}),
            node("freitext", dict({d: ["11:00-14:00"] for d in WEEK}, friday=["nach Vereinbarung"])),
            node("neu", {d: ["8:00-15:00"] for d in WEEK}, database_id=99),
        ]
        return utils.sync_canteens(canteens, nodes)

    def test_hand_entered_hours_follow_graphql(self):
        merged, _, _, _, changed, _ = self.run_sync()
        self.assertEqual(merged["20"]["times"], "Mo-Fr 11:30-14:00 Uhr")
        self.assertEqual([c["key"] for c in changed], ["20"])
        self.assertEqual(changed[0]["before"], "Mo-Fr 11:00-14:00 Uhr")

    def test_same_hours_in_another_spelling_are_no_change(self):
        merged, _, _, _, changed, _ = self.run_sync()
        self.assertEqual(merged["21"]["times"], "Mo-Fr 11:30-14:00 Uhr")
        self.assertNotIn("21", [c["key"] for c in changed])

    def test_free_text_keeps_the_old_value_and_is_reported(self):
        merged, _, _, _, _, irregular = self.run_sync()
        self.assertEqual(merged["22"]["times"], "Mo-Fr 11:00-14:00 Uhr")
        self.assertEqual(irregular[0]["key"], "22")
        self.assertIn("Fr: 'nach Vereinbarung'", irregular[0]["slots"])

    def test_new_and_removed_still_work(self):
        merged, new_keys, added, removed, _, _ = self.run_sync()
        self.assertEqual(removed, ["23"])
        self.assertIn("databaseId:99", new_keys)
        self.assertEqual(merged["databaseId:99"]["times"], "Mo-Fr 08:00-15:00 Uhr")

    def test_pr_body_lists_both(self):
        merged, new_keys, added, removed, changed, irregular = self.run_sync()
        summary = utils.build_summary(added, removed, 3, "x", changed, irregular)
        body = utils.build_pr_body(summary)
        self.assertIn("## Opening hours updated from GraphQL", body)
        self.assertIn("## Opening hours left unchanged", body)


if __name__ == '__main__':
    unittest.main()
