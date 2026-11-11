from datetime import date, timedelta, datetime
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
import html
import json
from util import StyledLazyBuilder as LazyBuilder
import re


class Canteen:
    def __init__(self, uri: str):
        match = re.search(r"https:\/\/www\.mensen\.at\/standort\/(.*?)(\/|$)", uri)
        if match:
            self.location = match.group(1)
        else:
            raise ValueError("No canteen id found in link: " + uri)

    def fetchWeekMenus(self):
        query = gql("""
query Location($locationUri: String!) {
      nodeByUri(uri: $locationUri) {
        ... on Location {
          menuplanCurrentWeek
          menuplanNextWeek
        }
      }
    }
    """)

        # Define the transport with the GraphQL endpoint
        transport = RequestsHTTPTransport(url="https://backend.mensen.at/api")
        client = Client(
            transport=transport,
            fetch_schema_from_transport=False,  # Disable schema fetching
        )

        params = {
            "locationUri": f"standort/{self.location}"
        }

        result = client.execute(query, variable_values=params)

        node = (result or {}).get("nodeByUri") or {}
        return {
            "menuplanCurrentWeek": self.parseMenuplan(node.get("menuplanCurrentWeek")),
            "menuplanNextWeek": self.parseMenuplan(node.get("menuplanNextWeek")),
        }

    @staticmethod
    def parseMenuplan(raw):
        """Turn one menuplan field into a dict.
        """
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def generateTotalFeedXml(self) -> str:
        weekMenus = self.fetchWeekMenus()
        self.feed = LazyBuilder()
        self.addWeekMenuToFeed(weekMenus["menuplanCurrentWeek"])
        self.addWeekMenuToFeed(weekMenus["menuplanNextWeek"])

        return self.feed.toXMLFeed()

    def genereateCurrentWeekFeedXml(self) -> str:
        self.feed = LazyBuilder()
        weekMenus = self.fetchWeekMenus()
        self.addWeekMenuToFeed(weekMenus["menuplanCurrentWeek"])

        return self.feed.toXMLFeed()

    def addWeekMenuToFeed(self, weekMenu) -> str:
        """Add one week to the feed.
        """
        if not isinstance(weekMenu, dict) or weekMenu.get("available") is False:
            return

        firstDayOfTheWeek = weekMenu.get("first_day")
        if not firstDayOfTheWeek:
            return

        for category in weekMenu.get("menus") or []:
            if not isinstance(category, dict):
                continue

            category_name = self.strip_html(category.get("name"))
            days = category.get("menus")
            if category_name == "" or not isinstance(days, dict):
                continue

            for weekday, menu in days.items():
                try:
                    current_date = self.calculateDateFromWeekdayNumberGiven(firstDayOfTheWeek, weekday)
                except ValueError:
                    continue
                self.addMealsToFeed(category_name, current_date, menu)

    def addMealsToFeed(self, category_name, current_date, meals):
        if not isinstance(meals, list):
            return

        for meal in meals:
            if not isinstance(meal, dict):
                continue

            name, description = self.splitTitle(meal.get("title_de"))
            price = meal.get("price")
            if name == "" or price in (None, ""):
                continue

            notes = self.collectNotes(meal)
            notes.extend(self.splitNote(description))

            self.feed.addMeal(current_date, category_name, name,
                              notes=notes, prices={"other": price})

    # mensen.at separates the lines of a dish with <br />, and for most of
    # them that is the dish and what comes with it. Some carry a marketing
    # description in between, several sentences long - the "Brainfood" range
    # is the clearest example:
    #
    #     Brainfood Texanischer Bohneneintopf
    #     Bohnen, Paprika und ausgewaehlte Gewuerze sorgen fuer eine ...
    #     In Zusammenarbeit mit Prof.DDr. ... (Kuechenmeister)
    #     mit orientalischer Cous Cous
    #
    # Joining all of it into the name produces names of 250+ characters for
    # nine dishes across the 41 locations, up to 379. open-mensa-v2.xsd caps
    # a name at 250 and says so in as many words: "Shouldn't be more than a
    # couple of words or a sentence in maximum. Additional text may go into
    # several notes." Those feeds are invalid against the project's own
    # schema.
    #
    # The description becomes a note instead, so nothing is lost and the
    # name stays a name. It is recognised per dish rather than per line:
    # other locations wrap the same text into short lines, and one of those
    # on its own looks like a list of ingredients ("Eine vielfaeltige
    # Auswahl an Gemuese, kombiniert mit Kurkuma, Ingwer und" - 70
    # characters, no sentence end). Only in the context of the whole dish is
    # it clear that the line sits mid-sentence.
    #
    # The thresholds come from all 41 locations, 542 dishes, 693 lines after
    # the first break: the sentence-end test matches no genuine list of
    # ingredients at all, and 99 percent of those are at most 82 characters
    # (26 on average).
    SENTENCE_END = re.compile(r"[a-zäöüß]\.(\s|$)")
    VERY_LONG = 90
    INGREDIENTS_MAX = 50

    @classmethod
    def splitTitle(cls, title):
        """Split one title_de into the dish name and its description.

        Returns (name, description). The description is empty for the
        ordinary case of a dish followed by its ingredients.
        """
        parts = [cls.compact(p) for p in re.split(r"<br\s*/?>", title or "",
                                                  flags=re.IGNORECASE)]
        parts = [p for p in parts if p]
        if not parts:
            return "", ""

        head, rest = parts[0], parts[1:]
        has_description = any(len(p) >= cls.VERY_LONG or cls.SENTENCE_END.search(p)
                              for p in rest)
        if not has_description:
            return cls.tidyCommas(", ".join([head] + rest)), ""

        ingredients = [p for p in rest
                       if len(p) <= cls.INGREDIENTS_MAX and not cls.SENTENCE_END.search(p)]
        description = [p for p in rest if p not in ingredients]
        return (cls.tidyCommas(", ".join([head] + ingredients)),
                " ".join(description))

    # open-mensa-v2.xsd caps a note at 250 characters just as it caps a
    # name, and the longest description across the 41 locations is 334. The
    # schema allows any number of notes per meal and points at them for
    # exactly this ("Additional text may go into several notes"), so a long
    # description is split rather than cut. Sentence boundaries first, a
    # word boundary where a single sentence is longer than the limit.
    NOTE_MAX = 250

    @classmethod
    def splitNote(cls, text):
        """Split one long description into notes of at most NOTE_MAX each.

        Returns a list, empty for empty input.
        """
        text = (text or "").strip()
        if not text:
            return []

        pieces = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if not sentence:
                continue
            if pieces and len(pieces[-1]) + 1 + len(sentence) <= cls.NOTE_MAX:
                pieces[-1] += " " + sentence
            else:
                pieces.append(sentence)

        notes = []
        for piece in pieces:
            while len(piece) > cls.NOTE_MAX:
                cut = piece.rfind(" ", 0, cls.NOTE_MAX)
                if cut <= 0:
                    cut = cls.NOTE_MAX
                notes.append(piece[:cut].strip())
                piece = piece[cut:].strip()
            if piece:
                notes.append(piece)
        return notes

    @staticmethod
    def compact(text):
        """Resolve entities, drop remaining tags, collapse whitespace."""
        if not text:
            return ""
        text = re.sub(r"<[^<]+?>|\n", " ", text)
        return re.sub(r"\s+", " ", html.unescape(text)).strip()

    @staticmethod
    def collectNotes(meal):
        """Allergen letters plus the labels under "informations".
        """
        notes = []
        for field in ("allergens", "informations"):
            value = meal.get(field)
            if isinstance(value, dict):
                notes.extend(str(key) for key in value.keys() if str(key))
            elif isinstance(value, (list, tuple)):
                notes.extend(str(entry) for entry in value if entry)
        return notes

    # for some reason, mensen.at doesnt provide the concrete date of the menu but the number of the week day of the current week.
    # To get the correct date we need to calculate the date again
    def calculateDateFromWeekdayNumberGiven(self, firstDayOfTheWeekStr: str, weekDayNumber: str) -> date:
        try:
            firstDayOfTheWeek = datetime.strptime(firstDayOfTheWeekStr, "%Y-%m-%d").date()
            delta = int(weekDayNumber) - 1
            currentDate = firstDayOfTheWeek + timedelta(days=delta)
            return currentDate.strftime("%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Failed to generate week day date: {e}") from e

    def strip_html(self, text):
        """Turn one HTML field from mensen.at into plain text.

        mensen.at puts the dish and what comes with it into a single field and
        separates the two with <br />:

            Seelachsfilet MSC im Backteig<br />
            Gemuesereis | Sauce Tyrolienne | Zitrone

        XML entities are resolved as well.
        """
        if not text:
            return ""
        text = re.sub(r"<br\s*/?>", ", ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^<]+?>|\n", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return self.tidyCommas(text)

    @staticmethod
    def tidyCommas(text):
        """Collapse repeated commas and the whitespace around them.

        A line that already ends in a comma, or a trailing <br />, would
        otherwise leave two. A comma between digits is a decimal separator
        and stays untouched: several locations put a price in the category
        name ("Study Teller € 5,20"), and normalising every comma turned
        that into "€ 5, 20".
        """
        text = re.sub(r",(?:\s*,)+", ",", text)
        text = re.sub(r"\s+,", ",", text)
        text = re.sub(r",(?!\s)(?<!\d,)", ", ", text)
        return text.strip().strip(",").strip()
