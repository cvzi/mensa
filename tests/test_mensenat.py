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
    """Stands in for the feed builder and keeps what the parser hands over."""

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


def test_decimal_commas_survive():
    """Several locations put a price in the category name."""
    canteen = makeCanteen()

    assert canteen.strip_html("Tagesangebot VEGGIE / VEGAN / Study Teller € 5,20") \
        == "Tagesangebot VEGGIE / VEGAN / Study Teller € 5,20"
    assert canteen.strip_html("Menü 1,5 Liter Getränk") == "Menü 1,5 Liter Getränk"

    # A line of the source ending in a comma must still not produce two.
    assert canteen.strip_html("Rotbarsch<br />in feiner Sauce,<br />mit Reis") \
        == "Rotbarsch, in feiner Sauce, mit Reis"
    assert Canteen.tidyCommas("A,,,B") == "A, B"
    assert Canteen.tidyCommas("Sauce , mit Reis") == "Sauce, mit Reis"


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


def test_split_title_keeps_the_ordinary_case_intact():
    assert Canteen.splitTitle(
        "Seelachsfilet MSC im Backteig  <br />\nGemüsereis | Sauce Tyrolienne | Zitrone<br />\n"
    ) == ("Seelachsfilet MSC im Backteig, Gemüsereis | Sauce Tyrolienne | Zitrone", "")

    assert Canteen.splitTitle("Champignoncremesuppe") == ("Champignoncremesuppe", "")
    assert Canteen.splitTitle(None) == ("", "")

    # A line ending in a comma must not produce two.
    assert Canteen.splitTitle("Rotbarschfilet<br />in feiner Sauce,<br />mit Reis") \
        == ("Rotbarschfilet, in feiner Sauce, mit Reis", "")


def test_split_title_moves_a_description_out_of_the_name():
    name, description = Canteen.splitTitle(
        "Brainfood Texanischer Bohneneintopf<br />\n"
        "Bohnen, Paprika und ausgewählte Gewürze sorgen für eine aromatische "
        "Kombination mit leichter Schärfe.<br />\n"
        "In Zusammenarbeit mit Prof.DDr. Leal-Garcia & Attila Várnagy M.Sc. (Küchenmeister)<br />\n"
        "mit orientalischer Cous Cous")

    # The side dish stays with the name, the sentences move to the note.
    assert name == "Brainfood Texanischer Bohneneintopf, mit orientalischer Cous Cous"
    assert description.startswith("Bohnen, Paprika und ausgewählte Gewürze sorgen")
    assert "Küchenmeister" in description
    assert len(name) <= 250


def test_split_title_sees_a_description_wrapped_into_short_lines():
    """Other locations wrap the same text; no single line looks like prose."""
    name, description = Canteen.splitTitle(
        "Brainfood Gemüse Curry Madras mit Hirse<br />"
        "Eine vielfältige Auswahl an Gemüse, kombiniert mit Kurkuma, Ingwer und<br />"
        "Kreuzkümmel, verleiht diesem Curry sein charakteristisches Aroma. Kokosmilch<br />"
        "sorgt für eine cremige Textur, während Cranberries und Datteln eine dezente<br />"
        "natürliche Süße beisteuern.")

    assert name == "Brainfood Gemüse Curry Madras mit Hirse"
    assert "Kreuzkümmel" in description


def test_description_becomes_a_note():
    canteen = makeCanteen()
    canteen.addWeekMenuToFeed({
        "available": True,
        "first_day": "2026-10-26",
        "menus": [{
            "name": "Menü Veggie",
            "menus": {"4": [{
                "title_de": ("Brainfood Chili sin Carne<br />"
                             "Bohnen und Gewürze verleihen diesem Gericht seine Note.<br />"
                             "mit Reis"),
                "price": "6.80",
                "allergens": {"F": "Sojabohne"},
                "informations": {"VEGAN": {"name": "VEGAN"}},
            }]},
        }],
    })

    meal = canteen.feed.meals[0]
    assert meal["name"] == "Brainfood Chili sin Carne, mit Reis"
    assert meal["notes"] == ["F", "VEGAN",
                             "Bohnen und Gewürze verleihen diesem Gericht seine Note."]


def test_a_long_description_is_split_into_several_notes():
    """open-mensa-v2.xsd caps a note at 250 characters, like a name."""
    sentences = ("Bohnen, Paprika und Gewürze sorgen für eine aromatische Note. "
                 "Cashewkerne ergänzen das Gericht. ") * 4
    notes = Canteen.splitNote(sentences)

    assert notes, "a description must not vanish"
    assert all(len(n) <= 250 for n in notes)
    # Nothing is lost: every sentence is still there.
    assert "Cashewkerne ergänzen das Gericht." in " ".join(notes)

    # A single sentence longer than the limit is split at a word boundary.
    notes = Canteen.splitNote("Wort " * 80)
    assert all(len(n) <= 250 for n in notes)
    assert not any(n.endswith("Wor") for n in notes)

    assert Canteen.splitNote("") == []
    assert Canteen.splitNote(None) == []
