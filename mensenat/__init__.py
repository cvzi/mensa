import sys
import os
import json
import logging
import urllib
import re

try:
    from mensenat.tools import getMenu
    from util import xmlEscape
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from tools import getMenu
    from util import xmlEscape

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

class Parser:
    def feed(self, refName):
        return getMenu(self.canteens[refName]["id"])

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
                "source": mensa["source"],
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
                data[key] = xmlEscape(data[key])
            xml = template.format(**data)
            return xml

        return '<openmensa xmlns="http://openmensa.org/open-mensa-v2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.1" xsi:schemaLocation="http://openmensa.org/open-mensa-v2 http://openmensa.org/open-mensa-v2.xsd"/>'

    def __init__(self, urlTemplate):
        with open(metaJson, 'r', encoding='utf8') as f:
            canteenDict = json.load(f)

        self.urlTemplate = urlTemplate

        self.canteens = {}
        for mensaId, mensa in canteenDict.items():
            mensa["id"] = mensaId
            self.canteens[mensa["reference"]] = mensa

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)


def getParser(urlTemplate):
    return Parser(urlTemplate)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(getParser("http://localhost/{metaOrFeed}/mensenat_{mensaReference}.xml").feed("KlagenfurtUniMCafe"))
    # print(getParser("http://localhost/{metaOrFeed}/mensenat_{mensaReference}.xml").meta("EisenstadtFH"))
