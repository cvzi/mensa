import sys
import os
import json
import logging
import urllib
import re

try:
    from version import __version__
    from util import xml_escape, meta_from_xsl, xml_str_param
    from greifswald.FeedGenerator import generateToday, generateFull
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__
    from util import xml_escape, meta_from_xsl, xml_str_param
    from FeedGenerator import generateToday, generateFull


class Parser:
    canteen_json = os.path.join(os.path.dirname(__file__), "canteenDict.json")
    meta_xslt = os.path.join(os.path.dirname(__file__), "../meta.xsl")

    def feed_today(self, ref: str) -> str:
        if ref not in self.canteens:
            return f"Unkown canteen with ref='{xml_escape(ref)}'"

        return generateToday(ref)

    def feed_all(self, ref: str) -> str:
        if ref not in self.canteens:
            return f"Unkown canteen with ref='{xml_escape(ref)}'"

        return generateFull(ref)

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
            "feed_today": xml_str_param(self.url_template.format(metaOrFeed='today', mensaReference=urllib.parse.quote(ref))),
            "feed_full": xml_str_param(self.url_template.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
            "source": xml_str_param(f"https://www.stw-greifswald.de/essen/speiseplaene/{ref}"),
        }

        if "phone" in mensa:
            mensa["phone"] = xml_str_param(mensa["phone"])

        if "times" in mensa:
            data["times"] = mensa["times"]

        return meta_from_xsl(self.meta_xslt, data)

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
    # print(p.feed_all("mensa-am-berthold-beitz-platz"))
    print(p.meta("mensa-am-berthold-beitz-platz"))
