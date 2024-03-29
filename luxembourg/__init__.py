import os
import json
import logging
import urllib
import re

try:
    from luxembourg.tools import getMenu
    from util import weekdays_map
except ModuleNotFoundError:
    import sys
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from tools import getMenu
    from util import weekdays_map

metaJson = os.path.join(os.path.dirname(__file__), "canteenDict.json")
metaJsonAlternative = os.path.join(
    os.path.dirname(__file__), "canteenDictFrupstut.json")

metaTemplateFile = os.path.join(os.path.dirname(
    __file__), "metaTemplate_luxembourg.xml")

template_sourceURL = r"https://portal.education.lu/restopolis/Language/fr/MENUS/MENU-DU-JOUR/RestaurantId/%d/ServiceId/%d#12691"


class Parser:
    def feed(self, refName):
        if "active" in self.canteens[refName] and not self.canteens[refName]["active"]:
            return "Unknown reference or deactivated canteen"
        if "alternativeId" in self.canteens[refName]:
            alternativeId = self.canteens[refName]["alternativeId"]
            alternativeServiceIds = self.canteens[refName]["alternativeServiceIds"]
        else:
            alternativeId = None
            alternativeServiceIds = None
        xml, _, _, _ = getMenu(restaurantId=self.canteens[refName]["id"], serviceIds=self.canteens[refName]
                               ["services"], alternativeId=alternativeId, alternativeServiceIds=alternativeServiceIds)
        return xml

    def meta(self, refName):
        """Generate an openmensa XML meta feed from the static json file using an XML template"""
        with open(metaTemplateFile) as f:
            template = f.read()

        for reference, restaurant in self.canteens.items():
            if refName != reference:
                continue

            if "source" in restaurant and restaurant["source"]:
                sourceUrl = restaurant["source"]
            else:
                sourceUrl = template_sourceURL % (
                    int(restaurant["id"]), int(restaurant["services"][0][0]))

            address = ""
            if restaurant["street"]:
                address += restaurant["street"]
            if restaurant["zip"]:
                address += (", " if address else "") + restaurant["zip"]
            if restaurant["city"]:
                address += ((" " if restaurant["zip"] else ", ")
                            if address else "") + restaurant["city"]

            data = {
                "name": restaurant["name"] + (f" ({restaurant['region']})" if restaurant["region"] else ""),
                "address": address,
                "city": restaurant["city"],
                "phoneXML": f"<phone>{restaurant['phone']}</phone>" if "phone" in restaurant else "",
                "latitude": restaurant["latitude"],
                "longitude": restaurant["longitude"],
                "feed": self.urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(reference)),
                "source": sourceUrl,
            }
            openingTimes = ""
            pattern = re.compile(r"(\d{1,2}):(\d{2}) - (\d{1,2}):(\d{2})")
            serviceStr = " ## ".join(x[1] for x in restaurant["services"])
            m = re.findall(pattern, serviceStr)
            if len(m) == 2:
                fromTimeH, fromTimeM, toTimeH, toTimeM = [int(x) for x in m[0]]
                fromTime2H, fromTime2M, toTime2H, toTime2M = [
                    int(x) for x in m[1]]
                if (fromTime2H - toTimeH) * 60 + fromTime2M - toTimeM < 32:
                    toTimeH, toTimeM = toTime2H, toTime2M
            else:
                fromTimeH, fromTimeM, toTimeH, toTimeM = [int(x) for x in m[0]]

            openingTimes = "%02d:%02d-%02d:%02d" % (
                fromTimeH, fromTimeM, toTimeH, toTimeM)
            if "days" in restaurant:
                fromDay, toDay = [x.strip()
                                  for x in restaurant["days"].split("-")]
            else:
                fromDay, toDay = ['Mo', 'Su']

            isOpen = False
            for dayShort, dayXML in weekdays_map:
                if fromDay == dayShort:
                    isOpen = True
                if isOpen:
                    data[dayXML] = 'open="%s"' % openingTimes
                else:
                    data[dayXML] = 'closed="true"'
                if toDay == dayShort:
                    isOpen = False

            xml = template.format(**data)
            return xml

        return '<openmensa xmlns="http://openmensa.org/open-mensa-v2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.1" xsi:schemaLocation="http://openmensa.org/open-mensa-v2 http://openmensa.org/open-mensa-v2.xsd"/>'

    def __init__(self, urlTemplate):
        with open(metaJson, 'r', encoding='utf8') as f:
            canteenDict = json.load(f)
        with open(metaJsonAlternative, 'r', encoding='utf8') as f:
            canteenDictAlternative = json.load(f)

        self.urlTemplate = urlTemplate

        self.canteens = {}
        for restaurantId, restaurant in canteenDict.items():
            if "active" in restaurant and restaurant["active"] and "reference" in restaurant:
                restaurant["id"] = restaurantId
                self.canteens[restaurant["reference"]] = restaurant
                if "alternativeId" in canteenDictAlternative:
                    alternativeId = canteenDictAlternative["alternativeId"]
                    if restaurant["reference"] == canteenDictAlternative[alternativeId]["reference"]:
                        restaurant["alternativeId"] = alternativeId
                        restaurant["alternativeServiceIds"] = canteenDictAlternative[alternativeId]["services"]

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(reference))
        return json.dumps(tmp, indent=2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(Parser("http://localhost/").feed("LMLweier"))
    # print(Parser("http://localhost/").meta("CmpsKiBergAltius"))
