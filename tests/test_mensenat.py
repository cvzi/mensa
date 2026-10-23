"""Unit tests for the mensen.at parser.

These run without network access: the GraphQL call is never made, the tests
feed the parser the shapes the API actually returns.
"""
import os
import sys

include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, include)

from mensenat.canteen import Canteen  # noqa: E402


class RecordingFeed:
    """Stands in for LazyBuilder and keeps what the parser hands over."""

    def __init__(self):
        self.meals = []

    def addMeal(self, date, category, name, notes=None, prices=None, roles=None):
        self.meals.append({
            "date": date,
            "category": category,
            "name": name,
            "notes": list(notes or []),
            "prices": dict(prices or {}),
        })


def makeCanteen():
    canteen = Canteen("https://www.mensen.at/standort/mensa-m-cafe-vet-med")
    canteen.feed = RecordingFeed()
    return canteen


def test_strip_html_keeps_the_dish_boundary():
    canteen = makeCanteen()

    assert canteen.strip_html(
        "Seelachsfilet MSC im Backteig  <br />\nGemüsereis | Sauce Tyrolienne | Zitrone<br />\n"
    ) == "Seelachsfilet MSC im Backteig, Gemüsereis | Sauce Tyrolienne | Zitrone"

    assert canteen.strip_html("Putenfleisch Jägerart<br />\nTagliatelle") \
        == "Putenfleisch Jägerart, Tagliatelle"

    # No <br /> at all: the name stays as it is.
    assert canteen.strip_html("Champignoncremesuppe") == "Champignoncremesuppe"

    # Entities are resolved instead of being escaped a second time in the XML.
    assert canteen.strip_html("SO2 + Sulfite &gt;10mg/kg") == "SO2 + Sulfite >10mg/kg"

    assert canteen.strip_html(None) == ""


def test_parse_menuplan_survives_missing_weeks():
    assert Canteen.parseMenuplan(None) == {}
    assert Canteen.parseMenuplan("") == {}
    assert Canteen.parseMenuplan("not json") == {}
    assert Canteen.parseMenuplan('{"available": true}') == {"available": True}
    assert Canteen.parseMenuplan('[1, 2]') == {}


def test_available_location_without_menus_does_not_raise():
    """mensenat/WiVetMed answers like this; it used to raise KeyError."""
    canteen = makeCanteen()
    canteen.addWeekMenuToFeed({"available": True, "first_day": "2026-10-19"})
    assert canteen.feed.meals == []


def test_notes_carry_allergens_and_labels():
    canteen = makeCanteen()
    canteen.addWeekMenuToFeed({
        "available": True,
        "first_day": "2026-10-19",
        "menus": [{
            "name": "Menü Herzhaft",
            "menus": {
                "1": [{
                    "title_de": "Klare Gemüsesuppe mit Einlage",
                    "price": "2.30",
                    "allergens": {"A": "Glutenhaltiges Getreide", "C": "Ei"},
                    "informations": {"VEGAN": {"name": "VEGAN"}},
                }],
            },
        }],
    })

    meal = canteen.feed.meals[0]
    assert meal["date"] == "2026-10-19"
    assert meal["category"] == "Menü Herzhaft"
    assert meal["notes"] == ["A", "C", "VEGAN"]
    assert meal["prices"] == {"other": "2.30"}


def test_broken_entries_are_skipped_not_fatal():
    canteen = makeCanteen()
    canteen.addWeekMenuToFeed({
        "available": True,
        "first_day": "2026-10-19",
        "menus": [
            "not a category",
            {"name": "", "menus": {"1": []}},
            {"name": "No days", "menus": None},
            {"name": "Weekday is not a number", "menus": {"Montag": [
                {"title_de": "Egal", "price": "1.00"}]}},
            {"name": "Good", "menus": {"2": [
                "not a meal",
                {"title_de": "", "price": "1.00"},
                {"title_de": "Ohne Preis", "price": None},
                {"title_de": "Backhändl<br />Erdäpfelsalat", "price": "10.90"},
            ]}},
        ],
    })

    assert [m["name"] for m in canteen.feed.meals] == ["Backhändl, Erdäpfelsalat"]
    assert canteen.feed.meals[0]["date"] == "2026-10-20"


def test_week_that_is_not_a_dict_is_ignored():
    canteen = makeCanteen()
    for weekMenu in (None, [], "", {"available": False}, {"available": True}):
        canteen.addWeekMenuToFeed(weekMenu)
    assert canteen.feed.meals == []
