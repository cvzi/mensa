import sys
import os
import json
import logging
import urllib
import re
import textwrap

import requests
from bs4 import BeautifulSoup

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, nowBerlin
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, nowBerlin

metaJson = os.path.join(os.path.dirname(__file__), "canteenDict.json")

metaTemplateFile = os.path.join(os.path.dirname(__file__), "metaTemplate.xml")

weekdaysMap = [
    ("Mo", "monday"),
    ("Di", "tuesday"),
    ("Mi", "wednesday"),
    ("Do", "thursday"),
    ("Fr", "friday"),
    ("Sa", "saturday"),
    ("So", "sunday")
]


class Parser:
    def feed(self, refName):
        if refName not in self.canteens:
            return f"Unkown canteen '{refName}'"
        path = self.canteens[refName]["source"]
        domain = self.canteens[refName]["domain"]

        if "change_language" in self.canteens[refName]:
            lang = self.canteens[refName]["change_language"]
            html = requests.get(f"https://{domain}/change_language/{lang}", headers={
                                "Referer": f"https://{domain}{path}"}).text
        else:
            html = requests.get(f"https://{domain}{path}").text

        lazyBuilder = StyledLazyBuilder()
        document = BeautifulSoup(html, "html.parser")

        # Dates
        dates = []
        today = nowBerlin()
        for day in document.select(".days_container .day"):
            try:
                i = int(day.text)
            except ValueError:
                continue

            date = today.replace(day=i)
            if date.day > today.day:
                date = date.replace(month=date.month - 1)
            if dates and date < dates[-1]:
                date = date.replace(month=date.month + 1)
            dates.append(date)

        # Meals
        table = document.find("div", {"id": "settimana"}).find(
            "table", {"class": "tabella_menu_settimanale"})

        for tr in table.select("tr"):
            category = tr.find("th").text.strip()
            for td in tr.select("td"):
                day_index = int(td.attrs["data-giorno"]) - 1
                for p in td.select("p.piatto_inline"):
                    name = p.text.replace(
                        " *", "").replace("* ", "").replace("*", "").strip()
                    for mealText in textwrap.wrap(name, width=250):
                        lazyBuilder.addMeal(
                            dates[day_index].date(), category, mealText)

        return lazyBuilder.toXMLFeed()

    def meta(self, refName):
        """Generate an openmensa XML meta feed from the static json file using an XML template"""
        with open(metaTemplateFile) as f:
            template = f.read()

        for reference, mensa in self.canteens.items():
            if refName != reference:
                continue

            data = {
                "name": mensa["name"],
                "address": mensa["address"],
                "city": mensa["city"],
                "phone": mensa['phone'],
                "latitude": mensa["latitude"],
                "longitude": mensa["longitude"],
                "feed": self.urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(reference)),
                "source": f"https://{mensa['domain']}{mensa['source']}",
            }
            openingTimes = {}
            pattern = re.compile(
                r"([A-Z][a-z])(\s*-\s*([A-Z][a-z]))?\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2}) Uhr")
            m = re.findall(pattern, mensa["times"])
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
            for key in data:
                data[key] = data[key]
            xml = template.format(**data)
            return xml

        return '<openmensa xmlns="http://openmensa.org/open-mensa-v2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.1" xsi:schemaLocation="http://openmensa.org/open-mensa-v2 http://openmensa.org/open-mensa-v2.xsd"/>'

    def __init__(self, urlTemplate):
        with open(metaJson, 'r', encoding='utf8') as f:
            self.canteens = json.load(f)

        self.urlTemplate = urlTemplate

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)


def getParser(urlTemplate):
    return Parser(urlTemplate)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(getParser(
        "http://localhost/{metaOrFeed}/markas_{mensaReference}.xml").feed("bolzano"))
    print(getParser(
        "http://localhost/{metaOrFeed}/markas_{mensaReference}.xml").feed("bressanone"))
