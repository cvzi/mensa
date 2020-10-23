#!/usr/bin/env python
# Python 3
import datetime
import time
import os
import json
import urllib
import re
import logging
import string
import textwrap
from threading import Lock, Thread

import requests
from bs4 import BeautifulSoup

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, nowBerlin
except ModuleNotFoundError:
    import sys
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, nowBerlin

# Based on https://github.com/mswart/openmensa-parsers/blob/master/magdeburg.py

metaJson = os.path.join(os.path.dirname(__file__), "koeln.json")

metaTemplateFile = os.path.join(
    os.path.dirname(__file__), "metaTemplate_koeln.xml")

templateSource = r"https://www.kstw.de/speiseplan?l="
templateMealsUrl = "https://www.kstw.de/speiseplan?l={ids}&t={{date}}"

with open(metaJson, 'r', encoding='utf8') as f:
    canteenDict = json.load(f)

mealsUrl = templateMealsUrl.format(ids=",".join(canteenDict.keys()))

headers = {
    'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
}

weekdaysMap = [
    ("Mo", "monday"),
    ("Di", "tuesday"),
    ("Mi", "wednesday"),
    ("Do", "thursday"),
    ("Fr", "friday"),
    ("Sa", "saturday"),
    ("So", "sunday")
]

rolesOrder = ('student', 'employee', 'other')


# Global vars for caching
cacheMealsLock = Lock()
cacheMealsData = {}
cacheMealsTime = {}
lazyBuilderLock = Lock()


def _getMealsURL(url, maxAgeMinutes=30):
    """Download website, if available use a cached version"""
    if url in cacheMealsData:
        ageSeconds = (time.time() - cacheMealsTime[url])
        if ageSeconds < maxAgeMinutes*60:
            logging.debug(f"From cache: {url} [{round(ageSeconds)}s old]")
            return cacheMealsData[url]

    content = requests.get(url, headers=headers, timeout=10*60).text
    with cacheMealsLock:
        cacheMealsData[url] = content
        cacheMealsTime[url] = time.time()
    return content


def _parseMealsUrl(lazyBuilder, mensaId, day=None):
    if day is None:
        day = nowBerlin().date()
    date = day.strftime("%Y-%m-%d")

    content = _getMealsURL(mealsUrl.format(date=date))
    document = BeautifulSoup(content, "html.parser")

    mensaDivs = document.find_all(
        "div", class_="tx-epwerkmenu-menu-location-wrapper")
    mensaDivs = [
        mensaDiv for mensaDiv in mensaDivs if mensaDiv.attrs["data-location"] == str(mensaId)]
    if len(mensaDivs) != 1:
        # Check if mensa is in drowndown selector
        checkbox = document.find(id=f"building-id-{mensaId}")
        if checkbox:
            logging.debug(f"No meals found [id='{mensaId}']")
            with lazyBuilderLock:
                lazyBuilder.setDayClosed(date)
        else:
            logging.error(f"Mensa not found [id='{mensaId}']")
        return False

    mensaDiv = mensaDivs.pop()
    menuTiles = mensaDiv.find_all("div", class_="menue-tile")

    foundAny = False
    for menuTile in menuTiles:
        category = string.capwords(menuTile.attrs["data-category"])
        mealName = menuTile.find(
            class_="tx-epwerkmenu-menu-meal-title").text.strip()
        desc = menuTile.find(class_="tx-epwerkmenu-menu-meal-description")
        if desc and desc.text.strip():
            mealName = f"{mealName} {desc.text.strip()}"

        additives = menuTile.find(class_="tx-epwerkmenu-menu-meal-additives")
        for sup in additives.find_all('sup'):
            sup.extract()
        notes = [note.strip()
                 for note in additives.text.split("\n") if note.strip()]

        pricesDiv = menuTile.find(
            class_="tx-epwerkmenu-menu-meal-prices-values")

        roles = []
        prices = []
        for j, price in enumerate(pricesDiv.text.split('/')):
            price = price.strip().replace(',', '.')
            try:
                price = float(price)
                prices.append(price)
                roles.append(rolesOrder[j])
            except ValueError:
                pass

        with lazyBuilderLock:
            for j, mealText in enumerate(textwrap.wrap(mealName, width=250)):
                lazyBuilder.addMeal(date, category, mealName,
                                    notes if j == 0 else None,
                                    prices if j == 0 else None,
                                    roles if j == 0 else None)
        foundAny = True

    if foundAny:
        return True

    with lazyBuilderLock:
        lazyBuilder.setDayClosed(date)

    return False


def _generateCanteenMeta(mensa, urlTemplate):
    """Generate an openmensa XML meta feed from the static json file using an XML template"""
    template = open(metaTemplateFile).read()

    data = {
        "name": mensa["name"],
        "adress": "%s %s %s %s" % (mensa["name"], mensa["strasse"], mensa["plz"], mensa["ort"]),
        "city": mensa["ort"],
        "phone": mensa["phone"],
        "latitude": mensa["latitude"],
        "longitude": mensa["longitude"],
        "feed_today": urlTemplate.format(metaOrFeed='today', mensaReference=urllib.parse.quote(mensa["reference"])),
        "feed_full": urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(mensa["reference"])),
        "source_today": templateSource + mensa["id"],
        "source_full": templateSource + mensa["id"]
    }
    openingTimes = {}
    infokurz = mensa["infokurz"]
    pattern = re.compile(
        "([A-Z][a-z])( - ([A-Z][a-z]))? (\d{1,2})\.(\d{2}) - (\d{1,2})\.(\d{2}) Uhr")
    m = re.findall(pattern, infokurz)
    for result in m:
        fromDay, _, toDay, fromTimeH, fromTimeM, toTimeH, toTimeM = result
        openingTimes[fromDay] = "%02d:%02d-%02d:%02d" % (
            int(fromTimeH), int(fromTimeM), int(toTimeH), int(toTimeM))
        if toDay:
            select = False
            for short, long in weekdaysMap:
                if short == fromDay:
                    select = True
                elif select:
                    openingTimes[short] = "%02d:%02d-%02d:%02d" % (
                        int(fromTimeH), int(fromTimeM), int(toTimeH), int(toTimeM))
                if short == toDay:
                    select = False

        for short, long in weekdaysMap:
            if short in openingTimes:
                data[long] = 'open="%s"' % openingTimes[short]
            else:
                data[long] = 'closed="true"'

    xml = template.format(**data)
    return xml


class Parser:
    def __init__(self, urlTemplate):
        self.urlTemplate = urlTemplate
        self.canteens = {}
        for mensaId in canteenDict:
            canteenDict[mensaId]["id"] = mensaId
            self.canteens[canteenDict[mensaId]
                          ["reference"]] = canteenDict[mensaId]

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)

    def meta(self, name):
        if name in self.canteens:
            return _generateCanteenMeta(self.canteens[name], self.urlTemplate)
        return 'Wrong mensa name'

    def feed_today(self, name):
        if name in self.canteens:
            today = nowBerlin().date()
            lazyBuilder = StyledLazyBuilder()
            mensaId = self.canteens[name]["id"]
            _parseMealsUrl(lazyBuilder, mensaId, today)
            return lazyBuilder.toXMLFeed()
        return 'Wrong mensa name'

    def feed_all(self, name):
        startTime = time.time()
        if name in self.canteens:
            mensaId = self.canteens[name]["id"]
            lazyBuilder = StyledLazyBuilder()

            date = nowBerlin()

            # Get today
            ret = _parseMealsUrl(lazyBuilder, mensaId, date.date())

            n = 1
            if ret:
                date += datetime.timedelta(days=1)
                # Get this week
                threads = []
                while date.weekday() < 5:
                    t = Thread(target=_parseMealsUrl, args=(
                        lazyBuilder, mensaId, date.date()))
                    t.start()
                    threads.append(t)
                    date += datetime.timedelta(days=1)
                    n += 1


                # Skip over weekend
                date += datetime.timedelta(days=7 - date.weekday())

                # Get next week
                while date.weekday() < 5 and n < 5:
                    t = Thread(target=_parseMealsUrl, args=(
                        lazyBuilder, mensaId, date.date()))
                    t.start()
                    threads.append(t)
                    date += datetime.timedelta(days=1)
                    n += 1


                for t in threads:
                    t.join()

            endTime = time.time()
            logging.debug(
                f"feed_all({name}) took {endTime - startTime:.2f} seconds")

            return lazyBuilder.toXMLFeed()
        return 'Wrong mensa name'


def getParser(urlTemplate):
    parser = Parser(urlTemplate)
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = getParser("http://localhost/{metaOrFeed}/koeln_{mensaReference}.xml")
    # print(p.meta("iwz-deutz"))
    # print(p.feed_all("iwz-deutz"))
