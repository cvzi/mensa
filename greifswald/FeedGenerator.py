"""
Original file: https://github.com/derconno/OpenMensaParserHOST/blob/9b183e9eb0c93df9643cc9caf7ea2e68a6545112/FeedGenerator.py

Modified 2022-03-22 by cvzi (cuzi@openmail.cc)

"""

import sys
import os
import requests
from bs4 import BeautifulSoup
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
        for div in soup.find_all('div', {'class': 'csc-textpic-text'}):
            if 'KENNZEICHNUNGSPFLICHTIGE ZUSATZSTOFFE' in div.text:
                text = str(div.text).replace('KENNZEICHNUNGSPFLICHTIGE ALLERGENE:', '') \
                    .replace('KENNZEICHNUNGSPFLICHTIGE ZUSATZSTOFFE:', '') \
                    .replace('SONSTIGE KENNZEICHNUNGEN:', '')
                mensa.setLegendData(
                    text=text, regex='(?P<name>(\d|[a-zA-Z])+)\)\s*(?P<value>([\w/]+)((\s+\w+)*[^0-9)]))')

        if mensa.legendData:
            for key in mensa.legendData:
                mensa.legendData[key] = mensa.legendData[key].strip(',')

    for table in soup.find_all('table', {'class': 'table module-food-table'}):
        category = table.find('th').text.strip()
        for tr in table.find('tbody').find_all('tr'):
            td = tr.find('td').text.strip().split('\n')
            meal = ''
            price = ''
            for string in td:
                if '€' in string:
                    price = string.strip().split('\xa0€')[:3]
                elif len(string) > 1:
                    meal += (string.strip() + ' ')
            mensa.addMeal(day, category, meal, prices=price,
                          roles=['student', 'employee', 'other'])
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
