import sys
import os
import json
import requests
import logging
import urllib
import re

import lxml.etree
import defusedxml.lxml

try:
    from version import __version__, useragentname, useragentcomment
    from util import nowBerlin, xmlEscape
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import nowBerlin, xmlEscape, weekdays_map


class Parser:
    canteen_json = os.path.join(os.path.dirname(__file__), "canteens.json")
    meta_xslt = os.path.join(os.path.dirname(__file__), "meta.xsl")
    feed_xslt = os.path.join(os.path.dirname(__file__), "feed.xsl")
    headers = {
        'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
    }
    meals_current_week = 'https://menuplan.eurest.at/CurrentWeek/{ref}.xml'
    meals_next_week = 'https://menuplan.eurest.at/NextWeek/{ref}.xml'
    source_url = 'https://menuplan.eurest.at/menu.html?current_url=%2FCurrentWeek%2F{ref}.xml'

    def feed(self, ref: str, get_next_week=True) -> str:
        """Generate an openmensa XML feed from the source xml using XSLT"""
        if ref not in self.canteens:
            return f"Unknown canteen with ref='{xmlEscape(ref)}'"

        if nowBerlin().weekday() > 4:
            meals_url = self.meals_current_week.format(
                ref=urllib.parse.quote(ref))
        else:
            meals_url = self.meals_next_week.format(
                ref=urllib.parse.quote(ref))

        source = requests.get(meals_url, headers=self.headers, stream=True).raw
        dom = defusedxml.lxml.parse(source)
        xslt_tree = defusedxml.lxml.parse(self.feed_xslt)
        xslt = lxml.etree.XSLT(xslt_tree)
        new_dom = xslt(dom)
        return lxml.etree.tostring(new_dom,
                                   pretty_print=True,
                                   xml_declaration=True,
                                   encoding=new_dom.docinfo.encoding).decode('utf-8')

    def meta(self, ref):
        """Generate an openmensa XML meta feed using XSLT"""
        if ref not in self.canteens:
            return f"Unknown canteen with ref='{xmlEscape(ref)}'"
        mensa = self.canteens[ref]

        def param(s): return lxml.etree.XSLT.strparam(str(s))

        data = {
            "name": param(mensa["name"]),
            "address": param(mensa["address"]),
            "city": param(mensa["city"]),
            "latitude": param(mensa["latitude"]),
            "longitude": param(mensa["longitude"]),
            "feed": param(self.url_template.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
            "source": param(self.source_url.format(ref=urllib.parse.quote(ref))),
        }

        if "phone" in mensa:
            mensa["phone"] = param(mensa["phone"])

        if "times" in mensa:
            data["times"] = param(True)
            opening_times = {}
            pattern = re.compile(
                r"([A-Z][a-z])(\s*-\s*([A-Z][a-z]))?\s*(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2}) Uhr")
            m = re.findall(pattern, mensa["times"])
            for result in m:
                fromDay, _, toDay, fromTimeH, fromTimeM, toTimeH, toTimeM = result
                opening_times[fromDay] = "%02d:%02d-%02d:%02d" % (
                    int(fromTimeH), int(fromTimeM), int(toTimeH), int(toTimeM))
                if toDay:
                    select = False
                    for short, long in weekdays_map:
                        if short == fromDay:
                            select = True
                        elif select:
                            opening_times[short] = "%02d:%02d-%02d:%02d" % (
                                int(fromTimeH), int(fromTimeM), int(toTimeH), int(toTimeM))
                        if short == toDay:
                            select = False

                for short, long in weekdays_map:
                    if short in opening_times:
                        data[long] = param(opening_times[short])

        # Generate xml
        xslt_tree = lxml.etree.parse(self.meta_xslt)
        xslt = lxml.etree.XSLT(xslt_tree)
        return lxml.etree.tostring(xslt(lxml.etree.Element("foobar"), **data),
                                   pretty_print=True,
                                   xml_declaration=True,
                                   encoding="utf-8").decode("utf-8")

    def __init__(self, url_template):
        with open(self.canteen_json, 'r', encoding='utf8') as f:
            self.canteens = json.load(f)

        self.url_template = url_template

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.url_template.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)


def getParser(url_template):
    return Parser(url_template)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = getParser("http://localhost/{metaOrFeed}/wuwien_{mensaReference}.xml")
    print(p.feed("K16510_DEU"))
    # print(p.meta("K16510_DEU"))
