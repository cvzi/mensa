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
          openingHours {
            exceptions
          }
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
            "exceptions": self.parseExceptions((node.get("openingHours") or {}).get("exceptions")),
        }

    @staticmethod
    def parseExceptions(raw):
        r"""
        Turn openingHours.exceptions into {date: reason}.

        mensen.at sends the exceptions as a JSON string inside the JSON
        response, keyed by ISO date:

            "{\"2026-12-08\":{\"data\":\"Maria Empf\\u00e4ngnis\"}, ...}"

        With no exceptions it may be empty, null or "[]". Each location
        enters its own exceptions, and not all in the same form: a
        shortened day may come as a list of slots instead of a reason,
        e.g. "2027-02-01": ["07:30-14:00"] (Mensa PH Tirol, November 2026).
        Such a day is returned with the slots joined, so that
        addClosedDaysToFeed sees the time range and leaves it open. An
        empty reason ({"data": ""}) is a closed day without explanation.
        """
        if not raw:
            return {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                return {}
        if not isinstance(raw, dict):
            return {}
        exceptions = {}
        for day, value in raw.items():
            try:
                datetime.strptime(day, "%Y-%m-%d")
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                reason = value.get("data")
            elif isinstance(value, (list, tuple)):
                reason = ", ".join(str(slot) for slot in value if slot)
            else:
                reason = value
            exceptions[day] = "" if reason is None else " ".join(str(reason).split())
        return exceptions

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
        self.addClosedDaysToFeed(weekMenus["exceptions"], weekMenus["menuplanCurrentWeek"], weeks=2)

        return self.feed.toXMLFeed()

    def genereateCurrentWeekFeedXml(self) -> str:
        self.feed = LazyBuilder()
        weekMenus = self.fetchWeekMenus()
        self.addWeekMenuToFeed(weekMenus["menuplanCurrentWeek"])
        self.addClosedDaysToFeed(weekMenus["exceptions"], weekMenus["menuplanCurrentWeek"], weeks=1)

        return self.feed.toXMLFeed()

    # A time range in the reason means changed hours, not a closed day
    CHANGED_HOURS = re.compile(r"\d{1,2}[:.]\d{2}\s*[-–]\s*\d{1,2}[:.]\d{2}")

    def addClosedDaysToFeed(self, exceptions, currentWeek, weeks=2):
        """
        Mark holidays and closing periods from openingHours.exceptions.

        Only days within the weeks the feed covers are marked, so the feed
        does not grow with closing periods months ahead. A day that has
        meals stays open: the menu is the better evidence. A reason that
        names a time range ("nur 11:00-13:00") is a shortened day, which
        OpenMensa cannot express, so it is left alone.
        """
        if not exceptions:
            return
        first = None
        if isinstance(currentWeek, dict) and currentWeek.get("first_day"):
            try:
                first = datetime.strptime(currentWeek["first_day"], "%Y-%m-%d").date()
            except ValueError:
                first = None
        if first is None:
            today = date.today()
            first = today - timedelta(days=today.weekday())
        last = first + timedelta(days=7 * weeks - 1)

        for day, reason in sorted(exceptions.items()):
            current = datetime.strptime(day, "%Y-%m-%d").date()
            if current < first or current > last:
                continue
            if self.CHANGED_HOURS.search(reason or ""):
                continue
            if self.feed.hasMealsFor(current):
                continue
            self.feed.setDayClosed(current)

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
        # A trailing <br /> is common and would leave a dangling comma.
        text = re.sub(r"\s*,(\s*,)*\s*", ", ", text)
        return text.strip().strip(",").strip()
