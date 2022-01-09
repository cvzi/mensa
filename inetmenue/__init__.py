import sys
import os
import json
import logging
import urllib
import re
import requests
import bs4
import pyopenmensa
import lxml

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, xmlEscape, weekdays_map
except ModuleNotFoundError:
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, xmlEscape, weekdays_map


class Parser:
    canteen_json = os.path.join(os.path.dirname(__file__), "canteenDict.json")
    meta_xslt = os.path.join(os.path.dirname(__file__), "meta.xsl")
    price_pattern = re.compile('\d+,\d{2}')
    global_categories = {
        "https://cdn.inetmenue.de/media%2F00512471%2Fcdd3290ac929fba511b3d2f5497f4172560ece12.jpg": "*closed*",
        "*schneemann.gif": "*closed*",
        "https://cdn.inetmenue.de/media%2F00512471%2Fedc0f3199cbf3b7e3b570d7a6f27185bf088bdb0.jpg": "*ignore*",
        "https://cdn.inetmenue.de/media%2F00060380%2Fb0ab12b157398fdd8141d7eb71f4fc920c9925cf.jpg": "*ignore*",
        "https://cdn.inetmenue.de/media%2F00017709%2Fd92b8df29ef5be9a89f438f5f2af24189b85f4bc.png": "*ignore*",
        "https://cdn.inetmenue.de/media%2F00060385%2F9080_0000%2B-%2Blogo%2Bpartyk%25E3%25BCche%2Bkempe%2Bmit%2Bwww.jpg": "*ignore*",
        "https://cdn.inetmenue.de/media%2F00017709%2F683_peg-cat.jpg": "*ignore*",
        "https://cdn.inetmenue.de/media%2F00280005%2F04699e67275bb021b3a883e8f107a081452c0c2578b8bb819f2bf373e1710d20.jpg": "*ignore*",
        "https://cdn.inetmenue.de/media%2F00017709%2Fc6b053e7e3b5eca2162f8a7db28d2ef13d4a650b.jpg": "Nudelbuffet",
        "https://cdn.inetmenue.de/media%2F00209660%2F0d6cb6be82321a6db02c87fc126503ab9317a0e3.jpg": "DGE-Qualitätsstandard",
        "https://cdn.inetmenue.de/media%2F00143229%2F10597_mensa%2Bfps.jpg": "*ignore*",
        "https://cdn.inetmenue.de/media%2F00143229%2Fd7e19a1d1ad799edf4a25fdb9662ee0b06cfcff3.jpg": "Salat",
        "*_dummy%2Bklein.jpg": "*ignore*",
        "*_test-bild-gross.jpg": "*ignore*",
        "*_standardbild.jpg": "*ignore*",
    }

    def feed_today(self, ref: str) -> str:
        return self.feed_all(ref, get_next_week=False)


    def feed_all(self, ref: str, get_next_week=True) -> str:
        if ref not in self.canteens:
            return f"Unkown canteen with ref='{xmlEscape(ref)}'"

        builder = StyledLazyBuilder()

        # This week
        url_parts = urllib.parse.urlsplit(self.canteens[ref]['source'], scheme="https")
        resp = self._get_cached(url_parts.geturl())
        next_week_path = self.parseMeals(ref, builder, resp.text)

        # Next week
        if get_next_week and next_week_path:
            this_week_url = url_parts.geturl()
            url_parts = list(url_parts)
            url_parts[2] = next_week_path
            url = urllib.parse.urlunsplit(url_parts)
            if url != this_week_url:
                resp = self._get_cached(url)
                logging.debug(f"This week url='{this_week_url}'")
                logging.debug(f"Next week url='{url}'")
                self.parseMeals(ref, builder, resp.text)
            else:
                logging.debug(f"No distinct next week url found")
        elif get_next_week:
            logging.debug(f"No next week url found")

        return builder.toXMLFeed()

    def parseMeals(self, ref:str, builder: pyopenmensa.feed.LazyBuilder, html: str) -> str:
        document = bs4.BeautifulSoup(html, "html.parser")
        if document.find(id='week-content'):
            return self.parseMealsFS(ref, builder, document)
        elif document.find(class_='week_table'):
            return self.parseMealsSF(ref, builder, document)
        else:
            if document.find(class_='oops'):
                logging.error(document.find(class_='oops').text)
            raise RuntimeError("Unknown page structure")


    def parseMealsSF(self, ref:str, builder: pyopenmensa.feed.LazyBuilder, document: bs4.BeautifulSoup) -> str:
        # parse http://{name}.inetmenue.de/sf/index.php
        dates = []
        mealtime = ""
        next_week_url = None

        next_week_a = document.select('#day-tabs .next_week a')
        if next_week_a:
            next_week_url = next_week_a[0]["href"]
        for date in document.select('.week_table th .day_date'):
            dates.append(date.text.strip())

        meal_row_index = 0
        for tr in document.select('.week_table tbody')[0].children:
            if not isinstance(tr, bs4.element.Tag) or tr.name != "tr":
                continue

            if "class" in tr.attrs and "menutime" in tr["class"]:
                mealtime = tr.text.strip()
            else:
                meal_row_index += 1
                for day_index, td in enumerate(tr.find_all("td")):
                    menu_box = td.find(class_="menu_box")
                    if not menu_box:
                        continue
                    menuinfo = menu_box.find(class_='menuinfo')
                    if menuinfo:
                        category_name = (mealtime + " " + menuinfo.text.strip()).strip()
                    else:
                        category_name = mealtime
                    if not category_name:
                        category_name = 'Essen %02d' % (meal_row_index,)

                    name = menu_box.find("h4").text.strip()
                    builder.addMeal(dates[day_index], category_name, name.strip())

        return next_week_url


    def parseMealsFS(self, ref:str, builder: pyopenmensa.feed.LazyBuilder, document: bs4.BeautifulSoup) -> str:
        # parse http://{name}.inetmenue.de/fs/menu/week
        predefined_categories = self.canteens[ref].get("categories", {}) | self.global_categories
        
        category_prefix = ''
        category_index = 0
        next_week_url = None

        for child in document.find(id='week-content').children:
            if not isinstance(child, bs4.element.Tag):
                continue

            if child.name == "h2":
                # Table row: Canteen name
                category_prefix = child.text.strip() + ' '

            elif "day-header" in child["class"]:
                # Table row: Dates
                dates = []
                for date in child.select('.day .long small'):
                    dates.append(date.text.strip())

                for a in child.select('a.jmp'):
                    if a.find(class_='fa-caret-right'):
                        next_week_url = a["href"]

            elif "menu-line" in child["class"]:
                # Table row: Meals
                category_index += 1
                menu_line = child
                category_name = ""
                for day_index, day_div in enumerate(menu_line.select('.day')):
                    additives = set()
                    name_suffix = ''
                    if 'no-menu' in day_div['class']:
                        continue
                    order_end = day_div.find(class_='order-end')
                    if order_end:
                        name_suffix = '⚠️' + order_end.text.strip()

                    name = day_div.select('.product h4')[0].text.strip()
                    if "Mensa geschlossen" in name or "Heute keine Mittagsverpflegung" in name:
                        builder.setDayClosed(dates[day_index])
                        continue

                    header = day_div.find("header")
                    if header:
                        if header.text.strip():
                            category_name = header.text.strip()
                        icon = header.find(class_="icon")
                        if icon and icon["title"]:
                            additives.add(icon["title"].strip())
                            if not category_name:
                                category_name = icon["title"].strip()

                    elif day_div.select('.product .image') and day_div.select('.product .image')[0]['style']:
                        category_img = day_div.select('.product .image')[0]['style'].split("url(")[1].split(")")[0]
                        if category_img in predefined_categories:
                            category_name = predefined_categories[category_img]
                        else:
                            for query in predefined_categories:
                                if query.startswith("$") and category_img.endswith(query[1:]):
                                    category_name = predefined_categories[query]
                                if query.startswith("^") and category_img.startswith(query[1:]):
                                    category_name = predefined_categories[query]
                                if query.startswith("*") and query[1:] in category_img:
                                    category_name = predefined_categories[query]
                            if not category_name:
                                logging.debug(f"Unknown category image: {category_img}")

                    if category_name == "*remove*":
                        continue

                    if not category_name.strip() or category_name == "*ignore*":
                        category_name = 'Essen %02d' % (category_index,)
                        logging.info(f"No category found, using default %r" % (category_name,))
                    elif category_name == "*closed*":
                        builder.setDayClosed(dates[day_index])
                        continue



                    allergens = day_div.find(class_='allergens')
                    if day_div.find(class_='allergens'):
                        for a in allergens['title'].split(","):
                            a = a.strip().strip("=")
                            if a:
                                additives.add(a)

                    try:
                        prices = [self.price_pattern.search(day_div.select(".price").text).group(0)]
                        roles = ("pupil",)
                    except:
                        prices = None
                        roles = None

                    category = category_prefix + category_name
                    full_name = name + name_suffix

                    builder.addMeal(dates[day_index], category.strip(), full_name.strip(), notes=additives, prices=prices, roles=roles)

        return next_week_url


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
            "source": param('https:' + mensa["source"]),
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
        if len(self._cache) > 20:
            self._cache.pop(0)
        return content

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
    print(p.feed_today("menseria-oesede"))
    #print(p.feed_all("menseria-oesede"))
    #print(p.meta("menseria-oesede"))
