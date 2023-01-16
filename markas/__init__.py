import sys
import os
import json
import logging
import urllib
import re
import textwrap
import datetime

import requests
from bs4 import BeautifulSoup

try:
    from version import __version__
    from util import StyledLazyBuilder, now_local, weekdays_map
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, now_local, weekdays_map

metaJson = os.path.join(os.path.dirname(__file__), "canteenDict.json")

metaTemplateFile = os.path.join(os.path.dirname(__file__), "metaTemplate.xml")


class Parser:
    def feed(self, refName):
        if refName not in self.canteens:
            return f"Unkown canteen '{refName}'"
        path = self.canteens[refName]["source"]
        domain = self.canteens[refName]["domain"]
        pasto = self.canteens[refName].get("pasto", None)

        today = now_local()

        if "{timestamp}" in path:
            if today.weekday() == 6:
                ts = today + datetime.timedelta(days=1)
            else:
                ts = today

            path = path.format(timestamp=int(ts.timestamp()))
        if "change_language" in self.canteens[refName]:
            lang = self.canteens[refName]["change_language"]
            html = requests.get(f"https://{domain}/change_language/{lang}", headers={
                                "Referer": f"https://{domain}{path}"}).text
        else:
            html = requests.get(f"https://{domain}{path}").text

        lazyBuilder = StyledLazyBuilder()
        document = BeautifulSoup(html, "html.parser")

        # Log name
        logging.debug("\tReference: %s", refName)
        for selected in document.select('#selector_bar_container select option[selected]'):
            if selected.text:
                logging.debug("\tSelected: %s", selected.text)
            else:
                logging.debug("\tSelected: %s", selected)

        # Dates
        dates = []
        monday = today - datetime.timedelta(days=today.weekday())
        for day in document.select(".days_container .day"):
            try:
                i = int(day.text)
            except ValueError:
                continue

            try:
                date = monday.replace(day=i)
            except ValueError:
                date = monday.replace(
                    month=monday.month + 1 if monday.month < 12 else 1, day=i)

            if dates and date < dates[-1]:
                date = monday.replace(
                    month=monday.month + 1 if monday.month < 12 else 1, day=i)

            dates.append(date)

        # Meals

        settimana = document.find("div", {"id": "settimana"})
        if settimana:
            for table in settimana.select("table.tabella_menu_settimanale"):

                if table.find("h5"):
                    heading = table.find("h5").text.strip().lower()
                    if heading:
                        if pasto and heading != pasto.lower():
                            logging.debug(
                                f"\tSkipping pasto: {heading} (!= {pasto.lower()})")
                            continue
                        else:
                            logging.debug("\tUsing pasto: %s", heading)

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

            path = mensa['source'].replace("{timestamp}", "")
            data = {
                "name": mensa["name"],
                "address": mensa["address"],
                "city": mensa["city"],
                "phone": mensa['phone'],
                "latitude": mensa["latitude"],
                "longitude": mensa["longitude"],
                "feed": self.urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(reference)),
                "source": f"https://{mensa['domain']}{path}",
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
                    for short, long in weekdays_map:
                        if short == fromDay:
                            select = True
                        elif select:
                            openingTimes[short] = "%02d:%02d-%02d:%02d" % (
                                int(fromTimeH), int(fromTimeM), int(toTimeH), int(toTimeM))
                        if short == toDay:
                            select = False

                for short, long in weekdays_map:
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(Parser("http://localhost/{metaOrFeed}/markas_{mensaReference}.xml")
          .feed("bolzano"))
