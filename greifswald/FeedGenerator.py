from pyopenmensa.feed import LazyBuilder
from urllib.request import urlopen
from bs4 import BeautifulSoup
from datetime import date, timedelta

mensa = LazyBuilder()

def getMealsForDay(day: str):

    if date.fromisoformat(day).weekday() > 4:  # Saturday or Sunday
        mensa.setDayClosed(date.fromisoformat(day))
        return True

    html = urlopen("https://www.stw-greifswald.de/essen/speiseplaene/mensa-stralsund/?datum=" + day).read()
    soup = BeautifulSoup(html, 'html.parser')

    if mensa.legendData == None:
        for div in soup.find_all('div', {'class': 'csc-textpic-text'}):
            if 'KENNZEICHNUNGSPFLICHTIGE ZUSATZSTOFFE' in div.text:
                text = str(div.text).replace('KENNZEICHNUNGSPFLICHTIGE ALLERGENE:', '') \
                    .replace('KENNZEICHNUNGSPFLICHTIGE ZUSATZSTOFFE:', '') \
                    .replace('SONSTIGE KENNZEICHNUNGEN:', '')
                mensa.setLegendData(text=text, regex='(?P<name>(\d|[a-zA-Z])+)\)\s*(?P<value>([\w/]+)((\s+\w+)*[^0-9)]))')

    for table in soup.find_all('table', {'class': 'table module-food-table'}):
        category = table.find('th').text
        for tr in table.find('tbody').find_all('tr'):
            td = tr.find('td').text.strip().split('\n')
            meal = ''
            price = ''
            for string in td:
                if '€' in string:
                    price = string.strip().split('\xa0€')[:3]
                elif len(string) > 1:
                    meal += (string.strip() + ' ')
            mensa.addMeal(day, category, meal, prices=price,
                          roles=['student', 'employee', 'other'])
    return mensa.hasMealsFor(date.fromisoformat(day))

def generateFull():
    day = date.today()
    while getMealsForDay(day.isoformat()):
        day = day + timedelta(days=1)

    with open('full.xml', 'w') as fd:
        fd.write(mensa.toXMLFeed())

if __name__=="__main__":
    generateFull()