import sys
import os
import json
import json5
import logging
import urllib
import re
import requests

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
    script_src_pattern = re.compile('<script src="/([^"]+)"></script>')
    roles = ("student", "employee", "other")

    def _load_prices(self):
        # Load prices
        if self._price_relations is not None:
            return

        html = self._get_cached(
            "https://www.studierendenwerk-kaiserslautern.de/de/essen/speiseplaene").text
        # Open all .js files that are listed in <script> tags to find the one that contains the priceRelations variable
        # At the time of writing the last <script> contains the priceRelations variable, therefore we iterate in reverse order
        for m in reversed(list(self.script_src_pattern.finditer(html))):
            url = f"https://www.studierendenwerk-kaiserslautern.de/{m.group(1)}"
            js = self._get_cached(url).text
            if "priceRelations =" in js:
                try:
                    js_str = js.split("priceRelations =")[1].split("};")[0]
                    self._price_relations = json5.loads(js_str + "}")
                    return
                except (IndexError, ValueError):
                    logging.exception("Failed to parse priceRelations")
                    break
        # In case we can't find or parse the priceRelations variable, we use a default value to prevent reloading the prices every time
        self._price_relations = {}

    def _get_price(self, meal):
        self._load_prices()
        p_key = meal["dpartname"] + ' ' + meal["artgebname"]
        for k, price in self._price_relations.items():
            if k == p_key:
                if 'Mittagsmen' in p_key:
                    return (price['price'], price['price'], price['price'])
                else:
                    return (price['stu'], price['bed'], price['gas'])
        return ("5,55 €", "5,55 €", "5,55 €")

    def feed(self, ref: str) -> str:
        if ref not in self.canteens:
            return f"Unkown canteen with ref='{xml_escape(ref)}'"

        builder = StyledLazyBuilder()

        resp = self._get_cached(
            "https://www.studierendenwerk-kaiserslautern.de/fileadmin/templates/stw-kl/loadcsv/load_db_speiseplan.php?canteens=1&days=30")

        for meal in resp.json():
            if meal["dportname"] != self.canteens[ref]["dportname"]:
                continue

            category = meal["artname1"] or meal["dpartname"]

            name_key = "atextohnezsz%d"
            index = 1
            name = ""
            while name_key % index in meal:
                name += " " + meal[name_key % index].strip()
                index += 1
            name = name.replace(" ,", ",").strip()

            notes = [zs.strip() for zs in meal["zsnamen"].split(",")]
            notes.append(meal.get("frei1", None))
            notes.append(meal.get("frei2", None))
            notes.append(meal.get("frei3", None))

            prices = self._get_price(meal)

            builder.addMeal(meal["proddatum"], category, name, [
                            note for note in notes if note], prices, self.roles)

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
            "source": xml_str_param('https://www.studierendenwerk-kaiserslautern.de/de/essen/speiseplaene'),
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
        self.session = requests.Session()
        self.session.headers = {
            'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}',
            'Accept-Encoding': 'utf-8'
        }
        self._cache = []
        self._price_relations = None

    def _get_cached(self, url):
        for key, content in self._cache:
            if key == url:
                logging.debug(f"Retrieved from cache: {url}")
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
    print(p.feed("tumensa"))
    # print(p.meta("tumensa"))
