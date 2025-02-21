from datetime import datetime
import locale
import sys
import os
import json
import logging
import urllib
import requests
from bs4 import BeautifulSoup as parse

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, xml_escape, meta_from_xsl, xml_str_param
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, xml_escape, meta_from_xsl, xml_str_param


class Parser:
    canteen_json = os.path.join(os.path.dirname(__file__), "canteenDict.json")
    meta_xslt = os.path.join(os.path.dirname(__file__), "../meta.xsl")
    roles = ("student", "employee", "other")

    def feed(self, ref: str) -> str:
        if ref not in self.canteens:
            return f"Unkown canteen with ref='{xml_escape(ref)}'"
        builder = StyledLazyBuilder()
        locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8') 

        document = parse(self._get_cached(
            "https://www.swerk-wue.de/wuerzburg/essen-trinken/mensen-speiseplaene/"+ref+"/menu").text, 'lxml')
        
        for day in document.find_all('div', class_='day-menu'):
            try:
                date = datetime.strptime(day.find('h3').text.split(", ")[1].strip() , "%d. %B %Y").date()
            except BaseException as e:
                logging.error("Error parsing date: %s", e)
                continue

            for meal in day.find(class_='day-menu-entries').find_all('article'):
                try:
                    name = meal.find('h5').text
                    category = meal.find('span', class_='food-icon')['title']
                    notes = [note.text.strip() for note in meal.find('div', class_='additive-list').find_all('li') if note.text.strip()]
                    priceDiv = meal.find('div', class_='price')
                    prices = [priceDiv.get('data-price-student'), priceDiv.get('data-price-servant'), priceDiv.get('data-price-guest')]
                    logging.debug("%s - Gericht: %s - Category: %s - Notes: %s - Prices: %s", date, name, category, notes, prices)
                    if not name or not category or not date:
                        raise Exception("Nececarry data missing")
                    else:
                        builder.addMeal(date, category, name, notes, prices, self.roles)
                except BaseException as e:
                    logging.error("Error parsing meal: %s", e)
                    continue
        
        return builder.toXMLFeed()

    def meta(self, ref):
        """Generate an openmensa XML meta feed using XSLT"""
        if ref not in self.canteens:
            return 'Unknown canteen'
        mensa = self.canteens[ref]

        data = {
            "name": xml_str_param(mensa["name"]),
            "address": xml_str_param(mensa["address"]),
            "city": xml_str_param(mensa["city"]),
            "latitude": xml_str_param(mensa["latitude"]),
            "longitude": xml_str_param(mensa["longitude"]),
            "feed": xml_str_param(self.url_template.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
            "source": xml_str_param('https://www.swerk-wue.de/wuerzburg/essen-trinken/mensen-speiseplaene'),
        }

        day_mapping = {
            "Montag": "Mo",
            "Dienstag": "Di",
            "Mittwoch": "Mi",
            "Donnerstag": "Do",
            "Freitag": "Fr",
            "Samstag": "Sa",
            "Sonntag": "So"
        }

        # Fetch opening Times from website
        document = parse(self._get_cached(
            "https://www.swerk-wue.de/wuerzburg/essen-trinken/mensen-speiseplaene/"+ref+"/menu").text, 'lxml')
        times = ""
        openingData = document.find('div', class_='opening-time_listing-all')
        if openingData:
            for dayData in openingData.find_all('div', class_='opening-time_days'):
                try:
                    day = dayData.find('div', class_='opening-time-day-range').text
                    time = dayData.find('div', class_='opening-times__time').text
                    for full_day, short_day in day_mapping.items():
                        day = day.replace(full_day, short_day)
                    times += (" " + day + time)
                except BaseException as e:
                    logging.error("Error parsing opening times: %s", e)
                    continue
        data["times"] = times
        print("Tines", data["times"])
        return meta_from_xsl(self.meta_xslt, data)

    def __init__(self, url_template):
        with open(self.canteen_json, 'r', encoding='utf8') as f:
            self.canteens = json.load(f)

        self.url_template = url_template
        self.session = requests.Session()
        self.session.headers = {
            'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}',
            'Accept-Encoding': 'utf-8'
        }
        self._cache = []

    def _get_cached(self, url):
        for key, content in self._cache:
            if key == url:
                logging.debug("Retrieved from cache: %s", url)
                return content
        content = self.session.get(url)
        self._cache.append((url, content))
        if len(self._cache) > 20:
            self._cache.pop(0)
        return content

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.url_template.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = Parser("http://localhost/")
    print(p.feed("mensa-am-studentenhaus-wuerzburg"))
    print(p.meta("mensa-am-studentenhaus-wuerzburg"))
