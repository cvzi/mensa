import sys
import os
import json
import logging
import urllib
import re
import textwrap

import requests
from pyopenmensa.feed import LazyBuilder
from bs4 import BeautifulSoup

try:
    from version import __version__, useragentname, useragentcomment
except ModuleNotFoundError:
    __version__, useragentname, useragentcomment = 0.1, requests.utils.default_user_agent(), "Python 3"

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

legend = {
    'A':  'kann Restalkohol enthalten',
    'Bio': 'Bio',
    'Ei': 'Eier und Eierzeugnisse',
    'En': 'Erdnüsse',
    'Fi': 'Fisch',
    'G': 'Geflügel',
    'Gl': 'Glutenhaltiges Getreide',
    'Gt': 'Gelantine',
    'K': 'Kalb',
    'Kr': 'Krebstiere (Krusten- und Schalentiere)',
    'L': 'Lamm',
    'La': 'Laktose',
    'Lu': 'Lupine',
    'Nu': 'Schalenfrüchte (Nüsse)',
    'R': 'Rind',
    'S': 'Schwein',
    'Se': 'Sesam',
    'Sf': 'Senf',
    'Sl': 'Sellerie',
    'So': 'Soja',
    'Sw': 'Schwefeldioxid (&quot;SO2&quot;) und Sulfite',
    'V': 'Vegetarisch',
    'V+': 'vegan',
    'W': 'Wild',
    'Wt': 'Weichtiere',
    '1': 'Farbstoff',
    '2': 'Konservierungsstoff',
    '3': 'Antioxidationsmittel',
    '4': 'Geschmacksverstärker',
    '5': 'geschwefelt',
    '6': 'geschwärzt',
    '7': 'gewachst',
    '8': 'Phosphat',
    '9': 'Süßungsmittel',
    '10': 'enthält eine Phenylalaninquelle'
}

allRoles = ('student', 'employee', 'other')
allRolesTitles = 'Studenten', 'Bedienstete', 'Gäste'


baseUrl = 'https://www.studierendenwerk-kaiserslautern.de/'

s = requests.Session()
s.headers = {
    'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
}


class Parser:
    def feed(self, refName):
        if refName not in self.canteens:
            return f"Unkown canteen '{refName}'"
        url = baseUrl + self.canteens[refName]["source"]
        lazyBuilder = LazyBuilder()
        lazyBuilder.setLegendData(legend)
        r = s.get(url)
        document = BeautifulSoup(r.text, "html.parser")

        for dayDiv in document.select(".dailyplan .dailyplan_content"):
            date = dayDiv.h5.text.strip()
            if "geschlossen" in date.lower():
                lazyBuilder.setDayClosed(date)
            for mealDiv in dayDiv.select(".subcolumns"):
                category = ("Ausgabe " + mealDiv.select(".counter-name strong")[0].text.strip()).strip()
                mealNode = mealDiv.select(".counter-meal strong")[0].extract()
                mealName = mealNode.text.strip()

                if mealDiv.select(".counter-meal u") and mealDiv.select(".counter-meal u")[0]:
                    specialName = mealDiv.select(".counter-meal u")[0].extract()
                    if category == "Ausgabe":
                        category = specialName.text.strip()
                    else:
                        category += ' ' + specialName.text.strip()
                if category.endswith(":"):
                    category = category[0:-1]

                prices = []
                roles = []
                pricesText = mealDiv.select(".counter-meal")[0].text.strip()
                for p in pricesText.split(" | "):
                    if p.strip():
                        for i, r in enumerate(allRolesTitles):
                            if r in p:
                                value = p.split(r)[1]
                                value = float(value.replace(
                                    ",", ".").replace("€", "").strip())
                                prices.append(value)
                                roles.append(allRoles[i])
                                break

                for j, productName in enumerate(textwrap.wrap(mealName, width=250)):
                    lazyBuilder.addMeal(date,
                                        category,
                                        productName,
                                        None,
                                        prices if j == 0 else None,
                                        roles if j == 0 else None)

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
                "source": baseUrl + mensa["source"],
            }
            openingTimes = {}
            pattern = re.compile(r"([A-Z][a-z])(\s*-\s*([A-Z][a-z]))?\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2}) Uhr")
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

    @staticmethod
    def __now():
        berlin = pytz.timezone('Europe/Berlin')
        now = datetime.datetime.now(berlin)
        return now

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)


def getParser(baseurl):
    return Parser(baseurl)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(getParser("http://localhost/{metaOrFeed}/mensenat_{mensaReference}.xml").feed("tuatrium"))
