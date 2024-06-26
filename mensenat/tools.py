import os
import re
import datetime
import logging
import textwrap
import ssl
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.poolmanager import PoolManager
from requests.packages.urllib3.util import ssl_
from bs4 import BeautifulSoup

try:
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, now_local
except ModuleNotFoundError:
    import sys
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import StyledLazyBuilder, now_local

__all__ = ['getMenu']

url = "https://www.mensen.at/"
s = requests.Session()
s.headers = {
    'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
}
legend = {
    'A': 'Gluten',
    'B': 'Krebstiere',
    'C': 'Eier',
    'D': 'Fisch',
    'E': 'Erdnüsse',
    'F': 'Sojabohnen',
    'G': 'Milch',
    'H': 'Schalenfrüchte',
    'L': 'Sellerie',
    'M': 'Senf',
    'N': 'Sesam',
    'O': 'Schwefeldioxid/Sulfite',
    'P': 'Lupinen',
    'R': 'Weichtiere/Schnecken/Muscheln/Tintenfische'
}

imageLegend = {
    'logo_vegetarisch.png': 'vegetarisch',
    'logo_vegan.png': 'vegan',
    'bio-logo-klein.png': 'Bio',
    'logo_msc.png': 'MSC',
    'logo_asc.png': 'ASC',
    'logo_umweltzeichen.png': 'Österr. Umweltzeichen',
    'logo_st.jpg': 'Styria vitalis',
    'bio_garantie_logo_mit_code_icon_50x50.png': 'Bio',
    'klimateller_icon_klein_typo.png': 'Klimateller',
}

roles = ('student', )


class OldInsecureWebsiteAdapter(HTTPAdapter):
    """
    Taken from https://stackoverflow.com/a/51713352/
    """

    def __init__(self, **kwargs):
        super(OldInsecureWebsiteAdapter, self).__init__(**kwargs)

    def init_poolmanager(self, *pool_args, **pool_kwargs):
        """
        Add a supported protocal and cipher
        """
        context = ssl_.create_urllib3_context(
            ssl.PROTOCOL_TLSv1_2, ciphers="AES256-SHA")

        """
        Exclude all other protocols
        """
        context.options |= ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_3
        context.options |= ssl.OP_NO_SSLv3 | ssl.OP_NO_SSLv2

        self.poolmanager = PoolManager(
            *pool_args, ssl_context=context, **pool_kwargs)


def askMensenAt(mensaId=None):
    """
    Fetch raw data from mensen.at
    """
    cookies = {}
    if mensaId is not None:
        cookies['mensenExtLocation'] = str(mensaId)
    try:
        return s.get(url, cookies=cookies)
    except requests.exceptions.SSLError as e:
        logging.debug(e)
        logging.warning("Connect with OldInsecureWebsiteAdapter")
        s.mount(url, OldInsecureWebsiteAdapter())
        return s.get(url, cookies=cookies, verify=Path(__file__).with_name('mensen-at-chain.pem'))


def getMenu(mensaId):
    """
    Create openmensa feed from mensen.at website
    """
    lazyBuilder = StyledLazyBuilder()

    today = now_local().date()
    year = today.year
    month = today.month

    r = askMensenAt(mensaId=mensaId)
    if r.status_code != 200:
        status = 'Could not open mensen.at'
        if 'status' in r.headers:
            status = f"{status}: {r.headers['status']}"
        logging.error(status)
        from pprint import pprint
        pprint(r.headers)
        return status

    document = BeautifulSoup(r.text, "html.parser")

    def extractLine(line, data):
        def price(m):
            data['price'] = m[1].replace(',', '.')
            if len(data['price'].split('.')[1]) == 1:
                data['price'] += "0"
            return ""

        def addi(m):
            data['additives'] += [x.strip()
                                  for x in m.group(0)[1:-1].split(',') if x.strip()]
            return ""

        line = re.sub(r"€\s+(\d+[,\.]\d+)", price, line)
        line = re.sub(r"\(([A-Z],?\s*)+\)", addi, line)
        line = re.sub(r"\s+", " ", line).strip().replace(' ,', ',')
        data['text'].append(line)

    dates = {}
    for navItem in document.select('.weekdays .nav-item[data-index]'):
        index = int(navItem.attrs['data-index'])
        date = navItem.find('span', class_="date").text.split('.')
        dates[index] = datetime.date(
            year + 1 if int(date[1]) < month else year, int(date[1]), int(date[0]))

    mealDict = {}

    for menuItem in document.select(".menu-item[class*='menu-item-']"):
        index = int([className.split('menu-item-')[1]
                     for className in menuItem.attrs['class'] if 'menu-item-' in className][0])
        category = menuItem.h2.text

        if index not in mealDict:
            mealDict[index] = {}

        lines = []
        imgs = []

        for p in menuItem.find_all('p'):
            lines.append(p.text)
            imageList = []
            imgs.append(imageList)

            for img in p.find_all('img'):
                if 'alt' in img.attrs:
                    imageList.append(img.attrs['alt'])
                else:
                    foundSrc = False
                    for src, alt in imageLegend.items():
                        if src in img.attrs['src']:
                            imageList.append(alt)
                            foundSrc = True
                            break
                    if not foundSrc:
                        logging.warning("Unkown image found: %r", img)

        lines = [p.text.strip() for p in menuItem.find_all('p')]
        lines.append('#end')
        imgs.append([])

        data = {'additives': [], 'text': []}
        for i, line in enumerate(lines):
            data['additives'] += imgs[i]

            addMeal = False
            if line == '#end':
                addMeal = True
            elif all(c == '*' for c in line):  # *********
                addMeal = True
            else:
                extractLine(line, data)
            if 'price' in data:
                addMeal = True

            if line.startswith('*') and addMeal:
                addMeal = False

            if addMeal and data['text']:
                data['additives'] = [
                    legend[add] if add in legend else add for add in data['additives'] if add]
                notes = list(dict.fromkeys([note[0:249]
                             for note in data['additives']]))
                for j, productName in enumerate(textwrap.wrap(" ".join(data['text']).strip(), width=250)):
                    if category not in mealDict[index]:
                        mealDict[index][category] = []
                    if productName not in mealDict[index][category]:
                        mealDict[index][category].append(productName)
                        lazyBuilder.addMeal(dates[index],
                                            category,
                                            productName,
                                            notes if j == 0 else None,
                                            (data['price'],
                                             ) if 'price' in data and j == 0 else None,
                                            roles if 'price' in data and j == 0 else None)
                data = {'additives': [], 'text': []}

    return lazyBuilder.toXMLFeed()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(getMenu(46))
