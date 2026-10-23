from datetime import date, timedelta, datetime
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
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

            allergens = meal.get("allergens")
            if isinstance(allergens, dict):
                notes = list(allergens.keys())
            elif isinstance(allergens, (list, tuple)):
                notes = list(allergens)
            else:
                notes = []

            self.feed.addMeal(current_date, category_name, name,
                              notes=notes, prices={"other": price})

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
        if not text:
            return ""
        return re.sub(" +", " ", re.sub("<[^<]+?>|\\n", " ", text)).strip()
