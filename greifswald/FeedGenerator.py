"""
Original file: https://github.com/derconno/OpenMensaParserHOST/blob/9b183e9eb0c93df9643cc9caf7ea2e68a6545112/FeedGenerator.py

Modified 2022-03-22 by cvzi (cuzi@openmail.cc)

"""

import sys
import os
import requests
from bs4 import BeautifulSoup
import bs4.element
from datetime import date, timedelta

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder

headers = {
    'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
}


def getMealsForDay(mensa: StyledLazyBuilder, day: str, canteen: str):

    if date.fromisoformat(day).weekday() > 4:  # Saturday or Sunday
        mensa.setDayClosed(date.fromisoformat(day))
        return True

    html = requests.get("https://www.stw-greifswald.de/essen/speiseplaene/" +
                        canteen + "/?datum=" + day, headers=headers).text
    soup = BeautifulSoup(html, 'html.parser')

    if mensa.legendData is None:
        for div in soup.find_all('div', {'class': 'col-12'}):
            for child in div.children:
                if type(child) == bs4.element.Tag and child.text == 'Kennzeichnungspflichtige Zusatzstoffe':
                    mensa.legendData = {}
                    for item in div.find_all("li"):
                        mensa.legendData[item.contents[0].text] = item.contents[1].text

    for table in soup.find_all('table', {'class': 'menu-table'}):
        category = ''
        for tr in table.find_all('tr'):
            if 'class' in tr.attrs and "menu-table-row" in tr.attrs['class']:
                category = tr.find("td").text.strip()
            else:
                meal = tr.find("td").text.strip()
                prices = [_p.text.strip().replace("\xa0", " ")
                          for _p in tr.find_all("td")[-3:]]
                if '' in prices:
                    mensa.addMeal(day, category, meal)
                else:
                    mensa.addMeal(day, category, meal, prices=prices, roles=[
                                  'student', 'employee', 'other'])
    return mensa.hasMealsFor(date.fromisoformat(day))


def generateToday(canteen_name: str):
    mensa = StyledLazyBuilder()

    day = date.today()

    getMealsForDay(mensa, day.isoformat(), canteen_name)

    return mensa.toXMLFeed()


def generateFull(canteen_name: str):
    mensa = StyledLazyBuilder()

    day = date.today()

    while getMealsForDay(mensa, day.isoformat(), canteen_name):
        day = day + timedelta(days=1)

    return mensa.toXMLFeed()


if __name__ == "__main__":
    print(generateToday("mensa-am-berthold-beitz-platz"))
