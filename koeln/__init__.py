#!/usr/bin/env python
# Python 3
import time
import os
import json
import urllib
import logging
from threading import Lock

import requests
from bs4 import BeautifulSoup

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, xml_escape, meta_from_xsl, xml_str_param
except ModuleNotFoundError:
    import sys
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, xml_escape, meta_from_xsl, xml_str_param

# Based on https://github.com/mswart/openmensa-parsers/blob/master/magdeburg.py

metaJson = os.path.join(os.path.dirname(__file__), "koeln.json")

metaTemplateFile = os.path.join(
    os.path.dirname(__file__), "metaTemplate_koeln.xml")


with open(metaJson, 'r', encoding='utf8') as meta_file:
    canteenDict = json.load(meta_file)

sourceUrl = "https://www.kstw.de/speiseplan"
mealsUrl = "https://sw-koeln.maxmanager.xyz/index.php"

headers = {
    'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
}

rolesOrder = ('student', 'employee', 'other')

# Global vars for caching
cacheMealsLock = Lock()
cacheMealsData = {}
cacheMealsTime = {}


def _getMealsURL(url, maxAgeMinutes=30):
    """Download website, if available use a cached version"""
    if url in cacheMealsData:
        ageSeconds = (time.time() - cacheMealsTime[url])
        if ageSeconds < maxAgeMinutes*60:
            logging.debug("From cache: %s [%ds old]", url, ageSeconds)
            return cacheMealsData[url]

    content = requests.get(url, headers=headers, timeout=10*60).text
    with cacheMealsLock:
        cacheMealsData[url] = content
        cacheMealsTime[url] = time.time()
    return content


def _parseMealsUrl(lazyBuilder, mensaId):
    content = _getMealsURL(mealsUrl)
    document = BeautifulSoup(content, "html.parser")

    mensaDivs = document.find_all(
        "div", class_="einrichtungsblock", attrs={"data-einrichtung": mensaId})

    if len(mensaDivs) < 2:
        logging.error("Mensa not found [id='%s']", mensaId)
        return

    for div in mensaDivs:
        for block in div.find_all("div", class_="essensblock"):
            date = block.attrs["data-essensdatum"]
            category = block.attrs["data-menuelinie"]
            for meal in block.find_all("div", class_="essenfakten"):
                essenstext = meal.find(class_="essenstext")
                beschreibungtext = meal.find(class_="beschreibungtext")
                mealName = ""
                if essenstext:
                    mealName += essenstext.text.strip()
                if beschreibungtext:
                    mealName += " " + beschreibungtext.text.strip()
                if not mealName:
                    continue

                prices = []
                preise = meal.find(class_="preise")
                if preise:
                    prices = [price.strip()
                              for price in preise.text.split('/')]
                    if len(prices) > 3:
                        prices = prices[:2] + prices[-1:]

                notes = []
                allerg = meal.find(attrs={"data-allerg": True})
                if allerg:
                    notes += [note.strip()
                              for note in allerg.attrs["data-allerg"].split("<br>")]

                zusatz = meal.find(attrs={"data-zusatz"})
                if zusatz:
                    notes += [note.strip()
                              for note in zusatz.attrs["data-zusatz"].split("<br>")]

                sonst = meal.find(attrs={"data-sonst"})
                if sonst:
                    notes += [note.strip()
                              for note in sonst.attrs["data-sonst"].split("<br>")]

                notes = [note.split("=")[-1].strip()
                         for note in notes if note.split("=")[-1].strip()]
                notes = [note for note in notes if note]

                lazyBuilder.addMeal(date, category, mealName,
                                    notes if notes else None,
                                    prices if prices else None,
                                    rolesOrder[0:len(prices)] if prices else None)


class Parser:
    def __init__(self, urlTemplate):
        self.urlTemplate = urlTemplate
        self.meta_xslt = os.path.join(os.path.dirname(__file__), "../meta.xsl")
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

    def meta(self, ref):
        """Generate an openmensa XML meta feed using XSLT"""
        if ref not in self.canteens:
            return 'Unknown canteen'
        mensa = self.canteens[ref]

        data = {
            "name": xml_str_param(mensa["name"]),
            "address": xml_str_param("%s, %s %s" % (mensa["strasse"], mensa["plz"], mensa["ort"])),
            "city": xml_str_param(mensa["ort"]),
            "latitude": xml_str_param(mensa["latitude"]),
            "longitude": xml_str_param(mensa["longitude"]),
            "phone": xml_str_param(mensa["phone"]),
            "times": mensa["infokurz"],
            "feed": xml_str_param(self.urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(mensa["reference"]))),
            "source": xml_str_param(sourceUrl),
        }

        return meta_from_xsl(self.meta_xslt, data)

    def feed(self, name):
        if name in self.canteens:
            lazyBuilder = StyledLazyBuilder()
            mensaId = self.canteens[name]["id"]
            _parseMealsUrl(lazyBuilder, mensaId)
            return lazyBuilder.toXMLFeed()
        return 'Wrong mensa name'


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = Parser("http://localhost/{metaOrFeed}/koeln_{mensaReference}.xml")
    # print(p.meta("iwz-deutz"))
    # print(p.feed("iwz-deutz"))
