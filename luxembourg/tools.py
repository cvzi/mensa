import os
import re
import time
import datetime
import logging
import threading
import textwrap
from collections.abc import Iterable

import requests
import bs4
from bs4 import BeautifulSoup

try:
    from version import __version__, useragentname, useragentcomment
    from util import xmlEscape, StyledLazyBuilder, nowBerlin
except ModuleNotFoundError:
    import sys
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import xmlEscape, StyledLazyBuilder, nowBerlin

__all__ = ['getMenu', 'askRestopolis']

url = "https://ssl.education.lu/eRestauration/CustomerServices/Menu"
s = requests.Session()

s.headers = {
    'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}',
    'Accept-Language': 'fr-LU,fr,lb-LU,lb,de-LU,de,en',
    'Accept-Encoding': 'utf-8'
}

requests.utils.add_dict_to_cookiejar(s.cookies, {
    ".AspNetCore.Culture":  "c=fr|uic=fr",
    "CustomerServices.Restopolis.DisplayAllergens": "True"
})

allergens = {
    1: "Céréales contenant du gluten et produits à base de ces céréales",
    2: "Crustacés et produits à base de crustacés",
    3: "Oeufs et produits à base d‘oeufs",
    4: "Poissons et produits à base de poissons",
    5: "Arachides et produits à base d‘arachides",
    6: "Soja et produits à base de soja",
    7: "Lait et produits à base de lait (y compris le lactose)",
    8: "Fruits à coque et produits à base de ces fruits",
    9: "Céleri et produits à base de céleri",
    10: "Moutarde et produits à base de moutarde",
    11: "Graines de sésame et produits à base de graines de sésame",
    12: "Anhydride sulfureux et sulfites en concentrations de plus de 10mg/kg ou 10mg/litre",
    13: "Lupin et produits à base de lupin",
    14: "Mollusques et produits à base de mollusques"
}

imgs = {
    "/terroir.png": "produit du Luxembourg",
    "/bio.png": "produit biologique",
    "/transfair.png": "produit Transfair",
    "/vegetarian.png" : "produit végétarien",
    "/vegan.png" : "produit végétalien"
}


def allergen(key):
    try:
        key = int(key)
    except ValueError:
        logging.info("Unkown allergen :" + str(key))
        return key
    return allergens[key] if key in allergens else str(key)


def askRestopolis(restaurant=None, service=None, date=None):
    """
    Fetch raw data from Restopolis
    """

    startTime = time.time()
    cookies = {}
    if restaurant is not None:
        cookies["CustomerServices.Restopolis.SelectedRestaurant"] = str(restaurant)
    if service is not None:
        cookies["CustomerServices.Restopolis.SelectedService"] = str(service)
    if date is not None:
        cookies["CustomerServices.Restopolis.SelectedDate"] = date.strftime("%d.%m.%Y")


    r = s.get(url, cookies=cookies, timeout=10.0)

    r.duration = time.time() - startTime
    return r


def testHeaders():
    """
    Test askRestopolis request headers, cookies, ...
    """
    global url
    tmp = url
    url = "http://httpbin.org/anything"
    r = askRestopolis(restaurant=123, service=456, date=datetime.date(1991,8,6))
    __import__("pprint").pprint(r.json(), width=102)
    url = tmp


def getMenu(restaurantId, datetimeDay=None, serviceIds=None, alternativeId=None, alternativeServiceIds=None):
    """
    Create openmensa feed from restopolis website
    """
    startTime = time.time()
    lazyBuilder = StyledLazyBuilder()
    comments = []

    if not datetimeDay:
        datetimeDay = nowBerlin().date()

    if isinstance(serviceIds, str) or not isinstance(serviceIds, Iterable):
        serviceIds = [(serviceIds, ""), ]
    for i, service in enumerate(serviceIds):
        if isinstance(service, str) or isinstance(service, int):
            serviceIds[i] = (service, "")

    mealCounter = 0
    dayCounter = set()
    weekdayCounter = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    repeat = len(serviceIds) == 1
    repeatCounter = 0
    mealCounterLast = mealCounter
    for service in serviceIds:
        serviceSuffix = f"({service[1]})" if service[1] and len(serviceIds) > 1 else ""
        r = askRestopolis(restaurant=restaurantId,
                          service=service[0], date=datetimeDay)
        if r.status_code != 200:
            status = 'Could not open restopolis'
            if 'status' in r.headers:
                status = f"{status}: {r.headers['status']}"
            logging.error(status)
            from pprint import pprint
            pprint(r.headers)
            return status, 0, 0, weekdayCounter

        if '<' not in r.text:
            comments.append(f"Restaurant [id={restaurantId}, service={service}]: No HTML in response body: `{r.text}`")
            break

        document = BeautifulSoup(r.text, "html.parser")

        # Extract available dates from date selector
        dateSelector = document.find("div", {"class": "date-selector-desktop"})
        if not dateSelector:
            logging.warning(f"No div.date-selector-desktop found")
            comments.append(f"Restaurant [id={restaurantId}, service={service}] not found")
            break

        dateButtons = dateSelector.find_all("button", {"class": "day"})
        dates = []
        for button in dateButtons:
            dates.append(datetime.datetime.strptime(
                button.attrs["data-full-date"], '%d.%m.%Y').date())

        # Extract menu for each date
        for i, oneDayDiv in enumerate(document.select(".daily-menu>div")):
            dayCounter.add(dates[i])
            date = dates[i]
            weekDay = date.weekday()
            courseName = ""
            categoryNotes = []
            notes = []
            productSection = ""
            productName = ""
            productAllergens = []
            productDescription = ""
            isClosed = False

            oneDayDiv.append(document.new_tag("div", attrs={"class":"fake-last"}))
            children = list(oneDayDiv.children)
            for div in children:
                if not isinstance(div, bs4.element.Tag):
                    # Skip text node children
                    continue
                if not isClosed and courseName and productName and "class" in div.attrs and ("fake-last" in div.attrs["class"] or "product-name" in div.attrs["class"] or "course-name" in div.attrs["class"] or "product-section" in div.attrs["class"]):
                    # Add meal
                    mealCounter += 1
                    weekdayCounter[weekDay] += 1
                    category = courseName
                    if productSection:
                        category += " " + productSection
                    if serviceSuffix:
                        category += " " + serviceSuffix
                    if productDescription:
                        notes += textwrap.wrap(productDescription, width=250)
                    if productAllergens:
                        notes += productAllergens
                    if categoryNotes:
                        notes += categoryNotes
                    lazyBuilder.addMeal(
                        date, category, productName[0:249], [note[0:249] for note in notes])
                    productName = ""
                    productAllergens = []
                    productDescription = ""
                    notes = []

                # walk through all div and collect info
                if "class" in div.attrs:
                    if "fake-last" in div.attrs["class"]:
                        pass
                    elif "no-products" in div.attrs["class"] or div.find(".formulaeContainer.no-products"):
                        # Closed (No meals)
                        lazyBuilder.setDayClosed(date)
                        isClosed = True
                    elif "fermé" in div.text.lower() or "fermé" in str(div.attrs).lower():
                        # Closed (explicit)
                        lazyBuilder.setDayClosed(date)
                        isClosed = True
                    elif "course-name" in div.attrs["class"]:
                        courseName = div.text.strip()
                        productSection = ""
                    elif "product-section" in div.attrs["class"]:
                        productSection = div.text.strip()
                    elif "product-allergens" in div.attrs["class"]:
                        productAllergensGen = (
                            a.strip() for a in div.text.split(",") if a.strip())
                        productAllergens += [re.sub("\d+", lambda m: allergen(m[0]), a)
                                             for a in productAllergensGen]
                    elif "product-description" in div.attrs["class"]:
                        productDescription = div.text.strip()
                    elif "product-name" in div.attrs["class"]:
                        productName = div.text.strip()
                        productName = productName.replace("''", '"')
                        productName = productName.replace("1/2 ", '½ ')
                    elif "product-flag" in div.attrs["class"]:
                        unknownImg = True
                        for img in imgs:
                            if div.attrs["src"].endswith(img):
                                notes.append(imgs[img])
                                unknownImg = False
                        if unknownImg:
                            logging.warning(f"Unkown img {div.attrs['src']} [restaurant={restaurantId}]")
                            comments.append(f"Unkown img {div.attrs['src']} [restaurant={restaurantId}]")
                    elif "wrapper-theme-day" in div.attrs["class"]:
                        logging.info(f"Theme day: {div.text.strip()} [restaurant={restaurantId}]")
                        comments.append(f"Theme day: {div.text.strip()} [restaurant={restaurantId}]")
                    elif "wrapper-category" in div.attrs["class"]:
                        for categoryButton in div.find_all('button'):
                            if "showConstantProducts" not in categoryButton.attrs['class'] and "showFormulae" not in categoryButton.attrs['class']:
                                logging.info(f"Unknown category button: {categoryButton.attrs['class']}: {categoryButton.text.strip()}")
                                comments.append(f"Unknown category button: {categoryButton.attrs['class']}: {categoryButton.text.strip()}")
                    elif "cb" in div.attrs["class"]:
                        pass
                    elif "formulaeContainer" in div.attrs["class"] or "constantProductContainer" in div.attrs["class"]:
                        # Append content of category container
                        last = children.pop()
                        children.extend(div.children)
                        children.append(last)

                        if "constantProductContainer" in div.attrs["class"]:
                            categoryNotes = ["produit constant"]
                        else:
                            categoryNotes = []

                    else:
                        logging.debug(div)
                        raise RuntimeWarning(
                            f"unknown tag <{div.name}> with class {div.attrs['class']}: oneDayDiv->else [restaurant={restaurantId}]")
                elif div.name == 'ul':
                    mealCounter += 1
                    weekdayCounter[weekDay] += 1
                    for li in div.select('li'):
                        if not li.text or not li.text.strip():
                            continue
                        # Add meal
                        category = courseName
                        if productSection:
                            category += " " + productSection
                        lazyBuilder.addMeal(
                            date, category, li.text.strip()[0:249])
                        productName = ""
                        productAllergens = []
                        productDescription = ""
                else:
                    logging.debug(div)
                    raise RuntimeWarning(
                        f"unknown tag <{div.name}>: oneDayDiv->else")

        if hasattr(r, 'duration') and r.duration < 2000 and time.time() - startTime < 7000:
            if repeat and repeatCounter < 3 and mealCounter > 0 and mealCounter > mealCounterLast:
                repeatCounter += 1
                mealCounterLast = mealCounter
                serviceIds.append(service)
                datetimeDay += datetime.timedelta(days=7)

    if mealCounter == 0 and alternativeId:
        logging.debug("No meals -> trying alternativeId")
        return getMenu(alternativeId, datetimeDay=datetimeDay, serviceIds=alternativeServiceIds, alternativeId=None, alternativeServiceIds=None)
    
    xml = lazyBuilder.toXMLFeed()
    for commentStr in comments:
        xml += f"\n<!-- {commentStr.replace('--', '- -')} -->\n"

    print(f" {len(dayCounter):3d} 📅 {mealCounter:4d} 🍽️ ", end="")
    return xml, len(dayCounter), mealCounter, weekdayCounter


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(getMenu(137)[0])
