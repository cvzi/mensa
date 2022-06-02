import sys
import os
import json
import logging
import urllib
import re
import lxml

try:
    from version import __version__
    from util import xmlEscape, weekdays_map
    from greifswald.FeedGenerator import generateToday, generateFull
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import xmlEscape, weekdays_map
    from FeedGenerator import generateToday, generateFull


class Parser:
    canteen_json = os.path.join(os.path.dirname(__file__), "canteenDict.json")
    meta_xslt = os.path.join(os.path.dirname(__file__), "meta.xsl")

    def feed_today(self, ref: str) -> str:
        if ref not in self.canteens:
            return f"Unkown canteen with ref='{xmlEscape(ref)}'"

        return generateToday(ref)

    def feed_all(self, ref: str) -> str:
        if ref not in self.canteens:
            return f"Unkown canteen with ref='{xmlEscape(ref)}'"

        return generateFull(ref)


    def meta(self, ref):
        """Generate an openmensa XML meta feed using XSLT"""
        if ref not in self.canteens:
            return 'Unknown canteen'
        mensa = self.canteens[ref]

        param = lambda s: lxml.etree.XSLT.strparam(str(s))

        data = {
            "name": param(mensa["name"]),
            "address": param(mensa["address"]),
            "city": param(mensa["city"]),
            "latitude": param(mensa["latitude"]),
            "longitude": param(mensa["longitude"]),
            "feed_today": param(self.url_template.format(metaOrFeed='today', mensaReference=urllib.parse.quote(ref))),
            "feed_full": param(self.url_template.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
            "source": param(f"https://www.stw-greifswald.de/essen/speiseplaene/{ref}"),
        }

        if "phone" in mensa:
            mensa["phone"] = param(mensa["phone"])

        if "times" in mensa:
            data["times"] = param(True)
            opening_times = {}
            pattern = re.compile(
                r"([A-Z][a-z])(\s*-\s*([A-Z][a-z]))?\s*(\d{1,2})[:\.](\d{2})\s*[-–]\s*(\d{1,2})[:\.](\d{2}) Uhr")
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
    p = getParser("http://localhost/")
    print(p.feed_today("mensa-am-berthold-beitz-platz"))
    #print(p.feed_all("mensa-am-berthold-beitz-platz"))
    #print(p.meta("mensa-am-berthold-beitz-platz"))
