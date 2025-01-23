from datetime import date, timedelta, datetime
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
import json
from pyopenmensa.feed import LazyBuilder
import re
import logging

class Canteen:
    def __init__(self, uri: str):
        match = re.search(r"https:\/\/www\.mensen\.at\/standort\/(.*?)(\/|$)", uri)
        if match:
            self.location= match.group(1)
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
            fetch_schema_from_transport=False  # Disable schema fetching
        )

        params = {
                "locationUri": f"standort/{self.location}"
            }

        result = client.execute(query, variable_values=params)

        menuplanCurrentWeek = json.loads(result["nodeByUri"]["menuplanCurrentWeek"])
        menuPlanNextWeek = json.loads(result["nodeByUri"]["menuplanNextWeek"])
        weekMenus = {
            "menuplanCurrentWeek": menuplanCurrentWeek,
            "menuplanNextWeek": menuPlanNextWeek
            }

        return weekMenus
    
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
        if weekMenu['available'] == False:
            return
        
        firstDayOfTheWeek = weekMenu["first_day"]
        
        for category in weekMenu["menus"]:
            category_name = category["name"]
            if category_name == '' or not 'menus' in category:
                continue

            for weekday, menu in category["menus"].items():
                current_date = self.calculateDateFromWeekdayNumberGiven(firstDayOfTheWeek, weekday)
                self.addMealsToFeed(category_name, current_date, menu)


    def addMealsToFeed(self, category_name, current_date, meals):
        for meal in meals:
            name = meal['title_de']
            price = meal['price']
            allergens = meal['allergens']
            if isinstance(allergens, dict):
                allergens = allergens.keys()
            notes = allergens
            prices = {'other': meal['price']}
            self.feed.addMeal(current_date, category_name, name, notes=notes, prices=prices)
        
    

    # for some reason, mensen.at doesnt provide the concrete date of the menu but the number of the week day of the current week.
    # To get the correct date we need to calculate the date again
    def calculateDateFromWeekdayNumberGiven(self, firstDayOfTheWeekStr: str, weekDayNumber: str) -> date:
        try:
            firstDayOfTheWeek = datetime.strptime(firstDayOfTheWeekStr,"%Y-%m-%d").date()
            delta = int(weekDayNumber) - 1
            currentDate = firstDayOfTheWeek + timedelta(days=delta)
            return currentDate.strftime("%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Failed to generate week day date: {e}") from e

    