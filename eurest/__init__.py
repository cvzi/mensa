import sys
import os
import json
import requests
import logging
import urllib
import lxml.etree
import defusedxml.lxml

try:
    from version import __version__, useragentname, useragentcomment
    from util import now_local, xml_escape, meta_from_xsl, xml_str_param
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import now_local, xml_escape, meta_from_xsl, xml_str_param


class Parser:
    canteen_json = os.path.join(os.path.dirname(__file__), "canteens.json")
    meta_xslt = os.path.join(os.path.dirname(__file__), "../meta.xsl")
    feed_xslt = os.path.join(os.path.dirname(__file__), "feed.xsl")
    headers = {
        'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
    }
    meals_current_week = 'https://menuplan.eurest.at/CurrentWeek/{ref}.xml'
    meals_next_week = 'https://menuplan.eurest.at/NextWeek/{ref}.xml'
    source_url = 'https://menuplan.eurest.at/menu.html?current_url=%2FCurrentWeek%2F{ref}.xml'

    def feed(self, ref: str) -> str:
        """Generate an openmensa XML feed from the source xml using XSLT"""
        if ref not in self.canteens:
            return f"Unknown canteen with ref='{xml_escape(ref)}'"
        id = self.canteens[ref]["id"]

        if now_local().weekday() > 4:
            meals_url = self.meals_current_week.format(
                ref=urllib.parse.quote(id))
        else:
            meals_url = self.meals_next_week.format(
                ref=urllib.parse.quote(id))

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
            return f"Unknown canteen with ref='{xml_escape(ref)}'"
        mensa = self.canteens[ref]

        data = {
            "name": xml_str_param(mensa["name"]),
            "address": xml_str_param(mensa["address"]),
            "city": xml_str_param(mensa["city"]),
            "latitude": xml_str_param(mensa["latitude"]),
            "longitude": xml_str_param(mensa["longitude"]),
            "feed": xml_str_param(self.url_template.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
            "source": xml_str_param(self.source_url.format(ref=urllib.parse.quote(mensa["id"]))),
        }

        if "phone" in mensa:
            data["phone"] = mensa["phone"]

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = Parser("http://localhost/{metaOrFeed}/eurest_{mensaReference}.xml")
    print(p.feed("wuwien"))
    #print(p.meta("wuwien"))
