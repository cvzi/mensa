import os
import json
import datetime
import requests
import logging

import lxml.etree
import defusedxml.lxml

try:
    from version import __version__, useragentname, useragentcomment
    from util import nowBerlin
except ModuleNotFoundError:
    import sys
    include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, include)
    from version import __version__, useragentname, useragentcomment
    from util import nowBerlin

mealsURL = 'http://www.eurest.at/wumensa/app/app_tagesplan.xml'
xslFile = os.path.join(os.path.dirname(__file__), 'wuwien.xsl')
metaTemplateFile = os.path.join(os.path.dirname(__file__), 'metaTemplate.xml')
sourceURL = 'http://wumensa.at/'

headers = {
    'User-Agent': f'{useragentname}/{__version__} ({useragentcomment}) {requests.utils.default_user_agent()}'
}


class Parser:
    def feed_today(self, refName):
        """Generate an openmensa XML feed from the source xml using XSLT"""
        if refName not in self.canteens:
            return 'Unknown canteen'
        source = requests.get(mealsURL, headers=headers, stream=True).raw
        dom = defusedxml.lxml.parse(source)
        xslt_tree = defusedxml.lxml.parse(xslFile)
        xslt = lxml.etree.XSLT(xslt_tree)
        now = nowBerlin()
        year = now.year + 1 if now.month == 12 and now.day == 31 else now.year
        newdom = xslt(dom, year=lxml.etree.XSLT.strparam(str(year)))
        return lxml.etree.tostring(newdom,
                                   pretty_print=True,
                                   xml_declaration=True,
                                   encoding=newdom.docinfo.encoding).decode('utf-8')

    def meta(self, refName):
        """Generate the openmensa XML meta feed"""
        if refName not in self.canteens:
            return 'Unknown canteen'
        with open(metaTemplateFile, 'r', encoding='utf-8') as f:
            template = f.read()
        xml = template.format(source=sourceURL, feed=self.urlTemplate.format(
            metaOrFeed='today', mensaReference=refName))
        return xml

    def __init__(self, urlTemplate):
        self.urlTemplate = urlTemplate

        self.canteens = {'wu0': None}

    def json(self):
        tmp = {}
        for reference in self.canteens:
            tmp[reference] = self.urlTemplate.format(
                metaOrFeed='meta', mensaReference=reference)
        return json.dumps(tmp, indent=2)


def getParser(baseurl):
    return Parser(baseurl)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    p = getParser("http://localhost/{metaOrFeed}/wuwien_{mensaReference}.xml")
    print(p.feed_today("wu0"))
    # print(p.meta("wu0"))
