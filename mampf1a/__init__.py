import sys
import os
import json
import logging
import urllib
import re
import textwrap

import requests
import bs4
from bs4 import BeautifulSoup

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, nowBerlin, xmlEscape, weekdays_map
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, nowBerlin, xmlEscape, weekdays_map

metaJson = os.path.join(os.path.dirname(__file__), "canteenDict.json")

metaTemplateFile = os.path.join(os.path.dirname(__file__), "metaTemplate.xml")


datePattern = re.compile(r"\d{1,2}\.\d{1,2}\.\d{0,4}")
legendPattern = re.compile(r"([-+\w]+)\s+-\s+(.+)")
pricePattern = re.compile("(\d+(,\d\d)?)\s+(€|eur)", re.IGNORECASE)

baseUrl = 'https://login.mampf1a.de/{reference}/winEsel5/speiseplan.php?no_cache=1{urlParams}'
baseUrlMeta = 'https://login.mampf1a.de/{reference}/winEsel5/speiseplan.php?{urlParams}'

spans = []
class Parser:

    @staticmethod
    def build_url(refName, base=baseUrl):
        refParts = refName.rsplit('~', 1)
        if len(refParts) == 2:
            refName = refParts[0]

        refParts = refName.split('.', 1)
        if len(refParts) == 2:
            reference, urlParams = refParts[0], '&typ=' + refParts[1].strip('?& ')
        else:
            reference, urlParams = refParts[0], ''

        url = base.format(reference=reference, urlParams=urlParams)
        return url

    def feed(self, refName):
        if refName not in self.canteens:
            return f"Canteen refName='{refName}' not found in canteenDict.json"
        url = self.build_url(refName)

        lazyBuilder = StyledLazyBuilder()

        r = self._get_cached(url)
        document = BeautifulSoup(r.text, "html.parser")

        # Generate legend (unique for each canteen)
        legend = {}
        for div in document.find_all('div', {"style" : "padding-bottom: 8px;"}):
            m = legendPattern.match(div.text)
            if not m:
                print("Could not parse legend line: %r" % (div.text,))
            else:
                legend[m[1]] = m[2]

        if document.select('table.std thead'):
            self.parseHorizontalDates(document, lazyBuilder, legend)
        else:
            self.parseVerticalDates(document, lazyBuilder, legend)


        return lazyBuilder.toXMLFeed()

    @staticmethod
    def parseHorizontalDates(document, lazyBuilder, legend):
        lazyBuilder.setLegendData(legend) # Useless, because the legends are usually incomplete
        tables = document.select('table.std thead')
        if not tables:
            logging.warning("No tables found")
            return

        for thead in tables:
            dates = []
            now = nowBerlin()
            dateTexts = [td.text.strip() for td in thead.tr.select('td')]
            for s in dateTexts:
                m = datePattern.search(s)
                if not m:
                    continue
                date = m[0]
                spt = date.split('.')
                if spt[-1] == '':
                    if int(spt[-2]) < now.month:
                        date += str(now.year + 1)
                    else:
                        date += str(now.year)
                dates.append(date)

            firstRow = True
            for tr in thead.children:
                if not isinstance(tr, bs4.element.Tag):
                    continue
                if firstRow:
                    # First row are the dates
                    firstRow = False
                    continue

                category = tr.td.text.strip()

                dateIndex = 0
                for td in tr.select('td.zelle_inhalt'):
                    date = dates[dateIndex]
                    dateIndex += 1

                    notes = []
                    if not td.a:
                        continue
                    if "gruen" in td.a["class"]:
                        notes.append("fleischlos")

                    additives = [x.attrs["alt"].strip() for x in td.select('a')[0].select('.additive img[alt]') if x.attrs["alt"].strip()]
                    for span in td.select('div[style*="font-size:10px"] span'):
                        additive = span.text.strip()
                        if additive not in additives:
                            additives.append(additive)
                        span.clear()

                    notes += [legend[additive] if additive in legend else additive for additive in additives]

                    mealName = " ".join(x.strip(" ,").strip() for x in td.select('a')[0].strings)

                    price = 0
                    for m in pricePattern.findall(mealName):
                        price += float(m[0].replace(',', '.'))

                    prices = []
                    roles = []

                    if price > 0:
                        prices.append(price)
                        roles.append('student')

                    if not mealName:
                        continue


                    for j, productName in enumerate(textwrap.wrap(mealName, width=250)):
                        lazyBuilder.addMeal(date,
                                            category,
                                            productName,
                                            notes if j == 0 else None,
                                            prices if j == 0 else None,
                                            roles if j == 0 else None)


    @staticmethod
    def parseVerticalDates(document, lazyBuilder, legend):
        trs = document.select('table.std>tr')
        if not trs:
            logging.warning("No tr found")
            return

        categories = [td.text.strip() for td in trs[0].find_all('td', class_="zelleF")][1:]
        if not categories:
            categories = [f"Menü {i + 1}" for i in range(100)]

        for tr in trs[1:]:
            date = datePattern.search(tr.td.text)[0]
            catIndex = 0

            firstChild = True
            for child in tr:
                if firstChild:
                    # Skip first child, it's the date
                    firstChild = False
                    continue
                tds = child.select('table td')
                zelle_inhalt = tr.td.next_sibling

                if 0 <= catIndex < len(categories) and categories[catIndex]:
                    category = categories[catIndex]
                else:
                    category = f"Menü {catIndex + 1}"
                catIndex += 1

                for td in tds:
                    notes = []
                    if "gruen" in td.a["class"]:
                        notes.append("fleischlos")
                    mealName = " ".join(x.strip() for x in td.select('.speiseplan__titel')[0].strings)
                    additives = [x.text.strip() for x in td.select('.speiseplan__zusatzstoffe span') if x.text.strip()]
                    notes += [legend[additive] if additive in legend else additive for additive in additives]

                    # TODO price
                    mealPrice = td.select('.speiseplan__preis')
                    if mealPrice and mealPrice[0] and mealPrice[0].text.strip():
                        print(mealPrice[0])

                    prices = []
                    roles = []

                    for j, productName in enumerate(textwrap.wrap(mealName, width=250)):
                        lazyBuilder.addMeal(date,
                                            category,
                                            productName,
                                            notes if j == 0 else None,
                                            prices if j == 0 else None,
                                            roles if j == 0 else None)



    def meta(self, refName):
        """Generate an openmensa XML meta feed from the static json file using an XML template"""
        with open(metaTemplateFile) as f:
            template = f.read()

        for ref, mensa in self.canteens.items():
            if refName != ref:
                continue

            data = {
                "name": mensa["name"],
                "address": mensa["address"],
                "city": mensa["city"],
                "latitude": mensa["latitude"],
                "longitude": mensa["longitude"],
                "feed": xmlEscape(self.urlTemplate.format(metaOrFeed='feed', mensaReference=urllib.parse.quote(ref))),
                "source": xmlEscape(self.build_url(refName, baseUrlMeta)),
            }
            if "phone" in mensa:
                data["phone"] = f"<phone>{mensa['phone']}</phone>"
            else:
                data["phone"] = ""

            if "times" in mensa:
                openingTimes = {}
                pattern = re.compile(r"([A-Z][a-z])(\s*-\s*([A-Z][a-z]))?\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2}) Uhr")
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
                data['times'] = f"""
    <times type="opening">
      <monday {data['monday']} />
      <tuesday {data['tuesday']} />
      <wednesday {data['wednesday']} />
      <thursday {data['thursday']} />
      <friday {data['friday']} />
      <saturday {data['saturday']} />
      <sunday {data['sunday']} />
    </times>"""
            else:
                data['times'] = ''

            for key in data:
                data[key] = data[key]
            xml = template.format(**data)
            return xml

        return '<openmensa xmlns="http://openmensa.org/open-mensa-v2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.1" xsi:schemaLocation="http://openmensa.org/open-mensa-v2 http://openmensa.org/open-mensa-v2.xsd"/>'

    def __init__(self, urlTemplate):
        with open(metaJson, 'r', encoding='utf8') as f:
            self.canteens = json.load(f)

        self.urlTemplate = urlTemplate
        self.session = requests.Session()
        self.session.headers = {
            'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}',
            'Accept-Encoding': 'utf-8'
        }
        self._cache = []

    def _get_cached(self, url):
        for key, content in self._cache:
            if key == url:
                logging.debug(f"Retrieved from cache: {url}")
                return content
        content = self.session.get(url)
        self._cache.append((url, content))
        if len(self._cache) > 30:
            self._cache.pop(0)
        return content

    def json(self):
        tmp = {}
        for refName in self.canteens:
            tmp[refName] = self.urlTemplate.format(
                metaOrFeed='meta', mensaReference=urllib.parse.quote(refName))
        return json.dumps(tmp, indent=2)


def getParser(baseurl):
    return Parser(baseurl)



if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = getParser("http://localhost/{metaOrFeed}/mampf1a_{mensaReference}.xml")
    k = "Kreuzschwestern.Theodor-Florentini-Schule"
    print("feed:")
    print(p.feed(k))
    print("meta:")
    print(p.meta(k))
