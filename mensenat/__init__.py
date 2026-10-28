import sys
import os
import json
import logging
import urllib
import json5


try:
    from util import meta_from_xsl, xml_str_param
    from .canteen import Canteen

except ModuleNotFoundError:
    # Only "util" lives in the project root; canteen.py sits in this package,
    # so importing it without the dot fails whenever this branch is taken -
    # and hides the real cause behind a ModuleNotFoundError for "canteen".
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, include)
    from util import meta_from_xsl, xml_str_param
    from .canteen import Canteen

metaJson = os.path.join(os.path.dirname(__file__), "canteenDict.json")

metaXslt = os.path.join(os.path.dirname(__file__), "../meta.xsl")


class Parser:
    def feed_all(self, canteenReference: str):
        uri = self.canteens[canteenReference]["source"]
        canteen = Canteen(uri)
        return canteen.generateTotalFeedXml()

    def feed_today(self, canteenReference: str):
        uri = self.canteens[canteenReference]["source"]
        canteen = Canteen(uri)
        return canteen.genereateCurrentWeekFeedXml()

    def meta(self, ref):
        """Generate an openmensa XML meta feed using XSLT"""
        if ref not in self.canteens:
            return "Unknown canteen"
        mensa = self.canteens[ref]

        data = {
            "name": xml_str_param(mensa["name"]),
            "address": xml_str_param(f"{mensa['address']}"),
            "city": xml_str_param(mensa["city"]),
            "latitude": xml_str_param(mensa["latitude"]),
            "longitude": xml_str_param(mensa["longitude"]),
            "phone": xml_str_param(mensa["phone"]),
            "times": mensa["times"],
            "feed_today": xml_str_param(self.urlTemplate.format(metaOrFeed='today', mensaReference=urllib.parse.quote(ref))),
            "feed_full": xml_str_param(self.urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
            "source": xml_str_param(mensa["source"]),
        }

        return meta_from_xsl(self.meta_xslt, data)


    def __init__(self, urlTemplate):
        with open(metaJson, "r", encoding="utf8") as f:
            canteenDict = json5.load(f)

        self.urlTemplate = urlTemplate
        self.meta_xslt = os.path.join(os.path.dirname(__file__), "../meta.xsl")

        self.canteens = {}
        for mensaId, mensa in canteenDict.items():
            mensa["id"] = mensaId
            self.canteens[mensa["reference"]] = mensa

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(metaOrFeed="meta", mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    #print(Parser("http://localhost/{metaOrFeed}/mensenat_{mensaReference}.xml").feed_today("WiTUSchroedingerFreihaus"))
    print(Parser("http://localhost/{metaOrFeed}/mensenat_{mensaReference}.xml").meta("WiTUSchroedingerFreihaus"))
