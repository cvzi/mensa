"""Opening hours in the canteen lists, read by util.parse_opening_times.

Runs without network access: python -m pytest tests/test_opening_times.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.relpath(os.path.join(os.path.dirname(__file__), '..')))

from util import parse_opening_times  # noqa: E402


class OpeningTimesTest(unittest.TestCase):
    def test_monday_to_friday(self):
        self.assertEqual(parse_opening_times("Mo-Fr 11:00-14:00 Uhr"),
                         {d: "11:00-14:00" for d in ("Mo", "Tu", "We", "Th", "Fr")})

    def test_german_range_ends_on_thursday(self):
        # "Do" used to be unknown, so the range ran on into the weekend
        self.assertEqual(parse_opening_times("Mo-Do 11:30-13:30 Uhr\nFr 11:00-13:00 Uhr"), {
            "Mo": "11:30-13:30", "Tu": "11:30-13:30", "We": "11:30-13:30",
            "Th": "11:30-13:30", "Fr": "11:00-13:00"})

    def test_german_range_starts_on_tuesday(self):
        # "Di" used to be unknown, so Tuesday to Friday came out closed
        self.assertEqual(parse_opening_times("Mo 11:30-14:30 Uhr\nDi-Fr 09:00-14:30 Uhr"), {
            "Mo": "11:30-14:30", "Tu": "09:00-14:30", "We": "09:00-14:30",
            "Th": "09:00-14:30", "Fr": "09:00-14:30"})

    def test_saturday_but_not_sunday(self):
        times = parse_opening_times("Mo-Do 07:30-16:00 Uhr\nFr 07:30-15:00 Uhr\nSa 08:30-13:30 Uhr")
        self.assertEqual(times["Sa"], "08:30-13:30")
        self.assertNotIn("Su", times)

    def test_single_days_and_spaces(self):
        self.assertEqual(parse_opening_times("Mi 07:00-13:30\nSo 8:00 - 15:00 Uhr"),
                         {"We": "07:00-13:30", "Su": "08:00-15:00"})

    def test_english_abbreviations_still_work(self):
        self.assertEqual(parse_opening_times("Tu-Th 10:00-12:00"),
                         {"Tu": "10:00-12:00", "We": "10:00-12:00", "Th": "10:00-12:00"})

    def test_unknown_day_is_skipped_not_spread(self):
        self.assertEqual(parse_opening_times("Mo-Xy 10:00-12:00 Uhr"), {})

    def test_empty(self):
        self.assertEqual(parse_opening_times(""), {})


if __name__ == '__main__':
    unittest.main()
