"""Closed days for mensen.at, from openingHours.exceptions.

Runs without network access: python -m pytest tests/test_mensenat_closed_days.py
The response shapes are taken from backend.mensen.at for
"standort/mensa-m-cafe-vet-med" in November 2026.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.relpath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.relpath(os.path.join(os.path.dirname(__file__), '..', 'mensenat')))

from canteen import Canteen  # noqa: E402
from util import StyledLazyBuilder  # noqa: E402

SOURCE = "https://www.mensen.at/standort/mensa-m-cafe-vet-med"

# As sent by the API: a JSON string inside the JSON response
EXCEPTIONS = json.dumps({
    "2026-12-08": {"data": "Maria Empfängnis"},
    "2026-12-09": {"data": "Betriebsausflug"},
    "2026-12-10": {"data": "nur 11:00-13:00"},
    "2026-12-24": {"data": "Weihnacht/Neujahrs Schließzeit"},
})

MEAL = {"title_de": "Gemüsecurry", "price": "6,80", "allergens": {"A": "Gluten"}}


def week(first_day, menus):
    return {"available": True, "first_day": first_day,
            "menus": [{"name": "Menü Veggie", "menus": menus}]}


class ClosedDaysTest(unittest.TestCase):
    def feed(self, current, following=None, exceptions=EXCEPTIONS):
        canteen = Canteen(SOURCE)
        canteen.fetchWeekMenus = lambda: {
            "menuplanCurrentWeek": current,
            "menuplanNextWeek": following or {},
            "exceptions": Canteen.parseExceptions(exceptions),
        }
        return canteen.generateTotalFeedXml()

    @staticmethod
    def closed(xml, day):
        start = xml.find('<day date="%s">' % day)
        return start >= 0 and "<closed" in xml[start:xml.find("</day>", start) + 6]

    def test_holiday_without_meals_is_closed(self):
        xml = self.feed(week("2026-12-07", {"1": [MEAL], "3": [MEAL]}))
        self.assertTrue(self.closed(xml, "2026-12-08"))

    def test_day_with_meals_stays_open(self):
        xml = self.feed(week("2026-12-07", {"1": [MEAL], "3": [MEAL]}))
        self.assertFalse(self.closed(xml, "2026-12-09"))
        self.assertIn("Gemüsecurry", xml)

    def test_shortened_day_is_not_closed(self):
        xml = self.feed(week("2026-12-07", {"1": [MEAL]}))
        self.assertNotIn('<day date="2026-12-10">', xml)

    def test_only_weeks_in_the_feed(self):
        xml = self.feed(week("2026-12-07", {"1": [MEAL]}))
        self.assertNotIn('<day date="2026-12-24">', xml)
        xml = self.feed(week("2026-12-14", {"1": [MEAL]}), week("2026-12-21", {}))
        self.assertTrue(self.closed(xml, "2026-12-24"))

    def test_closing_week_without_menu(self):
        # A closing week comes as "available": false, without first_day
        canteen = Canteen(SOURCE)
        canteen.feed = StyledLazyBuilder()
        canteen.addClosedDaysToFeed(Canteen.parseExceptions(EXCEPTIONS), {"available": False}, weeks=2)
        # Falls back to the current week; must not fail
        canteen.feed.toXMLFeed()

    def test_shapes_seen_in_november_2026(self):
        # Mensa PH Tirol: shortened days as a list, closed days without reason
        raw = json.dumps({"2027-02-01": ["07:30-14:00"], "2027-02-06": {"data": ""},
                          "2027-02-13": {"data": "Betriebsurlaub"}})
        parsed = Canteen.parseExceptions(raw)
        self.assertEqual(parsed, {"2027-02-01": "07:30-14:00", "2027-02-06": "",
                                  "2027-02-13": "Betriebsurlaub"})
        xml = self.feed(week("2027-02-01", {}), week("2027-02-08", {}), exceptions=raw)
        self.assertNotIn('<day date="2027-02-01">', xml)
        self.assertTrue(self.closed(xml, "2027-02-06"))
        self.assertTrue(self.closed(xml, "2027-02-13"))
        # Trailing spaces in reasons, escaped slash inside the inner JSON
        raw = '{"2026-12-08":{"data":"Maria Empf\\u00e4ngnis "},"2026-12-24":{"data":"Weihnacht\\/Neujahr"}}'
        self.assertEqual(Canteen.parseExceptions(raw),
                         {"2026-12-08": "Maria Empf\u00e4ngnis", "2026-12-24": "Weihnacht/Neujahr"})

    def test_parse_exceptions_shapes(self):
        self.assertEqual(Canteen.parseExceptions(EXCEPTIONS)["2026-12-08"], "Maria Empfängnis")
        self.assertEqual(Canteen.parseExceptions({"2026-12-08": {"data": "x"}}), {"2026-12-08": "x"})
        for empty in (None, "", "[]", [], "{", "null", {"kein-datum": {"data": "x"}}):
            self.assertEqual(Canteen.parseExceptions(empty), {}, empty)
        self.assertEqual(Canteen.parseExceptions({"2026-12-08": {"data": None}}), {"2026-12-08": ""})


if __name__ == '__main__':
    unittest.main()
