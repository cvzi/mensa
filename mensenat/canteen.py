from datetime import date, timedelta, datetime
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
import html
import json
from pyopenmensa.feed import LazyBuilder
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

        The API hands the plan over as a JSON string. It returns null for a
        week it has no plan for, and nodeByUri itself is null for an unknown
        location. Both used to reach json.loads and raise, which aborted the
        whole feed. An empty dict lets the other week still be written.
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

        Everything is read defensively. A location can report itself as
        available and still come without a "menus" key - that is what the
        Vienna M-Cafe (mensenat/WiVetMed) does, and reading the key straight
        raised KeyError for the whole run. A week, a category or a single day
        that does not fit the expected shape is skipped instead.
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

            name = self.strip_html(meal.get("title_de"))
            price = meal.get("price")
            if name == "" or price in (None, ""):
                continue

            self.feed.addMeal(current_date, category_name, name,
                              notes=self.collectNotes(meal),
                              prices={"other": price})

    @staticmethod
    def collectNotes(meal):
        """Allergen letters plus the labels under "informations".

        Both arrive as a dict keyed by the short code, with the readable text
        as the value, and as an empty list when there is nothing. The labels
        were dropped before, so "VEGAN" never reached the feed although
        mensen.at marks several dishes with it every day.
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

        Replacing every tag with a space merged both lines into one run of
        words ("Seelachsfilet MSC im Backteig Gemuesereis | ..."), and the
        boundary could not be recovered afterwards. A comma keeps it readable
        and matches how the koeln parser joins a main dish with its sides.

        Entities are resolved as well; without it a note such as
        "SO2 + Sulfite &gt;10mg/kg" ended up double escaped in the XML.
        """
        if not text:
            return ""
        text = re.sub(r"<br\s*/?>", ", ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^<]+?>|\n", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        # A trailing <br /> is common and would leave a dangling comma.
        text = re.sub(r"\s*,(\s*,)*\s*", ", ", text)
        return text.strip().strip(",").strip()
